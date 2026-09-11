"""The live-forecast refresher, shared by the API and the standalone scheduler.

WHY THIS MODULE KNOWS ABOUT THE FILESYSTEM, unlike the rest of the package:
`scripts/07_live.py` and `api/services/engine.py` were two copies of the same
physics, and they drifted -- the API ended up serving a simple-WBGT
approximation while the file pipeline served Liljegren, so the two tabs in the
UI disagreed. One shared implementation is what stops that recurring, and the
price is that this one module knows where `web/data/live/` is. Every path is a
defaulted parameter so the knowledge stays overridable.

The refresh rule, in one sentence: callers take a lock; whoever gets it computes
and writes, and whoever does not reads what the winner wrote. Running the API
alone, the scheduler alone, or both is therefore correct, and running both costs
one compute per interval rather than two.
"""
import json
import os
import socket
import sys
import time
import uuid
from contextlib import contextmanager, nullcontext
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from heatstress import advisory as ad
from heatstress import insight as ins
from heatstress import scenario_grid as sg
from heatstress import whatif as wi
from heatstress import physiology as ph
from heatstress import psychro as ps
from heatstress import risk as rk
from heatstress import solar as so
from heatstress import spatial as sp
from heatstress import thermal as th
from heatstress import vulnerability as vu
from heatstress.sources import openmeteo as om

PERSONA_ORDER = ["construction", "delivery", "child", "elderly"]

DEFAULT_CONFIG = "config/ahmedabad.yaml"
LIVE_DIR = ROOT / "web" / "data" / "live"

# Open-Meteo refreshes its blended forecast roughly hourly, so a TTL under that
# never leaves us sitting on data the upstream has already superseded. At a
# 5-minute cadence this is ~96 calls/day against a ~10,000/day free tier.
LIVE_MAX_AGE_MINUTES = 15
LIVE_REFRESH_SECONDS = 300
LOCK_PORT = 8765

# dict key -> filename. The two non-obvious ones (map->hexes, summary->city) are
# why this mapping is asserted in tests rather than inlined at each call site.
PAYLOAD_FILES = {
    "map": "hexes.geojson",
    "hourly": "hourly.json",
    "summary": "city.json",
    "personas": "personas.json",
    "advisory": "advisory.json",
    "insights": "insights.json",
    "meta": "meta.json",          # written LAST -- see write_payload
}

_RETRY_DELAYS = (0.02, 0.05, 0.10, 0.20, 0.40)


class RefreshBusy(RuntimeError):
    """Another process holds the refresh lock."""


@dataclass
class RefreshResult:
    payload: dict
    status: str                    # "computed" | "read_from_disk"
    duration_s: float
    written: dict | None = None    # filename -> did the bytes change


# ----------------------------------------------------------------- settings
@dataclass(frozen=True)
class RefreshSettings:
    interval_seconds: int
    max_age_minutes: int


def load_settings(config_path=DEFAULT_CONFIG, *, interval=None, max_age=None):
    """Precedence: CLI flag > config `live:` block > module constant."""
    path = Path(config_path)
    if not path.is_absolute():
        path = ROOT / path
    live = {}
    if path.exists():
        live = (yaml.safe_load(path.read_text(encoding="utf-8")) or {}).get("live") or {}
    return RefreshSettings(
        interval_seconds=int(interval or live.get("refresh_seconds", LIVE_REFRESH_SECONDS)),
        max_age_minutes=int(max_age if max_age is not None
                            else live.get("max_age_minutes", LIVE_MAX_AGE_MINUTES)),
    )


