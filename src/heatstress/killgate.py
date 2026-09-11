"""The project's own go/no-go verdict, as a function instead of a print statement.

WHY THIS MODULE EXISTS
----------------------
The kill gate is the single decision the whole prototype was built to make: is
intra-city thermal-stress variation large enough to lead with a map? Until now
that logic lived inside ``scripts/05_kill_gate.py``, interleaved with printing,
and was therefore untestable and untested.

The current margin is **0.88 degC** -- a 3.88 degC spread against a 3.0 degC
threshold. Phase 5 replaces the assumed urban-heat amplitude with a measured
satellite pattern, which changes that spread. Without a guard, such a change
could silently flip the project's own verdict and nobody would notice until
someone read the console output on stage. So the verdict is extracted and
tested *before* anything touches the temperature offset.

WHAT THE VERDICT IS COMPUTED ON
-------------------------------
The strongest thermal-stress spread at the focus hour, taken as the larger of
the WBGT and UTCI spreads -- not air temperature, which is an input rather than
a result, and not the heat index, which is a shade-only US measure. Which of
WBGT and UTCI wins is itself a finding (see ``scripts/05_kill_gate.py`` on
damping), so the winner is reported alongside the number.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

__all__ = ["PROCEED", "MARGINAL", "PIVOT", "Verdict", "spread", "verdict",
           "focus_index", "verdict_from_cube"]

PROCEED = "PROCEED"
MARGINAL = "MARGINAL"
PIVOT = "PIVOT"

_HEADLINES = {
    PROCEED: "Geography is the story; lead with the map.",
    MARGINAL: "Real but not dramatic. Lead with humidity + physiology; "
              "keep the map as support, not as the headline.",
    PIVOT: "The spatial premise is too weak to lead with. Fall back to "
           "'same place, different bodies': persona divergence and the "
           "night-recovery chart.",
}


@dataclass(frozen=True)
class Verdict:
    """The decision, the number behind it, and how much room there was.

    decision:   PROCEED / MARGINAL / PIVOT
    spread_c:   the strongest thermal-stress spread, degC
    driver:     which index produced it -- "WBGT" or "UTCI"
    margin_c:   spread minus the threshold it cleared. Negative when the
                verdict is PIVOT, i.e. how far short it fell.
    """

    decision: str
    spread_c: float
    driver: str
    wbgt_spread_c: float
    utci_spread_c: float
    proceed_spread_c: float
    pivot_spread_c: float

    @property
    def margin_c(self) -> float:
        threshold = (self.proceed_spread_c if self.decision == PROCEED
                     else self.pivot_spread_c)
        return self.spread_c - threshold

    @property
    def headline(self) -> str:
        return _HEADLINES[self.decision]


def spread(values) -> float:
    """Max minus min, ignoring NaN. The plain definition, named once."""
    array = np.asarray(values, dtype=float)
    return float(np.nanmax(array) - np.nanmin(array))


def verdict(wbgt_spread_c: float, utci_spread_c: float,
            proceed_spread_c: float, pivot_spread_c: float) -> Verdict:
    """Apply the two declared thresholds to the strongest spread.

    Thresholds come from ``config/<city>.yaml`` and were written down before
    the number was known -- which is the only kind of threshold that means
    anything. ``proceed_spread_c`` must not sit below ``pivot_spread_c``;
    each band is inclusive at its lower edge.
    """
    if proceed_spread_c < pivot_spread_c:
        raise ValueError(
            f"proceed threshold {proceed_spread_c} is below the pivot "
            f"threshold {pivot_spread_c}; the bands would be inverted"
        )

    wbgt_spread_c, utci_spread_c = float(wbgt_spread_c), float(utci_spread_c)
    if utci_spread_c >= wbgt_spread_c:
        best, driver = utci_spread_c, "UTCI"
    else:
        best, driver = wbgt_spread_c, "WBGT"

    if best >= proceed_spread_c:
        decision = PROCEED
    elif best >= pivot_spread_c:
        decision = MARGINAL
    else:
        decision = PIVOT

    return Verdict(decision=decision, spread_c=best, driver=driver,
                   wbgt_spread_c=wbgt_spread_c, utci_spread_c=utci_spread_c,
                   proceed_spread_c=float(proceed_spread_c),
                   pivot_spread_c=float(pivot_spread_c))


def focus_index(timestamps, focus_date: str, focus_hour_ist: int) -> int:
    """Row index of the focus hour in the stored cube's timestamp array.

    Raises rather than silently scoring the wrong hour: a kill gate evaluated
    at 03:00 would report a spread near zero and read as a genuine PIVOT.
    """
    prefix = f"{focus_date} {focus_hour_ist:02d}"
    for i, stamp in enumerate(timestamps):
        if str(stamp).startswith(prefix):
            return i
    raise LookupError(f"{prefix}:00 IST is not in the stored hours")


def verdict_from_cube(cube, focus_date: str, focus_hour_ist: int,
                      proceed_spread_c: float, pivot_spread_c: float) -> Verdict:
    """Score a stored ``indices_<city>.npz`` cube (or any mapping like one).

    This is the form the test suite pins: it reads the committed arrays, so a
    change to the urban-heat offset that would flip the verdict fails a test
    instead of surprising someone mid-demo.
    """
    idx = focus_index(cube["timestamps_ist"], focus_date, focus_hour_ist)
    return verdict(spread(cube["wbgt"][idx]), spread(cube["utci"][idx]),
                   proceed_spread_c, pivot_spread_c)
