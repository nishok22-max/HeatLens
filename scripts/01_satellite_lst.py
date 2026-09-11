"""Export satellite surface temperature to the H3 grid -- the measured pattern.

    python scripts/01_satellite_lst.py config/ahmedabad.yaml [--source modis|gee]
                                       [--project <id>] [--force-refresh]

Writes ``data/processed/satellite_<city>.json``: what the satellite actually
measured, per zone, plus the anomaly each zone sits at relative to the city.
Script 12 turns that into temperature offsets; 04 -> 05 -> 06 then rebuild the
whole product on top of it.

TWO SOURCES, ONE OUTPUT SCHEMA
------------------------------
``--source modis`` (default)
    MODIS Aqua at 1 km from ORNL DAAC. **No registration, no API key, no
    approval wait** -- the same property that made Overpass and Open-Meteo the
    right calls for this project, applied to thermal imagery. Day and night.
    Terra is used as an independent instrument for the rank cross-check.

``--source gee``
    Landsat 8/9 at 30 m through Earth Engine, plus greenness, built surface and
    population. Better in every way except one: it needs a browser sign-in and
    an Earth Engine-enabled Cloud project. Run
    ``python -c "import ee; ee.Authenticate()"`` once, then pass ``--source
    gee --project <id>``, and everything downstream picks up the finer data
    with no other change.

RUN THIS ONCE. Every request is cached under ``data/raw``, so a re-run makes
zero network calls and an interrupted run resumes where it stopped (NFR-1).
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np
import yaml

from heatstress import satellite as sat
from heatstress import spatial as sp
from heatstress.sources import modis_ornl as mo

ROOT = Path(__file__).resolve().parents[1]
RULE = "=" * 74

# Declared here rather than in the config because it gates nothing: coverage is
# reported either way. A hole that announces itself is honest; a hole that
# aborts the build is merely inconvenient.
MIN_OBSERVED_FRACTION = 0.90


# ---------------------------------------------------------------------------
# MODIS path -- works today, no credential
# ---------------------------------------------------------------------------

def export_modis(city, cells, composite, block_resolution,
                 force_refresh: bool) -> dict:
    cfg = composite["modis"]
    centre = (city["centre"]["lat"], city["centre"]["lon"])
    source = mo.ORNLModisLST(product=cfg["product"])

    codes = source.available_dates(*centre, composite["years"],
                                   composite["months"], force_refresh)
    print(f"\n{cfg['product']} 8-day composites in "
          f"{composite['months']} of {composite['years']}: {len(codes)} "
          f"(minimum {composite['min_scenes']})")
    if len(codes) < composite["min_scenes"]:
        raise SystemExit(
            f"\nABORTED. {len(codes)} composites is below the declared minimum "
            f"of {composite['min_scenes']}. Widen "
            "urban_heat.lst_composite.years or months -- and say which."
        )

    grids = {}
    for label, lst_band, qc_band in (("day", "LST_Day_1km", "QC_Day"),
                                     ("night", "LST_Night_1km", "QC_Night")):
        print(f"\n  {label} ({lst_band}):")
        grids[label] = source.composite(
            *centre, lst_band, qc_band, codes, cfg["subset_km"],
            cfg["max_error_class"], force_refresh, verbose=True)

    day, night = grids["day"], grids["night"]
    usable = day.usable(cfg["min_valid_obs_per_cell"])
    print(f"\n  pixels {day.lat.size}, usable {int(usable.sum())}, "
          f"mean observations per pixel {day.n_obs.mean():.1f}")

    day_rows = mo.sample_zones(day, cells, cfg["min_valid_obs_per_cell"],
                               cfg["max_sample_distance_km"])
    night_rows = mo.sample_zones(night, cells, cfg["min_valid_obs_per_cell"],
                                 cfg["max_sample_distance_km"])
    for cell, row in night_rows.items():
        day_rows[cell]["lst_night_c"] = row["lst_c"]

    records, city_mean = sat.build_cells(day_rows, cells,
                                         cfg["min_valid_obs_per_cell"])
    night_mean = sat.add_night_layer(records, day_rows)
    for cell, row in day_rows.items():
        records[cell]["sample_distance_km"] = row.get("sample_distance_km")

    # -- the independent instrument -------------------------------------
    print(f"\n  cross-check against {cfg['cross_check_product']} "
          "(different satellite, different overpass time):")
    other = mo.ORNLModisLST(product=cfg["cross_check_product"])
    other_codes = other.available_dates(*centre, composite["years"],
                                        composite["months"], force_refresh)
    other_grid = other.composite(*centre, "LST_Day_1km", "QC_Day", other_codes,
                                 cfg["subset_km"], cfg["max_error_class"],
                                 force_refresh, verbose=True)
    other_rows = mo.sample_zones(other_grid, cells,
                                 cfg["min_valid_obs_per_cell"],
                                 cfg["max_sample_distance_km"])
    cross = sat.cross_check_blocks(
        records, {c: r["lst_c"] for c, r in other_rows.items()
                  if r["lst_c"] is not None},
        block_resolution, cfg["cross_check_product"])

    distinct = len({r["lst_c"] for r in records.values()
                    if r["lst_c"] is not None})
    return {
        "source": {
            "instrument": f"MODIS Aqua {cfg['product']} (ORNL DAAC subset API)",
            "bands": ["LST_Day_1km", "LST_Night_1km"],
            "native_resolution_m": round(day.cellsize_m, 1),
            "overpass_local": "13:30 day / 01:30 night",
            "years": composite["years"],
            "months": composite["months"],
            "n_composites": day.n_composites,
            "max_error_class": cfg["max_error_class"],
            "min_valid_obs_per_cell": cfg["min_valid_obs_per_cell"],
            "requires_credential": False,
            # The honest headline about resolution, carried in the data so the
            # UI and the deck cannot quietly overstate it.
            "distinct_pixels_behind_zones": distinct,
            "zones_per_pixel": round(len(cells) / max(distinct, 1), 2),
            "upgrade_path": "Landsat 8/9 at 30 m via --source gee once Earth "
                            "Engine is authorised; same schema, no downstream "
                            "change",
        },
        "records": records,
        "city_mean": city_mean,
        "night_city_mean": night_mean,
        "cross_check": cross,
        "n_scenes": day.n_composites,
    }


# ---------------------------------------------------------------------------
# Earth Engine path -- finer, needs a credential
# ---------------------------------------------------------------------------

def export_gee(city, cells, composite, population, block_resolution,
               project, force_refresh: bool) -> dict:
    from heatstress.sources import gee

    source = gee.GEESurfaceSource(project=project)
    scenes = source.scene_inventory(city["bbox"], composite, force_refresh)
    print(f"\nusable Landsat scenes: {scenes['n_scenes']} "
          f"(minimum {composite['min_scenes']})  "
          f"mean cloud {scenes['mean_cloud_cover_pct']}%")
    if scenes["n_scenes"] < composite["min_scenes"]:
        raise SystemExit(
            f"\nABORTED. {scenes['n_scenes']} usable scenes is below the "
            f"declared minimum of {composite['min_scenes']}. A composite this "
            "thin is a snapshot of a few afternoons, not a climatology."
        )

    print(f"\nreducing {len(cells)} zones "
          f"({len(gee.chunked(cells))} cached chunks):")
    rows = source.fetch_zones(cells, composite, population, force_refresh)
    records, city_mean = sat.build_cells(rows, cells,
                                         composite["min_valid_px_per_cell"])
    modis = source.modis_blocks(cells, composite, block_resolution,
                                force_refresh)
    cross = gee.modis_cross_check(records, modis, block_resolution)
    return {
        "source": {
            "instrument": "Landsat 8/9 Collection 2 L2 (Earth Engine)",
            "bands": ["ST_B10", "SR_B4/5/6"],
            "native_resolution_m": gee.LANDSAT_SCALE_M,
            "years": composite["years"],
            "months": composite["months"],
            "max_cloud_cover_pct": composite["max_cloud_cover_pct"],
            "min_valid_px_per_cell": composite["min_valid_px_per_cell"],
            "population": f"{population['source']}/{population['epoch']}",
            "requires_credential": True,
        },
        "records": records,
        "city_mean": city_mean,
        "night_city_mean": None,
        "cross_check": cross,
        "n_scenes": scenes["n_scenes"],
        "scenes": scenes,
    }


# ---------------------------------------------------------------------------

def main(config_path: str, source_name: str = "modis",
         project: str | None = None, force_refresh: bool = False) -> None:
    config = yaml.safe_load(Path(config_path).read_text(encoding="utf-8"))
    city, grid_cfg, uhi = config["city"], config["grid"], config["urban_heat"]
    composite = uhi["lst_composite"]
    block_resolution = uhi["downscale"]["cv_group_resolution"]
    slug = city["name"].lower().replace(" ", "_")

    cells = sp.build_grid(city["bbox"], grid_cfg["h3_resolution"])
    print(RULE)
    print(f"SATELLITE EXPORT -- {city['name']}, {len(cells)} zones at H3 "
          f"resolution {grid_cfg['h3_resolution']}")
    print(RULE)

    if source_name == "gee":
        result = export_gee(city, cells, composite, config["population"],
                            block_resolution, project, force_refresh)
    else:
        result = export_modis(city, cells, composite, block_resolution,
                              force_refresh)

    records = result["records"]
    coverage = sat.coverage_summary(records, MIN_OBSERVED_FRACTION)
    anomalies = np.array([r["lst_anomaly_c"] for r in records.values()
                          if r["lst_anomaly_c"] is not None])

    out = {
        "city": city["name"],
        "h3_resolution": grid_cfg["h3_resolution"],
        "source": result["source"],
        "scenes": {"n_scenes": result["n_scenes"],
                   "min_scenes": composite["min_scenes"]},
        # SURFACE temperature, not air temperature. Script 12 multiplies the
        # anomaly by alpha to get an air-temperature offset; conflating the two
        # would overstate the intra-city spread several times over, which is
        # why the key says lst and never d_ta.
        "city_mean_lst_c": round(result["city_mean"], 3),
        "night_city_mean_lst_c": (None if result["night_city_mean"] is None
                                  else round(result["night_city_mean"], 3)),
        "coverage": coverage,
        "cross_check": result["cross_check"],
        "cells": records,
    }
    dest = ROOT / "data" / "processed" / f"satellite_{slug}.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(out), encoding="utf-8")

    # -- report -----------------------------------------------------------
    print(f"\n{RULE}\nWHAT THE SATELLITE MEASURED\n{RULE}")
    print(f"  instrument            : {result['source']['instrument']}")
    zone_km2 = sp.zone_area_km2(cells[0])
    print(f"  native resolution     : {result['source']['native_resolution_m']} m"
          f"   (zones are {zone_km2:.3f} km2, about "
          f"{zone_km2 ** 0.5 * 1000:.0f} m across)")
    print(f"  city mean surface temp: {result['city_mean']:6.2f} C")
    if result["night_city_mean"] is not None:
        night = np.array([r["lst_night_anomaly_c"] for r in records.values()
                          if r.get("lst_night_anomaly_c") is not None])
        print(f"  city mean at night    : {result['night_city_mean']:6.2f} C"
              f"   night anomaly spread {np.ptp(night):.2f} C")
    print(f"  zone anomaly          : {anomalies.min():+6.2f} to "
          f"{anomalies.max():+6.2f} C   spread {np.ptp(anomalies):5.2f} C")

    print("\n  implied AIR-temperature spread (surface anomaly x alpha):")
    lo, hi = uhi["alpha_range"]
    for alpha in (lo, uhi["alpha"], hi):
        mark = "   <- config" if alpha == uhi["alpha"] else ""
        print(f"    alpha={alpha:.2f}  ->  {np.ptp(anomalies) * alpha:5.2f} C"
              f"{mark}")
    print(f"    the method being replaced assumed {uhi['uhi_amplitude_c']:.2f} C")

    print(f"\n  zones observed  : {coverage['cells_observed']}/"
          f"{coverage['cells_total']} "
          f"({coverage['observed_fraction'] * 100:.1f}%, target "
          f"{MIN_OBSERVED_FRACTION * 100:.0f}%)"
          f"{'' if coverage['passes'] else '   *** BELOW TARGET ***'}")
    if "distinct_pixels_behind_zones" in result["source"]:
        print(f"  resolution truth: {result['source']['distinct_pixels_behind_zones']}"
              f" distinct pixels behind {len(cells)} zones "
              f"({result['source']['zones_per_pixel']} zones per pixel) -- "
              "neighbouring zones can share a value")

    cross = result["cross_check"]
    print(f"\n  cross-check vs {cross['instrument']} over {cross['n_blocks']} "
          f"blocks: rank agreement {cross['rank_agreement']}")
    if cross["rank_agreement"] is not None and cross["rank_agreement"] < 0.5:
        print("  *** WEAK. Report it; do not quietly drop the check. ***")

    print(f"\nwritten -> {dest.relative_to(ROOT)} "
          f"({dest.stat().st_size / 1024:.0f} KB)")
    print("re-running this script now makes zero network calls.")
    print("next: python scripts/12_downscaled_offsets.py " + config_path)
    print(RULE)


if __name__ == "__main__":
    args = sys.argv[1:]
    config = next((a for a in args if not a.startswith("--")),
                  "config/ahmedabad.yaml")
    source_name = "modis"
    project = None
    if "--source" in args:
        source_name = args[args.index("--source") + 1]
    if "--project" in args:
        project = args[args.index("--project") + 1]
    try:
        main(config, source_name, project, "--force-refresh" in args)
    except RuntimeError as exc:
        # The one expected failure on a fresh machine is a missing Earth Engine
        # credential. It deserves the instruction, not a traceback.
        raise SystemExit(f"\n{exc}") from None
