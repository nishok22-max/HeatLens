"""Compute per-cell, per-hour thermal indices and risk for the hindcast window.

    python scripts/04_compute_indices.py config/ahmedabad.yaml [urban_form.json]

Reads the city-level weather series and the per-cell urban-heat offsets, applies
the physics graph to every cell-hour, and writes the processed cube used by the
kill gate and the web bake.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np
import pandas as pd
import yaml

from heatstress import physiology as ph
from heatstress import psychro as ps
from heatstress import risk as rk
from heatstress import solar as so
from heatstress import spatial as sp
from heatstress import thermal as th
from heatstress import vulnerability as vu
from heatstress.sources import openmeteo as om

ROOT = Path(__file__).resolve().parents[1]


def main(config_path: str, urban_form_path: str | None = None) -> None:
    config = yaml.safe_load(Path(config_path).read_text(encoding="utf-8"))
    city, hind = config["city"], config["hindcast"]
    slug = city["name"].lower().replace(" ", "_")
    tz = city["timezone_offset_hours"]

    # -- urban form -------------------------------------------------------
    if urban_form_path is None:
        urban_form_path, level = sp.resolve_urban_form(
            ROOT, slug, config["urban_heat"].get("mode", "lst"))
        print(f"urban form: {Path(urban_form_path).name}  [{level}]")
    form = json.loads(Path(urban_form_path).read_text(encoding="utf-8"))

    if form.get("method") == "satellite_lst":
        print(f"  measured pattern from {form['source']['instrument']}")
        print(f"  alpha = {form['alpha']} (the one number still assumed)")

    if form.get("SYNTHETIC_PLACEHOLDER"):
        print("!" * 70)
        print("! USING SYNTHETIC PLACEHOLDER URBAN FORM -- NOT REAL DATA")
        print("! Output is for pipeline development only. Do not demo.")
        print("!" * 70)

    cells = sorted(form["cells"])
    d_ta = np.array([form["cells"][c]["d_ta_c"] for c in cells])
    intensity = np.array([form["cells"][c]["intensity"] for c in cells])

    # -- city-level weather ----------------------------------------------
    weather = om.fetch_hourly(city["centre"]["lat"], city["centre"]["lon"],
                              hind["start_date"], hind["end_date"])
    n_hours, n_cells = len(weather), len(cells)
    print(f"{city['name']}: {n_cells} cells x {n_hours} hours "
          f"= {n_cells * n_hours:,} cell-hours")

    ta_city = weather["temperature_2m"].to_numpy()[:, None]      # (T, 1)
    rh_city = weather["relative_humidity_2m"].to_numpy()[:, None]
    wind = weather["wind_speed_10m"].to_numpy()[:, None]
    ghi = weather["shortwave_radiation"].to_numpy()[:, None]
    direct = weather["direct_radiation"].to_numpy()[:, None]
    diffuse = weather["diffuse_radiation"].to_numpy()[:, None]
    pressure = weather["surface_pressure"].to_numpy()[:, None]

    # -- downscale to cells ----------------------------------------------
    ta = ta_city + d_ta[None, :]                                  # (T, C)

    # Humidity is NOT held constant across cells. The urban heat island warms the
    # air; it does not add water to it. So vapour pressure is what carries across
    # cells, and relative humidity falls where the air is warmer:
    #
    #     RH_cell = 100 * e_city / es(Ta_cell)
    #
    # Holding RH fixed instead would invent moisture in exactly the hottest cells
    # and overstate their humid heat stress -- a subtle error that would bias the
    # entire result in the direction we want it to go, which is the most
    # dangerous kind.
    e_city = ps.vapour_pressure(ta_city, rh_city)
    rh = np.clip(100.0 * e_city / ps.saturation_vapour_pressure(ta), 1.0, 100.0)

    # Wind, irradiance and pressure are held uniform across the city: their
    # intra-urban variation needs building geometry we do not have. V1 item.
    wind_b = np.broadcast_to(wind, ta.shape)
    ghi_b = np.broadcast_to(ghi, ta.shape)
    press_b = np.broadcast_to(pressure, ta.shape)

    mu = so.cos_solar_zenith_angle(city["centre"]["lat"], city["centre"]["lon"],
                                   weather["day_of_year"].to_numpy(),
                                   weather["hour_utc"].to_numpy())[:, None]
    fdir = so.direct_fraction_from_components(direct, diffuse)
    mu_b = np.broadcast_to(mu, ta.shape)
    fdir_b = np.broadcast_to(fdir, ta.shape)

    # -- physics ----------------------------------------------------------
    print("  computing WBGT (Liljegren)...")
    wbgt = th.tf_wbgt_liljegren(ta, rh, wind_b, ghi_b, fdir_b, mu_b, press_b)

    print("  computing UTCI...")
    tg = th.globe_temperature_regression(ta, rh, ghi_b)
    mrt = th.tf_mrt_from_globe(ta, tg, wind_b)
    utci = th.tf_utci(ta, rh, wind_b, mrt)

    print("  computing Heat Index...")
    heat_index = th.heat_index(ta, rh)

    # -- risk -------------------------------------------------------------
    print("  composing risk...")
    hazard = rk.normalise_hazard(wbgt)

    # Exposure: measured population when script 14 has run, the old proxy
    # otherwise. The fallback is loud on purpose -- under mode `lst` the proxy
    # is a linear function of d_Ta, which makes risk a monotone transform of
    # WBGT and the whole composition informationally empty (DECISIONS D15).
    pop_exposure, pop_note = vu.load_population_exposure(ROOT, slug, cells)
    if pop_exposure is None:
        print(f"  exposure: PROXY (intensity) -- {pop_note}")
        print("            risk will not reorder zones relative to hazard.")
        surface = vu.PlaceholderVulnerability().build(cells, intensity=intensity)
    else:
        print(f"  exposure: MEASURED population -- {pop_note}")
        surface = vu.MeasuredPopulationVulnerability().build(
            cells, exposure=pop_exposure, intensity=intensity,
            provenance=pop_note)

    risk = vu.combine_risk(hazard,
                           np.broadcast_to(surface.exposure[None, :], ta.shape),
                           np.broadcast_to(surface.vulnerability[None, :], ta.shape))

    # -- persist ----------------------------------------------------------
    index_ist = weather.index + pd.Timedelta(hours=tz)
    dest = ROOT / "data" / "processed" / f"indices_{slug}.npz"
    np.savez_compressed(
        dest,
        cells=np.array(cells, dtype='U16'),
        # Fixed-width unicode, not object dtype: npz refuses to load object
        # arrays without allow_pickle, which we do not want to enable.
        timestamps_ist=np.array(index_ist.strftime('%Y-%m-%d %H:%M'),
                                dtype='U16'),
        air_temp=ta.astype(np.float32), rh=rh.astype(np.float32),
        wbgt=wbgt.astype(np.float32), utci=utci.astype(np.float32),
        heat_index=heat_index.astype(np.float32), risk=risk.astype(np.float32),
        d_ta=d_ta.astype(np.float32), intensity=intensity.astype(np.float32),
        exposure=surface.exposure.astype(np.float32),
        vulnerability=surface.vulnerability.astype(np.float32),
        exposure_is_measured=bool(surface.exposure_is_measured),
        exposure_provenance=str(surface.exposure_provenance),
        is_placeholder_urban=bool(form.get("SYNTHETIC_PLACEHOLDER", False)),
    )

    focus = f"{hind['focus_date']} {hind['focus_hour_ist']:02d}"
    mask = np.array([str(t).startswith(focus) for t in index_ist])
    if mask.any():
        row = wbgt[mask][0]
        print(f"\n  at {focus}:00 IST -- WBGT min {row.min():.2f}  "
              f"max {row.max():.2f}  spread {row.max() - row.min():.2f} C")
    print(f"  written -> {dest.relative_to(ROOT)}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "config/ahmedabad.yaml",
         sys.argv[2] if len(sys.argv) > 2 else None)
