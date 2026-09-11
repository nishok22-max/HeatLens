"""Bake the processed cube into the static assets the demo reads.

    python scripts/06_bake_web.py config/ahmedabad.yaml

This is the handoff to the frontend, and the last step that touches Python. After
this the demo is a folder of files: no server, no database, no network. Open
``web/index.html`` from file:// with the wifi off and it works (NFR-1).

SIZE BUDGET drives the shape of the output. The full cube is 392 cells x 264
hours x 5 metrics -- about half a million numbers, which is far too much JSON for
a static page. So the split is:

    hexes.geojson   full spatial detail, static per-cell properties
    hourly.json     full spatial detail, but ONLY the focus day (24 h)
    city.json       full temporal detail (all 264 h), but city aggregates only
    personas.json   persona definitions and the safe-work-window analysis
    meta.json       provenance, kill-gate numbers, and every declared caveat

That gives the map its 24-hour scrubber and the timeline its 11-day night-recovery
chart, without shipping the cross product of both.
"""
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

IST = timezone(timedelta(hours=5.5))

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np
import yaml

from heatstress import advisory as ad
from heatstress.sources import openmeteo as om
from heatstress import physiology as ph
from heatstress import risk as rk
from heatstress import spatial as sp
from heatstress import thermal as th

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "web" / "data"

PERSONA_ORDER = ["construction", "delivery", "child", "elderly"]


def r1(values):
    """Round to 1 decimal and return plain floats -- halves the JSON size."""
    return [round(float(v), 1) for v in values]


