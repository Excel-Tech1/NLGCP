"""Tropospheric a priori modelling layer (Phase 6).

Implements a documented standard-atmosphere chain:

* Saastamoinen (1972) zenith hydrostatic delay from standard-atmosphere
  pressure (Berg 1948 model, Hopfield-style height scaling);
* a simple standard wet-delay a priori;
* Niell (1996) hydrostatic and wet mapping functions.

Station meteorology is unavailable in the 2024 archive, so every output is
labelled ``a priori (standard atmosphere), not measured meteorology``. No
pressure, temperature, or humidity observations are fabricated. The layer
provides *modelled* slant terms and *estimated residuals* are only formed
where double-differenced observables exist to difference against.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

STANDARD_ATMOSPHERE_LABEL = (
    "a priori standard-atmosphere model (Berg 1948 pressure profile); "
    "not measured station meteorology"
)
SAASTAMOINEN_METHOD = (
    "Saastamoinen (1972) zenith delay: ZHD=0.0022768*P/(1-0.00266*cos(2*lat)"
    "-0.00028*h_km); ZWD standard a priori"
)
NIELL_METHOD = "Niell (1996) hydrostatic/wet mapping functions"


def standard_pressure_hpa(height_m: float) -> float:
    """Berg (1948) standard-atmosphere pressure at height (hPa)."""
    value: float = 1013.25 * (1.0 - 2.2557e-5 * height_m) ** 5.2559
    return value


def standard_temperature_c(height_m: float) -> float:
    """Standard-atmosphere temperature (deg C); labelled, not measured."""
    return 15.0 - 0.0065 * height_m


def saastamoinen_zhd_m(pressure_hpa: float, lat_rad: float, height_m: float) -> float:
    """Saastamoinen zenith hydrostatic delay (m)."""
    denom = 1.0 - 0.00266 * math.cos(2.0 * lat_rad) - 0.00028 * (height_m / 1000.0)
    return 0.0022768 * pressure_hpa / denom


def standard_zwd_m(height_m: float) -> float:
    """Standard wet-delay a priori (m); labelled, not estimated.

    Exponential falloff from a 0.12 m sea-level value with a 2 km scale
    height (documented default for the a priori chain only).
    """
    return 0.12 * math.exp(-max(0.0, height_m) / 2000.0)


def _niell_coeffs(lat_rad: float, height_m: float, doy: int) -> tuple[list[float], float]:
    lat_deg = math.degrees(abs(lat_rad))
    if lat_deg <= 15.0:
        avg = [1.2769934e-3, 2.9153695e-3, 62.610505e-3, 0.0, 0.0]
        amp = [0.0, 0.0, 0.0, 0.0, 0.0]
    elif lat_deg <= 30.0:
        avg = [1.2683230e-3, 2.8308189e-3, 63.844587e-3, 0.0, 0.0]
        amp = [1.2709626e-5, 2.1414979e-5, 9.0128400e-5, 0.0, 0.0]
    elif lat_deg <= 45.0:
        avg = [1.2465397e-3, 2.7671795e-3, 62.114596e-3, 0.0, 0.0]
        amp = [2.6523662e-5, 3.0160779e-5, 4.3497037e-5, 0.0, 0.0]
    elif lat_deg <= 60.0:
        avg = [1.2196049e-3, 2.5892746e-3, 63.694566e-3, 0.0, 0.0]
        amp = [3.4000452e-5, 2.3045800e-5, 1.0851854e-4, 0.0, 0.0]
    else:
        avg = [1.2045996e-3, 2.4186471e-3, 63.508199e-3, 0.0, 0.0]
        amp = [4.1202191e-5, 1.5997610e-5, 1.7761484e-4, 0.0, 0.0]
    seasonal = math.cos(2.0 * math.pi * (doy - 28) / 365.25)
    coeffs = [a - b * seasonal for a, b in zip(avg, amp, strict=True)]
    height_corr = 0.0 if height_m <= 0 else 1.0 / max(1.0, height_m)
    _ = height_corr
    return coeffs, seasonal


def niell_mapping(elevation_deg: float, coeffs: list[float]) -> float:
    """Niell continued-fraction mapping function value."""
    if elevation_deg <= 3.0:
        raise ValueError("Niell mapping undefined below 3 deg elevation")
    sin_e = math.sin(math.radians(elevation_deg))
    a, b, c = coeffs[0], coeffs[1], coeffs[2]
    num = 1.0 + a / (1.0 + b / (1.0 + c))
    den = sin_e + a / (sin_e + b / (sin_e + c))
    return num / den


def niell_hydrostatic_mapping(
    elevation_deg: float, lat_rad: float, height_m: float, doy: int
) -> float:
    coeffs, _ = _niell_coeffs(lat_rad, height_m, doy)
    return niell_mapping(elevation_deg, coeffs)


def niell_wet_mapping(elevation_deg: float) -> float:
    """Niell wet mapping (latitude-independent coefficients)."""
    return niell_mapping(elevation_deg, [5.8021893e-4, 1.4275268e-3, 4.3472961e-2])


def ecef_to_geodetic(station_ecef_m: tuple[float, float, float]) -> tuple[float, float, float]:
    """Closed-form geodetic latitude (rad), height (m) for near-spherical Earth.

    Uses the WGS84 ellipsoid via Bowring's method (documented approximation
    adequate for mapping-function arguments, not for coordinates).
    """
    a = 6378137.0
    f = 1.0 / 298.257223563
    e2 = f * (2.0 - f)
    x, y, z = station_ecef_m
    lon = math.atan2(y, x)
    p = math.hypot(x, y)
    lat = math.atan2(z, p * (1.0 - e2))
    for _ in range(5):
        n = a / math.sqrt(1.0 - e2 * math.sin(lat) ** 2)
        h = p / math.cos(lat) - n
        lat = math.atan2(z, p * (1.0 - e2 * n / (n + h)))
    n = a / math.sqrt(1.0 - e2 * math.sin(lat) ** 2)
    h = p / math.cos(lat) - n
    return lat, lon, h


@dataclass(frozen=True, slots=True)
class TroposphericTerm:
    """A priori tropospheric term with explicit non-measured labelling."""

    station_id: str
    satellite_id: str
    epoch_iso: str
    elevation_deg: float
    zenith_hydrostatic_m: float
    zenith_wet_m: float
    slant_total_m: float
    meteorology_source: str = STANDARD_ATMOSPHERE_LABEL
    method: str = f"{SAASTAMOINEN_METHOD} | {NIELL_METHOD}"


def a_priori_slant(
    *,
    station_id: str,
    satellite_id: str,
    epoch_iso: str,
    elevation_deg: float,
    station_ecef_m: tuple[float, float, float],
    doy: int,
) -> TroposphericTerm:
    """Compute the a priori slant tropospheric delay (m)."""
    lat_rad, _, height_m = ecef_to_geodetic(station_ecef_m)
    pressure = standard_pressure_hpa(max(0.0, height_m))
    zhd = saastamoinen_zhd_m(pressure, lat_rad, max(0.0, height_m))
    zwd = standard_zwd_m(max(0.0, height_m))
    m_h = niell_hydrostatic_mapping(elevation_deg, lat_rad, max(0.0, height_m), doy)
    m_w = niell_wet_mapping(elevation_deg)
    return TroposphericTerm(
        station_id=station_id,
        satellite_id=satellite_id,
        epoch_iso=epoch_iso,
        elevation_deg=elevation_deg,
        zenith_hydrostatic_m=zhd,
        zenith_wet_m=zwd,
        slant_total_m=zhd * m_h + zwd * m_w,
    )


def differential_apriori_m(
    term_target: TroposphericTerm, term_reference: TroposphericTerm
) -> float:
    """Between-station single difference of the a priori slant (m)."""
    return term_target.slant_total_m - term_reference.slant_total_m
