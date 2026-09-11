"""MODIS land-surface temperature from ORNL DAAC -- satellite data, no credential.

WHY THIS EXISTS ALONGSIDE ``gee.py``
------------------------------------
The planned satellite path is Landsat 8/9 at 30 m through Earth Engine
(``sources/gee.py``). It is written and tested, and it is blocked on something
no code can do: a one-off browser sign-in and an Earth Engine-enabled Cloud
project. Until that happens the project ships a *guessed* thermal pattern.

ORNL DAAC serves MODIS land-surface temperature subsets over plain HTTP with
**no registration, no API key and no approval wait**, as JSON -- numbers, not
rasters. That is the same property that made Overpass and Open-Meteo the right
choices for this project (D2), applied to thermal imagery. So the pattern
becomes measured now, at 1 km, instead of assumed indefinitely at 0.69 km.

WHAT YOU GIVE UP, STATED PLAINLY
--------------------------------
1 km pixels against 0.69 km zones. About 300 distinct MODIS pixels back the 392
zones, so roughly 1.3 zones share a pixel and neighbouring zones can carry an
identical number. The map is therefore honestly blocky at the kilometre scale,
and no sub-pixel detail is invented by smoothing. Landsat at 30 m remains the
upgrade, behind the same schema -- swapping it in changes no downstream code.

WHY AQUA, AND WHY BOTH OVERPASSES
---------------------------------
Aqua crosses at about **13:30 and 01:30 local**. The project's focus hour is
14:00 IST, so the daytime overpass lands within half an hour of the exact hour
the kill gate is scored on -- a better match than Terra's 10:30, and much
better than a daily mean. The 01:30 pass gives the night-time pattern, which
matters more: the May 2010 deaths tracked six consecutive nights that never
dropped below 26.7 degC. Terra is then free to serve as the independent
instrument for the rank cross-check.

QUALITY SCREENING
-----------------
``QC_Day`` / ``QC_Night`` bits 0-1 are the mandatory QA flag and bits 6-7 the
LST error class. This module keeps pixels that were *produced* (mandatory <= 1)
with an average error of **2 K or better** (error class <= 1), which is the
screen the MODIS LST user guide describes for general use. Demanding the top
quality flag alone would discard 69 % of the observations here and leave only
84 distinct pixels behind the whole city -- a stricter filter that produces a
worse map. Both counts are reported, so the choice is visible rather than
buried.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
import warnings
from dataclasses import dataclass
from pathlib import Path

import h3
import numpy as np
import requests

from ..satellite import chunked

__all__ = [
    "ORNLModisLST",
    "PixelGrid",
    "AQUA",
    "TERRA",
    "MODIS_LST_SCALE",
    "sinusoidal_to_latlng",
    "pixel_centres",
    "quality_mask",
    "composite_pixels",
    "sample_zones",
]

BASE_URL = "https://modis.ornl.gov/rst/api/v1"

AQUA = "MYD11A2"    # 13:30 / 01:30 local overpass -- the primary source
TERRA = "MOD11A2"   # 10:30 local -- the independent cross-check only

# Scaled integers -> kelvin. Fill value is 0, which is also why a plain
# ``!= 0`` test is a legitimate fill check for this product.
MODIS_LST_SCALE = 0.02
KELVIN_ZERO_C = 273.15

# MODIS sinusoidal projection: a sphere, not an ellipsoid. Both directions are
# closed-form, so no pyproj and no GDAL.
SINUSOIDAL_RADIUS_M = 6371007.181

# ORNL returns at most a handful of composites per request; 7 keeps each
# response small and each cache entry independently resumable.
DATES_PER_REQUEST = 7

# A zone whose centroid is further than this from the nearest usable pixel
# centre is not measured, it is extrapolated. Half a MODIS pixel diagonal is
# about 0.66 km; 1.0 km allows the zone-to-pixel offset at the city edge
# without silently reaching across open country.
MAX_SAMPLE_DISTANCE_KM = 1.0

DEFAULT_CACHE_DIR = Path(__file__).resolve().parents[3] / "data" / "raw"


# ---------------------------------------------------------------------------
# Projection and geolocation -- pure, and verified against the service
# ---------------------------------------------------------------------------

def sinusoidal_to_latlng(x: float, y: float) -> tuple[float, float]:
    """MODIS sinusoidal metres -> (lat, lon) degrees.

    Forward is ``x = R*lon*cos(lat)``, ``y = R*lat`` in radians, so the inverse
    is exact and needs no iteration.
    """
    phi = y / SINUSOIDAL_RADIUS_M
    lam = x / (SINUSOIDAL_RADIUS_M * math.cos(phi))
    return math.degrees(phi), math.degrees(lam)


def pixel_centres(header: dict) -> tuple[np.ndarray, np.ndarray]:
    """(lat, lon) of every pixel centre in an ORNL subset, in ``data`` order.

    ROW 0 IS THE NORTHERNMOST ROW. That is not documented in an obvious place
    and getting it wrong mirrors the city north-south while leaving every
    number plausible, so it was verified against the service itself: the
    coordinates this function returns for the first pixel were fed back as a
    single-pixel subset request, and the value came back identical
    (15941 for A2023097). ``tests/test_modis.py`` pins the same property
    against a synthetic header.
    """
    xll, yll = float(header["xllcorner"]), float(header["yllcorner"])
    size = float(header["cellsize"])
    nrows, ncols = int(header["nrows"]), int(header["ncols"])

    lats = np.empty(nrows * ncols)
    lons = np.empty(nrows * ncols)
    for row in range(nrows):
        y = yll + (nrows - 1 - row + 0.5) * size
        for col in range(ncols):
            lat, lon = sinusoidal_to_latlng(xll + (col + 0.5) * size, y)
            lats[row * ncols + col] = lat
            lons[row * ncols + col] = lon
    return lats, lons


def quality_mask(qc: np.ndarray, max_error_class: int = 1) -> np.ndarray:
    """True where a MODIS LST observation is usable.

    bits 0-1  mandatory QA:   0 produced, good quality
                              1 produced, other quality (check the error class)
                              2 not produced, cloud
                              3 not produced, other reason
    bits 6-7  average error:  0 <= 1 K, 1 <= 2 K, 2 <= 3 K, 3 > 3 K
    """
    qc = np.asarray(qc, dtype=int)
    mandatory = qc & 0b11
    error_class = (qc >> 6) & 0b11
    return (mandatory <= 1) & (error_class <= max_error_class)


def composite_pixels(lst_stack, qc_stack,
                     max_error_class: int = 1) -> tuple[np.ndarray, np.ndarray]:
    """Average the usable observations per pixel across all composites.

    Returns the mean in degrees Celsius (NaN where nothing was usable) and the
    number of observations behind each pixel.
    """
    lst = np.asarray(lst_stack, dtype=float)
    qc = np.asarray(qc_stack, dtype=int)
    if lst.shape != qc.shape:
        raise ValueError(
            f"LST stack {lst.shape} and QC stack {qc.shape} disagree; they "
            "must be the same composites in the same order, or quality flags "
            "are being applied to the wrong dates"
        )

    usable = (lst != 0) & quality_mask(qc, max_error_class)
    celsius = np.where(usable, lst * MODIS_LST_SCALE - KELVIN_ZERO_C, np.nan)
    # A pixel with nothing usable is NaN by design -- it is an unmeasured zone,
    # not a freezing one -- so numpy's "mean of empty slice" warning is the
    # expected path and is silenced rather than printed on every run.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=RuntimeWarning)
        mean = np.nanmean(celsius, axis=0)
    return mean, usable.sum(axis=0)


@dataclass
class PixelGrid:
    """A composited MODIS field: one mean temperature per pixel centre."""

    lat: np.ndarray
    lon: np.ndarray
    value_c: np.ndarray
    n_obs: np.ndarray
    n_composites: int
    product: str
    band: str
    cellsize_m: float

    def usable(self, min_obs: int) -> np.ndarray:
        return np.isfinite(self.value_c) & (self.n_obs >= min_obs)


def sample_zones(grid: PixelGrid, cells: list[str], min_obs: int,
                 max_distance_km: float = MAX_SAMPLE_DISTANCE_KM) -> dict:
    """Give every zone the value of the pixel it sits in.

    Nearest pixel centre, not interpolation. At 1 km the pixel is about the
    size of the zone, so bilinear smoothing would manufacture sub-pixel detail
    that the instrument never resolved -- and this project's whole argument is
    that a plausible-looking invented pattern is worse than an honest coarse
    one. Zones further than ``max_distance_km`` from any usable pixel are
    returned with no value and get flagged as unmeasured downstream.
    """
    keep = grid.usable(min_obs)
    if not keep.any():
        raise ValueError("no usable MODIS pixel in the whole subset")

    lat, lon = grid.lat[keep], grid.lon[keep]
    values, obs = grid.value_c[keep], grid.n_obs[keep]

    rows = {}
    for cell in cells:
        clat, clon = h3.cell_to_latlng(cell)
        # Local flat-earth distance: over a 20 km city the error is negligible
        # and it avoids a trigonometric call per pixel per zone.
        dy = (lat - clat) * 111.32
        dx = (lon - clon) * 111.32 * math.cos(math.radians(clat))
        distance = np.hypot(dx, dy)
        nearest = int(distance.argmin())
        if distance[nearest] > max_distance_km:
            rows[cell] = {"lst_c": None, "valid_px": 0,
                          "sample_distance_km": round(float(distance[nearest]), 3)}
            continue
        rows[cell] = {
            "lst_c": float(values[nearest]),
            "valid_px": int(obs[nearest]),
            "sample_distance_km": round(float(distance[nearest]), 3),
        }
    return rows


# ---------------------------------------------------------------------------
# The client
# ---------------------------------------------------------------------------

class ORNLModisLST:
    """Fetch MODIS LST subsets from ORNL DAAC, cached permanently to disk.

    Every response is cached under ``data/raw`` keyed by a hash of the request,
    exactly as ``sources/osm.py`` and ``sources/openmeteo.py`` do, so a re-run
    makes zero network calls and an interrupted run resumes for free (NFR-1).
    """

    def __init__(self, product: str = AQUA, cache_dir: Path | None = None,
                 timeout: int = 300):
        self.product = product
        self.cache_dir = Path(cache_dir or DEFAULT_CACHE_DIR)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.timeout = timeout

    def _get(self, name: str, path: str, params: dict,
             force_refresh: bool = False) -> dict:
        spec = {"path": path, "params": params}
        digest = hashlib.sha1(
            json.dumps(spec, sort_keys=True).encode()).hexdigest()[:12]
        cache_path = self.cache_dir / f"modis_{self.product}_{name}_{digest}.json"
        if cache_path.exists() and not force_refresh:
            return json.loads(cache_path.read_text(encoding="utf-8"))

        response = requests.get(f"{BASE_URL}/{self.product}/{path}",
                                params=params, timeout=self.timeout)
        response.raise_for_status()
        payload = response.json()
        cache_path.write_text(json.dumps(payload), encoding="utf-8")
        return payload

    def available_dates(self, lat: float, lon: float, years, months,
                        force_refresh: bool = False) -> list[str]:
        """MODIS date codes (``A2023097``) inside the requested season."""
        payload = self._get("dates", "dates",
                            {"latitude": lat, "longitude": lon}, force_refresh)
        wanted = []
        for row in payload["dates"]:
            code = row["modis_date"]
            year, doy = int(code[1:5]), int(code[5:])
            month = (dt.date(year, 1, 1) + dt.timedelta(days=doy - 1)).month
            if year in set(years) and month in set(months):
                wanted.append(code)
        return sorted(wanted)

    def fetch_band(self, lat: float, lon: float, band: str, codes: list[str],
                   km: int, force_refresh: bool = False,
                   verbose: bool = False) -> tuple[dict[str, list], dict]:
        """One band over many composites, in cached chunks of dates."""
        values: dict[str, list] = {}
        header: dict = {}
        chunks = chunked(codes, DATES_PER_REQUEST)
        for i, chunk in enumerate(chunks, start=1):
            params = {"latitude": lat, "longitude": lon, "band": band,
                      "startDate": chunk[0], "endDate": chunk[-1],
                      "kmAboveBelow": km, "kmLeftRight": km}
            cached = self._cache_exists("subset", "subset", params)
            if verbose:
                print(f"    {band} {chunk[0]}..{chunk[-1]} "
                      f"({i}/{len(chunks)}) -- "
                      f"{'cached' if cached and not force_refresh else 'fetching'}")
            payload = self._get("subset", "subset", params, force_refresh)
            header = {k: v for k, v in payload.items() if k != "subset"}
            for entry in payload["subset"]:
                if entry["modis_date"] in chunk:
                    values[entry["modis_date"]] = entry["data"]
        return values, header

    def _cache_exists(self, name: str, path: str, params: dict) -> bool:
        spec = {"path": path, "params": params}
        digest = hashlib.sha1(
            json.dumps(spec, sort_keys=True).encode()).hexdigest()[:12]
        return (self.cache_dir /
                f"modis_{self.product}_{name}_{digest}.json").exists()

    def composite(self, lat: float, lon: float, lst_band: str, qc_band: str,
                  codes: list[str], km: int, max_error_class: int = 1,
                  force_refresh: bool = False,
                  verbose: bool = False) -> PixelGrid:
        """Fetch one LST band with its quality band and composite them.

        The two bands are aligned by date code before compositing. Pairing them
        by position instead would apply one date's cloud flags to another
        date's temperatures -- silent, and catastrophic.
        """
        lst, header = self.fetch_band(lat, lon, lst_band, codes, km,
                                      force_refresh, verbose)
        qc, _ = self.fetch_band(lat, lon, qc_band, codes, km,
                                force_refresh, verbose)

        shared = sorted(set(lst) & set(qc))
        if not shared:
            raise ValueError(
                f"no composite has both {lst_band} and {qc_band}; refusing to "
                "composite unscreened temperatures"
            )
        lst_stack = np.array([lst[code] for code in shared], dtype=float)
        qc_stack = np.array([qc[code] for code in shared], dtype=int)
        mean, n_obs = composite_pixels(lst_stack, qc_stack, max_error_class)

        lats, lons = pixel_centres(header)
        if lats.size != mean.size:
            raise ValueError(
                f"header describes {lats.size} pixels but the data has "
                f"{mean.size}; the grid and the values are not the same subset"
            )
        return PixelGrid(lat=lats, lon=lons, value_c=mean, n_obs=n_obs,
                         n_composites=len(shared), product=self.product,
                         band=lst_band, cellsize_m=float(header["cellsize"]))
