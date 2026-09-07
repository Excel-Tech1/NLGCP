"""Tests for network geometry, baseline matrix and coordinate verification.

SYNTHETIC TEST DATA — NOT VALID FOR SCIENTIFIC RESULTS.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from nlgcp_network_rtk.geometry import (
    baseline_length_m,
    compute_geometry,
    load_verified_coordinates,
)
from nlgcp_network_rtk.models import NetworkBlocked
from synthetic_fixtures import write_derived_coordinates

COORDS = {
    "ABFC00NGA": (6246471.17131, 820849.02064, 994268.16646),
    "EKAK00NGA": (6296841.32517, 875621.00415, 512343.12428),
    "MGBO00NGA": (6080985.75299, 1416995.42834, 1299050.34795),
    "PHRI00NGA": (6308877.98392, 772269.10256, 530087.60603),
}


def test_verified_coordinates_load_only_valid(tmp_path: Path) -> None:
    write_derived_coordinates(tmp_path, COORDS)
    verified = load_verified_coordinates(tmp_path)
    assert set(verified) == set(COORDS)


def test_missing_coordinates_file_blocked(tmp_path: Path) -> None:
    with pytest.raises(NetworkBlocked):
        load_verified_coordinates(tmp_path)


def test_geometry_matrix_symmetry_and_zero_diagonal(tmp_path: Path) -> None:
    write_derived_coordinates(tmp_path, COORDS)
    verified = load_verified_coordinates(tmp_path)
    geometry = compute_geometry(
        reference_stations=["ABFC00NGA", "EKAK00NGA", "MGBO00NGA"],
        test_station="PHRI00NGA",
        verified=verified,
    )
    matrix = geometry.baseline_matrix_m
    for first in matrix:
        for second in matrix[first]:
            assert matrix[first][second] == pytest.approx(matrix[second][first])
    for station in matrix:
        assert matrix[station][station] == 0.0


def test_geometry_nearest_farthest_mean(tmp_path: Path) -> None:
    write_derived_coordinates(tmp_path, COORDS)
    verified = load_verified_coordinates(tmp_path)
    geometry = compute_geometry(
        reference_stations=["ABFC00NGA", "EKAK00NGA", "MGBO00NGA"],
        test_station="PHRI00NGA",
        verified=verified,
    )
    assert geometry.nearest_reference == "EKAK00NGA"
    assert geometry.farthest_reference == "MGBO00NGA"
    expected_mean = sum(geometry.reference_to_rover_m.values()) / 3
    assert geometry.mean_reference_distance_m == pytest.approx(expected_mean)


def test_geometry_known_baseline_length(tmp_path: Path) -> None:
    write_derived_coordinates(tmp_path, COORDS)
    verified = load_verified_coordinates(tmp_path)
    geometry = compute_geometry(
        reference_stations=["ABFC00NGA", "EKAK00NGA", "MGBO00NGA"],
        test_station="PHRI00NGA",
        verified=verified,
    )
    # Real derived-coordinate distance EKAK-PHRI 105.553 km pins the computation.
    assert geometry.reference_to_rover_m["EKAK00NGA"] / 1000.0 == pytest.approx(105.553, abs=0.01)
    assert geometry.baseline_count == 6


def test_geometry_extent_is_max_pairwise(tmp_path: Path) -> None:
    write_derived_coordinates(tmp_path, COORDS)
    verified = load_verified_coordinates(tmp_path)
    geometry = compute_geometry(
        reference_stations=["ABFC00NGA", "EKAK00NGA", "MGBO00NGA"],
        test_station="PHRI00NGA",
        verified=verified,
    )
    flat = [v for row in geometry.baseline_matrix_m.values() for v in row.values()]
    assert geometry.network_spatial_extent_m == pytest.approx(max(flat))


def test_geometry_triangle_area_positive(tmp_path: Path) -> None:
    write_derived_coordinates(tmp_path, COORDS)
    verified = load_verified_coordinates(tmp_path)
    geometry = compute_geometry(
        reference_stations=["ABFC00NGA", "EKAK00NGA", "MGBO00NGA"],
        test_station="PHRI00NGA",
        verified=verified,
    )
    assert geometry.triangle_area_m2 is not None and geometry.triangle_area_m2 > 0


def test_unverified_station_blocked(tmp_path: Path) -> None:
    partial = {k: v for k, v in COORDS.items() if k != "MGBO00NGA"}
    write_derived_coordinates(tmp_path, partial)
    verified = load_verified_coordinates(tmp_path)
    with pytest.raises(NetworkBlocked):
        compute_geometry(
            reference_stations=["ABFC00NGA", "EKAK00NGA", "MGBO00NGA"],
            test_station="PHRI00NGA",
            verified=verified,
        )


def test_mixed_frames_blocked(tmp_path: Path) -> None:
    write_derived_coordinates(tmp_path, COORDS)
    path = tmp_path / "processed" / "single-base" / "derived-coordinates.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["stations"]["MGBO00NGA"]["reference_frame"] = "ITRF2014"
    path.write_text(json.dumps(payload), encoding="utf-8")
    verified = load_verified_coordinates(tmp_path)
    with pytest.raises(NetworkBlocked):
        compute_geometry(
            reference_stations=["ABFC00NGA", "MGBO00NGA"],
            test_station="PHRI00NGA",
            verified=verified,
        )


def test_baseline_length_helper(tmp_path: Path) -> None:
    assert baseline_length_m((0.0, 0.0, 0.0), (3.0, 4.0, 0.0)) == pytest.approx(5.0)


def test_centroid_is_mean(tmp_path: Path) -> None:
    write_derived_coordinates(tmp_path, COORDS)
    verified = load_verified_coordinates(tmp_path)
    geometry = compute_geometry(
        reference_stations=["ABFC00NGA", "EKAK00NGA"],
        test_station="PHRI00NGA",
        verified=verified,
    )
    xs = [COORDS[s][0] for s in ("ABFC00NGA", "EKAK00NGA", "PHRI00NGA")]
    assert geometry.centroid_ecef_m[0] == pytest.approx(sum(xs) / 3)
