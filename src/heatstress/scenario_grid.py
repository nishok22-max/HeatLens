"""Pre-computed what-if results, so the simulator answers offline.

WHY A GRID AND NOT AN API CALL
------------------------------
The dashboard must work from a local file with the wifi off (NFR-1), and
``IMPLEMENTATION_PLAN.md`` §5.1 rule 4 spells out what that costs: *"no new
network call at runtime, no reimplementation of the physics in TypeScript,
scenario grids pre-baked rather than computed live"*. All three clauses point at
the same design -- run every combination the user can ask for **during the
bake**, ship the answers as data, and let the browser do a table lookup.

So the intelligence in the what-if simulator is not in the browser. Every number
it displays was computed here, by the same ``insight.py`` functions that produce
the three headline scenario cards.

WHY TWO GRIDS INSTEAD OF ONE
----------------------------
The three levers do not share an outcome measure, and forcing them into one
table would invent relationships that do not exist:

  * shade and greening both change the **felt temperature at the focus hour**,
    and they compose -- greening cools the air, shade cuts the radiant load on
    top of that. They belong on one surface, crossed.
  * shifting work hours changes **how many hours of the day are unsafe**, which
    is a different quantity entirely and is not comparable to a temperature.
    It is crossed with persona instead, because a child's safe limit is not a
    construction worker's.

AN EARLIER START IS NOT AUTOMATICALLY BETTER
--------------------------------------------
``insight.shift_window`` moves the whole split shift, so an earlier start also
pulls the **evening** block earlier -- towards the afternoon rather than away
from it. Whether the early-morning gain outweighs that loss depends on the shape
of the day: on the May 2010 Ahmedabad data the earliest start wins clearly, but
on a day that never cools after dark the latest start does. Which is the entire
argument for computing this grid instead of hardcoding a "start at 6 a.m."
recommendation and calling it modelled.

NOTHING IS INTERPOLATED
-----------------------
A request between grid points snaps to the nearest row and says so. Smoothing
between rows would manufacture a plausible-looking number the physics never
produced -- the same failure ``DECISIONS.md`` D21 bans for satellite pixels.
"""

from __future__ import annotations

import numpy as np

from . import insight as ins

__all__ = [
    "SHADE_AXIS",
    "GREENING_AXIS",
    "SHIFT_START_AXIS",
    "PERSONA_AXIS",
    "build_grid",
    "nearest",
]

# The axes a user can ask about. Deliberately coarse: these are the values a
# municipal programme would actually choose between, and every extra point is a
# row shipped to every visitor.
SHADE_AXIS = [0.0, 0.3, 0.5, 0.7, 0.9]
GREENING_AXIS = [0.0, 0.2, 0.35, 0.5]
SHIFT_START_AXIS = [4, 5, 6, 7, 8, 9]
PERSONA_AXIS = ["construction", "delivery", "child", "elderly"]


def nearest(value: float, axis: list) -> tuple:
    """Snap a requested value onto an axis. Returns (snapped, was_snapped).

    Reported rather than hidden: a user who asks for 80% shade and is answered
    with the 90% row must be told, or the number is quietly not the one they
    asked for.
    """
    snapped = min(axis, key=lambda a: abs(a - value))
    return snapped, abs(snapped - value) > 1e-9


