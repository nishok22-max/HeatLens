"""Earth Engine: satellite surface temperature, greenness, built surface, people.

WHY THIS REPLACES THE OPENSTREETMAP FORMULA
-------------------------------------------
Today's spatial pattern is ``0.55*built + 0.25*roads - 0.30*green - 0.20*water``
multiplied by an assumed 3.0 degC. Two stacked assumptions -- and the first is
broken: ``built`` is 0.0 in all 392 zones, so the largest weight in the formula
contributes nothing and what is really being mapped is road density. See
``spatial.UrbanIntensity.composite`` and ARCHITECTURE.md D2 (superseded by D14).

The satellite path measures the pattern instead::

    Landsat thermal band -> surface temperature per zone
                         -> anomaly = zone temp - city mean      [MEASURED]
                         -> air offset = alpha * anomaly         [alpha still ASSUMED]

Exactly one number stays assumed: ``alpha``, how much surface heat becomes air
heat, which cannot be fitted without ground weather stations we do not have. The
``ASSUMED`` provenance row survives -- with its subject narrowed from the whole
magnitude to one coefficient.

THE FIVE RULES THIS MODULE OBEYS
--------------------------------
1. **Earth Engine is initialised inside a function, never at import.** The
   6-hourly job imports this package and runs the tests; an import-time
   ``ee.Initialize()`` would break it on a machine with no credentials. Every
   test in ``tests/test_gee.py`` exercises the pure functions on a synthetic
   payload and touches no network.
2. **Every chunk of zones is cached to disk**, keyed by a hash of the request,
   so an interrupted export resumes for free and a re-run makes zero network
   calls -- the pattern ``sources/osm.py`` already uses (NFR-1).
3. **Units are asserted, not assumed.** Landsat Collection 2 surface
   temperature ships as scaled integers; forgetting the scale factor yields
   about 3000 degC, and forgetting the offset about -150 degC. Both are caught
   here, in the same spirit as the wind-unit trap in ``openmeteo.py``.
4. **Fewer than ``min_scenes`` usable scenes aborts the export** rather than
   shipping a two-scene composite dressed up as a climatology.
5. **Every zone carries where its number came from** -- ``observed`` or
   ``insufficient_pixels`` -- instead of one misleading true/false flag. Thin
   zones are excluded from the fit and filled in by the model in Phase 5C, and
   the map can hatch them.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import h3
import numpy as np

# The record schema, the city-mean rule, the unit trap and the coverage report
# are source-agnostic and live in ``heatstress.satellite``, so that this module
# and ``modis_ornl.py`` cannot drift into producing subtly different files.
# Re-exported here because callers of a source should not need to know that.
from ..satellite import (  # noqa: F401
    INSUFFICIENT_PIXELS,
    OBSERVED,
    add_night_layer,
    assert_surface_temperature_plausible,
    build_cells,
    coverage_summary,
    rank_agreement,
)
from ..satellite import chunked as _chunked

__all__ = [
    "GEESurfaceSource",
    "OBSERVED",
    "INSUFFICIENT_PIXELS",
    "LANDSAT_COLLECTIONS",
    "ST_SCALE",
    "ST_OFFSET",
    "assert_surface_temperature_plausible",
    "surface_temperature_c",
    "chunked",
    "build_cells",
    "coverage_summary",
    "rank_agreement",
]

# ---------------------------------------------------------------------------
# Collections and scaling constants
# ---------------------------------------------------------------------------

# Landsat 8 and 9 Collection 2 Level 2 (atmospherically corrected surface
# reflectance + surface temperature). Both are used: two satellites eight days
# out of phase roughly double the number of usable pre-monsoon scenes.
LANDSAT_COLLECTIONS = ("LANDSAT/LC08/C02/T1_L2", "LANDSAT/LC09/C02/T1_L2")

# ST_B10 -> kelvin. Published USGS Collection 2 Level 2 scaling.
ST_SCALE, ST_OFFSET = 0.00341802, 149.0
# SR_B* -> reflectance 0-1. Same document, different band group.
SR_SCALE, SR_OFFSET = 0.0000275, -0.2
KELVIN_ZERO_C = 273.15

# QA_PIXEL bit flags we refuse: dilated cloud (1), cirrus (2), cloud (3),
# cloud shadow (4). Bit 0 is fill.
QA_REJECT_BITS = (1, 2, 3, 4)

# Coarse, independent instrument. Used ONLY as a rank sanity check on the
# pattern -- never mixed into the composite. 1 km pixels cannot resolve a
# 0.69 km zone, which is precisely why the check runs at parent-hexagon scale.
MODIS_AQUA_LST = "MODIS/061/MYD11A2"
MODIS_LST_SCALE = 0.02          # scaled integers -> kelvin

GHSL_BUILT_SURFACE = "JRC/GHSL/P2023A/GHS_BUILT_S"

# Native resolutions. Reducing at the sensor's own scale avoids Earth Engine
# silently resampling to the default 1 km, which would flatten the whole city.
LANDSAT_SCALE_M = 30
MODIS_SCALE_M = 1000
GHSL_SCALE_M = 100

# Zones per Earth Engine request. Large enough that 392 zones is four calls,
# small enough to stay well inside the payload limit and to make a resumed run
# cheap.
CHUNK_SIZE = 100

OBSERVED = "observed"
INSUFFICIENT_PIXELS = "insufficient_pixels"

DEFAULT_CACHE_DIR = Path(__file__).resolve().parents[3] / "data" / "raw"


# ---------------------------------------------------------------------------
# Pure functions -- everything testable without a network or a credential
# ---------------------------------------------------------------------------

def surface_temperature_c(digital_number):
    """Landsat Collection 2 ``ST_B10`` digital numbers -> degrees Celsius."""
    dn = np.asarray(digital_number, dtype=float)
    return dn * ST_SCALE + ST_OFFSET - KELVIN_ZERO_C


def chunked(items: list, size: int = CHUNK_SIZE) -> list[list]:
    """Split zones into request-sized chunks, defaulting to the EE batch size."""
    return _chunked(items, size)


def _round_or_none(value, digits: int):
    if value is None:
        return None
    value = float(value)
    return round(value, digits) if np.isfinite(value) else None


def zone_area_m2(cell: str) -> float:
    """Area of one H3 cell in square metres."""
    return float(h3.cell_area(cell, unit="m^2"))


# ---------------------------------------------------------------------------
# The Earth Engine client
# ---------------------------------------------------------------------------

class GEESurfaceSource:
    """Reduce satellite imagery to per-zone numbers on Google's servers.

    Nothing but numbers ever crosses the wire: no GeoTIFF, no rasterio, no
    GDAL. Every reduction happens in Earth Engine and comes back as JSON --
    which is the same reason ``sources/osm.py`` uses Overpass rather than
    shapefiles, and it keeps the 6-hourly job's install small.
    """

    def __init__(self, cache_dir: Path | None = None, project: str | None = None):
        self.cache_dir = Path(cache_dir or DEFAULT_CACHE_DIR)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.project = project
        self._ee = None

    # -- initialisation ---------------------------------------------------

    def ee(self):
        """Import and initialise Earth Engine, once, on first actual use.

        Never called at import time (rule 1). If every chunk of a request is
        already cached, this is never called at all -- which is what makes a
        re-run of the export offline and free.
        """
        if self._ee is None:
            import ee  # noqa: PLC0415 - deliberately deferred

            try:
                ee.Initialize(project=self.project) if self.project \
                    else ee.Initialize()
            except Exception as exc:  # noqa: BLE001 - re-raised with guidance
                raise RuntimeError(
                    "Earth Engine is not authenticated on this machine. Run\n"
                    "    .venv/Scripts/python.exe -c "
                    "\"import ee; ee.Authenticate()\"\n"
                    "once (it opens a browser), then re-run this export. The "
                    "account needs an Earth Engine-enabled Cloud project; pass "
                    "its id with --project or set it in the config."
                ) from exc
            self._ee = ee
        return self._ee

    # -- caching ----------------------------------------------------------

    def _cache_path(self, name: str, spec: dict) -> Path:
        digest = hashlib.sha1(
            json.dumps(spec, sort_keys=True).encode()).hexdigest()[:12]
        return self.cache_dir / f"gee_{name}_{digest}.json"

    def _cached(self, name: str, spec: dict, compute, force_refresh=False):
        """Return a cached reduction, or compute it once and store it.

        ``compute`` is a zero-argument callable that does the Earth Engine
        work. It is not invoked at all on a cache hit, so a completed export
        re-runs with the network off.
        """
        path = self._cache_path(name, spec)
        if path.exists() and not force_refresh:
            return json.loads(path.read_text(encoding="utf-8"))
        payload = compute()
        path.write_text(json.dumps(payload), encoding="utf-8")
        return payload

    # -- imagery ----------------------------------------------------------

    def _landsat_collection(self, region, composite: dict):
        """Cloud-screened, scaled Landsat 8+9 over the requested season."""
        ee = self.ee()
        years, months = composite["years"], composite["months"]
        start = f"{min(years)}-01-01"
        end = f"{max(years) + 1}-01-01"

        def prepare(image):
            qa = image.select("QA_PIXEL")
            mask = ee.Image.constant(1)
            for bit in QA_REJECT_BITS:
                mask = mask.And(qa.bitwiseAnd(1 << bit).eq(0))
            lst = (image.select("ST_B10")
                   .multiply(ST_SCALE).add(ST_OFFSET)
                   .subtract(KELVIN_ZERO_C).rename("lst_c"))
            optical = (image.select(["SR_B4", "SR_B5", "SR_B6"])
                       .multiply(SR_SCALE).add(SR_OFFSET))
            red, nir, swir = (optical.select("SR_B4"), optical.select("SR_B5"),
                              optical.select("SR_B6"))
            ndvi = nir.subtract(red).divide(nir.add(red)).rename("ndvi")
            ndbi = swir.subtract(nir).divide(swir.add(nir)).rename("ndbi")
            return (lst.addBands([ndvi, ndbi])
                    .updateMask(mask)
                    .copyProperties(image, ["system:time_start", "CLOUD_COVER"]))

        merged = None
        for collection_id in LANDSAT_COLLECTIONS:
            part = (ee.ImageCollection(collection_id)
                    .filterBounds(region)
                    .filterDate(start, end)
                    .filter(ee.Filter.calendarRange(min(years), max(years),
                                                    "year"))
                    .filter(ee.Filter.calendarRange(min(months), max(months),
                                                    "month"))
                    .filter(ee.Filter.lt("CLOUD_COVER",
                                         composite["max_cloud_cover_pct"])))
            merged = part if merged is None else merged.merge(part)
        return merged.map(prepare)

    def scene_inventory(self, bbox: dict, composite: dict,
                        force_refresh: bool = False) -> dict:
        """Which scenes the composite is built from -- counted before it is built.

        Rule 4: below ``min_scenes`` the caller aborts. A composite of two
        scenes is a snapshot of two afternoons, not a climatology, and calling
        it one would be the kind of quiet overclaim this project exists to
        avoid.
        """
        spec = {"kind": "scenes", "bbox": bbox, "composite": composite}

        def compute():
            ee = self.ee()
            region = _bbox_geometry(ee, bbox)
            collection = self._landsat_collection(region, composite)
            dates = collection.aggregate_array("system:time_start").getInfo()
            clouds = collection.aggregate_array("CLOUD_COVER").getInfo()
            return {"epoch_ms": dates, "cloud_cover_pct": clouds}

        raw = self._cached("scenes", spec, compute, force_refresh)
        epochs = raw.get("epoch_ms") or []
        return {
            "n_scenes": len(epochs),
            "dates": sorted({_iso_date(ms) for ms in epochs}),
            "mean_cloud_cover_pct": (
                round(float(np.mean(raw["cloud_cover_pct"])), 2)
                if raw.get("cloud_cover_pct") else None),
        }

    # -- the per-zone reduction -------------------------------------------

    def fetch_zones(self, cells: list[str], composite: dict,
                    population: dict, force_refresh: bool = False,
                    verbose: bool = True) -> dict[str, dict]:
        """Reduce every layer to every zone, one cached chunk at a time."""
        rows: dict[str, dict] = {}
        chunks = chunked(cells, CHUNK_SIZE)
        for i, chunk in enumerate(chunks, start=1):
            spec = {"kind": "zones", "cells": chunk, "composite": composite,
                    "population": population, "version": 1}
            path = self._cache_path("zones", spec)
            if verbose:
                state = "cached" if path.exists() and not force_refresh \
                    else "fetching"
                print(f"  zones {i}/{len(chunks)} ({len(chunk)} cells) -- {state}")
            payload = self._cached(
                "zones", spec,
                lambda chunk=chunk: self._reduce_zones(chunk, composite,
                                                       population),
                force_refresh)
            rows.update(payload)
        return rows

    def _reduce_zones(self, cells: list[str], composite: dict,
                      population: dict) -> dict[str, dict]:
        ee = self.ee()
        features = ee.FeatureCollection([
            ee.Feature(_cell_geometry(ee, cell), {"h3_index": cell})
            for cell in cells
        ])
        region = features.geometry()

        collection = self._landsat_collection(region, composite)
        mean_image = collection.select(["lst_c", "ndvi", "ndbi"]).mean()

        # Mean and count are reduced separately and deliberately. Reducing a
        # stacked count band with a mean reducer would return the average
        # number of contributing scenes per pixel, not the number of pixels --
        # a plausible-looking number that means something else entirely.
        thermal = mean_image.reduceRegions(
            collection=features, reducer=ee.Reducer.mean(),
            scale=LANDSAT_SCALE_M)
        # Unmasked 30 m pixels behind the zone's mean: what gates a zone into
        # or out of the fit (rule 5).
        pixels = mean_image.select("lst_c").reduceRegions(
            collection=features, reducer=ee.Reducer.count(),
            scale=LANDSAT_SCALE_M)

        built = (ee.Image(f"{GHSL_BUILT_SURFACE}/{population['epoch']}")
                 .select("built_surface")
                 .reduceRegions(collection=features, reducer=ee.Reducer.sum(),
                                scale=GHSL_SCALE_M))
        people = (ee.Image(f"{population['source']}/{population['epoch']}")
                  .select("population_count")
                  .reduceRegions(collection=features, reducer=ee.Reducer.sum(),
                                 scale=GHSL_SCALE_M))

        rows: dict[str, dict] = {}
        for name, collection_result in (("thermal", thermal), ("pixels", pixels),
                                        ("built", built), ("people", people)):
            for feature in collection_result.getInfo()["features"]:
                props = feature["properties"]
                cell = props["h3_index"]
                row = rows.setdefault(cell, {})
                if name == "thermal":
                    row["lst_c"] = props.get("lst_c")
                    row["ndvi"] = props.get("ndvi")
                    row["ndbi"] = props.get("ndbi")
                elif name == "pixels":
                    row["valid_px"] = props.get("count")
                elif name == "built":
                    # m2 of built surface -> fraction of the zone's own area
                    total = props.get("sum")
                    row["built_s"] = (None if total is None
                                      else float(total) / zone_area_m2(cell))
                else:
                    row["population"] = props.get("sum")
        return rows

    # -- the independent cross-check --------------------------------------

    def modis_blocks(self, cells: list[str], composite: dict,
                     block_resolution: int,
                     force_refresh: bool = False) -> dict[str, float]:
        """Mean MODIS Aqua daytime LST over each coarse parent hexagon.

        A SANITY CHECK, NOT AN INPUT. MODIS is never mixed into the composite:
        its 1 km pixels cannot resolve a 0.69 km zone. What it can do is tell
        us, from a different satellite on a different orbit, whether the
        coarse blocks of the city rank in the same order -- which is a real
        falsification test the OpenStreetMap formula never had.
        """
        blocks = sorted({h3.cell_to_parent(c, block_resolution) for c in cells})
        spec = {"kind": "modis", "blocks": blocks, "composite": composite}

        def compute():
            ee = self.ee()
            years, months = composite["years"], composite["months"]
            features = ee.FeatureCollection([
                ee.Feature(_cell_geometry(ee, block), {"h3_index": block})
                for block in blocks
            ])
            image = (ee.ImageCollection(MODIS_AQUA_LST)
                     .filterDate(f"{min(years)}-01-01", f"{max(years) + 1}-01-01")
                     .filter(ee.Filter.calendarRange(min(months), max(months),
                                                     "month"))
                     .select("LST_Day_1km")
                     .mean()
                     .multiply(MODIS_LST_SCALE)
                     .subtract(KELVIN_ZERO_C)
                     .rename("modis_lst_c"))
            reduced = image.reduceRegions(collection=features,
                                          reducer=ee.Reducer.mean(),
                                          scale=MODIS_SCALE_M)
            return {f["properties"]["h3_index"]: f["properties"].get("mean")
                    for f in reduced.getInfo()["features"]}

        return self._cached("modis", spec, compute, force_refresh)


def modis_cross_check(records: dict[str, dict], modis: dict[str, float],
                      block_resolution: int) -> dict:
    """Do Landsat and MODIS rank the city's coarse blocks the same way?

    Landsat zone means are aggregated up to the parent hexagons MODIS was
    reduced over, then the two are compared by rank only (see
    ``rank_agreement``). Reported whatever it says: a weak agreement is a
    finding about the data, not a reason to hide the check.
    """
    grouped: dict[str, list[float]] = {}
    for cell, row in records.items():
        if row["provenance"] != OBSERVED:
            continue
        block = h3.cell_to_parent(cell, block_resolution)
        grouped.setdefault(block, []).append(row["lst_c"])

    blocks = sorted(set(grouped) & {b for b, v in modis.items() if v is not None})
    landsat_means = [float(np.mean(grouped[b])) for b in blocks]
    modis_means = [float(modis[b]) for b in blocks]
    return {
        "instrument": MODIS_AQUA_LST,
        "block_resolution": block_resolution,
        "n_blocks": len(blocks),
        "rank_agreement": (None if not blocks
                           else _round_or_none(rank_agreement(landsat_means,
                                                              modis_means), 3)),
        "blocks": {b: {"landsat_lst_c": round(l, 2), "modis_lst_c": round(m, 2)}
                   for b, l, m in zip(blocks, landsat_means, modis_means)},
        "note": "independent instrument, rank check only -- never mixed in",
    }


# ---------------------------------------------------------------------------
# Geometry helpers (need ``ee``, so they take it as an argument)
# ---------------------------------------------------------------------------

def _cell_geometry(ee, cell: str):
    """One H3 cell as an Earth Engine polygon, in [lon, lat] order."""
    from ..spatial import cell_polygon

    return ee.Geometry.Polygon([cell_polygon(cell)], proj="EPSG:4326",
                               geodesic=False)


def _bbox_geometry(ee, bbox: dict):
    return ee.Geometry.Rectangle(
        [bbox["min_lon"], bbox["min_lat"], bbox["max_lon"], bbox["max_lat"]],
        proj="EPSG:4326", geodesic=False)


def _iso_date(epoch_ms: float) -> str:
    from datetime import datetime, timezone

    return datetime.fromtimestamp(epoch_ms / 1000.0,
                                  tz=timezone.utc).strftime("%Y-%m-%d")
