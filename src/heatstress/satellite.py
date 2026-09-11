"""The satellite data contract, shared by every source that can supply it.

WHY THIS IS SEPARATE FROM THE SOURCE MODULES
--------------------------------------------
Two instruments can measure the same thing. ``sources/gee.py`` reduces Landsat
8/9 at 30 m on Google's servers and needs an authorised Earth Engine account;
``sources/modis_ornl.py`` pulls MODIS at 1 km from a public endpoint that needs
no credential at all. Everything downstream -- the anomaly, the offsets, the
kill gate, the map -- must not care which one produced the file.

So the record schema, the city-mean rule, the unit trap and the coverage report
live here, and each source module's only job is to turn its own API into
``{h3_index: {...}}`` rows.

THE ONE RULE WORTH READING TWICE
--------------------------------
**The city mean is computed over observed zones only.** Every zone's anomaly is
measured against it, and the anomaly is what the entire product rests on. Let a
zone with no measurement contribute a zero, or drop it after the mean is taken,
and every other zone in the city is quietly shifted.
"""

from __future__ import annotations

import numpy as np

__all__ = [
    "OBSERVED",
    "INSUFFICIENT_PIXELS",
    "FILLED_NEIGHBOUR",
    "PROVENANCE_VALUES",
    "assert_surface_temperature_plausible",
    "build_cells",
    "add_night_layer",
    "coverage_summary",
    "chunked",
    "cross_check_blocks",
    "rank_agreement",
]

# Provenance, as a label rather than a boolean: a true/false "is this real?"
# cannot say *how* a filled zone was filled, and Phase 5C adds a fourth value
# ("modelled") when the Ridge fit starts supplying gaps.
OBSERVED = "observed"
INSUFFICIENT_PIXELS = "insufficient_pixels"
FILLED_NEIGHBOUR = "filled_neighbour"
PROVENANCE_VALUES = (OBSERVED, INSUFFICIENT_PIXELS, FILLED_NEIGHBOUR)

# Plausible land-surface temperature, deliberately wide. This catches unit
# mistakes, not warm afternoons: bare tarmac in Ahmedabad in May genuinely
# reaches the high 50s, and surface temperature is not air temperature.
PLAUSIBLE_LST_C = (-20.0, 80.0)


def assert_surface_temperature_plausible(values, label: str = "LST") -> None:
    """Refuse land-surface temperatures outside a physically possible range.

    UNIT TRAP, deliberately pinned -- the satellite analogue of the wind-speed
    trap in ``openmeteo.py``. Every satellite thermal product ships scaled
    integers, and every one uses a different scale: Landsat is
    ``0.00341802 * DN + 149 K``, MODIS is ``0.02 * DN`` kelvin. Forget a scale
    factor and you get thousands of degrees; forget an offset and you get minus
    a hundred; forget the kelvin conversion and everything is 273 too high.
    All three are silent, and all three produce a beautiful, wrong map.
    """
    array = np.asarray(values, dtype=float)
    finite = array[np.isfinite(array)]
    if finite.size == 0:
        raise ValueError(f"{label}: no finite values at all")
    lo, hi = float(finite.min()), float(finite.max())
    if lo < PLAUSIBLE_LST_C[0] or hi > PLAUSIBLE_LST_C[1]:
        raise ValueError(
            f"{label} spans {lo:.1f} to {hi:.1f} degC, outside the plausible "
            f"{PLAUSIBLE_LST_C[0]:.0f}..{PLAUSIBLE_LST_C[1]:.0f} degC. Check "
            "the scale factor, the offset and the kelvin conversion -- surface "
            "temperature must be in Celsius here."
        )


def build_cells(rows: dict[str, dict], cells: list[str],
                min_valid_px: int) -> tuple[dict[str, dict], float]:
    """Assemble per-zone records and the city mean, with provenance on each.

    ``rows`` maps H3 index -> whatever the source measured for that zone. A
    zone qualifies as observed when it has a finite temperature backed by at
    least ``min_valid_px`` valid observations; everything else is labelled and
    left empty for the model to fill.
    """
    observed = {}
    for cell in cells:
        row = rows.get(cell) or {}
        lst = row.get("lst_c")
        valid = int(row.get("valid_px") or 0)
        if lst is not None and np.isfinite(lst) and valid >= min_valid_px:
            observed[cell] = float(lst)

    if not observed:
        raise ValueError(
            f"no zone reached {min_valid_px} valid observations; the composite "
            "is unusable. Widen the year or month window, or relax the cloud "
            "and quality screens."
        )

    assert_surface_temperature_plausible(list(observed.values()))
    city_mean = float(np.mean(list(observed.values())))

    records = {}
    for cell in cells:
        row = rows.get(cell) or {}
        is_observed = cell in observed
        record = {
            "lst_c": round(observed[cell], 3) if is_observed else None,
            "lst_anomaly_c": (round(observed[cell] - city_mean, 3)
                              if is_observed else None),
            "valid_px": int(row.get("valid_px") or 0),
            "provenance": OBSERVED if is_observed else INSUFFICIENT_PIXELS,
        }
        for key, digits in (("ndvi", 4), ("ndbi", 4), ("built_s", 4),
                            ("population", 1)):
            if key in row:
                record[key] = _round_or_none(row.get(key), digits)
        records[cell] = record
    return records, city_mean


