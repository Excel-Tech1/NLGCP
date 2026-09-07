"""Network-error observation model (Phase 6 spatial records).

Builds the general network-error records consumed by the interpolation
layer. Fields unsupported by evidence are None with the reason carried in
``quality_flags``/``provenance`` rather than invented.
"""

from __future__ import annotations

import math
from typing import Any

from .models import SpatialRecord, StationCoordinate


def baseline_length_m(
    a: tuple[float, float, float], b: tuple[float, float, float]
) -> float:
    return math.dist(a, b)


def ecef_to_local_enu(
    station_ecef: tuple[float, float, float],
    origin_ecef: tuple[float, float, float],
) -> tuple[float, float, float]:
    """Station offset in a local ENU frame about the origin (metres)."""
    ox, oy, oz = origin_ecef
    dx = (station_ecef[0] - ox, station_ecef[1] - oy, station_ecef[2] - oz)
    lon = math.atan2(oy, ox)
    lat = math.atan2(oz, math.hypot(ox, oy))
    s_lat, c_lat = math.sin(lat), math.cos(lat)
    s_lon, c_lon = math.sin(lon), math.cos(lon)
    return (
        -s_lon * dx[0] + c_lon * dx[1],
        -s_lat * c_lon * dx[0] - s_lat * s_lon * dx[1] + c_lat * dx[2],
        c_lat * c_lon * dx[0] + c_lat * s_lon * dx[1] + s_lat * dx[2],
    )


def build_spatial_records(
    *,
    epoch_iso: str,
    satellite_id: str,
    constellation: str,
    target: StationCoordinate,
    references: list[StationCoordinate],
    iono_by_station: dict[str, float | None],
    tropo_by_station: dict[str, float | None],
    elevation_by_station: dict[str, float | None],
    azimuth_by_station: dict[str, float | None],
    provenance: str,
) -> list[SpatialRecord]:
    """Assemble one record per reference station for an epoch/satellite."""
    target_xyz = (target.x_m, target.y_m, target.z_m)
    records: list[SpatialRecord] = []
    for ref in references:
        ref_xyz = (ref.x_m, ref.y_m, ref.z_m)
        iono = iono_by_station.get(ref.station_id)
        tropo = tropo_by_station.get(ref.station_id)
        flags: list[str] = []
        if iono is None:
            flags.append("ionosphere_proxy unavailable: no dual-frequency GF arc")
        if tropo is None:
            flags.append("troposphere_proxy unavailable: no elevation/ephemeris")
        combined: float | None = None
        if iono is not None and tropo is not None:
            combined = iono + tropo
        elif iono is not None or tropo is not None:
            flags.append("combined_residual partial: single component only")
            combined = iono if iono is not None else tropo
        else:
            flags.append("combined_residual unavailable: no component proxies")
        records.append(SpatialRecord(
            epoch_iso=epoch_iso,
            satellite_id=satellite_id,
            constellation=constellation,
            reference_station=ref.station_id,
            target_station=target.station_id,
            station_x_m=ref.x_m,
            station_y_m=ref.y_m,
            station_z_m=ref.z_m,
            baseline_length_m=baseline_length_m(ref_xyz, target_xyz),
            azimuth_deg=azimuth_by_station.get(ref.station_id),
            elevation_deg=elevation_by_station.get(ref.station_id),
            ionosphere_proxy_m=iono,
            troposphere_proxy_m=tropo,
            combined_residual_m=combined,
            quality_flags=tuple(flags),
            provenance=provenance,
        ))
    return records


def records_to_rows(records: list[SpatialRecord]) -> list[dict[str, Any]]:
    """Serialise records to machine-readable rows."""
    rows: list[dict[str, Any]] = []
    for record in records:
        rows.append({
            "epoch": record.epoch_iso,
            "satellite": record.satellite_id,
            "constellation": record.constellation,
            "reference_station": record.reference_station,
            "target_station": record.target_station,
            "station_x_m": record.station_x_m,
            "station_y_m": record.station_y_m,
            "station_z_m": record.station_z_m,
            "baseline_length_m": record.baseline_length_m,
            "azimuth_deg": record.azimuth_deg,
            "elevation_deg": record.elevation_deg,
            "ionosphere_proxy_m": record.ionosphere_proxy_m,
            "troposphere_proxy_m": record.troposphere_proxy_m,
            "combined_residual_m": record.combined_residual_m,
            "quality_flags": list(record.quality_flags),
            "provenance": record.provenance,
        })
    return rows
