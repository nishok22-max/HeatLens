"""THE KILL GATE. The Day-1 deliverable.

    python scripts/05_kill_gate.py config/ahmedabad.yaml

The prototype exists to answer one question: does meaningful intra-city thermal
stress variation actually show up? This script produces the number, honestly,
including the parts that are assumed rather than measured.

READ THE EPISTEMIC WARNING BELOW BEFORE QUOTING ANY OF THIS.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np
import yaml

from heatstress import killgate as kg
from heatstress import psychro as ps
from heatstress import risk as rk
from heatstress import solar as so
from heatstress import spatial as sp
from heatstress import thermal as th
from heatstress.sources import openmeteo as om

ROOT = Path(__file__).resolve().parents[1]

RULE = "=" * 74


def spread_report(name, values, unit="C"):
    lo, hi = float(np.min(values)), float(np.max(values))
    p10, p90 = float(np.percentile(values, 10)), float(np.percentile(values, 90))
    print(f"  {name:12s} min {lo:7.2f}  max {hi:7.2f}  "
          f"spread {hi - lo:6.2f} {unit}   p10-p90 {p90 - p10:5.2f} {unit}")
    return hi - lo


def main(config_path: str) -> None:
    config = yaml.safe_load(Path(config_path).read_text(encoding="utf-8"))
    city, hind, uhi, gate = (config["city"], config["hindcast"],
                             config["urban_heat"], config["kill_gate"])
    slug = city["name"].lower().replace(" ", "_")

    cube = np.load(ROOT / "data" / "processed" / f"indices_{slug}.npz",
                   allow_pickle=False)
    timestamps = cube["timestamps_ist"]
    focus = f"{hind['focus_date']} {hind['focus_hour_ist']:02d}"
    idx = kg.focus_index(timestamps, hind["focus_date"], hind["focus_hour_ist"])

    print(RULE)
    print(f"KILL GATE -- {city['name']}, {focus}:00 IST")
    print(RULE)

    if bool(cube["is_placeholder_urban"]):
        print("\n  *** SYNTHETIC PLACEHOLDER URBAN FORM IN USE ***")
        print("  The spatial pattern below is invented. Only the physical")
        print("  relationships (damping, sensitivity) carry over to real data.\n")

    print("\nIntra-city spread at the focus hour:")
    d_air = spread_report("air temp", cube["air_temp"][idx])
    d_wbgt = spread_report("WBGT", cube["wbgt"][idx])
    d_utci = spread_report("UTCI", cube["utci"][idx])
    d_hi = spread_report("heat index", cube["heat_index"][idx])
    spread_report("risk index", cube["risk"][idx], unit="  ")

    # -- the damping finding ---------------------------------------------
    print(f"\n{RULE}\nWHY WBGT SPREAD IS SMALLER THAN AIR-TEMPERATURE SPREAD\n{RULE}")
    print(f"  air temperature spread : {d_air:5.2f} C")
    print(f"  WBGT spread            : {d_wbgt:5.2f} C   "
          f"(damping ratio {d_wbgt / d_air:.2f})")
    print(f"  UTCI spread            : {d_utci:5.2f} C   "
          f"(amplification {d_utci / d_air:.2f})")
    print("""
  This is physics, not error. The urban heat island warms the air without
  adding water to it, so a hotter cell is also a *drier* cell. WBGT is 70%
  weighted on wet-bulb temperature, which barely moves -- so the temperature
  and humidity terms partly cancel and WBGT is damped.

  UTCI behaves the opposite way: it is driven by air temperature and radiant
  load rather than by evaporation, so intra-city differences are amplified.

  CONSEQUENCE FOR THE PRODUCT: WBGT is the wrong index to map for a *dry*
  heatwave. Choosing per-city, per-event which index to lead with is itself
  a finding worth presenting.""")

    # -- sensitivity to the assumed amplitude -----------------------------
    print(f"\n{RULE}\nSENSITIVITY TO THE ASSUMED UHI AMPLITUDE\n{RULE}")
    print("""  EPISTEMIC WARNING. The spatial *pattern* comes from real urban form,
  but the *amplitude* is a literature value, not a local measurement. So the
  spreads above are partly an input, not purely a discovery. The honest
  question is therefore: across the plausible literature range, does the
  resulting stress spread matter? That is what this sweep answers.
""")
    lo_amp, hi_amp = uhi["uhi_amplitude_range"]
    baseline = uhi["uhi_amplitude_c"]
    weather = om.fetch_hourly(city["centre"]["lat"], city["centre"]["lon"],
                              hind["start_date"], hind["end_date"])
    row = weather.iloc[idx]
    mu = float(so.cos_solar_zenith_angle(city["centre"]["lat"],
                                         city["centre"]["lon"],
                                         row["day_of_year"], row["hour_utc"]))
    fdir = float(so.direct_fraction_from_components(row["direct_radiation"],
                                                    row["diffuse_radiation"]))
    intensity = cube["intensity"]

    print(f"  {'amplitude':>10} {'dTa':>8} {'dWBGT':>8} {'dUTCI':>8} {'dRisk':>8}")
    for amp in np.linspace(lo_amp, hi_amp, 4):
        offset = sp.urban_heat_offset(intensity, amp)
        ta = row["temperature_2m"] + offset
        e = ps.vapour_pressure(row["temperature_2m"], row["relative_humidity_2m"])
        rh = np.clip(100.0 * e / ps.saturation_vapour_pressure(ta), 1.0, 100.0)
        wind = np.full_like(ta, row["wind_speed_10m"])
        ghi = np.full_like(ta, row["shortwave_radiation"])

        wbgt = th.tf_wbgt_liljegren(ta, rh, wind, ghi,
                                    np.full_like(ta, fdir), np.full_like(ta, mu),
                                    np.full_like(ta, row["surface_pressure"]))
        tg = th.globe_temperature_regression(ta, rh, ghi)
        utci = th.tf_utci(ta, rh, wind, th.tf_mrt_from_globe(ta, tg, wind))
        hazard = rk.normalise_hazard(wbgt)
        mark = "  <- config" if abs(amp - baseline) < 1e-6 else ""
        print(f"  {amp:10.1f} {np.ptp(ta):8.2f} {np.ptp(wbgt):8.2f} "
              f"{np.ptp(utci):8.2f} {np.ptp(hazard):8.3f}{mark}")

    # -- verdict ----------------------------------------------------------
    # The decision itself lives in heatstress.killgate and is tested against
    # the committed arrays, so a change to the urban-heat offset cannot flip
    # it unnoticed. This script only prints what that function returns.
    print(f"\n{RULE}\nVERDICT\n{RULE}")
    result = kg.verdict(d_wbgt, d_utci, gate["proceed_spread_c"],
                        gate["pivot_spread_c"])
    print(f"  Strongest thermal-stress spread: {result.spread_c:.2f} C  "
          f"(on {result.driver})")
    print(f"  Thresholds -- proceed >= {result.proceed_spread_c}, "
          f"pivot < {result.pivot_spread_c}")
    print(f"\n  >>> {result.decision}. {result.headline}")
    print(f"      margin {result.margin_c:+.2f} C against the threshold it "
          f"was scored on")
    print(f"\n{RULE}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "config/ahmedabad.yaml")
