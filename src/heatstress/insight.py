"""Decision-support layer: what is driving the heat, and what would help.

Everything here is computed from the same physics as the rest of the pipeline.
Nothing is illustrative and nothing is invented -- if an intervention cannot be
modelled with what we have, it is not offered rather than being faked.

WHAT IS DELIBERATELY ABSENT
  * headcounts ("18,420 people at risk"). We have no population data; the
    vulnerability layer is a declared placeholder. A precise-looking number
    would be the single most damaging thing this project could print.
  * water stations / hydration measures. Real and important, but hydration is
    not a thermal quantity -- our model cannot say anything about it, so it is
    not listed as though it could.
"""

from __future__ import annotations

import numpy as np

from . import physiology as ph
from . import psychro as ps
from . import thermal as th

__all__ = [
    "driver_attribution",
    "scenario_shift_hours",
    "scenario_shade",
    "scenario_greening",
    "recommended_actions",
]


def _utci_from(ta, rh, wind, ghi):
    """UTCI for a set of conditions, using the pipeline's own chain."""
    tg = th.globe_temperature_regression(ta, rh, ghi)
    mrt = th.tf_mrt_from_globe(ta, tg, wind)
    return th.tf_utci(ta, rh, wind, mrt)


def driver_attribution(ta, rh, wind, ghi) -> list[dict]:
    """Which inputs are driving the heat stress here, as shares of 100%.

    A local (one-at-a-time) sensitivity analysis: each input is nudged by a
    realistic increment, and the resulting change in UTCI is measured. Shares are
    the absolute effects, normalised.

    Increments are chosen to be comparable in *plausibility*, not in raw units --
    a 1 degC temperature change and a 1% humidity change are not equivalent
    events. We use roughly one standard deviation of hourly variation for each:

        air temperature   1.0 degC
        humidity          5.0 %
        solar radiation   100 W/m2
        wind              1.0 m/s

    HONEST LIMITATION: this is a local derivative at one operating point, not a
    variance decomposition over a season. It answers "what is pushing this hour",
    which is what an operator needs, and not "what explains heat here in
    general".
    """
    base = float(np.mean(_utci_from(ta, rh, wind, ghi)))

    steps = [
        ("Air temperature", float(np.mean(_utci_from(ta + 1.0, rh, wind, ghi)))),
        ("Humidity", float(np.mean(_utci_from(ta, np.clip(rh + 5.0, 1, 100), wind, ghi)))),
        ("Solar radiation", float(np.mean(_utci_from(ta, rh, wind, np.clip(ghi + 100.0, 0, None))))),
        ("Wind", float(np.mean(_utci_from(ta, rh, np.clip(wind + 1.0, 0.5, None), ghi)))),
    ]

    # Magnitude decides the share; SIGN decides how it is described. Wind
    # typically has a large effect that *reduces* stress, and reporting it as a
    # "31% driver of heat" without that sign would be actively misleading.
    effects = [(name, value - base) for name, value in steps]
    total = sum(abs(e) for _, e in effects) or 1.0
    return [
        {
            "driver": name,
            "share": round(100.0 * abs(effect) / total, 1),
            "delta_utci_c": round(effect, 2),
            "direction": "raises" if effect > 0 else "lowers",
        }
        for name, effect in effects
    ]


def _unsafe_hours(wbgt_by_hour, persona, working_hours) -> tuple[float, int]:
    """Person-hours of scheduled work that exceed the safe allowance.

    ``wbgt_by_hour`` maps hour-of-day (0-23) -> WBGT. A scheduled hour with no
    forecast is skipped rather than guessed, so the second return value says how
    many hours actually carried data. That distinction matters at the edges of a
    forecast window, where the first and last local dates are part-days.
    """
    total = 0.0
    scored = 0
    for hour in working_hours:
        wbgt = wbgt_by_hour.get(hour)
        if wbgt is None:
            continue
        allowed = float(ph.safe_work_minutes_per_hour(wbgt, persona))
        total += (60.0 - allowed) / 60.0
        scored += 1
    return total, scored


DEFAULT_SHIFT = list(range(9, 18))          # 09:00-17:00, a conventional day
SHIFTED = [6, 7, 8, 9, 10, 17, 18, 19, 20]  # early start, evening return