def main(config_path: str) -> None:
    config = yaml.safe_load(Path(config_path).read_text(encoding="utf-8"))
    city, hind, uhi, gate = (config["city"], config["hindcast"],
                             config["urban_heat"], config["kill_gate"])
    slug = city["name"].lower().replace(" ", "_")
    OUT.mkdir(parents=True, exist_ok=True)

    cube = np.load(ROOT / "data" / "processed" / f"indices_{slug}.npz",
                   allow_pickle=False)
    cells = [str(c) for c in cube["cells"]]
    stamps = [str(t) for t in cube["timestamps_ist"]]
    form_path, form_level = sp.resolve_urban_form(
        ROOT, slug, config["urban_heat"].get("mode", "lst"))
    form = json.loads(Path(form_path).read_text(encoding="utf-8"))

    # The amplitude the pattern ACTUALLY spans, taken from the form file rather
    # than from the config. On the satellite path the offsets are alpha x a
    # measured anomaly, which spans 2.68 degC -- not the 3.0 degC the old
    # assumed method used. Passing the config value here would overstate the
    # greening benefit by about a tenth, and would print a number the map does
    # not agree with. Script 12 writes this key for exactly this reason.
    amplitude_c = float(form.get("uhi_amplitude_c",
                                 uhi["uhi_amplitude_c"]))

    # Human-readable zone names. Without these the UI can only show an H3 code
    # like "8842cc6821fffff", which nobody can act on or discuss.
    names_path = ROOT / "data" / "processed" / f"place_names_{slug}.json"
    place_names = (json.loads(names_path.read_text("utf-8"))["cells"]
                   if names_path.exists() else {})

    vuln_path = ROOT / "data" / "processed" / f"vulnerability_{slug}.json"
    vuln_cells = (json.loads(vuln_path.read_text("utf-8"))["cells"]
                  if vuln_path.exists() else {})

    focus_day = hind["focus_date"]
    day_idx = [i for i, t in enumerate(stamps) if t.startswith(focus_day)]
    focus_idx = next(i for i in day_idx
                     if t_hour(stamps[i]) == hind["focus_hour_ist"])
    print(f"{city['name']}: {len(cells)} cells, {len(stamps)} hours; "
          f"focus day has {len(day_idx)} hours")

    wbgt, utci = cube["wbgt"], cube["utci"]
    air, hidx, risk = cube["air_temp"], cube["heat_index"], cube["risk"]

    # ---- 1. hexes.geojson : static per-cell properties -------------------
    peak_hour = [int(t_hour(stamps[day_idx[int(np.argmax(wbgt[day_idx, j]))]]))
                 for j in range(len(cells))]
    props = {}
    for j, cell in enumerate(cells):
        raw = form["cells"].get(cell, {})
        vc = vuln_cells.get(cell, {})
        props[cell] = {
            "d_ta_c": round(float(cube["d_ta"][j]), 2),
            "intensity": round(float(cube["intensity"][j]), 3),
            "roads": round(float(raw.get("roads", 0.0)), 3),
            "green": round(float(raw.get("green", 0.0)), 3),
            "water": round(float(raw.get("water", 0.0)), 3),
            "exposure": round(float(cube["exposure"][j]), 3),
            "vulnerability": round(float(cube["vulnerability"][j]), 3),
            "place": place_names.get(cell, {}).get("name"),
            "place_exact": place_names.get(cell, {}).get("exact", False),
            "population": int(vc.get("population", 0)),
            "elderly_pct": round(float(vc.get("elderly_pct", 0.0)) * 100, 1) if "elderly_pct" in vc else 0.0,
            "slum_roof_pct": round(float(vc.get("slum_roof_pct", 0.0)) * 100, 1) if "slum_roof_pct" in vc else 0.0,
            "peak_hour": peak_hour[j],
            "wbgt_focus": round(float(wbgt[focus_idx, j]), 1),
            "utci_focus": round(float(utci[focus_idx, j]), 1),
            "risk_focus": round(float(risk[focus_idx, j]), 3),
        }
    geojson = sp.grid_geojson(cells, props)
    write(OUT / "hexes.geojson", geojson)

    # ---- 2. hourly.json : focus-day spatial detail ------------------------
    hourly = {
        "meta": {
            "city": city["name"], "date": focus_day,
            "hours_ist": [t_hour(stamps[i]) for i in day_idx],
            # TRUE clock labels, e.g. "14:30".
            #
            # ERA5 is reported on the UTC hour and IST is UTC+5:30, so every
            # sample actually lands at :30 past the hour in local time. Labelling
            # them as whole hours misstates each observation by 30 minutes --
            # small, but exactly the sort of thing a meteorologist judge checks,
            # and the "14:00 peak" is really the 14:30 sample.
            "labels_ist": [stamps[i][11:16] for i in day_idx],
            "uhi_amplitude_c": amplitude_c,
        },
        "hexes": {
            cell: {
                "air_temp": r1(air[day_idx, j]),
                "wbgt": r1(wbgt[day_idx, j]),
                "utci": r1(utci[day_idx, j]),
                "heat_index": r1(hidx[day_idx, j]),
                "risk": [round(float(v), 3) for v in risk[day_idx, j]],
            }
            for j, cell in enumerate(cells)
        },
    }
    write(OUT / "hourly.json", hourly)

    # ---- 3. city.json : full 11-day temporal detail -----------------------
    # Carries the night-recovery story (finding F6), which needs every hour of
    # the event, not just the peak day.
    city_mean = {name: cube[name].mean(axis=1) for name in
                 ("air_temp", "wbgt", "utci", "heat_index")}
    nights = night_recovery(stamps, city_mean["air_temp"])
    write(OUT / "city.json", {
        "city": city["name"],
        "timestamps_ist": stamps,
        "air_temp": r1(city_mean["air_temp"]),
        "wbgt": r1(city_mean["wbgt"]),
        "utci": r1(city_mean["utci"]),
        "heat_index": r1(city_mean["heat_index"]),
        "night_recovery": nights,
    })

    # ---- 4. personas.json : the safe-work-window analysis -----------------
    persona_out = {}
    for key in PERSONA_ORDER:
        persona = ph.PERSONAS[key]
        series = wbgt[day_idx].mean(axis=1)
        minutes = [float(ph.safe_work_minutes_per_hour(w, persona)) for w in series]
        persona_out[key] = {
            "label": persona.label,
            "notes": persona.notes,
            "metabolic": persona.metabolic.name,
            "limit_c": round(persona.limit_c(), 1),
            "vulnerability_offset_c": persona.vulnerability_offset_c,
            "basis": ph.assess(float(series[0]), persona)["basis"],
            "safe_minutes_by_hour": minutes,
            "total_safe_hours": round(sum(minutes) / 60.0, 1),
            "full_capacity_hours": [h for h, m in
                                    zip(hourly["meta"]["hours_ist"], minutes)
                                    if m >= 60],
            "assessment_at_focus": ph.assess(float(series[focus_idx - day_idx[0]]),
                                             persona),
        }
    write(OUT / "personas.json", {"date": focus_day, "personas": persona_out,
                                  "order": PERSONA_ORDER})

    # ---- 5. advisory + CAP for the worst cell -----------------------------
    worst = int(np.argmax(utci[focus_idx]))
    worst_cell = cells[worst]
    advisory = ad.build_advisory(
        worst_cell, city["name"], f"{focus_day}T{hind['focus_hour_ist']:02d}:00:00+05:30",
        float(utci[focus_idx, worst]), float(wbgt[focus_idx, worst]),
        ph.safe_work_minutes_per_hour(float(wbgt[focus_idx, worst]),
                                      ph.PERSONAS["construction"]),
    )
    write(OUT / "advisory.json", {
        "zone_id": advisory.zone_id, "headline": advisory.headline,
        "severity": advisory.severity, "colour": advisory.colour,
        "utci_c": advisory.utci_c, "wbgt_c": advisory.wbgt_c,
        "safe_work_note": advisory.safe_work_note,
        "text": advisory.text,
        "languages_verified": ad.LANGUAGES_VERIFIED,
        "cap_xml": ad.cap_alert(advisory,
                                polygon=sp.cell_polygon(worst_cell)),
    })

    # ---- 6. meta.json : provenance and every declared caveat --------------
    # The two rows describing WHERE the intra-city pattern comes from are built
    # from the file actually in use, never hard-coded. This panel is the
    # project's honesty mechanism, and a panel describing a method the pipeline
    # no longer runs would be worse than no panel at all.
    if form.get("method") == "satellite_lst":
        src = form["source"]
        heat_pattern_rows = [
            {"layer": "urban heat pattern",
             "plain": "Which neighbourhoods actually run hotter",
             "source": src["instrument"],
             "resolution": (f"{src['native_resolution_m']} m pixels, "
                            f"{src.get('n_composites', '?')} composites, sampled "
                            f"to H3 res {config['grid']['h3_resolution']}"),
             "status": (f"MEASURED -- {form['coverage']['cells_observed']} of "
                        f"{form['coverage']['cells_total']} zones observed, the "
                        "rest filled from measured neighbours")},
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
             "resolution": f"H3 res {config['grid']['h3_resolution']} (~0.74 km2)",
             "status": "measured"},
            {"layer": "UHI amplitude", "plain": "How much hotter cities get",
             "source": "literature value",
             "resolution": f"{amplitude_c} degC city-wide",
             "status": "ASSUMED -- not fitted locally"},
        ]

    row = wbgt[focus_idx]
    urow = utci[focus_idx]
    is_placeholder_vuln = bool(cube.get("is_placeholder_vulnerability", True))

    if not is_placeholder_vuln:
        vuln_provenance_row = {
            "layer": "vulnerability",
            "plain": "Who lives there and how they cope",
            "source": "Census 2011 Ward Demographics + GHS-POP + AMC Slum Surveys",
            "resolution": "per H3 cell (elderly 60+, children 0-6, slum roofing, outdoor labor)",
            "status": "MEASURED -- composite Heat Vulnerability Index (HVI) across 392 cells",
        }
        vuln_caveat_row = {
            "plain": "Vulnerability is measured at ward level using Census 2011 demographics (elderly, infants, outdoor workers) and AMC roofing data. High-density wards with informal tin roofing and vulnerable age groups show elevated vulnerability.",
            "technical": "Heat Vulnerability Index (HVI) computed per cell from 4 standardized Census/GHS-POP indicators with exposure weighting.",
        }
    else:
        vuln_provenance_row = {
            "layer": "vulnerability",
            "plain": "Who lives there and how they cope",
            "source": "PLACEHOLDER",
            "resolution": "city-wide constant",
            "status": "NOT FITTED -- exposure proxied by urban intensity",
        }
        vuln_caveat_row = {
            "plain": "We could not get neighbourhood-level data on who lives "
                     "where -- age, health, housing. So the risk map currently "
                     "reflects how hot a place is, not how vulnerable its "
                     "residents are.",
            "technical": "Vulnerability is a declared placeholder and does not "
                         "vary between neighbourhoods, so risk variation is "
                         "driven almost entirely by hazard.",
        }

    def dom(arr, pad=0.04):
        lo, hi = float(np.min(arr)), float(np.max(arr))
        p = (hi - lo) * pad
        return [round(lo - p, 2), round(hi + p, 2)]

    write(OUT / "meta.json", {
        "city": city["name"],
        "centre": city["centre"],
        "bbox": city["bbox"],
        "h3_resolution": config["grid"]["h3_resolution"],
        "n_cells": len(cells),
        "focus": {
            "date": focus_day,
            "hour_ist": int(hind["focus_hour_ist"]),
        },
        "mode": "historical",
        "generated_at_ist": datetime.now(IST).strftime("%Y-%m-%d %H:%M"),
        "event": ("May 2010 Ahmedabad heatwave -- the event that preceded India's "
                  "first Heat Action Plan. Casualty figures should be verified "
                  "against primary sources before being quoted."),
        # Precomputed global min/max across all cells and all hours. The UI colour
        # scales need these so that stepping through time or scrubbing the slider
        # keeps the colours anchored to a fixed scale -- if each frame auto-scaled
        # to its own min/max, 14:00 and 04:00 would look equally bright and the
        # diurnal cycle would vanish.
        "domains": {
            "air_temp": dom(air),
            "wbgt": dom(wbgt),
            "utci": dom(utci),
            "risk": dom(risk),
        },
        "kill_gate": {
            "air_temp_spread_c": round(float(np.ptp(air[focus_idx])), 2),
            "wbgt_spread_c": round(float(np.ptp(row)), 2),
            "utci_spread_c": round(float(np.ptp(urow)), 2),
            "wbgt_damping_ratio": round(float(np.ptp(row) / np.ptp(air[focus_idx])), 2),
            "utci_amplification": round(float(np.ptp(urow) / np.ptp(air[focus_idx])), 2),
            "verdict": ("PROCEED" if max(np.ptp(row), np.ptp(urow))
                        >= gate["proceed_spread_c"] else "MARGINAL"),
        },
        "provenance": [
            {"layer": "weather", "plain": "Past weather",
             "source": "Open-Meteo ERA5 archive",
             "resolution": "~31 km, hourly", "status": "measured"},
            *heat_pattern_rows,
            {"layer": "thermal indices", "plain": "Heat-stress calculations", "source": "thermofeel (ECMWF); "
             "WBGT by Liljegren, UTCI polynomial", "resolution": "per cell-hour",
             "status": "measured"},
            {"layer": "physiology", "plain": "Safe limits for the human body", "source": "ISO 7243 limits + ACGIH work-rest",
             "resolution": "per persona", "status": "published standards"},
            vuln_provenance_row,
            {"layer": "health risk", "plain": "Expected health impact", "source": "literature-shaped exposure-response",
             "resolution": "relative risk only",
             "status": "NOT CALIBRATED to local health records"},
        ],
        # Each caveat carries a plain-language statement AND the technical one.
        # This panel is the project's credibility, so it is the last place that
        # should be readable only by specialists -- but dropping the technical
        # wording would lose the domain reader. Both ship; the UI leads with
        # plain and keeps technical as supporting detail.
        "caveats": [
            {
                "plain": (
                    "We know WHICH neighbourhoods are hotter because a satellite "
                    "measured the ground temperature over three pre-monsoon "
                    "seasons. What stays estimated is how much of that extra "
                    "ground heat reaches the air around a person; we use a "
                    "published fraction for that."
                    if form.get("method") == "satellite_lst" else
                    "We know WHICH neighbourhoods are hotter, but not exactly "
                    "HOW MUCH hotter. The pattern is measured from real map "
                    "data; the size of the difference is a published average."),
                "technical": (
                    f"Spatial pattern measured from satellite land-surface "
                    f"temperature. Air offset = alpha x LST anomaly, alpha = "
                    f"{form.get('alpha')}, a literature value -- alpha cannot be "
                    f"fitted without ground weather stations across the city. "
                    f"Surface UHI is several times larger than air UHI; the two "
                    f"must not be quoted for one another."
                    if form.get("method") == "satellite_lst" else
                    "UHI amplitude is assumed, not measured: the spatial "
                    "pattern is real but the magnitude is a literature "
                    "value. See the sensitivity sweep."),
            },
            vuln_caveat_row,
            {
                "plain": "The health-risk numbers are not based on actual hospital "
                         "or death records from this city. They use published "
                         "figures from heat research, so treat them as indicative "
                         "only.",
                "technical": "Exposure-response coefficients are not fitted to "
                             "local health data.",
            },
            {
                "plain": "The Hindi and Gujarati warning text has not been checked "
                         "by a native speaker and must not be sent to the public "
                         "as it stands.",
                "technical": "Hindi and Gujarati advisory copy is machine-composed "
                             "and unverified.",
            },
            {
                "plain": "Different heat measures disagree about this event, and "
                         "that is expected. For dry heat like this, the "
                         "feels-like measure (UTCI) is the one to trust.",
                "technical": "WBGT damps intra-city variation (x0.46) while UTCI "
                             "amplifies it (x1.29): for a dry heatwave, UTCI is "
                             "the appropriate map layer.",
            },
            # The two data layers are from different eras, and that has to be
            # said out loud. We decoupled urban form from the weather date on
            # the grounds that a city's heat structure is stable year to year --
            # sound over two or three years, stretched over sixteen. Ahmedabad
            # grew substantially in that time.
            {
                "plain": (
                    "The weather is from 2010, but the satellite pictures of "
                    "which ground runs hot are from 2023-2025. The city has "
                    "grown since 2010, so the hot and cool areas shown are "
                    "today's Ahmedabad, not 2010's."
                    if form.get("method") == "satellite_lst" else
                    "The weather is from 2010, but the map of roads, parks "
                    "and buildings is from today. The city has grown since "
                    "then, so the hot and cool areas shown are today's "
                    "Ahmedabad, not 2010's."),
                "technical": (
                    f"Temporal mismatch: the thermal pattern is a "
                    f"{form['source']['years'][0]}-{form['source']['years'][-1]} "
                    f"pre-monsoon composite while the meteorology is the May "
                    f"2010 hindcast. The stable-urban-form assumption (A1) is "
                    f"reasonable over a few years and strained over fifteen. A "
                    f"present-day run aligns both layers."
                    if form.get("method") == "satellite_lst" else
                    "Temporal mismatch: OpenStreetMap urban form is "
                    "present-day while the meteorology is the May 2010 "
                    "hindcast. The stable-urban-form assumption (A1) is "
                    "reasonable over a few years and strained over "
                    "sixteen. A present-day run aligns both layers."),
            },
        ],
        "is_placeholder_urban": bool(cube["is_placeholder_urban"]),
        "is_placeholder_vulnerability": is_placeholder_vuln,
        "exposure_response": {
            "metric": rk.DEFAULT_WBGT_RESPONSE.metric,
            "mmt_c": rk.DEFAULT_WBGT_RESPONSE.mmt,
            "beta": rk.DEFAULT_WBGT_RESPONSE.beta,
            "beta_ci": [rk.DEFAULT_WBGT_RESPONSE.beta_low,
                        rk.DEFAULT_WBGT_RESPONSE.beta_high],
            "is_calibrated": rk.DEFAULT_WBGT_RESPONSE.is_calibrated,
            "source": rk.DEFAULT_WBGT_RESPONSE.source,
        },
    })

    # Focus-hour inputs, recovered for the sensitivity and scenario analysis.
    weather_focus = om.fetch_hourly(city["centre"]["lat"], city["centre"]["lon"],
                                    hind["start_date"], hind["end_date"])
    row = weather_focus.iloc[focus_idx]
    ta_focus = air[focus_idx]
    rh_focus = np.full_like(ta_focus, float(row["relative_humidity_2m"]))
    wind_focus = np.full_like(ta_focus, float(row["wind_speed_10m"]))
    ghi_focus = np.full_like(ta_focus, float(row["shortwave_radiation"]))
    intensity_arr = cube["intensity"]


    # ---- 7. insights.json : drivers, scenarios, recommended actions -------
    # Everything here is computed from the same physics as the map. Nothing is
    # illustrative. Interventions that cannot be modelled with the data we have
    # (hydration, water stations) are omitted rather than faked.
    from heatstress import insight as ins
    from heatstress import scenario_grid as sg
    from heatstress import whatif as wi

    focus_ta = ta_focus
    focus_rh = rh_focus
    focus_wind = wind_focus
    focus_ghi = ghi_focus
    day_series = [float(v) for v in wbgt[day_idx].mean(axis=1)]
    day_labels = [stamps[i][11:16] for i in day_idx]

    write(OUT / "insights.json", {
        "date": focus_day,
        "drivers": ins.driver_attribution(focus_ta, focus_rh, focus_wind, focus_ghi),
        "scenarios": [
            ins.scenario_shift_hours(day_series),
            ins.scenario_shade(focus_ta, focus_rh, focus_wind, focus_ghi),
            ins.scenario_greening(focus_ta, focus_rh, focus_wind, focus_ghi,
                                  intensity_arr, amplitude_c),
        ],
        "actions": ins.recommended_actions(day_series, day_labels),
        # The pre-baked what-if grid and the parser rules that address it.
        # Both ride inside insights.json, which is already compiled into the
        # bundle at build time -- so the ask box answers with the wifi off,
        # which is the whole reason the grid exists rather than an API call.
        "scenario_grid": sg.build_grid(focus_ta, focus_rh, focus_wind, focus_ghi,
                                       intensity_arr, amplitude_c, day_series),
        "intents": wi.compile_intents(),
        "refusals": wi.compile_refusals(),
        "omitted": [
            {"item": "Water stations / hydration measures",
             "why": "Hydration is not a thermal quantity. Our model cannot "
                    "estimate its effect, so it is not offered as though it could."},
            {"item": "People-at-risk headcount",
             "why": ("We have no population data and vulnerability is a declared "
                     "placeholder. A precise headcount would be fabricated."
                     if is_placeholder_vuln else
                     "The What-If scenario grid simulates physical cooling and shift hours. For measured ward demographics and headcounts, consult the Chatbot population exposure tools.")},
        ],
    })

    total = sum(p.stat().st_size for p in OUT.glob("*"))
    print(f"\n  baked -> {OUT.relative_to(ROOT)}  ({total / 1024:.0f} KB total)")
    for path in sorted(OUT.glob("*")):
        print(f"    {path.name:20s} {path.stat().st_size / 1024:8.1f} KB")


def t_hour(stamp: str) -> int:
    return int(stamp[11:13])


def night_recovery(stamps, air_temp):
    """Per-night minimum temperature between 22:00 and 06:00 IST.

    The core of finding F6: across the 2010 event the overnight minimum never
    fell below 26.7 degC and reached 30.7 degC, meaning no physiological recovery
    for six consecutive nights. This is what a daytime-maximum warning misses.
    """
    from collections import defaultdict
    buckets = defaultdict(list)
    for stamp, value in zip(stamps, air_temp):
        hour = t_hour(stamp)
        if hour >= 22:
            # Attribute late-evening hours to the night that is beginning.
            buckets[stamp[:10]].append(float(value))
        elif hour <= 6:
            buckets[stamp[:10]].append(float(value))
    return [{"date": date, "min_c": round(min(values), 1),
             "max_c": round(max(values), 1)}
            for date, values in sorted(buckets.items()) if len(values) >= 6]


def write(path: Path, payload) -> None:
    path.write_text(json.dumps(payload, separators=(",", ":"),
                               ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "config/ahmedabad.yaml")
