"""Deterministic network geometry utilities.

Only coordinates that passed provenance/verification gates are used.
No coordinates are invented: every station must be scientifically valid
in ``processed/single-base/derived-coordinates.json`` with an explicit
reference frame and coordinate epoch.
"""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from nlgcp_network_rtk import GEOMETRY_SCHEMA_VERSION
from nlgcp_network_rtk.models import BLOCKED_MESSAGE, NetworkBlocked


@dataclass(frozen=True, slots=True)
class StationGeometry:
    station_id: str
    ecef_x_m: float
    ecef_y_m: float
    ecef_z_m: float
    reference_frame: str
    coordinate_epoch: str
    provenance: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class NetworkGeometry:
    stations: tuple[StationGeometry, ...]
    baseline_matrix_m: dict[str, dict[str, float]]
    centroid_ecef_m: tuple[float, float, float]
    reference_to_rover_m: dict[str, float]
    nearest_reference: str | None
    farthest_reference: str | None
    mean_reference_distance_m: float | None
    network_spatial_extent_m: float
    triangle_area_m2: float | None
    coordinate_frame: str
    baseline_count: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": GEOMETRY_SCHEMA_VERSION,
            "coordinate_frame": self.coordinate_frame,
            "stations": [row.as_dict() for row in self.stations],
            "baseline_matrix_m": self.baseline_matrix_m,
            "centroid_ecef_m": list(self.centroid_ecef_m),
            "reference_to_rover_m": self.reference_to_rover_m,
            "nearest_reference": self.nearest_reference,
            "farthest_reference": self.farthest_reference,
            "mean_reference_distance_m": self.mean_reference_distance_m,
            "network_spatial_extent_m": self.network_spatial_extent_m,
            "triangle_area_m2": self.triangle_area_m2,
            "baseline_count": self.baseline_count,
        }


def load_verified_coordinates(data_root: Path) -> dict[str, dict[str, Any]]:
    """Load only scientifically valid station coordinates."""
    path = data_root / "processed" / "single-base" / "derived-coordinates.json"
    if not path.is_file():
        raise NetworkBlocked(f"{BLOCKED_MESSAGE}: verified coordinates unavailable: {path}")
    payload: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    result: dict[str, dict[str, Any]] = {}
    for station_id, row in payload.get("stations", {}).items():
        if not isinstance(row, dict) or row.get("scientifically_valid") is not True:
            continue
        ecef = row.get("ecef") or {}
        try:
            provenance = str(
                row.get("pos_file_path", "processed/single-base/derived-coordinates.json")
            )
            result[station_id] = {
                "x_m": float(ecef["x_m"]),
                "y_m": float(ecef["y_m"]),
                "z_m": float(ecef["z_m"]),
                "reference_frame": str(row["reference_frame"]),
                "coordinate_epoch": str(row["coordinate_epoch"]),
                "provenance": provenance,
            }
        except (KeyError, TypeError, ValueError):
            continue
    return result


def baseline_length_m(
    first: tuple[float, float, float], second: tuple[float, float, float]
) -> float:
    return math.sqrt(
        (first[0] - second[0]) ** 2 + (first[1] - second[1]) ** 2 + (first[2] - second[2]) ** 2
    )


def compute_geometry(
    *,
    reference_stations: list[str],
    test_station: str,
    verified: dict[str, dict[str, Any]],
) -> NetworkGeometry:
    """Compute deterministic network geometry; fail closed on unverified input."""
    stations = sorted(set(reference_stations) | {test_station})
    missing = [s for s in stations if s not in verified]
    if missing:
        raise NetworkBlocked(
            f"{BLOCKED_MESSAGE}: no verified coordinate for {', '.join(missing)}"
        )
    frames = {verified[s]["reference_frame"] for s in stations}
    if len(frames) != 1:
        raise NetworkBlocked(f"{BLOCKED_MESSAGE}: mixed coordinate frames {sorted(frames)}")
    coords = {s: (verified[s]["x_m"], verified[s]["y_m"], verified[s]["z_m"]) for s in stations}
    matrix: dict[str, dict[str, float]] = {s: {} for s in stations}
    for first in stations:
        for second in stations:
            matrix[first][second] = (
                0.0 if first == second else baseline_length_m(coords[first], coords[second])
            )
    centroid = (
        sum(coords[s][0] for s in stations) / len(stations),
        sum(coords[s][1] for s in stations) / len(stations),
        sum(coords[s][2] for s in stations) / len(stations),
    )
    ref_to_rover = {ref: matrix[ref][test_station] for ref in sorted(reference_stations)}
    nearest = min(ref_to_rover, key=lambda k: ref_to_rover[k]) if ref_to_rover else None
    farthest = max(ref_to_rover, key=lambda k: ref_to_rover[k]) if ref_to_rover else None
    mean_ref = sum(ref_to_rover.values()) / len(ref_to_rover) if ref_to_rover else None
    extent = max(matrix[a][b] for a in stations for b in stations)
    triangle = _triangle_area(reference_stations, matrix) if len(reference_stations) == 3 else None
    geometries = tuple(
        StationGeometry(
            station_id=s,
            ecef_x_m=coords[s][0],
            ecef_y_m=coords[s][1],
            ecef_z_m=coords[s][2],
            reference_frame=str(verified[s]["reference_frame"]),
            coordinate_epoch=str(verified[s]["coordinate_epoch"]),
            provenance=str(verified[s]["provenance"]),
        )
        for s in stations
    )
    baseline_count = sum(1 for a in stations for b in stations if a < b)
    return NetworkGeometry(
        stations=geometries,
        baseline_matrix_m=matrix,
        centroid_ecef_m=centroid,
        reference_to_rover_m=ref_to_rover,
        nearest_reference=nearest,
        farthest_reference=farthest,
        mean_reference_distance_m=mean_ref,
        network_spatial_extent_m=extent,
        triangle_area_m2=triangle,
        coordinate_frame=next(iter(frames)),
        baseline_count=baseline_count,
    )


def _triangle_area(refs: list[str], matrix: dict[str, dict[str, float]]) -> float | None:
    a, b, c = sorted(refs)
    try:
        ab, bc, ca = matrix[a][b], matrix[b][c], matrix[c][a]
    except KeyError:
        return None
    s = (ab + bc + ca) / 2.0
    area_sq = s * (s - ab) * (s - bc) * (s - ca)
    return math.sqrt(area_sq) if area_sq > 0 else 0.0
