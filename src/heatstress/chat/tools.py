"""
Data-payload tools for the HeatLens chat agent.

All tools are READ-ONLY.  Each returns a typed dict that always includes a
``_source`` field (which file or cache key the data came from) so the numeric
guard and the UI's "Sources" panel can trace every figure.

The tools are described in JSON-Schema format (``TOOL_SPECS``) for the LLM's
function-calling API, and implemented as plain Python functions (``TOOL_IMPLS``).
The agent calls ``execute_tool(name, args, payload)`` to dispatch.

ADDING A TOOL:
  1. Write the implementation function below.
  2. Add its JSON-Schema spec to TOOL_SPECS.
  3. Add it to TOOL_IMPLS.
  Nothing else needs to change.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# Root of the web/data/ directory tree.
# tools.py lives at:  <root>/src/heatstress/chat/tools.py
#   parents[0] = chat/
#   parents[1] = heatstress/
#   parents[2] = src/
#   parents[3] = project root
_DATA_ROOT = Path(__file__).resolve().parents[3] / "web" / "data"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_file(filename: str, live: bool = False) -> dict:
    """Read a baked JSON payload, live folder takes priority when requested."""
    path = _DATA_ROOT / ("live" if live else "") / filename
    if not path.exists():
        # Fall back to the non-live folder.
        path = _DATA_ROOT / filename
    return json.loads(path.read_text(encoding="utf-8"))


def _source_tag(filename: str, live: bool) -> str:
    folder = "live" if live else "historical"
    return f"web/data/{folder}/{filename}"


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------

def _get_city_summary(args: dict, payload: dict | None, live: bool) -> dict:
    """Return city-level stats: UTCI/WBGT spread, kill-gate verdict, event info."""
    if payload and "summary" in payload:
        # live_cache structure: payload["summary"] is city.json content
        # payload["meta"] is meta.json content
        meta = payload.get("meta", {})
        src = "live_cache"
    else:
        meta = _load_file("meta.json", live)
        src = _source_tag("meta.json", live)

    kg = meta.get("kill_gate", {})
    return {
        "city": meta.get("city", "unknown"),
        "event": meta.get("event", ""),
        "utci_spread_c": kg.get("utci_spread_c"),
        "wbgt_spread_c": kg.get("wbgt_spread_c"),
        "utci_amplification": kg.get("utci_amplification"),
        "wbgt_damping_ratio": kg.get("wbgt_damping_ratio"),
        "kill_gate_verdict": kg.get("verdict"),
        "n_zones": meta.get("n_cells"),
        "focus_date": (meta.get("focus") or {}).get("date"),
        "focus_hour_ist": (meta.get("focus") or {}).get("hour_ist"),
        "caveats": [c.get("plain") for c in meta.get("caveats", [])],
        "_source": src,
    }


def _get_advisory(args: dict, payload: dict | None, live: bool) -> dict:
    """Return the verbatim public advisory text (English only; hi/gu flagged as unverified)."""
    if payload and "advisory" in payload:
        adv = payload["advisory"]
        src = "live_cache"
    else:
        adv = _load_file("advisory.json", live)
        src = _source_tag("advisory.json", live)

    return {
        "severity": adv.get("severity"),
        "colour": adv.get("colour"),
        "utci_c": adv.get("utci_c"),
        "wbgt_c": adv.get("wbgt_c"),
        "safe_work_note": adv.get("safe_work_note"),
        # English text is verified; other langs are flagged.
        "text_en": adv.get("text", {}).get("en"),
        "text_hi": adv.get("text", {}).get("hi"),
        "text_gu": adv.get("text", {}).get("gu"),
        "languages_verified": adv.get("languages_verified", {}),
        "headline": adv.get("headline"),
        "_source": src,
        "_note": (
            "Hindi and Gujarati translations are machine-composed and NOT verified by a "
            "native speaker. Do not quote them as authoritative."
        ),
    }


def _get_insights(args: dict, payload: dict | None, live: bool) -> dict:
    """Return drivers, intervention scenarios, and recommended actions."""
    if payload and "insights" in payload:
        ins = payload["insights"]
        src = "live_cache"
    else:
        ins = _load_file("insights.json", live)
        src = _source_tag("insights.json", live)

    return {
        "date": ins.get("date"),
        "drivers": ins.get("drivers", []),
        "scenarios": ins.get("scenarios", []),
        "actions": ins.get("actions", []),
        "omitted": ins.get("omitted", []),
        "_source": src,
    }


def _get_exposure_response(args: dict, payload: dict | None, live: bool) -> dict:
    """Return the exposure-response model card — including calibration status."""
    if payload and "meta" in payload:
        er = payload["meta"].get("exposure_response", {})
        src = "live_cache"
    else:
        meta = _load_file("meta.json", live)
        er = meta.get("exposure_response", {})
        src = _source_tag("meta.json", live)

    return {
        "metric": er.get("metric"),
        "mmt_c": er.get("mmt_c"),         # minimum-morbidity threshold
        "beta": er.get("beta"),
        "beta_ci": er.get("beta_ci"),
        "is_calibrated": er.get("is_calibrated", False),
        "source": er.get("source"),
        "_source": src,
        "_warning": (
            "is_calibrated=False. Risk figures are relative and shaped by "
            "published literature, NOT fitted to local health records. "
            "Do NOT quote absolute casualty numbers from this model."
        ),
    }


def _get_metadata(args: dict, payload: dict | None, live: bool) -> dict:
    """Return data provenance, caveats, and model assumptions."""
    if payload and "meta" in payload:
        meta = payload["meta"]
        src = "live_cache"
    else:
        meta = _load_file("meta.json", live)
        src = _source_tag("meta.json", live)

    return {
        "city": meta.get("city"),
        "n_zones": meta.get("n_cells"),
        "h3_resolution": meta.get("h3_resolution"),
        "provenance": meta.get("provenance", []),
        "caveats": meta.get("caveats", []),
        "is_placeholder_urban": meta.get("is_placeholder_urban"),
        "generated_at_ist": meta.get("generated_at_ist"),
        "_source": src,
    }


def _get_work_safety_window(args: dict, payload: dict | None, live: bool) -> dict:
    """Return daily safe-work window for a persona from ISO 7243 / ACGIH.

    Args (in args dict):
        persona: one of 'construction', 'delivery', 'child', 'elderly', 'office'
    """
    import sys
    from pathlib import Path as P
    sys.path.insert(0, str(P(__file__).resolve().parents[3]))

    from heatstress import physiology as ph

    persona_key = args.get("persona", "construction")
    if persona_key not in ph.PERSONAS:
        return {
            "error": f"Unknown persona '{persona_key}'. "
                     f"Valid: {list(ph.PERSONAS.keys())}",
            "_source": "physiology.py",
        }

    persona = ph.PERSONAS[persona_key]

    # Load WBGT time series for the focus date.
    if payload and "hourly" in payload:
        hourly = payload["hourly"]
        src = "live_cache"
    else:
        hourly = _load_file("hourly.json", live)
        src = _source_tag("hourly.json", live)

    hours = hourly.get("meta", {}).get("hours_ist", [])
    labels = hourly.get("meta", {}).get("labels_ist", hours)

    # Average WBGT across all zones for the focus day.
    hexes = hourly.get("hexes", {})
    windows = []
    if hexes:
        import numpy as np
        wbgt_by_hour: list[float] = []
        for h_idx in range(len(hours)):
            vals = [
                float(cell["wbgt"][h_idx])
                for cell in hexes.values()
                if isinstance(cell, dict) and "wbgt" in cell
                   and h_idx < len(cell["wbgt"])
            ]
            wbgt_by_hour.append(float(np.mean(vals)) if vals else float("nan"))

        for h_idx, (hour, label) in enumerate(zip(hours, labels)):
            wbgt = wbgt_by_hour[h_idx]
            if not (wbgt == wbgt):   # nan check
                continue
            allowed = float(ph.safe_work_minutes_per_hour(wbgt, persona))
            windows.append({
                "hour_ist": label,
                "wbgt_c": round(wbgt, 1),
                "safe_minutes_per_hour": round(allowed),
                "full_capacity": allowed >= 60,
                "banned": allowed <= 0,
            })

    zero_hours = [w["hour_ist"] for w in windows if w["banned"]]
    full_hours = [w["hour_ist"] for w in windows if w["full_capacity"]]

    return {
        "persona": persona_key,
        "persona_label": persona.label,
        "standard": "ISO 7243 + ACGIH work/rest schedule",
        "hours": windows,
        "hours_at_zero": zero_hours,
        "hours_at_full_capacity": full_hours,
        "_source": src,
    }


def _get_zone_detail(args: dict, payload: dict | None, live: bool) -> dict:
    """Return hourly heat-stress stats for a specific H3 zone.

    Args:
        hex_id: the H3 cell identifier (e.g. '8842cc69edfffff')
    """
    hex_id = args.get("hex_id", "")
    if not hex_id:
        return {"error": "hex_id is required", "_source": "none"}

    if payload and "hourly" in payload:
        hourly = payload["hourly"]
        src = "live_cache"
    else:
        hourly = _load_file("hourly.json", live)
        src = _source_tag("hourly.json", live)

    hexes = hourly.get("hexes", {})
    if hex_id not in hexes:
        available = list(hexes.keys())[:5]
        return {
            "error": f"Zone '{hex_id}' not found. Sample IDs: {available}",
            "_source": src,
        }

    labels = hourly.get("meta", {}).get("labels_ist", [])
    hours_ist = hourly.get("meta", {}).get("hours_ist", [])
    zone_data = hexes[hex_id]   # dict: {"wbgt": [...], "utci": [...], "air_temp": [...], ...}

    hours_out = []
    wbgt_arr = zone_data.get("wbgt", [])
    utci_arr = zone_data.get("utci", [])
    hi_arr = zone_data.get("heat_index", [])
    ta_arr = zone_data.get("air_temp", [])

    for i, hour in enumerate(hours_ist):
        label = labels[i] if i < len(labels) else str(hour)
        hours_out.append({
            "time_ist": label,
            "utci_c": utci_arr[i] if i < len(utci_arr) else None,
            "wbgt_c": wbgt_arr[i] if i < len(wbgt_arr) else None,
            "heat_index_c": hi_arr[i] if i < len(hi_arr) else None,
            "ta_c": ta_arr[i] if i < len(ta_arr) else None,
        })

    return {
        "hex_id": hex_id,
        "hours": hours_out,
        "_source": src,
    }


# ---------------------------------------------------------------------------
# What-if / decision tools
#
# These read the scenario grid that scenario_grid.py pre-computed during the
# bake. They never run physics and never interpolate: a requested value is
# snapped to the nearest grid point and the snap is reported (DECISIONS D21),
# so the LLM can only ever cite a number the Python produced.
# ---------------------------------------------------------------------------

def _load_insights(payload: dict | None, live: bool) -> tuple[dict, str]:
    if payload and "insights" in payload:
        return payload["insights"], "live_cache"
    return _load_file("insights.json", live), _source_tag("insights.json", live)


def _nearest(value: float, axis: list) -> float:
    return min(axis, key=lambda candidate: abs(candidate - value))


def _pct(fraction: float) -> int:
    return int(round(fraction * 100))


def _simulate_intervention(args: dict, payload: dict | None, live: bool) -> dict:
    """Look up the modelled outcome of one intervention combination."""
    ins, src = _load_insights(payload, live)
    grid = ins.get("scenario_grid")
    if not grid:
        return {"error": "This dataset has no scenario grid.", "_source": src}
    axes = grid["axes"]

    shade_pct = args.get("shade_pct")
    greening_pct = args.get("greening_pct")
    shift = args.get("shift_start_hour")
    persona = args.get("persona")
    if shade_pct is None and greening_pct is None and shift is None:
        return {"error": "Name at least one lever: shade_pct, greening_pct or "
                         "shift_start_hour.", "_source": src}
    for name, value, hi in (("shade_pct", shade_pct, 100),
                            ("greening_pct", greening_pct, 100),
                            ("shift_start_hour", shift, 23)):
        if value is not None and not (0 <= float(value) <= hi):
            return {"error": f"{name} must be between 0 and {hi}.", "_source": src}

    out: dict = {"snaps": [], "_source": src, "basis": grid.get("basis", "")}

    if shade_pct is not None or greening_pct is not None:
        asked_s = float(shade_pct or 0) / 100
        asked_g = float(greening_pct or 0) / 100
        s = _nearest(asked_s, axes["shade"])
        g = _nearest(asked_g, axes["greening"])
        for name, asked, used in (("shade", asked_s, s), ("greening", asked_g, g)):
            if _pct(asked) != _pct(used):
                out["snaps"].append({"parameter": name, "asked": f"{_pct(asked)}%",
                                     "used": f"{_pct(used)}%"})
        row = next((r for r in grid["cooling"]
                    if r["shade"] == s and r["greening"] == g), None)
        if row is None:
            return {"error": "No grid row for that shade/greening pair.", "_source": src}
        out["cooling"] = {**row, "shade_pct": _pct(s), "greening_pct": _pct(g)}

    if shift is not None:
        who = persona or axes["persona"][0]
        if who not in axes["persona"]:
            return {"error": f"Unknown persona '{who}'. Valid: {axes['persona']}",
                    "_source": src}
        h = int(_nearest(int(shift), axes["shift_start"]))
        if h != int(shift):
            out["snaps"].append({"parameter": "shift_start", "asked": f"{int(shift)}:00",
                                 "used": f"{h}:00"})
        row = next((r for r in grid["scheduling"]
                    if r["shift_start"] == h and r["persona"] == who), None)
        if row is None:
            return {"error": "No grid row for that shift/persona pair.", "_source": src}
        out["scheduling"] = row
    return out


def _list_intervention_options(args: dict, payload: dict | None, live: bool) -> dict:
    """Every modelled option, ranked, plus cost labels and what is not modelled."""
    ins, src = _load_insights(payload, live)
    grid = ins.get("scenario_grid")
    if not grid:
        return {"error": "This dataset has no scenario grid.", "_source": src}
    cooling = sorted(
        ({**r, "shade_pct": _pct(r["shade"]), "greening_pct": _pct(r["greening"])}
         for r in grid["cooling"]),
        key=lambda r: r["delta_c"])
    scheduling = sorted(grid["scheduling"], key=lambda r: -r["reduction_pct"])
    return {
        "axes": {
            "shade_pct": [_pct(v) for v in grid["axes"]["shade"]],
            "greening_pct": [_pct(v) for v in grid["axes"]["greening"]],
            "shift_start_hour": grid["axes"]["shift_start"],
            "persona": grid["axes"]["persona"],
        },
        "cooling_ranked_most_cooling_first": cooling,
        "scheduling_ranked_biggest_reduction_first": scheduling,
        "headline_scenarios_with_cost": [
            {k: s.get(k) for k in ("key", "label", "detail", "cost", "basis")}
            for s in ins.get("scenarios", [])
        ],
        "not_modelled": ins.get("omitted", []),
        "basis": grid.get("basis", ""),
        "_source": src,
    }


def _get_hottest_zones(args: dict, payload: dict | None, live: bool) -> dict:
    """Hottest neighbourhoods at the focus hour, one row per named place."""
    n = max(1, min(int(args.get("n", 5) or 5), 15))
    if payload and ("map" in payload or "hexes" in payload):
        hexes = payload.get("map") or payload.get("hexes")
        meta = payload.get("meta", {})
        src = "live_cache"
    else:
        hexes = _load_file("hexes.geojson", live)
        meta = _load_file("meta.json", live)
        src = _source_tag("hexes.geojson", live)

    rows, seen = [], set()
    for f in sorted(hexes.get("features", []),
                    key=lambda f: -(f["properties"].get("utci_focus") or -1e9)):
        p = f["properties"]
        key = p.get("place") or p["h3_index"]
        if key in seen:
            continue
        seen.add(key)
        rows.append({
            "place": (p.get("place") if p.get("place_exact", True)
                      else f"near {p.get('place')}") if p.get("place") else None,
            "hex_id": p["h3_index"],
            "utci_c": p.get("utci_focus"),
            "wbgt_c": p.get("wbgt_focus"),
            "relative_risk": p.get("risk_focus"),
            "peak_hour_ist": p.get("peak_hour"),
        })
        if len(rows) == n:
            break
    focus = meta.get("focus", {})
    return {
        "focus_date": focus.get("date"),
        "focus_hour_ist": focus.get("hour_ist"),
        "zones": rows,
        "_note": "Names are the nearest OpenStreetMap place, not ward boundaries. "
                 "relative_risk is relative, not calibrated.",
        "_source": src,
    }


def _get_population_exposure(args: dict, payload: dict | None, live: bool) -> dict:
    """How many people are standing in the heat, per zone and per severity band.

    Backed by ``data/processed/population_ahmedabad.json`` (WorldPop zonal
    statistics). Two things this deliberately does NOT return, because no source
    for them exists in this repo:

      * age, roof-material or occupation splits -- there is no ward-level
        demographic table here, so an "elderly in extreme heat" count would be a
        fabricated number wearing a measured label;
      * casualties. That is the calibration refusal, and it is unchanged.

    WorldPop is itself modelled -- census totals disaggregated onto a 100 m grid
    with covariates -- so the payload says "modelled residential population",
    never "a count of people".
    """
    if payload and "map" in payload:
        geojson = payload["map"]
        meta = payload.get("meta", {})
        src = "live_cache"
    else:
        geojson = _load_file("hexes.geojson", live)
        meta = _load_file("meta.json", live)
        src = _source_tag("hexes.geojson", live)

    features = geojson.get("features", [])
    if not features:
        return {"error": "No spatial grid features found", "_source": src}

    pop_path = (_DATA_ROOT.parents[1] / "data" / "processed"
                / "population_ahmedabad.json")
    if not pop_path.exists():
        return {
            "error": (
                "No measured population layer. Run scripts/14_population.py to "
                "fetch WorldPop zonal statistics."
            ),
            "_is_measured": False,
            "_source": src,
        }

    pop_payload = json.loads(pop_path.read_text("utf-8"))
    pop_cells = pop_payload.get("cells", {})
    pop_source = pop_payload.get("source", {})

    total_pop = 0.0
    bands = {"extreme_heat_utci_46_plus": 0.0,
             "very_strong_heat_utci_42_to_46": 0.0,
             "strong_heat_utci_38_to_42": 0.0,
             "moderate_heat_below_38": 0.0}
    ward_stats: dict[str, dict] = {}
    missing = 0

    for f in features:
        p = f.get("properties", {})
        cell_id = p.get("h3_index", "")
        row = pop_cells.get(cell_id)
        if row is None:
            missing += 1
            continue
        pop = float(row.get("population", 0.0))
        total_pop += pop

        utci = float(p.get("utci_focus", 0.0))
        risk = float(p.get("risk_focus", 0.0))
        if utci >= 46.0:
            band = "extreme_heat_utci_46_plus"
        elif utci >= 42.0:
            band = "very_strong_heat_utci_42_to_46"
        elif utci >= 38.0:
            band = "strong_heat_utci_38_to_42"
        else:
            band = "moderate_heat_below_38"
        bands[band] += pop

        place = p.get("place") or "Unknown"
        ws = ward_stats.setdefault(place, {
            "place": place, "population": 0.0,
            "pop_in_extreme_heat": 0.0, "utci_max": utci, "risk_max": risk,
        })
        ws["population"] += pop
        if utci >= 46.0:
            ws["pop_in_extreme_heat"] += pop
        ws["utci_max"] = max(ws["utci_max"], utci)
        ws["risk_max"] = max(ws["risk_max"], risk)

    top_n = min(int(args.get("top_n", 5)), 10)
    top_wards = sorted(
        ward_stats.values(),
        key=lambda w: (w["pop_in_extreme_heat"], w["population"]),
        reverse=True,
    )[:top_n]

    focus = meta.get("focus", {})
    out = {
        "city": meta.get("city", "Ahmedabad"),
        "focus_date": focus.get("date"),
        "focus_hour_ist": focus.get("hour_ist"),
        "total_population": int(round(total_pop)),
        "exposure_by_heat_severity": {k: int(round(v)) for k, v in bands.items()},
        "top_exposed_wards": [
            {
                "place": w["place"],
                "total_population": int(round(w["population"])),
                "population_in_extreme_heat": int(round(w["pop_in_extreme_heat"])),
                "peak_utci_c": round(w["utci_max"], 1),
                "peak_relative_risk": round(w["risk_max"], 3),
            }
            for w in top_wards
        ],
        "_is_measured": True,
        "_population_nature": pop_source.get(
            "nature",
            "modelled residential population; census totals disaggregated onto "
            "a grid using covariates",
        ),
        "_not_available": (
            "No age, roof-material or occupation breakdown exists for these "
            "zones, so counts of elderly, infants, informal-roof dwellers or "
            "outdoor workers cannot be given. Vulnerability remains a city-wide "
            "constant and does not vary between zones."
        ),
        "_source": (
            f"{pop_source.get('provider', 'WorldPop')} "
            f"{pop_source.get('dataset', '')} {pop_source.get('year', '')} "
            f"({pop_source.get('native_resolution_m', 100)} m) + {src}"
        ).strip(),
        "_note": (
            "Population is modelled, not counted. Absolute casualty or death "
            "figures are still not provided: the exposure-response model is not "
            "calibrated to local health records."
        ),
    }
    if missing:
        out["_coverage_warning"] = (
            f"{missing} of {len(features)} zones have no population row and "
            "were excluded from every total."
        )
    return out


# ---------------------------------------------------------------------------
# Dispatch table
# ---------------------------------------------------------------------------

TOOL_IMPLS: dict[str, Any] = {
    "get_city_summary": _get_city_summary,
    "get_advisory": _get_advisory,
    "get_insights": _get_insights,
    "get_exposure_response": _get_exposure_response,
    "get_metadata": _get_metadata,
    "get_work_safety_window": _get_work_safety_window,
    "get_zone_detail": _get_zone_detail,
    "simulate_intervention": _simulate_intervention,
    "list_intervention_options": _list_intervention_options,
    "get_hottest_zones": _get_hottest_zones,
    "get_population_exposure": _get_population_exposure,
}


def execute_tool(
    name: str,
    args: dict,
    payload: dict | None = None,
    live: bool = False,
) -> dict:
    """Dispatch a tool call and return the result dict.

    All tool errors are returned as dicts (not raised) so the agent loop can
    feed the error back to the LLM and let it retry or explain.
    """
    impl = TOOL_IMPLS.get(name)
    if impl is None:
        return {"error": f"Unknown tool '{name}'", "_source": "none"}
    try:
        return impl(args, payload, live)
    except Exception as exc:
        return {"error": f"{type(exc).__name__}: {exc}", "_source": "none"}


# ---------------------------------------------------------------------------
# JSON-Schema specs for the LLM
# ---------------------------------------------------------------------------

TOOL_SPECS: list[dict] = [
    {
        "function": {
            "name": "get_city_summary",
            "description": (
                "Returns city-level heat-stress statistics: UTCI and WBGT spread across zones, "
                "the spatial amplification ratios, the kill-gate verdict, event description, "
                "and the list of important caveats. Use this for any question about "
                "city-wide heat levels or the go/no-go result."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        }
    },
    {
        "function": {
            "name": "get_advisory",
            "description": (
                "Returns the public health advisory for the peak zone: severity level, "
                "colour code, UTCI/WBGT values, safe-work note, and the verbatim advisory "
                "text in English, Hindi, and Gujarati. "
                "ALWAYS use this tool — never paraphrase or invent advisory text."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        }
    },
    {
        "function": {
            "name": "get_insights",
            "description": (
                "Returns what is driving the heat (driver attribution shares), "
                "the three modelled intervention scenarios (shift work hours, shade, greening), "
                "and the ranked recommended actions. Use for 'what can be done' questions."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        }
    },
    {
        "function": {
            "name": "get_exposure_response",
            "description": (
                "Returns the heat-health exposure-response model card: metric, threshold (MMT), "
                "beta coefficient, confidence interval, and calibration status. "
                "Use whenever someone asks about health risk, mortality, or model validation. "
                "Note: is_calibrated=False — never quote absolute death figures from this model."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        }
    },
    {
        "function": {
            "name": "get_metadata",
            "description": (
                "Returns data provenance, model assumptions, and known caveats "
                "(e.g. UHI amplitude is assumed, vulnerability is a placeholder). "
                "Use for questions about data sources, methodology, or limitations."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        }
    },
    {
        "function": {
            "name": "get_work_safety_window",
            "description": (
                "Returns the hourly safe-work window for a given worker persona "
                "based on ISO 7243 limits and ACGIH work/rest schedules. "
                "Shows which hours are fully banned, partially restricted, or safe. "
                "Use for questions about when it is safe to work outdoors."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "persona": {
                        "type": "string",
                        "description": (
                            "Worker type. One of: 'construction', 'delivery', "
                            "'child', 'elderly', 'office'."
                        ),
                        "enum": ["construction", "delivery", "child", "elderly", "office"],
                    }
                },
                "required": [],
            },
        }
    },
    {
        "function": {
            "name": "get_zone_detail",
            "description": (
                "Returns hourly UTCI, WBGT, Heat Index, temperature, and humidity for "
                "a specific H3 zone. Use when the user asks about a particular neighbourhood."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "hex_id": {
                        "type": "string",
                        "description": "The H3 cell identifier (e.g. '8842cc69edfffff').",
                    }
                },
                "required": ["hex_id"],
            },
        }
    },
    {
        "function": {
            "name": "simulate_intervention",
            "description": (
                "Returns the modelled before/after outcome of ONE intervention combination, "
                "looked up from the pre-computed physics grid. Levers: shade over outdoor work "
                "areas (shade_pct), extra vegetation in the hottest 25% of zones (greening_pct), "
                "and moving the working day to start at shift_start_hour for a persona. "
                "Values are snapped to the nearest grid point and every snap is reported. "
                "Call once per option you want to compare."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "shade_pct": {"type": "number",
                                  "description": "Percent of direct sun blocked, 0-100."},
                    "greening_pct": {"type": "number",
                                     "description": "Percent more vegetation in the hottest zones, 0-100."},
                    "shift_start_hour": {"type": "integer",
                                         "description": "Hour (0-23) the working day starts."},
                    "persona": {"type": "string",
                                "description": "Who the shift result is for.",
                                "enum": ["construction", "delivery", "child", "elderly"]},
                },
                "required": [],
            },
        }
    },
    {
        "function": {
            "name": "list_intervention_options",
            "description": (
                "Returns EVERY modelled intervention option ranked by effect (cooling rows by "
                "felt-heat reduction, scheduling rows by unsafe-hour reduction), the grid axes, "
                "cost labels for the headline scenarios, and what is NOT modelled. Use this to "
                "compare options, find the most effective or cheapest, or answer 'what should we do'."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        }
    },
    {
        "function": {
            "name": "get_hottest_zones",
            "description": (
                "Returns the hottest neighbourhoods at the focus hour by felt heat (UTCI), one row "
                "per named place, with WBGT, relative risk and each zone's peak hour. Use for "
                "'where should we act first' questions."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "n": {"type": "integer", "description": "How many zones, 1-15. Default 5."},
                },
                "required": [],
            },
        }
    },
    {
        "function": {
            "name": "get_population_exposure",
            "description": (
                "Returns modelled residential population (WorldPop) exposed to heat stress: "
                "totals per UTCI severity band and the most exposed wards. "
                "Use for 'how many people are at risk' or 'population exposed'. "
                "It has NO age, roof-material or occupation breakdown, so it cannot "
                "answer 'how many elderly' or 'who is most vulnerable' -- say so rather "
                "than estimating."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "top_n": {
                        "type": "integer",
                        "description": "How many top exposed wards to return (1-10, default 5).",
                    },
                },
                "required": [],
            },
        }
    },
]
