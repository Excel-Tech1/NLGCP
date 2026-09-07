"""Deterministic network quality metrics.

Single-baseline metrics are reported per baseline.  Network aggregates
(mean RMSE, availability, FIX/FLOAT distribution, inter-baseline
consistency) are labelled as network-INPUT aggregates.  An average of
independent solutions is never called a VRS solution.
"""

from __future__ import annotations

import math
from statistics import mean, pstdev
from typing import Any

from nlgcp_network_rtk import METRICS_SCHEMA_VERSION
from nlgcp_network_rtk.baselines import BaselineResult
from nlgcp_network_rtk.geometry import NetworkGeometry
from nlgcp_network_rtk.overlap import OverlapResult


def compute_metrics(
    *,
    experiment_id: str,
    admitted_count: int,
    rejected_count: int,
    geometry: NetworkGeometry | None,
    overlap: OverlapResult | None,
    baselines: list[BaselineResult],
) -> dict[str, Any]:
    per_baseline: list[dict[str, Any]] = []
    for row in sorted(baselines, key=lambda b: b.baseline_id):
        metrics = row.solution_metrics
        per_baseline.append(
            {
                "baseline_id": row.baseline_id,
                "reference_station": row.reference_station,
                "test_station": row.test_station,
                "outcome": row.outcome,
                "baseline_distance_m": row.baseline_distance_m,
                "solution_epoch_count": metrics.get("solution_epoch_count"),
                "expected_epoch_count": metrics.get("expected_epoch_count"),
                "solution_availability": metrics.get("solution_availability"),
                "fix_epoch_count": metrics.get("fix_epoch_count"),
                "fix_rate_expected_epochs": metrics.get("fix_rate_expected_epochs"),
                "ttff_seconds": metrics.get("ttff_seconds"),
                "horizontal_rmse_m": metrics.get("horizontal_rmse_m"),
                "up_rmse_m": metrics.get("up_rmse_m"),
                "three_d_rmse_m": metrics.get("three_d_rmse_m"),
                "quality_counts": metrics.get("quality_counts", {}),
            }
        )
    complete = [b for b in baselines if b.outcome == "COMPLETE"]
    fix_total = sum(int(b.solution_metrics.get("fix_epoch_count") or 0) for b in complete)
    epoch_total = sum(int(b.solution_metrics.get("solution_epoch_count") or 0) for b in complete)
    quality_totals: dict[str, int] = {}
    for row in complete:
        counts = row.solution_metrics.get("quality_counts", {})
        if isinstance(counts, dict):
            for key, value in counts.items():
                quality_totals[str(key)] = quality_totals.get(str(key), 0) + int(value or 0)
    horiz = _float_list(complete, "horizontal_rmse_m")
    vert = _float_list(complete, "up_rmse_m")
    three_d = _float_list(complete, "three_d_rmse_m")
    avail = _float_list(complete, "solution_availability")
    distances = sorted(b.baseline_distance_m for b in baselines)
    network_aggregate = {
        "label": (
            "network-input aggregate of independent single-base solutions "
            "(NOT a VRS solution)"
        ),
        "baseline_count": len(complete),
        "mean_horizontal_rmse_m": mean(horiz) if horiz else None,
        "mean_vertical_rmse_m": mean(vert) if vert else None,
        "mean_3d_rmse_m": mean(three_d) if three_d else None,
        "std_horizontal_rmse_m": pstdev(horiz) if len(horiz) >= 2 else None,
        "inter_baseline_consistency_m": pstdev(horiz) if len(horiz) >= 2 else None,
        "mean_availability": mean(avail) if avail else None,
        "total_fix_epochs": fix_total,
        "total_solution_epochs": epoch_total,
        "fix_rate_over_baseline_epochs": (fix_total / epoch_total) if epoch_total else None,
        "quality_distribution": quality_totals,
        "baseline_distances_m": distances,
        "min_baseline_distance_m": min(distances) if distances else None,
        "max_baseline_distance_m": max(distances) if distances else None,
    }
    geometry_summary: dict[str, Any] | None = None
    if geometry is not None:
        geometry_summary = {
            "coordinate_frame": geometry.coordinate_frame,
            "baseline_count": geometry.baseline_count,
            "network_spatial_extent_m": geometry.network_spatial_extent_m,
            "nearest_reference": geometry.nearest_reference,
            "farthest_reference": geometry.farthest_reference,
            "mean_reference_distance_m": geometry.mean_reference_distance_m,
            "reference_to_rover_m": geometry.reference_to_rover_m,
            "triangle_area_m2": geometry.triangle_area_m2,
        }
    return {
        "schema_version": METRICS_SCHEMA_VERSION,
        "experiment_id": experiment_id,
        "admitted_station_count": admitted_count,
        "rejected_station_count": rejected_count,
        "common_interval_duration_seconds": overlap.common_duration_seconds if overlap else None,
        "common_epoch_count": overlap.expected_epochs if overlap else None,
        "single_baseline_metrics": per_baseline,
        "network_aggregate_metrics": network_aggregate,
        "spatial_geometry_summary": geometry_summary,
    }


def comparison_rows(
    *,
    metrics: dict[str, Any],
    nearest_reference: str | None,
) -> list[dict[str, Any]]:
    """Compare nearest single reference vs the multiple-reference network input."""
    per_baseline = {row["baseline_id"]: row for row in metrics.get("single_baseline_metrics", [])}
    nearest_row: dict[str, Any] | None = None
    if nearest_reference:
        for row in per_baseline.values():
            if row.get("reference_station") == nearest_reference:
                nearest_row = row
                break
    aggregate = metrics.get("network_aggregate_metrics", {})
    rows: list[dict[str, Any]] = []
    rows.append(
        {
            "comparison": "single_nearest_reference",
            "reference": nearest_reference or "",
            "horizontal_rmse_m": (nearest_row or {}).get("horizontal_rmse_m"),
            "three_d_rmse_m": (nearest_row or {}).get("three_d_rmse_m"),
            "fix_rate": (nearest_row or {}).get("fix_rate_expected_epochs"),
            "note": "independent single-base solution; preserved benchmark, not re-tuned",
        }
    )
    rows.append(
        {
            "comparison": "multiple_reference_network_input",
            "reference": f"{aggregate.get('baseline_count', 0)} independent baselines",
            "horizontal_rmse_m": aggregate.get("mean_horizontal_rmse_m"),
            "three_d_rmse_m": aggregate.get("mean_3d_rmse_m"),
            "fix_rate": aggregate.get("fix_rate_over_baseline_epochs"),
            "note": "mean of independent baselines; NOT a VRS solution; "
            "improvement may only be claimed if computed values support it",
        }
    )
    return rows


def rmse(values: list[float]) -> float | None:
    if not values:
        return None
    return math.sqrt(sum(v * v for v in values) / len(values))


def _float_list(baselines: list[BaselineResult], key: str) -> list[float]:
    values: list[float] = []
    for row in baselines:
        value = row.solution_metrics.get(key)
        if value is not None:
            values.append(float(value))
    return values
