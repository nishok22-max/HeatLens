"""Build the H3 grid and fetch urban form -> per-cell temperature offsets.

Run once per city. Everything is cached, so a re-run is instant and an
interrupted run resumes from where it stopped.

    python scripts/02_urban_form.py config/ahmedabad.yaml
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np
import yaml

from heatstress import spatial as sp
from heatstress.sources.osm import OSMUrbanForm

ROOT = Path(__file__).resolve().parents[1]


def main(config_path: str) -> None:
    config = yaml.safe_load(Path(config_path).read_text(encoding="utf-8"))
    city, grid_cfg, uhi = config["city"], config["grid"], config["urban_heat"]
    slug = city["name"].lower().replace(" ", "_")

    cells = sp.build_grid(city["bbox"], grid_cfg["h3_resolution"])
    print(f"{city['name']}: {len(cells)} H3 cells at resolution "
          f"{grid_cfg['h3_resolution']}")

    source = OSMUrbanForm()
    form = source.fetch(
        city["bbox"], cells, grid_cfg["h3_resolution"],
        include_buildings=uhi.get("include_buildings", False),
    )
    incomplete = bool(getattr(source, "failed_tiles", []))

    intensity = form.composite(cells)
    offset = sp.urban_heat_offset(intensity, uhi["uhi_amplitude_c"])

    # A layer with no coverage contributes nothing whatever its weight, so the
    # formula's real composition is printed and stored rather than assumed.
    coverage = form.coverage(cells)
    print("\nlayer coverage in the composite formula:")
    print(sp.format_coverage(coverage))

    out = {
        "city": city["name"],
        # Recorded so downstream consumers can see the surface is partial.
        "incomplete_coverage": incomplete,
        "failed_tile_queries": [f"tile {i} / {k}" for i, k, _ in
                                getattr(source, "failed_tiles", [])],
        "h3_resolution": grid_cfg["h3_resolution"],
        "uhi_amplitude_c": uhi["uhi_amplitude_c"],
        # Which layers actually carry the formula on this surface. Stored, not
        # just printed, so downstream consumers can show it too.
        "layer_coverage": {
            name: {k: round(v, 4) if isinstance(v, float) else v
                   for k, v in row.items()}
            for name, row in coverage.items()
        },
        "cells": {
            cell: {
                "intensity": round(float(intensity[i]), 4),
                "d_ta_c": round(float(offset[i]), 3),
                "built": round(form.built.get(cell, 0.0), 4),
                "roads": round(form.roads.get(cell, 0.0), 4),
                "green": round(form.green.get(cell, 0.0), 4),
                "water": round(form.water.get(cell, 0.0), 4),
            }
            for i, cell in enumerate(cells)
        },
    }

    dest = ROOT / "data" / "processed" / f"urban_form_{slug}.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(out), encoding="utf-8")

    print(f"\nintensity  min={intensity.min():.3f}  max={intensity.max():.3f}")
    print(f"dTa offset min={offset.min():+.2f}  max={offset.max():+.2f}  "
          f"spread={offset.max() - offset.min():.2f} C")
    print(f"written -> {dest.relative_to(ROOT)}")
    if incomplete:
        print("\n  *** COVERAGE INCOMPLETE -- re-run to fill the gaps. ***")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "config/ahmedabad.yaml")