# -------------------------------------------------------------------- io
def atomic_write_json(path: Path, payload, *, skip_if_unchanged: bool = True) -> bool:
    """Serialise, then swap. Returns True if the bytes on disk changed.

    Serialising BEFORE touching the filesystem is the load-bearing part: if
    json.dumps raises on a stray numpy scalar, no temp file was created and the
    good file is untouched, so a compute bug can never leave a torn output dir.

    The PermissionError retry is for Windows. os.replace must delete the
    destination, and CPython's open() does not pass FILE_SHARE_DELETE, so a
    reader -- or Defender's scanner -- holding the file makes the swap fail
    where POSIX would simply succeed. Only PermissionError is retried; ENOSPC
    and cross-device errors should fail loudly.
    """
    blob = json.dumps(payload, separators=(",", ":"),
                      ensure_ascii=False).encode("utf-8")

    path.parent.mkdir(parents=True, exist_ok=True)
    if skip_if_unchanged and path.exists():
        try:
            if path.read_bytes() == blob:
                return False
        except OSError:
            pass

    tmp = path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex[:8]}.tmp")
    try:
        with open(tmp, "wb") as fh:
            fh.write(blob)
            fh.flush()
            os.fsync(fh.fileno())
        for delay in _RETRY_DELAYS:
            try:
                os.replace(tmp, path)
                return True
            except PermissionError:
                time.sleep(delay)
        os.replace(tmp, path)          # final attempt; let it raise
        return True
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass


def write_payload(payload: dict, out_dir=None) -> dict:
    """Write all seven files, `meta.json` last.

    Seven replaces are not one transaction, so a reader can straddle a swap.
    Committing meta last means the worst tear is "new map, old meta", which
    renders fine -- meta is what the UI reads to pick focus and colour domains.
    """
    out = Path(out_dir) if out_dir is not None else LIVE_DIR
    keys = [k for k in PAYLOAD_FILES if k != "meta"] + ["meta"]
    return {PAYLOAD_FILES[k]: atomic_write_json(out / PAYLOAD_FILES[k], payload[k])
            for k in keys}


def read_json_retry(path: Path, *, attempts: int = 4, delay: float = 0.05):
    """Read JSON that a refresher may be replacing underneath us."""
    last = None
    for i in range(attempts):
        try:
            return json.loads(Path(path).read_text(encoding="utf-8"))
        except (PermissionError, json.JSONDecodeError, FileNotFoundError) as exc:
            last = exc
            time.sleep(delay * (i + 1))
    raise last


def read_payload(out_dir=None) -> dict:
    out = Path(out_dir) if out_dir is not None else LIVE_DIR
    return {k: read_json_retry(out / name) for k, name in PAYLOAD_FILES.items()}


# ------------------------------------------------------------------ lock
@contextmanager
def single_instance(port: int = LOCK_PORT, *, wait: float = 0.0):
    """Exclusive, self-healing, cross-platform lock for the duration of a block.

    A listening socket is reclaimed by the OS however the process dies, so there
    is no stale-lock case to detect -- which is the entire reason this is not a
    PID file. (The usual liveness probe, os.kill(pid, 0), *terminates* the target
    on Windows, so a PID file here would risk killing the user's uvicorn.)

    Never set SO_REUSEADDR: on Windows it permits a second bind to the same
    address, which is precisely what this is preventing.
    """
    deadline = time.monotonic() + wait
    while True:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.bind(("127.0.0.1", port))
            sock.listen(1)
        except OSError:
            sock.close()
            if time.monotonic() >= deadline:
                raise RefreshBusy(
                    f"127.0.0.1:{port} is held -- another refresher is running "
                    f"(or something else owns that port; use --lock-port)")
            time.sleep(0.5)
            continue
        try:
            yield
        finally:
            sock.close()
        return


def focus_index(payload: dict) -> int:
    """Index of the focus hour within the city series.

    `meta` records the focus as a date plus an IST hour rather than an index,
    so callers that want the city-mean at that hour have to look it up.
    """
    focus = payload["meta"]["focus"]
    prefix = f"{focus['date']} {focus['hour_ist']:02d}:"
    stamps = payload["summary"]["timestamps_ist"]
    for i, stamp in enumerate(stamps):
        if stamp.startswith(prefix):
            return i
    return 0


def _fresh_enough(out_dir: Path, seconds: float) -> bool:
    """Did someone already write a payload within the last `seconds`?"""
    meta = Path(out_dir) / PAYLOAD_FILES["meta"]
    if not meta.exists():
        return False
    return (time.time() - meta.stat().st_mtime) < seconds


