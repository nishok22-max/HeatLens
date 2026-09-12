"""Measure how many people live in each zone, from WorldPop.

    python scripts/14_population.py config/ahmedabad.yaml [--force]

Reads the zone list from the resolved urban-form file and writes
``data/processed/population_<city>.json``. Script 04 then uses it as the
*exposure* term of the IPCC risk triple, replacing the proxy.

WHY THIS MATTERS MORE THAN IT LOOKS (DECISIONS D15)
---------------------------------------------------
Before this step, exposure was the per-zone ``intensity`` field. Under
``urban_heat.mode: lst`` that field is a min-max rescale of the same satellite
anomaly that produces ``d_ta`` -- so exposure was a linear function of the
hazard offset, not an independent quantity. With vulnerability also a city-wide
constant, the whole risk composition collapsed:

    exposure = 0.373 * d_Ta + 0.610     (max residual 2e-4, i.e. rounding)
    spearman(risk, WBGT) = 1.0000       at all 264 hours
    top-20 worst zones by risk vs WBGT: 20/20 identical

Ranking zones by risk was identical to ranking them by WBGT. Population is the
first term in that product not derived from temperature, so this is the step
that makes ``risk`` capable of disagreeing with ``hazard`` at all.

WHAT THIS DOES NOT FIX
----------------------
Vulnerability stays a city-wide constant. This measures *how many people*, not
*who they are* -- no age, no occupation, no housing. The elderly-density half of
PS-5 needs WorldPop's age-sex rasters and is not done here.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np
import yaml

from heatstress import spatial as sp
from heatstress.sources import worldpop as wp

ROOT = Path(__file__).resolve().parents[1]
RULE = "=" * 74


def main(config_path: str, force: bool = False) -> None:
    config = yaml.safe_load(Path(config_path).read_text(encoding="utf-8"))
    city = config["city"]
    slug = city["name"].lower().replace(" ", "_")

    form_path, level = sp.resolve_urban_form(
        ROOT, slug, config["urban_heat"].get("mode", "lst"))
    form = json.loads(Path(form_path).read_text(encoding="utf-8"))
    cells = sorted(form["cells"])
    print(f"{city['name']}: {len(cells)} zones from {Path(form_path).name} "
          f"[{level}]")

    pop_cfg = config.get("population", {})
    dataset = pop_cfg.get("worldpop_dataset", wp.DEFAULT_DATASET)
    year = int(pop_cfg.get("year", pop_cfg.get("epoch", wp.DEFAULT_YEAR)))
    print(f"WorldPop dataset={dataset} year={year}")
    print("  (free public API, one zone per request -- first run is slow)")

    source = wp.WorldPopPopulation()
    counts = source.fetch_cells(cells, dataset=dataset, year=year,
                                force_refresh=force)

    missing = [c for c in cells if c not in counts]
    if missing:
        # Refusing to write is the point. A zone silently defaulted to zero
        # people would read as "no one at risk here" on the map, which is the
        # most dangerous possible failure mode for this particular layer.
        print(f"\n{len(missing)} of {len(cells)} zones have no population "
              f"answer. Refusing to write a partial surface.")
        for cell, why in source.failed[:5]:
            print(f"  {cell}: {why}")
        raise SystemExit(1)

    people = np.array([counts[c] for c in cells], dtype=float)
    area_km2 = np.array([sp.zone_area_km2(c) for c in cells], dtype=float)
    density = people / area_km2

    # Scale to 0-1 against a high percentile rather than the maximum, so one
    # unusually dense zone cannot flatten every other zone toward zero. A zone
    # with genuinely nobody in it still scores 0 -- that is correct, and it is
    # what makes "dangerous heat over an empty field is not an emergency" fall
    # out of the arithmetic instead of being asserted.
    p95 = float(np.percentile(density, 95))
    exposure = np.clip(density / p95, 0.0, 1.0) if p95 > 0 else np.zeros_like(density)

    out = {
        "city": city["name"],
        "h3_resolution": form["h3_resolution"],
        "method": "worldpop_zonal_api",
        "source": {
            "provider": "WorldPop",
            "dataset": dataset,
            "year": year,
            "api": wp.API_URL,
            "native_resolution_m": 100,
            "nature": "modelled residential population; census totals "
                      "disaggregated onto a grid using covariates",
        },
        "total_population": round(float(people.sum()), 1),
        "density_per_km2": {
            "min": round(float(density.min()), 1),
            "p50": round(float(np.median(density)), 1),
            "p95": round(p95, 1),
            "max": round(float(density.max()), 1),
        },
        "exposure_scaling": {
            "method": "density / p95(density), clipped to [0, 1]",
            "p95_per_km2": round(p95, 1),
        },
        "cells": {
            cell: {
                "population": round(float(people[i]), 1),
                "density_per_km2": round(float(density[i]), 1),
                "exposure": round(float(exposure[i]), 4),
            }
            for i, cell in enumerate(cells)
        },
    }

    dest = ROOT / "data" / "processed" / f"population_{slug}.json"
    dest.write_text(json.dumps(out, indent=1), encoding="utf-8")

    print(f"\n{RULE}")
    print(f"total population across {len(cells)} zones: {people.sum():,.0f}")
    print(f"density per km2: min {density.min():,.0f} | "
          f"median {np.median(density):,.0f} | p95 {p95:,.0f} | "
          f"max {density.max():,.0f}")
    print(f"{RULE}")
    print(f"  wrote -> {dest.relative_to(ROOT)}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    main(sys.argv[1], force="--force" in sys.argv)