def scenario_shift_hours(wbgt_series, personas=None, hours=None) -> dict:
    """Move outdoor work out of the worst hours. Costs nothing but scheduling.

    Fully determined by data we already have: the hourly safe-work allowance is
    computed from ISO 7243 and ACGIH, so moving the same nine hours of work to a
    different part of the day gives an exact answer, not an estimate.

    ``hours`` gives the hour-of-day for each entry of ``wbgt_series``. Pass it
    whenever the series might not be a full midnight-to-midnight day -- a live
    forecast window is requested in UTC and read in local time, so its first and
    last local dates are part-days. Omitting it assumes entry *i* is hour *i*,
    which is exact for a complete day and wrong for anything else. Scheduled
    hours with no data are excluded from both sides of the comparison, and
    ``hours_scored`` reports how many were actually counted.
    """
    personas = personas or ["construction", "delivery"]
    if hours is None:
        hours = range(len(wbgt_series))
    by_hour = {int(h): float(w) for h, w in zip(hours, wbgt_series)}

    before = after = 0.0
    scored_before = scored_after = 0
    for key in personas:
        persona = ph.PERSONAS[key]
        b, sb = _unsafe_hours(by_hour, persona, DEFAULT_SHIFT)
        a, sa = _unsafe_hours(by_hour, persona, SHIFTED)
        before += b
        after += a
        scored_before += sb
        scored_after += sa

    expected = len(personas) * (len(DEFAULT_SHIFT) + len(SHIFTED))
    complete = (scored_before + scored_after) == expected
    return {
        "key": "shift_hours",
        "label": "Shift outdoor work hours",
        "detail": "Move the working day to 06:00-11:00 and 17:00-21:00.",
        "cost": "No cost - scheduling only",
        "unsafe_before": round(before, 1),
        "unsafe_after": round(after, 1),
        "reduction_pct": round(100.0 * (before - after) / before, 0) if before else 0.0,
        "modelled": True,
        "hours_scored": scored_before + scored_after,
        "covers_full_shift": complete,
        "basis": ("Exact: recomputed from the ISO 7243 / ACGIH hourly allowance."
                  if complete else
                  "Partial: the forecast window does not cover every scheduled "
                  "hour, so uncovered hours are excluded from both sides."),
    }


def scenario_shade(ta, rh, wind, ghi, shade_fraction: float = 0.7) -> dict:
    """Provide shade over work areas: cuts the radiant load, not the air heat.

    Modelled by reducing incident shortwave radiation, which is exactly what
    shade does. Air temperature and humidity are unchanged -- shade does not cool
    the air, and pretending otherwise would overstate the benefit.
    """
    base = float(np.mean(_utci_from(ta, rh, wind, ghi)))
    shaded = float(np.mean(_utci_from(ta, rh, wind, ghi * (1.0 - shade_fraction))))
    return {
        "key": "shade",
        "label": "Shade over outdoor work areas",
        "detail": f"Tarpaulin or tree cover blocking {int(shade_fraction * 100)}% of direct sun.",
        "cost": "Low - materials and labour",
        "utci_before": round(base, 1),
        "utci_after": round(shaded, 1),
        "delta_c": round(shaded - base, 1),
        "modelled": True,
        "basis": "Radiation term reduced; air temperature and humidity unchanged.",
    }


