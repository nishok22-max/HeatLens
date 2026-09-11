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
]
