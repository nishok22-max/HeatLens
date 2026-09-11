"""Turn the measured satellite anomaly into the published temperature offsets.

    python scripts/12_downscaled_offsets.py config/ahmedabad.yaml

Reads ``satellite_<city>.json`` and writes ``urban_form_lst_<city>.json`` in the
same schema the OpenStreetMap file uses, plus the satellite columns. Scripts 04,
06 and ``live.py`` then pick it up through the three-level resolver with no
other change.

THE ONE ASSUMPTION LEFT
-----------------------
    dTa_zone = alpha * (LST_zone - LST_city_mean)

The anomaly is measured. ``alpha`` -- how much of a surface-temperature
difference shows up in the *air* a person breathes -- is not, and cannot be
without ground weather stations across the city. Surface UHI is several times
larger than air UHI, so quoting the surface anomaly as an air temperature would
overstate the result by a factor of two or three. The sweep over
``alpha_range`` is printed for exactly that reason.

WHY THE OBSERVATION AND NOT A MODEL PREDICTION (ARCHITECTURE D14)
-----------------------------------------------------------------
A fitted model's predictions pull toward the mean, which would shrink the
city-wide spread by roughly the square root of the fit quality -- and that
spread is the number the project's own go/no-go test is scored on. So the
operational number comes from the observation. A model's proper jobs are gaps,
error bars and what-if; the gap-filling here is a declared neighbour mean, not
a fit, and every filled zone says so.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import h3
import numpy as np
import yaml

from heatstress import satellite as sat
from heatstress import spatial as sp

ROOT = Path(__file__).resolve().parents[1]
RULE = "=" * 74

# How far out to look when filling a zone the satellite could not measure.
# 3 rings is about 2.5 km; beyond that a "neighbour" is a different part of the
# city and the fill would be fiction.
MAX_FILL_RINGS = 3


def fill_gaps(cells, anomaly, provenance):
    """Fill unmeasured zones with the mean of their measured neighbours.

    Declared, not fitted: a zone filled this way is labelled ``filled_neighbour``
    and stays labelled all the way to the map, so a viewer can see which parts
    of the picture are measurement and which are interpolation.
    """
    known = {c: a for c, a in zip(cells, anomaly) if a is not None}
    filled = {}
    for cell, value in zip(cells, anomaly):
        if value is not None:
            continue
        for ring in range(1, MAX_FILL_RINGS + 1):
            neighbours = [known[n] for n in h3.grid_disk(cell, ring)
                          if n in known]
            if neighbours:
                filled[cell] = float(np.mean(neighbours))
                break
    for cell, value in filled.items():
        provenance[cell] = sat.FILLED_NEIGHBOUR
    return filled


def main(config_path: str) -> None:
    config = yaml.safe_load(Path(config_path).read_text(encoding="utf-8"))
    city, grid_cfg, uhi = config["city"], config["grid"], config["urban_heat"]
    slug = city["name"].lower().replace(" ", "_")
    alpha = uhi["alpha"]

    satellite_path = ROOT / "data" / "processed" / f"satellite_{slug}.json"
    if not satellite_path.exists():
        raise SystemExit(
            f"{satellite_path.relative_to(ROOT)} does not exist. Run "
            "scripts/01_satellite_lst.py first."
        )
    export = json.loads(satellite_path.read_text(encoding="utf-8"))
    cells = sorted(export["cells"])

    print(RULE)
    print(f"SATELLITE OFFSETS -- {city['name']}")
    print(f"  {export['source']['instrument']}")
    print(f"  dTa = alpha x (LST_zone - LST_city_mean),  alpha = {alpha}")
    print(RULE)

    anomaly = [export["cells"][c]["lst_anomaly_c"] for c in cells]
    provenance = {c: export["cells"][c]["provenance"] for c in cells}
    filled = fill_gaps(cells, anomaly, provenance)
    values = np.array([a if a is not None else filled[c]
                       for c, a in zip(cells, anomaly)], dtype=float)
    if np.isnan(values).any():
        raise SystemExit(
            f"{int(np.isnan(values).sum())} zones have no measurement and no "
            f"measured neighbour within {MAX_FILL_RINGS} rings."
        )

    # Re-centre across every zone. The satellite anomaly was centred on the
    # *observed* zones; after filling, re-centring keeps the offsets summing to
    # zero, which is what makes this a redistribution of the city forecast
    # rather than an injection of extra heat into it.
    values = values - values.mean()
    d_ta = alpha * values
    intensity = sp._minmax(values)

    night = np.array([export["cells"][c].get("lst_night_anomaly_c") or np.nan
                      for c in cells], dtype=float)

    # OpenStreetMap land cover, carried through to DESCRIBE each zone -- the
    # "built-up / green / water" text in the zone panel and the river and park
    # outlines on the map. It is deliberately not an input to the offsets:
    # scripts/13_compare_sources.py shows OSM features cannot locate heat in
    # this city (held-out rank agreement with the satellite -0.18), so letting
    # them touch d_ta would undo the measurement. Zeros when the file is absent.
    osm_path = ROOT / "data" / "processed" / f"urban_form_{slug}.json"
    osm = (json.loads(osm_path.read_text(encoding="utf-8"))
           if osm_path.exists() else None)
    osm_cells = osm["cells"] if osm else {}

    def land_cover(cell):
        raw = osm_cells.get(cell, {})
        return {k: round(float(raw.get(k, 0.0)), 4)
                for k in ("built", "roads", "green", "water")}

    out = {
        "city": city["name"],
        "h3_resolution": grid_cfg["h3_resolution"],
        "method": "satellite_lst",
        "source": export["source"],
        "alpha": alpha,
        # Kept so any consumer still reading this key gets a truthful answer:
        # the equivalent full-city air-temperature spread this method produces.
        "uhi_amplitude_c": round(float(np.ptp(d_ta)), 3),
        "city_mean_lst_c": export["city_mean_lst_c"],
        "night_city_mean_lst_c": export.get("night_city_mean_lst_c"),
        "coverage": export["coverage"],
        "cross_check": export["cross_check"],
        "incomplete_coverage": bool(filled),
        "cells": {
            cell: {
                # The two keys every downstream consumer reads.
                "intensity": round(float(intensity[i]), 4),
                "d_ta_c": round(float(d_ta[i]), 3),
                # The satellite columns, carried through so the map and the
                # provenance panel can show what is measured and what is not.
                "lst_c": export["cells"][cell]["lst_c"],
                "lst_anomaly_c": round(float(values[i]), 3),
                "lst_night_c": export["cells"][cell].get("lst_night_c"),
                "lst_night_anomaly_c": export["cells"][cell].get(
                    "lst_night_anomaly_c"),
                "valid_obs": export["cells"][cell]["valid_px"],
                "provenance": provenance[cell],
                # Descriptive only -- see land_cover() above. Previously zero
                # for every zone, which made the zone panel call riverside
                # zones "almost no water" and removed the map's outlines.
                **land_cover(cell),
            }
            for i, cell in enumerate(cells)
        },
    }

    dest = ROOT / "data" / "processed" / f"urban_form_lst_{slug}.json"
    dest.write_text(json.dumps(out), encoding="utf-8")

    # -- report, including the honest comparison --------------------------
    counts = {}
    for value in provenance.values():
        counts[value] = counts.get(value, 0) + 1
    print("\nprovenance per zone:")
    for name in sat.PROVENANCE_VALUES:
        if name in counts:
            print(f"  {name:<20} {counts[name]:>4}")

    print(f"\nsurface anomaly  {values.min():+.2f} to {values.max():+.2f} C   "
          f"spread {np.ptp(values):.2f} C")
    print(f"air offset       {d_ta.min():+.2f} to {d_ta.max():+.2f} C   "
          f"spread {np.ptp(d_ta):.2f} C   (alpha = {alpha})")
    lo, hi = uhi["alpha_range"]
    print(f"  across the alpha range {lo}-{hi}: "
          f"{np.ptp(values) * lo:.2f} to {np.ptp(values) * hi:.2f} C")
    if np.isfinite(night).any():
        print(f"night anomaly    {np.nanmin(night):+.2f} to "
              f"{np.nanmax(night):+.2f} C   spread "
              f"{np.nanmax(night) - np.nanmin(night):.2f} C "
              "(the pattern that matters for recovery)")

    if osm:
        old = np.array([osm["cells"][c]["d_ta_c"] for c in cells])
        agreement = sat.rank_agreement(old, d_ta)
        print(f"\n{RULE}\nMEASURED vs THE METHOD IT REPLACES\n{RULE}")
        print(f"  old (OpenStreetMap composite) spread : "
              f"{np.ptp(old):5.2f} C   [pattern assumed]")
        print(f"  new (satellite surface temperature)  : "
              f"{np.ptp(d_ta):5.2f} C   [pattern measured]")
        print(f"  rank agreement between them          : {agreement:5.3f}")
        moved = int((np.abs(old - d_ta) > 1.0).sum())
        print(f"  zones whose offset moves by >1 C      : {moved} of {len(cells)}")
        if agreement < 0.5:
            print("\n  The two disagree about which parts of the city are hot.")
            print("  That is the finding, not a bug: the old pattern was a")
            print("  hand-weighted guess whose largest term (buildings) was")
            print("  empty in every zone, so it had collapsed into road")
            print("  density. This is why the satellite path exists.")

    print(f"\nwritten -> {dest.relative_to(ROOT)} "
          f"({dest.stat().st_size / 1024:.0f} KB)")
    print("next: scripts 04 -> 05 -> 06 pick this up automatically.")
    print(RULE)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "config/ahmedabad.yaml")
