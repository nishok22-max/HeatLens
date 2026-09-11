"""H3 tessellation and the urban-heat offset that makes the map hyper-local.

WHY HEXAGONS AND NOT WARDS
--------------------------
Indian municipal ward shapefiles are a multi-day scavenge with essentially zero
learning value for the question the prototype exists to answer. H3 has no
dependency, tessellates any city in milliseconds, and every cell has identical
area -- so per-cell statistics are directly comparable, which is not true of
wards. Hexes map onto wards in production; the physics is unchanged.

THE URBAN-HEAT OFFSET
---------------------
Coarse reanalysis gives one weather series for the whole city. The intra-city
variation -- the entire premise of the project -- has to come from somewhere else.
We derive it from **urban form**:

    dTa_hex = uhi_amplitude * (intensity_hex - mean_intensity)

where ``intensity`` is a 0-1 index built from built-up density, road density and
(negatively) green and water cover. This is the same signal WUDAPT's Local
Climate Zones encode, computed directly from OpenStreetMap instead of from a
categorical raster.

APPROXIMATION, stated plainly and repeated on stage: this is a *proxy* for the
urban heat island, calibrated to a literature amplitude rather than fitted to
local observations. Production replaces it with satellite land-surface
temperature and a trained residual model -- which is exactly why the source is
pluggable (see ``UrbanFormSource``).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import h3
import numpy as np

__all__ = [
    "build_grid",
    "cell_polygon",
    "COMPOSITE_WEIGHTS",
    "format_coverage",
    "grid_geojson",
    "UrbanFormSource",
    "UrbanIntensity",
    "urban_heat_offset",
]


# ---------------------------------------------------------------------------
# Tessellation
# ---------------------------------------------------------------------------

def build_grid(bbox: dict, resolution: int = 8) -> list[str]:
    """Return the H3 cell indices covering a bounding box.

    Args:
        bbox: mapping with min_lat, max_lat, min_lon, max_lon
        resolution: H3 resolution. 8 gives ~0.74 km2 cells (~0.53 km edge),
            which is finer than a typical Indian municipal ward and coarse
            enough to stay under the ~3k-cell budget in NFR-6.

    Returns cell indices sorted for deterministic output -- the baked GeoJSON
    should not churn between runs.
    """
    poly = h3.LatLngPoly([
        (bbox["min_lat"], bbox["min_lon"]),
        (bbox["min_lat"], bbox["max_lon"]),
        (bbox["max_lat"], bbox["max_lon"]),
        (bbox["max_lat"], bbox["min_lon"]),
    ])
    return sorted(h3.polygon_to_cells(poly, resolution))


def cell_polygon(cell: str) -> list[list[float]]:
    """GeoJSON-ready [lon, lat] ring for one H3 cell, explicitly closed."""
    boundary = h3.cell_to_boundary(cell)
    ring = [[lon, lat] for lat, lon in boundary]
    ring.append(ring[0])
    return ring


def resolve_urban_form(root, slug: str, mode: str = "lst"):
    """Pick the urban-form file to build on, best available first.

    Three levels, in order:

    1. ``urban_form_lst_<city>.json`` -- offsets from **measured** satellite
       surface temperature (script 12).
    2. ``urban_form_<city>.json``     -- the OpenStreetMap composite, whose
       pattern is a hand-weighted guess and whose largest term is dead.
    3. ``urban_form_PLACEHOLDER.json``-- synthetic, for pipeline development.

    ``mode='osm_composite'`` skips level 1 deliberately, which is what makes
    the before/after comparison a one-argument re-run rather than a rebuild.
    Returns ``(path, level)`` where level is 'lst', 'osm' or 'placeholder', so
    callers can label the provenance instead of guessing at it.
    """
    from pathlib import Path

    processed = Path(root) / "data" / "processed"
    lst = processed / f"urban_form_lst_{slug}.json"
    osm = processed / f"urban_form_{slug}.json"
    placeholder = processed / "urban_form_PLACEHOLDER.json"

    if mode != "osm_composite" and lst.exists():
        return lst, "lst"
    if osm.exists():
        return osm, "osm"
    return placeholder, "placeholder"


def zone_area_km2(cell: str) -> float:
    """Area of one H3 cell in km2. Equal for every cell at a resolution, which
    is the whole reason for hexagons over wards (D1)."""
    return float(h3.cell_area(cell, unit="km^2"))


def cell_centroids(cells: list[str]) -> np.ndarray:
    """(N, 2) array of [lat, lon] centroids."""
    return np.array([h3.cell_to_latlng(c) for c in cells], dtype=float)


def grid_geojson(cells: list[str], properties: dict[str, dict] | None = None) -> dict:
    """Assemble cells into a GeoJSON FeatureCollection.

    ``properties`` maps cell index -> property dict, merged into each feature.
    """
    properties = properties or {}
    features = []
    for cell in cells:
        props = {"h3_index": cell}
        props.update(properties.get(cell, {}))
        features.append({
            "type": "Feature",
            "geometry": {"type": "Polygon", "coordinates": [cell_polygon(cell)]},
            "properties": props,
        })
    return {"type": "FeatureCollection", "features": features}


# ---------------------------------------------------------------------------
# Urban form -> temperature offset
# ---------------------------------------------------------------------------

@dataclass
class UrbanIntensity:
    """Per-cell urban-form measures, each normalised to 0-1.

    built:  building footprint area fraction
    roads:  road length density
    green:  vegetation and open-space fraction
    water:  water surface fraction
    """

    built: dict[str, float]
    roads: dict[str, float]
    green: dict[str, float]
    water: dict[str, float]

    def composite(self, cells: list[str]) -> np.ndarray:
        """Combine into a single 0-1 urban-heat intensity index.

        Weights reflect the physical drivers of the urban heat island:
        impervious mass stores and re-radiates heat (built, roads), while
        vegetation cools by evapotranspiration and water by thermal inertia.

        These weights are a judgement, not a fit. They are the first thing a
        production model should learn from data rather than assume.

        KNOWN DEFECT -- READ ``coverage`` BEFORE QUOTING THIS FORMULA.
        A layer with no coverage contributes nothing whatever its weight. On
        the shipped Ahmedabad surface ``built`` is 0.0 in all 392 zones,
        because ``include_buildings`` is off (the Overpass query is the
        heaviest by far), so the **largest weight in the formula contributes
        nothing** and what is actually being mapped is road density minus
        greenery and water. ``coverage()`` reports this per layer, and the
        pipeline prints it, so the defect cannot hide in a docstring. It is
        the strongest single argument for measuring the pattern from
        satellite instead -- see ARCHITECTURE.md D2 (superseded) and D14.
        """
        built = np.array([self.built.get(c, 0.0) for c in cells])
        roads = np.array([self.roads.get(c, 0.0) for c in cells])
        green = np.array([self.green.get(c, 0.0) for c in cells])
        water = np.array([self.water.get(c, 0.0) for c in cells])

        raw = 0.55 * built + 0.25 * roads - 0.30 * green - 0.20 * water
        return _minmax(raw)

    def coverage(self, cells: list[str]) -> dict[str, dict]:
        """Per-layer coverage, so a dead layer is visible rather than implied.

        For each layer: the weight it carries in ``composite``, the fraction
        of cells where it is non-zero, its mean, and ``effective_weight`` --
        the weight actually exercised, i.e. zero where the layer is empty.
        ``dead`` marks a layer present in the formula and absent from the data.
        """
        report = {}
        for name, weight in COMPOSITE_WEIGHTS.items():
            values = np.array([getattr(self, name).get(c, 0.0) for c in cells],
                              dtype=float)
            covered = float(np.mean(values > 0.0)) if values.size else 0.0
            report[name] = {
                "weight": weight,
                "covered_fraction": covered,
                "mean": float(np.mean(values)) if values.size else 0.0,
                "dead": covered == 0.0,
                "effective_weight": 0.0 if covered == 0.0 else weight,
            }
        return report


# The weights in ``UrbanIntensity.composite``, named so the coverage report
# and the formula cannot drift apart. Signs are dropped: what matters here is
# how much of the formula a layer accounts for, not which way it pushes.
COMPOSITE_WEIGHTS = {"built": 0.55, "roads": 0.25, "green": 0.30, "water": 0.20}


def format_coverage(report: dict[str, dict]) -> str:
    """Render ``UrbanIntensity.coverage`` as a table, dead layers called out."""
    lines = [f"  {'layer':<8}{'weight':>8}{'cells>0':>10}{'mean':>8}   note",
             "  " + "-" * 46]
    for name, row in report.items():
        note = "*** DEAD -- contributes nothing ***" if row["dead"] else ""
        lines.append(f"  {name:<8}{row['weight']:>8.2f}"
                     f"{row['covered_fraction'] * 100:>9.0f}%{row['mean']:>8.3f}   {note}")
    dead = [n for n, r in report.items() if r["dead"]]
    if dead:
        live = sum(r["effective_weight"] for r in report.values())
        lines.append(f"  {', '.join(dead)} empty: {live:.2f} of "
                     f"{sum(COMPOSITE_WEIGHTS.values()):.2f} of the formula's "
                     f"weight is actually in play.")
    return "\n".join(lines)


def _minmax(values: np.ndarray) -> np.ndarray:
    """Scale to 0-1, returning all-0.5 if the array is constant."""
    lo, hi = float(np.nanmin(values)), float(np.nanmax(values))
    if not np.isfinite(lo) or not np.isfinite(hi) or hi - lo < 1e-12:
        return np.full_like(values, 0.5, dtype=float)
    return (values - lo) / (hi - lo)


def urban_heat_offset(intensity: np.ndarray, uhi_amplitude_c: float = 3.0) -> np.ndarray:
    """Convert a 0-1 urban intensity index into an air-temperature offset, degC.

    Centred on the city mean so the offsets sum to ~zero: we are redistributing
    the coarse forecast across the city, not inventing extra heat. A cell at the
    hottest end of the index sits roughly ``+uhi_amplitude/2`` above the city
    mean and the greenest sits the same distance below.

    ``uhi_amplitude_c`` is the *air* temperature UHI range. Indian cities report
    canopy-layer UHI of roughly 2-5 degC; 3.0 degC is a deliberately conservative
    default. Surface UHI is much larger -- do not confuse the two.
    """
    return (np.asarray(intensity, dtype=float) - float(np.nanmean(intensity))) * uhi_amplitude_c


class UrbanFormSource(Protocol):
    """Pluggable provider of per-cell urban form.

    The prototype ships ``sources.osm.OSMUrbanForm``. Production adds a Landsat
    land-surface-temperature source; because both satisfy this interface,
    swapping them changes nothing downstream of ``spatial``.
    """

    def fetch(self, bbox: dict, cells: list[str]) -> UrbanIntensity:
        ...
