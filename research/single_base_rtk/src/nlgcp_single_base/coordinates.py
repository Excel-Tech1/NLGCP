"""Coordinate helpers for experiment geometry and residual reporting."""

from __future__ import annotations

from dataclasses import dataclass
from math import atan2, cos, degrees, hypot, isfinite, radians, sin, sqrt

WGS84_A_M = 6378137.0
WGS84_F = 1.0 / 298.257223563
WGS84_E2 = WGS84_F * (2.0 - WGS84_F)


@dataclass(frozen=True)
class GeodeticCoordinate:
    """Latitude, longitude and ellipsoidal height."""

    latitude_deg: float
    longitude_deg: float
    height_m: float


@dataclass(frozen=True)
class EcefCoordinate:
    """Earth-centred, Earth-fixed coordinate in metres."""

    x_m: float
    y_m: float
    z_m: float


def geodetic_to_ecef(coordinate: GeodeticCoordinate) -> EcefCoordinate:
    """Convert a WGS84 geodetic coordinate to ECEF."""

    lat = radians(coordinate.latitude_deg)
    lon = radians(coordinate.longitude_deg)
    sin_lat = sin(lat)
    n = WGS84_A_M / sqrt(1.0 - WGS84_E2 * sin_lat * sin_lat)
    x = (n + coordinate.height_m) * cos(lat) * cos(lon)
    y = (n + coordinate.height_m) * cos(lat) * sin(lon)
    z = (n * (1.0 - WGS84_E2) + coordinate.height_m) * sin_lat
    return EcefCoordinate(x_m=x, y_m=y, z_m=z)


def ecef_to_geodetic(coordinate: EcefCoordinate) -> GeodeticCoordinate:
    """Convert ECEF metres to WGS84 geodetic coordinates."""

    a = WGS84_A_M
    b = a * (1.0 - WGS84_F)
    ep2 = (a * a - b * b) / (b * b)
    p = hypot(coordinate.x_m, coordinate.y_m)
    theta = atan2(coordinate.z_m * a, p * b)
    lon = atan2(coordinate.y_m, coordinate.x_m)
    lat = atan2(
        coordinate.z_m + ep2 * b * sin(theta) ** 3,
        p - WGS84_E2 * a * cos(theta) ** 3,
    )
    n = a / sqrt(1.0 - WGS84_E2 * sin(lat) ** 2)
    height = p / cos(lat) - n
    return GeodeticCoordinate(
        latitude_deg=degrees(lat),
        longitude_deg=degrees(lon),
        height_m=height,
    )


def baseline_distance_m(base: EcefCoordinate, rover: EcefCoordinate) -> float:
    """Calculate physical ECEF baseline distance in metres."""

    return sqrt(
        (base.x_m - rover.x_m) ** 2
        + (base.y_m - rover.y_m) ** 2
        + (base.z_m - rover.z_m) ** 2
    )


def ecef_distance_m(first: EcefCoordinate, second: EcefCoordinate) -> float:
    """Calculate straight-line distance between two ECEF coordinates."""

    return baseline_distance_m(first, second)


def ensure_finite_ecef(coordinate: EcefCoordinate) -> None:
    """Reject non-finite coordinate components."""

    if not all(isfinite(value) for value in (coordinate.x_m, coordinate.y_m, coordinate.z_m)):
        raise ValueError("ECEF coordinate contains non-finite values")


def ecef_delta_to_enu(
    delta: EcefCoordinate,
    reference: GeodeticCoordinate,
) -> tuple[float, float, float]:
    """Rotate an ECEF delta into local east, north, up components."""

    lat = radians(reference.latitude_deg)
    lon = radians(reference.longitude_deg)
    east = -sin(lon) * delta.x_m + cos(lon) * delta.y_m
    north = (
        -sin(lat) * cos(lon) * delta.x_m
        - sin(lat) * sin(lon) * delta.y_m
        + cos(lat) * delta.z_m
    )
    up = (
        cos(lat) * cos(lon) * delta.x_m
        + cos(lat) * sin(lon) * delta.y_m
        + sin(lat) * delta.z_m
    )
    return east, north, up