# --------------------------------------------------------------- refresh
def refresh_once(config_path=DEFAULT_CONFIG, *, out_dir=None, write=True,
                 max_age_minutes=None, lock=True, lock_wait=120.0,
                 lock_port=LOCK_PORT, freshness_floor=60.0,
                 now=None) -> RefreshResult:
    """Compute and publish one refresh, or read the one someone else just made.

    Belt and braces: the lock stops two processes computing at the same moment,
    and the freshness floor stops the loser recomputing what just landed a
    second ago. Together they bound the machine to one compute per
    `freshness_floor` seconds regardless of how many refreshers are running.
    """
    out = Path(out_dir) if out_dir is not None else LIVE_DIR
    t0 = time.perf_counter()
    try:
        cm = single_instance(lock_port, wait=lock_wait) if lock else nullcontext()
        with cm:
            if write and _fresh_enough(out, freshness_floor):
                return RefreshResult(read_payload(out), "read_from_disk",
                                     time.perf_counter() - t0)
            payload = compute_live(config_path, max_age_minutes=max_age_minutes,
                                   now=now)
            written = write_payload(payload, out) if write else None
            return RefreshResult(payload, "computed",
                                 time.perf_counter() - t0, written)
    except RefreshBusy:
        return RefreshResult(read_payload(out), "read_from_disk",
                             time.perf_counter() - t0)


def r1(v):
    return [round(float(x), 1) for x in v]

def night_recovery(stamps, air_temp):
    from collections import defaultdict
    buckets = defaultdict(list)
    for stamp, value in zip(stamps, air_temp):
        hour = int(stamp[11:13])
        if hour >= 22 or hour <= 6:
            buckets[stamp[:10]].append(float(value))
    return [{"date": d, "min_c": round(min(v), 1), "max_c": round(max(v), 1)}
            for d, v in sorted(buckets.items()) if len(v) >= 6]


