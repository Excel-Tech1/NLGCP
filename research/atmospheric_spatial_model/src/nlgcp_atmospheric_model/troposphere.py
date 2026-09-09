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


# Niell (1996) Table 3, independently transcribed from pinned RTKLIB nmf.
_NMF = (
    (1.2769934e-3, 1.2683230e-3, 1.2465397e-3, 1.2196049e-3, 1.2045996e-3),
    (2.9153695e-3, 2.9152299e-3, 2.9288445e-3, 2.9022565e-3, 2.9024912e-3),
    (62.610505e-3, 62.837393e-3, 63.721774e-3, 63.824265e-3, 64.258455e-3),
    (0.0, 1.2709626e-5, 2.6523662e-5, 3.4000452e-5, 4.1202191e-5),
    (0.0, 2.1414979e-5, 3.0160779e-5, 7.2562722e-5, 11.723375e-5),
    (0.0, 9.0128400e-5, 4.3497037e-5, 84.795348e-5, 170.37206e-5),
    (5.8021897e-4, 5.6794847e-4, 5.8118019e-4, 5.9727542e-4, 6.1641693e-4),
    (1.4275268e-3, 1.5138625e-3, 1.4572752e-3, 1.5007428e-3, 1.7599082e-3),
    (4.3472961e-2, 4.6729510e-2, 4.3908931e-2, 4.4626982e-2, 5.4736038e-2),
)


def _latitude_coefficient(row: tuple[float, ...], lat_rad: float) -> float:
    if not math.isfinite(lat_rad) or abs(lat_rad) > math.pi / 2:
        raise ValueError("geodetic latitude must be finite radians")
    index = min(4.0, max(0.0, (abs(math.degrees(lat_rad)) - 15.0) / 15.0))
    lo = min(3, int(index))
    return row[lo] + (index - lo) * (row[lo + 1] - row[lo])


def _niell_coeffs(lat_rad: float, height_m: float, doy: float) -> tuple[list[float], float]:
    if not math.isfinite(height_m) or not 1 <= doy < 367:
        raise ValueError("invalid height/day for Niell mapping")
    seasonal = math.cos(2.0 * math.pi * ((doy - 28) / 365.25 + (0.5 if lat_rad < 0 else 0)))
    return [
        _latitude_coefficient(_NMF[i], lat_rad)
        - _latitude_coefficient(_NMF[i + 3], lat_rad) * seasonal
        for i in range(3)
    ], seasonal


def niell_mapping(elevation_deg: float, coeffs: list[float]) -> float:
    """Niell continued-fraction mapping function value."""
    if not math.isfinite(elevation_deg) or not 3.0 < elevation_deg <= 90.0:
        raise ValueError("Niell mapping undefined below 3 deg elevation")
    sin_e = math.sin(math.radians(elevation_deg))
    a, b, c = coeffs[0], coeffs[1], coeffs[2]
    num = 1.0 + a / (1.0 + b / (1.0 + c))
    den = sin_e + a / (sin_e + b / (sin_e + c))
    return num / den


def niell_hydrostatic_mapping(
    elevation_deg: float, lat_rad: float, height_m: float, doy: float
) -> float:
    coeffs, _ = _niell_coeffs(lat_rad, height_m, doy)
    correction = (
        (
            1.0 / math.sin(math.radians(elevation_deg))
            - niell_mapping(elevation_deg, [2.53e-5, 5.49e-3, 1.14e-3])
        )
        * height_m
        / 1000
    )
    return niell_mapping(elevation_deg, coeffs) + correction


def niell_wet_mapping(elevation_deg: float, lat_rad: float = 0.0) -> float:
    """Niell wet coefficients interpolated in absolute geodetic latitude."""
    return niell_mapping(elevation_deg, [_latitude_coefficient(row, lat_rad) for row in _NMF[6:]])


def ecef_to_geodetic(station_ecef_m: tuple[float, float, float]) -> tuple[float, float, float]:
    """Shared WGS84 ellipsoid conversion; radians/radians/ellipsoidal metres."""
    from nlgcp_single_base.coordinates import EcefCoordinate
    from nlgcp_single_base.coordinates import ecef_to_geodetic as convert

    point = convert(EcefCoordinate(*station_ecef_m))
    return math.radians(point.latitude_deg), math.radians(point.longitude_deg), point.height_m


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
    m_w = niell_wet_mapping(elevation_deg, lat_rad)
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
