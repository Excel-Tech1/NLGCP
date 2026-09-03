"""Cross-experiment analysis for Phase 3.

Builds the baseline-distance relationship and per-baseline aggregates from
per-experiment result manifests.  Failed/blocked sessions are preserved and
never averaged away.
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any

from nlgcp_single_base.io import read_json


def load_experiment_results(
    processed_root: Path,
    experiment_ids: list[str],
) -> dict[str, dict[str, Any]]:
    """Load result manifests for the given experiments under processed/single-base."""
    results: dict[str, dict[str, Any]] = {}
    for experiment_id in experiment_ids:
        manifest_path = (
            processed_root / "single-base" / experiment_id / "manifest.json"
        )
        if manifest_path.exists():
            results[experiment_id] = read_json(manifest_path)
        else:
            results[experiment_id] = {"experiment_id": experiment_id, "missing": True}
    return results


def successful_experiments(
    results: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Return only experiments whose execution completed with metrics."""
    return {
        eid: manifest
        for eid, manifest in results.items()
        if manifest.get("execution_status") == "complete"
        and manifest.get("validation_metrics")
    }


def baseline_analysis_rows(
    results: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Flatten completed experiments into analysis rows.

    Each row carries the baseline distance plus the key per-experiment
    metrics needed for the degradation analysis.
    """
    rows: list[dict[str, Any]] = []
    for eid, manifest in sorted(results.items()):
        distance_m = manifest.get("baseline_distance_m")
        if distance_m is None:
            continue
        metrics = manifest.get("validation_metrics") or {}
        rows.append(
            {
                "experiment_id": eid,
                "base": manifest.get("stations", ["", ""])[0],
                "rover": manifest.get("rover_or_control"),
                "baseline_distance_km": distance_m / 1000.0,
                "fix_rate": metrics.get("fix_rate_solution_epochs"),
                "ttff_seconds": metrics.get("ttff_seconds"),
                "solution_availability": metrics.get("solution_availability"),
                "horizontal_rmse_m": metrics.get("horizontal_rmse_m"),
                "vertical_rmse_m": metrics.get("up_rmse_m"),
                "three_d_rmse_m": metrics.get("three_d_rmse_m"),
                "fix_epoch_count": metrics.get("fix_epoch_count"),
                "solution_epoch_count": metrics.get("solution_epoch_count"),
            }
        )
    return rows


def per_baseline_aggregates(
    rows: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Aggregate analysis rows by unordered base-rover baseline pair.

    Only completed experiments contribute to aggregates; failures remain
    visible in the per-experiment tables.
    """
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        key = "-".join(sorted([row["base"], row["rover"]]))
        groups[key].append(row)

    aggregates: dict[str, dict[str, Any]] = {}
    for key, group in sorted(groups.items()):
        distances = [row["baseline_distance_km"] for row in group]
        aggregates[key] = {
            "stations": list(key.split("-")),
            "mean_baseline_distance_km": _mean(distances),
            "experiment_count": len(group),
            "mean_fix_rate": _mean([r["fix_rate"] for r in group if r["fix_rate"] is not None]),
            "mean_horizontal_rmse_m": _mean(
                [r["horizontal_rmse_m"] for r in group if r["horizontal_rmse_m"] is not None]
            ),
            "mean_vertical_rmse_m": _mean(
                [r["vertical_rmse_m"] for r in group if r["vertical_rmse_m"] is not None]
            ),
        }
    return aggregates


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None
