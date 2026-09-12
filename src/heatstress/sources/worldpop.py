"""Residential population per H3 zone, from WorldPop's zonal-statistics API.

WHY THIS AND NOT EARTH ENGINE
-----------------------------
``sources/gee.py`` already reduces GHS-POP per zone, and ``config/*.yaml`` still
declares ``JRC/GHSL/P2023A/GHS_POP`` as the population source. That path needs
Earth Engine credentials, which the offline/no-credential pipeline does not have
-- the shipped satellite export comes from the ORNL DAAC MODIS route precisely
because it needs no account. Population arriving through GEE would have made a
measured layer depend on a login that the rest of the pipeline deliberately
avoids.

WorldPop publishes the same quantity -- modelled residential head-count on a
100 m grid -- behind a public HTTP API that takes a GeoJSON polygon and returns
a summed population. No key, no account, JSON in and JSON out: the same shape as
the ORNL DAAC subset calls in ``sources/modis.py``.

It is also the source Phase 2 of this work needs anyway. Elderly density comes
from WorldPop's age-sex rasters, and taking the denominator (total people) and
the numerator (people 60+) from the same provider avoids an elderly *fraction*
built from two different population models.

WHAT THE NUMBER IS, AND IS NOT
------------------------------
WorldPop is **modelled**, not counted. Census totals are disaggregated onto a
grid using covariates (built surface, roads, night lights), so a single zone's
head-count carries real uncertainty even though the district total is anchored
to a census. That is still a measurement of population in the sense that
matters here -- it is derived from census observations rather than assumed by us
-- but it is not a doorstep count, and the provenance string must not imply one.

Per-cell responses are cached under ``data/raw``, so an interrupted run resumes
and only fetches the gaps. The API is a free public research service: requests
are issued one at a time with a delay between them, and that is deliberate.
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

import h3
import requests

__all__ = ["WorldPopPopulation", "DEFAULT_DATASET", "DEFAULT_YEAR"]

API_URL = "https://api.worldpop.org/v1/services/stats"

#: Global Project Population, 100 m, unconstrained. The global product, so the
#: pipeline stays portable to any city (NFR-5) rather than needing a per-country
#: file.
DEFAULT_DATASET = "wpgppop"
DEFAULT_YEAR = 2020

DEFAULT_CACHE_DIR = Path(__file__).resolve().parents[3] / "data" / "raw"

MAX_ATTEMPTS = 4
BACKOFF_BASE_S = 4
#: Courtesy gap between uncached requests to a free public research API.
THROTTLE_S = 0.5


class WorldPopPopulation:
    """Fetch WorldPop residential population summed over each H3 zone."""

    def __init__(self, cache_dir: Path | None = None, timeout: int = 90,
                 throttle_s: float = THROTTLE_S):
        self.cache_dir = Path(cache_dir or DEFAULT_CACHE_DIR)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.timeout = timeout
        self.throttle_s = throttle_s
        #: Cells the API never returned a usable answer for. The caller decides
        #: whether that is fatal; it is never silently turned into a zero,
        #: because "nobody lives here" and "we failed to ask" are different
        #: facts and only one of them should reduce a zone's risk.
        self.failed: list[tuple[str, str]] = []

    # -- plumbing ---------------------------------------------------------

    @staticmethod
    def cell_polygon(cell: str) -> dict:
        """H3 cell boundary as a closed GeoJSON Polygon geometry."""
        ring = [[lon, lat] for lat, lon in h3.cell_to_boundary(cell)]
        ring.append(ring[0])
        return {"type": "Polygon", "coordinates": [ring]}

    def _cache_path(self, cell: str, dataset: str, year: int) -> Path:
        key = f"{dataset}|{year}|{cell}"
        digest = hashlib.sha1(key.encode()).hexdigest()[:12]
        return self.cache_dir / f"worldpop_{dataset}_{year}_{digest}.json"

    def _fetch_cell(self, cell: str, dataset: str, year: int,
                    force_refresh: bool) -> dict | None:
        path = self._cache_path(cell, dataset, year)
        if path.exists() and not force_refresh:
            return json.loads(path.read_text(encoding="utf-8"))

        params = {
            "dataset": dataset,
            "year": year,
            "geojson": json.dumps(self.cell_polygon(cell)),
            # Synchronous: one small polygon resolves in a few seconds, and the
            # async task queue would add polling for no benefit at this size.
            "runasync": "false",
        }

        last_error: Exception | str | None = None
        for attempt in range(MAX_ATTEMPTS):
            try:
                response = requests.get(API_URL, params=params,
                                        timeout=self.timeout)
                if response.status_code == 200:
                    payload = response.json()
                    if payload.get("error"):
                        last_error = payload.get("error_message") or "API error"
                    else:
                        path.write_text(json.dumps(payload), encoding="utf-8")
                        time.sleep(self.throttle_s)
                        return payload
                else:
                    last_error = f"HTTP {response.status_code}"
            except Exception as exc:  # noqa: BLE001 - any failure is retryable
                last_error = exc

            if attempt < MAX_ATTEMPTS - 1:
                time.sleep(BACKOFF_BASE_S * (attempt + 1))

        self.failed.append((cell, str(last_error)))
        return None

    # -- the per-zone reduction -------------------------------------------

    def fetch_cells(self, cells: list[str], dataset: str = DEFAULT_DATASET,
                    year: int = DEFAULT_YEAR, force_refresh: bool = False,
                    verbose: bool = True) -> dict[str, float]:
        """Population summed over each cell. Missing cells are absent, not zero.

        Cells the API could not answer for are recorded in ``self.failed`` and
        left out of the returned mapping.
        """
        out: dict[str, float] = {}
        for i, cell in enumerate(cells, start=1):
            cached = self._cache_path(cell, dataset, year).exists()
            if verbose and (i == 1 or i % 25 == 0 or i == len(cells)):
                print(f"  zone {i}/{len(cells)} "
                      f"({'cached' if cached else 'fetching'})")
            payload = self._fetch_cell(cell, dataset, year, force_refresh)
            if payload is None:
                continue
            total = (payload.get("data") or {}).get("total_population")
            if total is None:
                self.failed.append((cell, "no total_population in response"))
                continue
            # The API can return a small negative for a polygon that clips only
            # nodata; treat that as empty rather than letting it poison a sum.
            out[cell] = max(0.0, float(total))
        return out