def scenario_greening(ta, rh, wind, ghi, intensity, uhi_amplitude_c: float,
                      greening: float = 0.35, target_quantile: float = 0.75) -> dict:
    """Green the hottest zones, and report the effect ON THOSE ZONES.

    A MODEL LIMITATION MADE EXPLICIT: our urban-heat offset is defined relative
    to the city mean, so greening every zone equally cannot lower the average at
    all -- it only narrows the spread. The model can redistribute heat between
    neighbourhoods; it cannot cool the city as a whole. Anything claiming
    otherwise from this pipeline would be an artefact.

    So this models what a real programme actually does: treat the worst zones,
    and measure the benefit where the treatment happened. The city-wide figure is
    deliberately not reported, because here it would always be zero.
    """
    from . import spatial as sp

    intensity = np.asarray(intensity, dtype=float)
    ta = np.asarray(ta, dtype=float)
    rh = np.asarray(rh, dtype=float)

    threshold = float(np.quantile(intensity, target_quantile))
    treated = intensity >= threshold
    if not treated.any():
        treated = np.ones_like(intensity, dtype=bool)

    reduced = intensity.copy()
    reduced[treated] = np.clip(reduced[treated] * (1.0 - greening), 0.0, 1.0)

    before_offset = sp.urban_heat_offset(intensity, uhi_amplitude_c)
    after_offset = sp.urban_heat_offset(reduced, uhi_amplitude_c)

    ta_after = ta + (after_offset - before_offset)
    e = ps.vapour_pressure(ta, rh)
    rh_after = np.clip(100.0 * e / ps.saturation_vapour_pressure(ta_after), 1.0, 100.0)

    base = float(np.mean(_utci_from(ta, rh, wind, ghi)[treated]))
    after = float(np.mean(_utci_from(ta_after, rh_after, wind, ghi)[treated]))
    return {
        "key": "greening",
        "label": "Green the hottest neighbourhoods",
        "detail": (f"Raise vegetation by {int(greening * 100)}% in the hottest "
                   f"{int((1 - target_quantile) * 100)}% of zones "
                   f"({int(treated.sum())} zones)."),
        "cost": "High - multi-year programme",
        "utci_before": round(base, 1),
        "utci_after": round(after, 1),
        "delta_c": round(after - base, 1),
        "zones_treated": int(treated.sum()),
        "scope": "treated zones only",
        "modelled": True,
        "basis": ("Measured across the treated zones only. Our offset is defined "
                  "relative to the city mean, so this model cannot represent "
                  "city-wide cooling -- and it inherits the ASSUMED amplitude, "
                  "making this the least certain of the three."),
    }


def recommended_actions(wbgt_series, labels, personas=None) -> list[dict]:
    """Concrete actions derived from the data, ranked by how much they help.

    These are rules over computed quantities, not an optimiser and not an LLM.
    Each carries the evidence that produced it, so an official can check the
    reasoning rather than trusting a black box.
    """
    personas = personas or ["construction", "delivery", "child", "elderly"]
    actions: list[dict] = []

    worker = ph.PERSONAS["construction"]
    allowances = [float(ph.safe_work_minutes_per_hour(w, worker)) for w in wbgt_series]

    blocked = [i for i, m in enumerate(allowances) if m == 0]
    if blocked:
        first, last = labels[blocked[0]], labels[blocked[-1]]
        actions.append({
            "title": "Stop outdoor work in the peak window",
            "detail": f"No safe outdoor work between {first} and {last}.",
            "impact": "high",
            "evidence": f"{len(blocked)} hours at zero permitted work for heavy labour.",
        })

    safe = [i for i, m in enumerate(allowances) if m >= 60]
    if safe:
        actions.append({
            "title": "Move shifts to the safe window",
            "detail": f"Full-capacity work is possible around {labels[safe[0]]}"
                      f"-{labels[safe[-1]]}.",
            "impact": "high",
            "evidence": f"{len(safe)} hours permit uninterrupted work.",
        })
    else:
        actions.append({
            "title": "No full-capacity hour exists today",
            "detail": "Every hour requires mandatory rest breaks for heavy labour.",
            "impact": "high",
            "evidence": "Peak allowance never reaches 60 minutes per hour.",
        })

    peak = int(np.argmax(wbgt_series))
    actions.append({
        "title": "Concentrate relief at the daily peak",
        "detail": f"Heat stress peaks at {labels[peak]}; position water, shade "
                  f"and rest points before then.",
        "impact": "medium",
        "evidence": f"Peak WBGT {wbgt_series[peak]:.1f} degC at {labels[peak]}.",
    })

    vulnerable = [k for k in personas
                  if ph.PERSONAS[k].vulnerability_offset_c > 0]
    if vulnerable:
        names = ", ".join(ph.PERSONAS[k].label.split(",")[0].lower()
                          for k in vulnerable)
        actions.append({
            "title": "Check on the most vulnerable first",
            "detail": f"Lower safe limits apply to {names}.",
            "impact": "medium",
            "evidence": "Reduced heat tolerance applied as a stated judgement.",
        })

    return actions
