"""Tests for the Phase 3 follow-on shorter-baseline control logic.

These tests exercise the pure selection/aggregation functions in
``nlgcp_single_base.control``: verified-baseline matrix construction with
scientific-eligibility filtering, shortest-available selection, distance
ranking, source tagging, and faithful comparison-row assembly that never
coerces an unattained FIX into a TTFF value.

All inputs are synthetic; these tests never support scientific accuracy claims.
"""

from __future__ import annotations

from typing import Any

from nlgcp_single_base.control import (
    build_comparison_rows,
    control_source_tag,
    eligible_station_count,
    rank_baselines,
    rank_rows_by_distance,
    shortest_available_baseline,
    verified_baseline_matrix,
)


def _coord(x: float, y: float, z: float) -> dict[str, Any]:
    return {"x_m": x, "y_m": y, "z_m": z}


def test_verified_baseline_matrix_filters_ineligible() -> None:
    registry: dict[str, dict[str, Any]] = {
        "VALID_A": {"scientifically_valid": True, "ecef": _coord(0, 0, 0)},
        "VALID_B": {"scientifically_valid": True, "ecef": _coord(100_000, 0, 0)},
        "NOT_VALID": {"scientifically_valid": False, "ecef": _coord(0, 1_000_000, 0)},
        "NO_COORD": {"scientifically_valid": True},
    }
    matrix = verified_baseline_matrix(registry)
    pairs = {b.ordered_pair for b in matrix}
    assert pairs == {("VALID_A", "VALID_B")}


def test_verified_baseline_matrix_pairs_and_ranking() -> None:
    registry: dict[str, dict[str, Any]] = {
        "VALID_A": {"scientifically_valid": True, "ecef": _coord(0, 0, 0)},
        "VALID_B": {"scientifically_valid": True, "ecef": _coord(100_000, 0, 0)},
        "VALID_C": {"scientifically_valid": True, "ecef": _coord(0, 200_000, 0)},
    }
    matrix = verified_baseline_matrix(registry)
    assert len(matrix) == 3, "expected 3 unordered pairs from 3 stations"
    ranked = rank_baselines(matrix)
    assert ranked[0].distance_km == min(b.distance_km for b in matrix)


def test_shortest_available_baseline_and_empty() -> None:
    registry: dict[str, dict[str, Any]] = {
        "VALID_A": {"scientifically_valid": True, "ecef": _coord(0, 0, 0)},
        "VALID_B": {"scientifically_valid": True, "ecef": _coord(101_000, 0, 0)},
    }
    shortest = shortest_available_baseline(verified_baseline_matrix(registry))
    assert shortest is not None
    assert shortest.ordered_pair == ("VALID_A", "VALID_B")
    assert shortest.distance_km == 101.0

    assert shortest_available_baseline(verified_baseline_matrix({})) is None


def test_eligible_station_count() -> None:
    registry: dict[str, dict[str, Any]] = {
        "VALID_A": {"scientifically_valid": True, "ecef": _coord(0, 0, 0)},
        "VALID_B": {"scientifically_valid": True, "ecef": _coord(1, 0, 0)},
        "INVALID": {"scientifically_valid": False, "ecef": _coord(2, 0, 0)},
    }
    assert eligible_station_count(registry) == 2


def test_shortest_available_matches_measured_distances() -> None:
    registry: dict[str, dict[str, Any]] = {
        "EKAK00NGA": {"scientifically_valid": True, "ecef": _coord(0, 0, 0)},
        "PHRI00NGA": {"scientifically_valid": True, "ecef": _coord(105_553, 0, 0)},
        "ABFC00NGA": {"scientifically_valid": True, "ecef": _coord(470_870, 0, 0)},
    }
    shortest = shortest_available_baseline(verified_baseline_matrix(registry))
    assert shortest is not None
    assert shortest.distance_km == 105.553


def test_control_source_tag() -> None:
    assert control_source_tag("sb-2024d026-ekak-phri-static") == "control_shortest_available"
    assert control_source_tag("sb-2024d026-abfc-ekak-static") == "milestone_long_baseline"


def test_build_comparison_rows_preserves_float_only() -> None:
    results = {
        "sb-2024d026-ekak-phri-static": {
            "execution_status": "complete",
            "baseline_distance_m": 105_553.0,
            "stations": ["EKAK00NGA", "PHRI00NGA"],
            "validation_metrics": {
                "solution_epoch_count": 2880,
                "solution_availability": 1.0,
                "fix_epoch_count": 0,
                "fix_rate_solution_epochs": 0.0,
                "float_rate_solution_epochs": 1.0,
                "ttff_seconds": None,
                "horizontal_rmse_m": 0.9677,
                "up_rmse_m": 0.5838,
                "three_d_rmse_m": 1.1301,
                "east_rmse_m": 0.9489,
                "north_rmse_m": 0.1899,
            },
        }
    }
    rows = build_comparison_rows(results)
    assert len(rows) == 1
    row = rows[0]
    assert row["source"] == "control_shortest_available"
    assert row["baseline_distance_km"] == 105.553
    assert row["fix_rate"] == 0.0
    assert row["ttff_to_fix"] == "not achieved"
    assert row["horizontal_rmse_m"] == 0.9677


def test_build_comparison_rows_skips_incomplete() -> None:
    results = {
        "sb-2024d026-abfc-ekak-static": {
            "execution_status": "blocked",
            "block_reason": "missing navigation",
            "baseline_distance_m": 487_636.0,
            "stations": ["ABFC00NGA", "EKAK00NGA"],
        }
    }
    assert build_comparison_rows(results) == []


def test_build_comparison_rows_ttff_when_fix_achieved() -> None:
    results = {
        "sb-x": {
            "execution_status": "complete",
            "baseline_distance_m": 1_000.0,
            "stations": ["A", "B"],
            "validation_metrics": {
                "solution_epoch_count": 2880,
                "solution_availability": 1.0,
                "fix_epoch_count": 2800,
                "fix_rate_solution_epochs": 0.97,
                "float_rate_solution_epochs": 0.03,
                "ttff_seconds": 45.0,
                "horizontal_rmse_m": 0.02,
                "up_rmse_m": 0.03,
                "three_d_rmse_m": 0.036,
                "east_rmse_m": 0.01,
                "north_rmse_m": 0.01,
            },
        }
    }
    row = build_comparison_rows(results)[0]
    assert row["ttff_to_fix"] == "45.0"


def test_rank_rows_by_distance() -> None:
    rows = [
        {"baseline_distance_km": 500.0},
        {"baseline_distance_km": 105.0},
        {"baseline_distance_km": 690.0},
    ]
    ranked = rank_rows_by_distance(rows)
    assert [r["baseline_distance_km"] for r in ranked] == [105.0, 500.0, 690.0]
