"""Persona-level heat strain: who can do what, for how long, in this cell.

This is the layer that answers the problem statement's actual demand -- "what the
weather will *do*" -- rather than what it will be. A single WBGT value is not an
answer: 32 degC WBGT is a manageable afternoon for a seated office worker and a
medical emergency for someone laying bricks.

WHY NOT ISO 7933 PHS
--------------------
The plan called for the ISO 7933 Predicted Heat Strain model, which integrates a
body heat balance to give a core-temperature trajectory. It lives in
``pythermalcomfort``.

An earlier version of this docstring said that package could not be imported
because Windows Application Control blocked a compiled ``scipy.optimize`` DLL.
That is no longer true: ``scipy 1.18.1``, ``scipy.optimize`` and
``pythermalcomfort 4.4.2`` all import cleanly here. The choice below is therefore
a choice, not a constraint -- and it still holds.

This module uses the other standard route to the same operational answer:
**ISO 7243 WBGT reference limits** combined with **ACGIH/NIOSH work-rest
allocation**. These are lookup tables rather than a differential equation, which
means:

  + no solver and no convergence failure can happen mid-demo
  + they are what occupational hygienists and labour inspectors actually use,
    so the output maps directly onto a decision an official can sign
  - no core-temperature *curve*, only a work/rest allocation

That trade is the right way round for this prototype. Restoring PHS is a V1 item.

EVERY THRESHOLD HERE IS A PUBLISHED STANDARD except the vulnerability offsets,
which are explicitly flagged as a judgement.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

__all__ = [
    "MetabolicClass",
    "Persona",
    "PERSONAS",
    "wbgt_limit",
    "safe_work_minutes_per_hour",
    "strain_ratio",
    "assess",
]


# ---------------------------------------------------------------------------
# Metabolic classes -- ISO 7243 / ISO 8996
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class MetabolicClass:
    name: str
    watts: float          # representative total metabolic rate
    iso_index: int        # ISO 7243 class 0-4


RESTING = MetabolicClass("resting", 105.0, 0)
LOW = MetabolicClass("low", 180.0, 1)
MODERATE = MetabolicClass("moderate", 300.0, 2)
HIGH = MetabolicClass("high", 415.0, 3)
VERY_HIGH = MetabolicClass("very high", 520.0, 4)

# ISO 7243 reference WBGT limit values, degC, indexed by metabolic class 0-4.
# Two regimes: acclimatised and unacclimatised workers.
ISO7243_LIMIT_ACCLIMATISED = [33.0, 30.0, 28.0, 26.0, 25.0]
ISO7243_LIMIT_UNACCLIMATISED = [32.0, 29.0, 26.0, 23.0, 20.0]

# ACGIH TLV work-rest allocation, degC WBGT, acclimatised workers.
# Row = work fraction of each hour; column = metabolic class 1-3 (low/mod/high).
# Read as: at or below this WBGT, that work fraction is permissible.
ACGIH_WORK_REST = {
    1.00: {1: 30.0, 2: 26.7, 3: 25.0},
    0.75: {1: 30.6, 2: 28.0, 3: 25.9},
    0.50: {1: 31.4, 2: 29.4, 3: 27.9},
    0.25: {1: 32.2, 2: 31.1, 3: 30.0},
}

# Unacclimatised workers are held to a lower ceiling. ACGIH publishes a separate
# action-limit table; the uniform offset here is a simplification of it.
UNACCLIMATISED_OFFSET_C = 2.5


# ---------------------------------------------------------------------------
# Personas
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Persona:
    """A body, with the attributes that decide how heat lands on it."""

    key: str
    label: str
    metabolic: MetabolicClass
    acclimatised: bool = True
    outdoor: bool = True
    #: Extra degC subtracted from the WBGT limit for reduced physiological
    #: reserve. JUDGEMENT, NOT A STANDARD -- ISO 7243 addresses fit working
    #: adults and does not cover age, medication or chronic illness. Displayed
    #: with this caveat attached wherever it is used.
    vulnerability_offset_c: float = 0.0
    notes: str = ""

    def limit_c(self) -> float:
        return wbgt_limit(self.metabolic, self.acclimatised) - self.vulnerability_offset_c


PERSONAS: dict[str, Persona] = {
    "construction": Persona(
        key="construction",
        label="Outdoor construction worker",
        metabolic=HIGH,
        acclimatised=True,
        outdoor=True,
        notes="Heavy sustained work in direct sun. The archetypal Indian "
              "heat-exposed informal worker.",
    ),
    "delivery": Persona(
        key="delivery",
        label="Delivery rider",
        metabolic=MODERATE,
        acclimatised=True,
        outdoor=True,
        notes="Moderate continuous work, some convective relief from riding, "
              "but no shade and no control over timing.",
    ),
    "elderly": Persona(
        key="elderly",
        label="Woman, 78, indoors, on blood-pressure medication",
        metabolic=RESTING,
        acclimatised=True,
        outdoor=False,
        vulnerability_offset_c=4.0,
        notes="At rest, but with blunted thermoregulation: reduced sweat "
              "capacity, diminished thirst, and diuretics promoting "
              "dehydration. The offset is a judgement, not a standard.",
    ),
    "child": Persona(
        key="child",
        label="School child, outdoors at midday",
        metabolic=LOW,
        acclimatised=False,
        outdoor=True,
        vulnerability_offset_c=2.0,
        notes="Higher surface-area-to-mass ratio and lower sweat rate than an "
              "adult; also unlikely to self-regulate exposure.",
    ),
}


# ---------------------------------------------------------------------------
# Assessment
# ---------------------------------------------------------------------------

def wbgt_limit(metabolic: MetabolicClass, acclimatised: bool = True) -> float:
    """ISO 7243 reference WBGT limit for a metabolic class, degC."""
    table = (ISO7243_LIMIT_ACCLIMATISED if acclimatised
             else ISO7243_LIMIT_UNACCLIMATISED)
    return table[metabolic.iso_index]


def safe_work_minutes_per_hour(wbgt_c, persona: Persona) -> float:
    """Permissible working minutes in each hour, 0-60. ACGIH TLV allocation.

    Returns 60 when the environment is below the continuous-work threshold, and
    steps down through the 75/50/25% regimens as WBGT rises. Zero means no work
    should be scheduled at all -- rest only, in shade, with fluids.

    For resting personas the concept of a work regimen does not apply; the
    result is a rest-tolerance proxy on the same 0-60 scale.
    """
    wbgt = np.asarray(wbgt_c, dtype=float)

    # Map any metabolic class onto the 1-3 columns the ACGIH table covers.
    column = int(np.clip(persona.metabolic.iso_index, 1, 3))
    offset = (0.0 if persona.acclimatised else UNACCLIMATISED_OFFSET_C)
    offset += persona.vulnerability_offset_c

    minutes = np.zeros_like(wbgt, dtype=float)
    # Walk from the most permissive regimen down; first satisfied wins.
    for fraction in (1.00, 0.75, 0.50, 0.25):
        threshold = ACGIH_WORK_REST[fraction][column] - offset
        minutes = np.where((minutes == 0.0) & (wbgt <= threshold),
                           fraction * 60.0, minutes)
    return float(minutes) if minutes.ndim == 0 else minutes


def strain_ratio(wbgt_c, persona: Persona) -> float:
    """WBGT as a fraction of this persona's limit. 1.0 means at the limit.

    A single comparable number across very different bodies: it is what lets the
    dashboard say "the same cell is 0.82 for a delivery rider and 1.19 for the
    78-year-old upstairs".
    """
    return np.asarray(wbgt_c, dtype=float) / persona.limit_c()


def assess(wbgt_c: float, persona: Persona) -> dict:
    """Full per-persona verdict for one WBGT value.

    Returns a dict ready to drop into the cell-detail panel.
    """
    minutes = float(safe_work_minutes_per_hour(wbgt_c, persona))
    ratio = float(strain_ratio(wbgt_c, persona))
    limit = persona.limit_c()

    if ratio >= 1.15:
        verdict, severity = "Unsafe -- stop exposure", "critical"
    elif ratio >= 1.0:
        verdict, severity = "Above limit -- rest only", "severe"
    elif ratio >= 0.9:
        verdict, severity = "Near limit -- mandatory rest breaks", "high"
    elif ratio >= 0.75:
        verdict, severity = "Elevated -- hydrate and pace", "moderate"
    else:
        verdict, severity = "Within tolerance", "low"

    return {
        "persona": persona.key,
        "label": persona.label,
        "wbgt_c": round(float(wbgt_c), 2),
        "limit_c": round(limit, 2),
        "strain_ratio": round(ratio, 3),
        "safe_work_min_per_hour": round(minutes, 0),
        "verdict": verdict,
        "severity": severity,
        "basis": ("ISO 7243 limit + ACGIH work-rest allocation"
                  + ("; includes a non-standard vulnerability offset of "
                     f"{persona.vulnerability_offset_c:.1f} degC"
                     if persona.vulnerability_offset_c else "")),
    }