def add_night_layer(records: dict[str, dict],
                    rows: dict[str, dict]) -> float | None:
    """Merge night-time surface temperature into existing records.

    Night is not a nice-to-have here. This project's strongest finding is that
    the May 2010 deaths tracked six consecutive nights that never dropped below
    26.7 degC -- bodies never got a chance to recover. Which neighbourhoods
    stay hot *at night* is therefore a different and more important question
    than which get hottest at noon, and the two patterns are not the same: a
    concrete-and-tarmac district releases stored heat all night, while bare
    ground on the periphery dumps it within an hour of sunset.

    Returns the night-time city mean, or None if no zone had a night value.
    """
    night = {}
    for cell, record in records.items():
        value = (rows.get(cell) or {}).get("lst_night_c")
        if value is not None and np.isfinite(value):
            night[cell] = float(value)

    if not night:
        return None

    assert_surface_temperature_plausible(list(night.values()), "night LST")
    city_mean = float(np.mean(list(night.values())))
    for cell, record in records.items():
        value = night.get(cell)
        record["lst_night_c"] = None if value is None else round(value, 3)
        record["lst_night_anomaly_c"] = (None if value is None
                                         else round(value - city_mean, 3))
    return city_mean


def coverage_summary(records: dict[str, dict], min_fraction: float) -> dict:
    """Observed-zone coverage, and whether it clears the declared minimum."""
    total = len(records)
    observed = sum(1 for r in records.values() if r["provenance"] == OBSERVED)
    fraction = observed / total if total else 0.0
    return {
        "cells_total": total,
        "cells_observed": observed,
        "cells_insufficient_pixels": total - observed,
        "observed_fraction": round(fraction, 4),
        "min_observed_fraction": min_fraction,
        "passes": fraction >= min_fraction,
    }


def chunked(items: list, size: int) -> list[list]:
    """Split a list into fixed-size chunks; each becomes one cached request."""
    if size < 1:
        raise ValueError("chunk size must be at least 1")
    return [items[i:i + size] for i in range(0, len(items), size)]


def rank_agreement(a, b) -> float:
    """Spearman rank correlation, numpy only -- no scipy, no new dependency.

    Used for one job: checking that a second, independent instrument ranks the
    city the same way the primary one does. Rank rather than value, because two
    satellites measure at different times of day, at different resolutions,
    through different atmospheres -- so their *numbers* are not expected to
    match and only their *ordering* is meaningful.
    """
    x, y = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    keep = np.isfinite(x) & np.isfinite(y)
    x, y = x[keep], y[keep]
    if x.size < 3:
        return float("nan")
    rx, ry = _ranks(x), _ranks(y)
    if np.std(rx) == 0 or np.std(ry) == 0:
        return float("nan")
    return float(np.corrcoef(rx, ry)[0, 1])


def cross_check_blocks(records: dict[str, dict], other: dict[str, float],
                       block_resolution: int, instrument: str) -> dict:
    """Does a second, independent instrument rank the city the same way?

    Both fields are rolled up to parent hexagons and compared by rank. The
    check runs at block scale rather than per zone because two satellites with
    different pixel grids disagree about exactly where a boundary falls, and
    that disagreement is not the thing being tested -- whether they see the
    same city is.

    Reported whatever it says. A weak agreement is a finding about the data,
    not a reason to quietly drop the check: the OpenStreetMap formula this
    replaces had no way of being shown wrong at all.
    """
    import h3

    primary: dict[str, list[float]] = {}
    secondary: dict[str, list[float]] = {}
    for cell, record in records.items():
        if record["provenance"] != OBSERVED or cell not in other:
            continue
        block = h3.cell_to_parent(cell, block_resolution)
        primary.setdefault(block, []).append(record["lst_c"])
        secondary.setdefault(block, []).append(float(other[cell]))

    blocks = sorted(primary)
    a = [float(np.mean(primary[b])) for b in blocks]
    b_ = [float(np.mean(secondary[b])) for b in blocks]
    return {
        "instrument": instrument,
        "block_resolution": block_resolution,
        "n_blocks": len(blocks),
        "rank_agreement": (None if not blocks
                           else _round_or_none(rank_agreement(a, b_), 3)),
        "blocks": {block: {"primary_lst_c": round(x, 2),
                           "cross_check_lst_c": round(y, 2)}
                   for block, x, y in zip(blocks, a, b_)},
        "note": "independent instrument, ranks only -- never mixed in",
    }


def _ranks(values: np.ndarray) -> np.ndarray:
    """Ranks with ties averaged, which is what Spearman requires."""
    order = np.argsort(values, kind="mergesort")
    ranks = np.empty(values.size, dtype=float)
    ranks[order] = np.arange(values.size, dtype=float)
    for value in np.unique(values):
        tied = values == value
        if tied.sum() > 1:
            ranks[tied] = ranks[tied].mean()
    return ranks


def _round_or_none(value, digits: int):
    if value is None:
        return None
    value = float(value)
    return round(value, digits) if np.isfinite(value) else None
