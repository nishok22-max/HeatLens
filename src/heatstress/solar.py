"""Solar geometry: what the Liljegren WBGT model needs and Open-Meteo does not give.

``thermofeel.calculate_wbgt_liljegren`` requires two quantities beyond ordinary
weather variables:

  * ``cos_sza`` -- cosine of the solar zenith angle, which sets how obliquely the
    beam strikes a body, and
  * ``fdir``    -- the fraction of global irradiance arriving as direct beam
    rather than diffuse sky.

Both are computed here in pure numpy and closed-form. Not because scipy is
unavailable -- it imports fine -- but because a closed-form solar position has no
iteration to diverge, runs vectorised over 392 cells x 264 hours without thought,
and keeps the dependency list short enough that the 6-hourly CI job installs in
seconds.

All angles are radians internally and degrees at the public surface.
Times are **UTC**. Ahmedabad is UTC+5:30 -- convert before calling.
"""

from __future__ import annotations

import numpy as np

__all__ = [
    "solar_declination",
    "equation_of_time",
    "cos_solar_zenith_angle",
    "extraterrestrial_normal_irradiance",
    "direct_fraction_erbs",
    "direct_fraction_from_components",
]

SOLAR_CONSTANT_WM2 = 1361.0


def _fractional_year(day_of_year, hour_utc):
    """Fractional year gamma, radians. NOAA solar position algorithm."""
    doy = np.asarray(day_of_year, dtype=float)
    hr = np.asarray(hour_utc, dtype=float)
    return (2.0 * np.pi / 365.0) * (doy - 1.0 + (hr - 12.0) / 24.0)


def equation_of_time(day_of_year, hour_utc=12.0):
    """Equation of time, minutes. NOAA approximation.

    The offset between apparent solar time and mean solar time, caused by
    Earth's orbital eccentricity and axial tilt. Ignoring it misplaces solar noon
    by up to ~16 minutes, which matters when the whole point is the 15:00 peak.
    """
    g = _fractional_year(day_of_year, hour_utc)
    return 229.18 * (
        0.000075
        + 0.001868 * np.cos(g)
        - 0.032077 * np.sin(g)
        - 0.014615 * np.cos(2 * g)
        - 0.040849 * np.sin(2 * g)
    )


def solar_declination(day_of_year, hour_utc=12.0):
    """Solar declination, radians. NOAA series approximation."""
    g = _fractional_year(day_of_year, hour_utc)
    return (
        0.006918
        - 0.399912 * np.cos(g)
        + 0.070257 * np.sin(g)
        - 0.006758 * np.cos(2 * g)
        + 0.000907 * np.sin(2 * g)
        - 0.002697 * np.cos(3 * g)
        + 0.00148 * np.sin(3 * g)
    )


def cos_solar_zenith_angle(latitude_deg, longitude_deg, day_of_year, hour_utc):
    """Cosine of the solar zenith angle, clipped to [0, 1].

    Zero at and below the horizon, so night hours contribute no direct beam.

    Args:
        latitude_deg:  north positive
        longitude_deg: **east positive** (Ahmedabad is +72.58)
        day_of_year:   1-366
        hour_utc:      fractional hours UTC, e.g. 9.5 for 09:30 UTC (15:00 IST)
    """
    lat = np.radians(np.asarray(latitude_deg, dtype=float))
    lon = np.asarray(longitude_deg, dtype=float)
    hr = np.asarray(hour_utc, dtype=float)

    decl = solar_declination(day_of_year, hr)
    eot = equation_of_time(day_of_year, hr)

    # True solar time, minutes past local midnight.
    tst = (hr * 60.0) + eot + (4.0 * lon)
    hour_angle = np.radians((tst / 4.0) - 180.0)

    cos_sza = np.sin(lat) * np.sin(decl) + np.cos(lat) * np.cos(decl) * np.cos(hour_angle)
    return np.clip(cos_sza, 0.0, 1.0)


def extraterrestrial_normal_irradiance(day_of_year):
    """Solar irradiance at the top of the atmosphere, normal incidence, W/m2.

    Includes the eccentricity correction (~+/-3.3% across the year).
    """
    doy = np.asarray(day_of_year, dtype=float)
    return SOLAR_CONSTANT_WM2 * (1.0 + 0.033 * np.cos(2.0 * np.pi * doy / 365.0))


def direct_fraction_from_components(direct_wm2, diffuse_wm2):
    """Direct-beam fraction of global irradiance, 0-1, from measured components.

    Preferred path: Open-Meteo serves ``direct_radiation`` and
    ``diffuse_radiation`` directly, so no empirical model is needed. Falls back
    to 0 where the sun is down and both components vanish.
    """
    dir_ = np.clip(np.asarray(direct_wm2, dtype=float), 0.0, None)
    dif = np.clip(np.asarray(diffuse_wm2, dtype=float), 0.0, None)
    total = dir_ + dif
    return np.where(total > 1.0, dir_ / np.maximum(total, 1e-9), 0.0)


def direct_fraction_erbs(ghi_wm2, cos_sza, day_of_year):
    """Direct-beam fraction, 0-1, estimated from GHI alone. Erbs et al. (1982).

    Fallback for data sources that report only global horizontal irradiance.
    Works through the clearness index kt = GHI / extraterrestrial horizontal:

        kt <= 0.22 : kd = 1 - 0.09*kt                         (overcast)
        kt <= 0.80 : quartic polynomial                       (partly cloudy)
        kt >  0.80 : kd = 0.165                               (clear)

    where kd is the *diffuse* fraction, so fdir = 1 - kd.

    APPROXIMATION: an empirical fit derived from US midwestern data. Prefer
    ``direct_fraction_from_components`` whenever the components are available.
    """
    ghi = np.clip(np.asarray(ghi_wm2, dtype=float), 0.0, None)
    mu = np.clip(np.asarray(cos_sza, dtype=float), 0.0, 1.0)

    e0h = extraterrestrial_normal_irradiance(day_of_year) * mu
    kt = np.where(e0h > 1.0, ghi / np.maximum(e0h, 1e-9), 0.0)
    kt = np.clip(kt, 0.0, 1.0)

    kd_low = 1.0 - 0.09 * kt
    kd_mid = (
        0.9511
        - 0.1604 * kt
        + 4.388 * kt**2
        - 16.638 * kt**3
        + 12.336 * kt**4
    )
    kd = np.where(kt <= 0.22, kd_low, np.where(kt <= 0.80, kd_mid, 0.165))
    kd = np.clip(kd, 0.0, 1.0)

    # Sun below the horizon: no beam at all.
    return np.where(mu > 0.0, np.clip(1.0 - kd, 0.0, 1.0), 0.0)