def compute_live(config_path=DEFAULT_CONFIG, *, max_age_minutes=None,
                 now=None) -> dict:
    """Fetch the forecast, run the physics, return the seven payloads.

    Pure computation -- writes nothing. ``now`` is a test seam: the focus hour
    is "the peak stress hour *ahead*", so it moves with the wall clock, and
    that is exactly what a test needs to pin down.
    """
    config_file = Path(config_path)
    if not config_file.is_absolute():
        config_file = ROOT / config_file
    config = yaml.safe_load(config_file.read_text(encoding="utf-8"))
    city, uhi = config["city"], config["urban_heat"]
    slug = city["name"].lower().replace(" ", "_")
    tz = city["timezone_offset_hours"]
    lat, lon = city["centre"]["lat"], city["centre"]["lon"]

    form_path, form_level = sp.resolve_urban_form(
        ROOT, slug, uhi.get("mode", "lst"))
    form = json.loads(Path(form_path).read_text("utf-8"))

    # The amplitude the pattern ACTUALLY spans, taken from the form file rather
    # than from the config. On the satellite path the offsets are alpha x a
    # measured anomaly, which spans 2.68 degC -- not the 3.0 degC the old
    # assumed method used. Passing the config value here would overstate the
    # greening benefit by about a tenth, and would print a number the map does
    # not agree with. Script 12 writes this key for exactly this reason.
    amplitude_c = float(form.get("uhi_amplitude_c",
                                 uhi["uhi_amplitude_c"]))
    cells = sorted(form["cells"])
    d_ta = np.array([form["cells"][c]["d_ta_c"] for c in cells])
    intensity = np.array([form["cells"][c]["intensity"] for c in cells])

    names_path = ROOT / "data" / "processed" / f"place_names_{slug}.json"
    place_names = json.loads(names_path.read_text("utf-8"))["cells"] if names_path.exists() else {}

    max_age = LIVE_MAX_AGE_MINUTES if max_age_minutes is None else max_age_minutes
    weather = om.fetch_forecast(lat, lon, max_age_minutes=max_age)
    age = om.forecast_age_minutes(lat, lon)

    # ---- identical physics to the hindcast path --------------------------
    ta_city = weather["temperature_2m"].to_numpy()[:, None]
    rh_city = weather["relative_humidity_2m"].to_numpy()[:, None]
    wind = weather["wind_speed_10m"].to_numpy()[:, None]
    ghi = weather["shortwave_radiation"].to_numpy()[:, None]
    direct = weather["direct_radiation"].to_numpy()[:, None]
    diffuse = weather["diffuse_radiation"].to_numpy()[:, None]
    press = weather["surface_pressure"].to_numpy()[:, None]

    ta = ta_city + d_ta[None, :]
    e_city = ps.vapour_pressure(ta_city, rh_city)
    rh = np.clip(100.0 * e_city / ps.saturation_vapour_pressure(ta), 1.0, 100.0)

    shape = ta.shape
    wind_b = np.broadcast_to(wind, shape)
    ghi_b = np.broadcast_to(ghi, shape)
    press_b = np.broadcast_to(press, shape)
    mu = np.broadcast_to(
        so.cos_solar_zenith_angle(lat, lon, weather["day_of_year"].to_numpy(),
                                  weather["hour_utc"].to_numpy())[:, None], shape)
    fdir = np.broadcast_to(so.direct_fraction_from_components(direct, diffuse), shape)

    wbgt = th.tf_wbgt_liljegren(ta, rh, wind_b, ghi_b, fdir, mu, press_b)
    tg = th.globe_temperature_regression(ta, rh, ghi_b)
    utci = th.tf_utci(ta, rh, wind_b, th.tf_mrt_from_globe(ta, tg, wind_b))
    heat_index = th.heat_index(ta, rh)

    hazard = rk.normalise_hazard(wbgt)
    surface = vu.PlaceholderVulnerability().build(cells, intensity=intensity)
    risk = vu.combine_risk(hazard,
                           np.broadcast_to(surface.exposure[None, :], shape),
                           np.broadcast_to(surface.vulnerability[None, :], shape))

    stamps = (weather.index + pd.Timedelta(hours=tz)).strftime("%Y-%m-%d %H:%M")
    stamps = list(stamps)

    # ---- focus = the peak stress hour AHEAD, not a fixed date ------------
    now_ist = now if now is not None else datetime.now(timezone(timedelta(hours=tz)))
    now_key = now_ist.strftime("%Y-%m-%d %H:%M")
    future = [i for i, s in enumerate(stamps) if s >= now_key] or list(range(len(stamps)))

    # The window is requested in UTC and shifted to IST, so its first and last
    # IST dates are part-days. Prefer a complete day, because a full
    # midnight-to-midnight series is what the day charts and the work-shift
    # comparison are meaningful over. The fallback below may still hand back a
    # part-day, which is why day hours are passed explicitly to
    # insight.scenario_shift_hours rather than relied on to equal list positions
    # -- that assumption used to raise IndexError on the short tail.
    by_day: dict[str, list[int]] = {}
    for i, s in enumerate(stamps):
        by_day.setdefault(s[:10], []).append(i)
    complete = {day for day, idx in by_day.items() if len(idx) == 24}
    candidates = [i for i in future if stamps[i][:10] in complete] or future

    focus_idx = candidates[int(np.argmax(wbgt[candidates].mean(axis=1)))]
    focus_day = stamps[focus_idx][:10]
    day_idx = by_day[focus_day]

    peak_hour = [int(stamps[day_idx[int(np.argmax(wbgt[day_idx, j]))]][11:13])
                 for j in range(len(cells))]
    props = {}
    for j, cell in enumerate(cells):
        raw = form["cells"].get(cell, {})
        props[cell] = {
            "d_ta_c": round(float(d_ta[j]), 2),
            "intensity": round(float(intensity[j]), 3),
            "roads": round(float(raw.get("roads", 0.0)), 3),
            "green": round(float(raw.get("green", 0.0)), 3),
            "water": round(float(raw.get("water", 0.0)), 3),
            "exposure": round(float(surface.exposure[j]), 3),
            "vulnerability": round(float(surface.vulnerability[j]), 3),
            "place": place_names.get(cell, {}).get("name"),
            "place_exact": place_names.get(cell, {}).get("exact", False),
            "peak_hour": peak_hour[j],
            "wbgt_focus": round(float(wbgt[focus_idx, j]), 1),
            "utci_focus": round(float(utci[focus_idx, j]), 1),
            "risk_focus": round(float(risk[focus_idx, j]), 3),
        }

    hexes_data = sp.grid_geojson(cells, props)

    hourly_data = {
        "meta": {
            "city": city["name"], "date": focus_day,
            "hours_ist": [int(stamps[i][11:13]) for i in day_idx],
            "labels_ist": [stamps[i][11:16] for i in day_idx],
            "uhi_amplitude_c": amplitude_c,
        },
        "hexes": {
            cell: {
                "air_temp": r1(ta[day_idx, j]), "wbgt": r1(wbgt[day_idx, j]),
                "utci": r1(utci[day_idx, j]), "heat_index": r1(heat_index[day_idx, j]),
                "risk": [round(float(v), 3) for v in risk[day_idx, j]],
            }
            for j, cell in enumerate(cells)
        },
    }

    means = {n: a.mean(axis=1) for n, a in
             (("air_temp", ta), ("wbgt", wbgt), ("utci", utci),
              ("heat_index", heat_index))}
    city_data = {
        "city": city["name"], "timestamps_ist": stamps,
        **{k: r1(v) for k, v in means.items()},
        "night_recovery": night_recovery(stamps, means["air_temp"]),
    }

    persona_out = {}
    series = wbgt[day_idx].mean(axis=1)
    for key in PERSONA_ORDER:
        persona = ph.PERSONAS[key]
        minutes = [float(ph.safe_work_minutes_per_hour(w, persona)) for w in series]
        persona_out[key] = {
            "label": persona.label, "notes": persona.notes,
            "metabolic": persona.metabolic.name,
            "limit_c": round(persona.limit_c(), 1),
            "vulnerability_offset_c": persona.vulnerability_offset_c,
            "basis": ph.assess(float(series[0]), persona)["basis"],
            "safe_minutes_by_hour": minutes,
            "total_safe_hours": round(sum(minutes) / 60.0, 1),
            "full_capacity_hours": [int(stamps[i][11:13]) for i, m
                                    in zip(day_idx, minutes) if m >= 60],
            "assessment_at_focus": ph.assess(
                float(series[day_idx.index(focus_idx)]), persona),
        }
    personas_data = {"date": focus_day, "personas": persona_out, "order": PERSONA_ORDER}

    worst = int(np.argmax(utci[focus_idx]))
    adv = ad.build_advisory(
        cells[worst], city["name"], f"{stamps[focus_idx].replace(' ', 'T')}:00+05:30",
        float(utci[focus_idx, worst]), float(wbgt[focus_idx, worst]),
        ph.safe_work_minutes_per_hour(float(wbgt[focus_idx, worst]),
                                      ph.PERSONAS["construction"]))
    advisory_data = {
        "zone_id": adv.zone_id, "headline": adv.headline, "severity": adv.severity,
        "colour": adv.colour, "utci_c": adv.utci_c, "wbgt_c": adv.wbgt_c,
        "safe_work_note": adv.safe_work_note, "text": adv.text,
        "languages_verified": ad.LANGUAGES_VERIFIED,
        "cap_xml": ad.cap_alert(adv, polygon=sp.cell_polygon(cells[worst])),
    }

    def dom(arr, pad=0.04):
        lo, hi = float(np.min(arr)), float(np.max(arr))
        p = (hi - lo) * pad
        return [round(lo - p, 2), round(hi + p, 2)]

    # Which layers describe WHERE the intra-city pattern comes from, built from
    # the file actually loaded. The live forecast runs on the same offsets the
    # historical replay does, so it must make the same claims about them --
    # a live panel still citing OpenStreetMap while computing on satellite
    # measurements is exactly the drift this mechanism exists to catch.
    if form.get("method") == "satellite_lst":
        src = form["source"]
        heat_pattern_rows = [
            {"layer": "urban heat pattern",
             "plain": "Which neighbourhoods actually run hotter",
             "source": src["instrument"],
             "resolution": (f"{src['native_resolution_m']} m pixels, sampled to "
                            f"H3 res {config['grid']['h3_resolution']}"),
             "status": (f"MEASURED -- {form['coverage']['cells_observed']} of "
                        f"{form['coverage']['cells_total']} zones observed")},
            {"layer": "surface-to-air conversion",
             "plain": "How much of the ground's extra heat reaches the air you breathe",
             "source": f"alpha = {form['alpha']}, literature value",
             "resolution": "one coefficient, city-wide",
             "status": "ASSUMED -- the only assumed number left in the pattern"},
        ]
    else:
        heat_pattern_rows = [
            {"layer": "urban form", "plain": "How built-up each area is",
             "source": "OpenStreetMap via Overpass",
             "resolution": f"H3 res {config['grid']['h3_resolution']}",
             "status": "measured"},
            {"layer": "UHI amplitude", "plain": "How much hotter cities get",
             "source": "literature value",
             "resolution": f"{amplitude_c} degC city-wide",
             "status": "ASSUMED -- not fitted locally"},
        ]

    meta_data = {
        "city": city["name"], "centre": city["centre"], "bbox": city["bbox"],
        "h3_resolution": config["grid"]["h3_resolution"], "n_cells": len(cells),
        "focus": {"date": focus_day, "hour_ist": int(stamps[focus_idx][11:13])},
        "mode": "live",
        "generated_at_ist": now_ist.strftime("%Y-%m-%d %H:%M"),
        "forecast_age_minutes": round(age, 1) if age is not None else None,
        "window_ist": [stamps[0], stamps[-1]],
        "event": (f"Live forecast for {city['name']}. Conditions from now to "
                  f"{stamps[-1][:10]}, updated when the pipeline is re-run."),
        "domains": {"air_temp": dom(ta), "wbgt": dom(wbgt), "utci": dom(utci),
                    "risk": dom(risk)},
        "kill_gate": {
            "air_temp_spread_c": round(float(np.ptp(ta[focus_idx])), 2),
            "wbgt_spread_c": round(float(np.ptp(wbgt[focus_idx])), 2),
            "utci_spread_c": round(float(np.ptp(utci[focus_idx])), 2),
            "wbgt_damping_ratio": round(float(np.ptp(wbgt[focus_idx]) /
                                              max(np.ptp(ta[focus_idx]), 1e-6)), 2),
            "utci_amplification": round(float(np.ptp(utci[focus_idx]) /
                                              max(np.ptp(ta[focus_idx]), 1e-6)), 2),
            "verdict": "LIVE",
        },
        "provenance": [
            {"layer": "weather", "plain": "Weather forecast",
             "source": "Open-Meteo forecast API", "resolution": "~11 km, hourly",
             "status": "measured"},
            *heat_pattern_rows,
            {"layer": "thermal indices", "plain": "Heat-stress calculations",
             "source": "thermofeel (ECMWF); WBGT by Liljegren, UTCI polynomial",
             "resolution": "per cell-hour", "status": "measured"},
            {"layer": "physiology", "plain": "Safe limits for the human body",
             "source": "ISO 7243 limits + ACGIH work-rest",
             "resolution": "per persona", "status": "published standards"},
            {"layer": "vulnerability", "plain": "Who lives there and how they cope",
             "source": "PLACEHOLDER", "resolution": "city-wide constant",
             "status": "NOT FITTED -- exposure proxied by urban intensity"},
            {"layer": "health risk", "plain": "Expected health impact",
             "source": "literature-shaped exposure-response",
             "resolution": "relative risk only",
             "status": "NOT CALIBRATED to local health records"},
        ],
        "caveats": [
            {"plain": "This is a forecast, so the days ahead are predictions and "
                      "will change. It was last updated at the time shown above.",
             "technical": "Open-Meteo forecast, refreshed when the pipeline runs; "
                          "no ensemble spread or prediction intervals are shown."},
            {"plain": ("Being live does not make it more accurate. Which "
                       "neighbourhoods run hotter is measured from satellite "
                       "images; how much of that reaches the air is still a "
                       "published average."
                       if form.get("method") == "satellite_lst" else
                       "Being live does not make it more accurate. How much hotter "
                       "each neighbourhood gets is still a published average, not "
                       "something measured here."),
             "technical": ("Which zones are hotter is measured from satellite "
                           "surface temperature; the surface-to-air coefficient "
                           "alpha remains assumed. Live input changes currency, "
                           "not validation."
                           if form.get("method") == "satellite_lst" else
                           "UHI amplitude remains assumed; live input changes "
                           "currency, not validation.")},
            {"plain": "We could not get neighbourhood-level data on who lives "
                      "where, so the risk map reflects how hot a place is, not "
                      "how vulnerable its residents are.",
             "technical": "Vulnerability is a declared placeholder and does not "
                          "vary between neighbourhoods."},
            {"plain": "The health-risk numbers are not based on real hospital or "
                      "death records from this city.",
             "technical": "Exposure-response coefficients are not fitted to local "
                          "health data."},
            {"plain": "The Hindi and Gujarati warning text has not been checked by "
                      "a native speaker.",
             "technical": "Advisory copy is machine-composed and unverified."},
        ],
        "is_placeholder_urban": False,
        "exposure_response": {
            "metric": rk.DEFAULT_WBGT_RESPONSE.metric,
            "mmt_c": rk.DEFAULT_WBGT_RESPONSE.mmt,
            "beta": rk.DEFAULT_WBGT_RESPONSE.beta,
            "beta_ci": [rk.DEFAULT_WBGT_RESPONSE.beta_low,
                        rk.DEFAULT_WBGT_RESPONSE.beta_high],
            "is_calibrated": rk.DEFAULT_WBGT_RESPONSE.is_calibrated,
            "source": rk.DEFAULT_WBGT_RESPONSE.source,
        },
    }

    focus_ta = ta[focus_idx]
    focus_rh = rh[focus_idx]
    focus_wind = np.full_like(focus_ta, float(weather["wind_speed_10m"].iloc[focus_idx]))
    focus_ghi = np.full_like(focus_ta, float(weather["shortwave_radiation"].iloc[focus_idx]))
    day_series = [float(v) for v in wbgt[day_idx].mean(axis=1)]
    day_labels = [stamps[i][11:16] for i in day_idx]
    day_hours = [int(stamps[i][11:13]) for i in day_idx]

    insights_data = {
        "date": focus_day,
        "drivers": ins.driver_attribution(focus_ta, focus_rh, focus_wind, focus_ghi),
        "scenarios": [
            ins.scenario_shift_hours(day_series, hours=day_hours),
            ins.scenario_shade(focus_ta, focus_rh, focus_wind, focus_ghi),
            ins.scenario_greening(focus_ta, focus_rh, focus_wind, focus_ghi,
                                  intensity, amplitude_c),
        ],
        "actions": ins.recommended_actions(day_series, day_labels),
        # The pre-baked what-if grid and the parser rules that address it.
        # Both ride inside insights.json, which is already compiled into the
        # bundle at build time -- so the ask box answers with the wifi off,
        # which is the whole reason the grid exists rather than an API call.
        "scenario_grid": sg.build_grid(focus_ta, focus_rh, focus_wind, focus_ghi,
                                       intensity, amplitude_c, day_series,
                                       hours=day_hours),
        "intents": wi.compile_intents(),
        "refusals": wi.compile_refusals(),
        "omitted": [
            {"item": "Water stations / hydration measures",
             "why": "Hydration is not a thermal quantity. Our model cannot "
                    "estimate its effect, so it is not offered as though it could."},
            {"item": "People-at-risk headcount",
             "why": "We have no population data and vulnerability is a declared "
                    "placeholder. A precise headcount would be fabricated."},
        ],
    }

    return {
        "map": hexes_data,
        "hourly": hourly_data,
        "summary": city_data,
        "personas": personas_data,
        "advisory": advisory_data,
        "meta": meta_data,
        "insights": insights_data
    }