def build_grid(ta, rh, wind, ghi, intensity, uhi_amplitude_c: float,
               wbgt_series, hours=None) -> dict:
    """Run every askable combination through the real physics.

    ``ta``/``rh``/``wind``/``ghi`` are the focus-hour fields across zones;
    ``wbgt_series`` is the day's hourly WBGT with ``hours`` giving each entry's
    hour of day (required whenever the window may be a part-day -- see
    ``insight.scenario_shift_hours``).
    """
    # The one true baseline, computed once and kept unrounded. Rounding before
    # subtracting is how the grid and the headline cards drifted apart by
    # 0.1 degC in the first draft -- small, but a table and a card showing
    # different numbers for the same intervention is exactly the kind of
    # discrepancy that costs an audience its trust.
    baseline = float(np.mean(ins._utci_from(ta, rh, wind, ghi)))

    cooling = []
    for greening in GREENING_AXIS:
        # Greening cools the air first; shade then acts on the radiant load of
        # that already-cooled air. Applying them in the other order, or adding
        # two separately-computed deltas, would double-count the interaction.
        if greening > 0.0:
            green = ins.scenario_greening(ta, rh, wind, ghi, intensity,
                                          uhi_amplitude_c, greening=greening)
            ta_g, rh_g = _greened_fields(ta, rh, intensity, uhi_amplitude_c,
                                         greening)
            zones_treated = green["zones_treated"]
        else:
            ta_g, rh_g, zones_treated = ta, rh, 0

        for shade in SHADE_AXIS:
            # Same call the headline card makes, so the physics path is
            # identical; the numbers are then derived from the unrounded mean
            # rather than from the card's already-rounded output.
            after = float(np.mean(ins._utci_from(
                ta_g, rh_g, wind, ghi * (1.0 - shade))))
            cooling.append({
                "shade": shade,
                "greening": greening,
                "zones_treated": zones_treated,
                "utci_before": round(baseline, 1),
                "utci_after": round(after, 1),
                "delta_c": round(after - baseline, 1),
            })

    scheduling = []
    for start in SHIFT_START_AXIS:
        window = ins.shift_window(start)
        for persona in PERSONA_AXIS:
            row = ins.scenario_shift_hours(wbgt_series, personas=[persona],
                                           hours=hours, shift=window)
            scheduling.append({
                "shift_start": start,
                "persona": persona,
                "window": ins._describe_shift(window),
                "unsafe_before": row["unsafe_before"],
                "unsafe_after": row["unsafe_after"],
                "reduction_pct": row["reduction_pct"],
                "covers_full_shift": row["covers_full_shift"],
            })

    return {
        "axes": {
            "shade": SHADE_AXIS,
            "greening": GREENING_AXIS,
            "shift_start": SHIFT_START_AXIS,
            "persona": PERSONA_AXIS,
        },
        "cooling": cooling,
        "scheduling": scheduling,
        "basis": ("Every row recomputed through the same ISO 7243 / ACGIH and "
                  "UTCI chain as the headline scenarios. Values between rows "
                  "snap to the nearest row and say so; nothing is interpolated."),
    }


def _greened_fields(ta, rh, intensity, uhi_amplitude_c: float, greening: float):
    """The air temperature and humidity left behind after greening.

    Mirrors ``insight.scenario_greening`` exactly -- treat the hottest quartile,
    recompute the urban-heat offset, and carry **vapour pressure** across rather
    than relative humidity. Holding RH fixed would invent moisture in the zones
    that just cooled, which is the same error ARCHITECTURE.md §2.1 exists to
    prevent.
    """
    from . import psychro as ps
    from . import spatial as sp

    intensity = np.asarray(intensity, dtype=float)
    threshold = float(np.quantile(intensity, 0.75))
    treated = intensity >= threshold
    if not treated.any():
        treated = np.ones_like(intensity, dtype=bool)

    reduced = intensity.copy()
    reduced[treated] = np.clip(reduced[treated] * (1.0 - greening), 0.0, 1.0)

    before = sp.urban_heat_offset(intensity, uhi_amplitude_c)
    after = sp.urban_heat_offset(reduced, uhi_amplitude_c)
    ta_after = np.asarray(ta, dtype=float) + (after - before)
    e = ps.vapour_pressure(np.asarray(ta, dtype=float), np.asarray(rh, dtype=float))
    rh_after = np.clip(100.0 * e / ps.saturation_vapour_pressure(ta_after),
                       1.0, 100.0)
    return ta_after, rh_after
