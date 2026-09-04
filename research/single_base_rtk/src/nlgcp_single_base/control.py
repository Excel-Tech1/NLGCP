"""Follow-on control logic for the Phase 3 shorter-baseline benchmark.

The original Phase 3 milestone processed only the ABFC-rooted long baselines
(471-690 km).  This module adds the pure, testable logic needed to (a) build the
verified baseline matrix from the authoritative coordinate registry, (b) rank
candidates by distance and identify the shortest scientifically-valid baseline,
and (c) assemble the combined milestone + control comparison set from result
manifests, preserving FLOAT-only and blocked/missing sessions faithfully.

No real experiment logic lives here; this is analysis/selection code only.
"""

from __future__ import annotations

from typing import Any

from nlgcp_single_base.baselines import Baseline, classify_baseline
from nlgcp_single_base.coordinates import EcefCoordinate, baseline_distance_m


def verified_baseline_matrix(registry: dict[str, dict[str, Any]]) -> list[Baseline]:
    """Return all unordered, scientifically-eligible station-pair baselines.

    Only stations recorded with ``scientifically_valid == True`` and a complete,
    finite verified ECEF coordinate are admitted.  Stations whose PRIDE solution
    is not usable (``scientifically_valid`` false) or that have no coordinate
    entry at all are excluded and never silently substituted.  Base->rover and
    rover->base are a single unordered pair each.
    """
    admitted: list[str] = []
    coords: dict[str, EcefCoordinate] = {}
    for station_id, entry in sorted(registry.items()):
        if not entry.get("scientifically_valid"):
            continue
        ecef = entry.get("ecef")
        if not isinstance(ecef, dict):
            continue
        try:
            coord = EcefCoordinate(
                x_m=float(ecef["x_m"]),
                y_m=float(ecef["y_m"]),
                z_m=float(ecef["z_m"]),
            )
        except (KeyError, TypeError, ValueError):
            continue
        admitted.append(station_id)
        coords[station_id] = coord

    baselines: list[Baseline] = []
    for i in range(len(admitted)):
        for j in range(i + 1, len(admitted)):
            a, b = admitted[i], admitted[j]
            distance_km = baseline_distance_m(coords[a], coords[b]) / 1000.0
            baselines.append(
                Baseline(
                    base_station_id=a,
                    rover_station_id=b,
                    distance_km=distance_km,
                    distance_class=classify_baseline(distance_km),
                )
            )
    return baselines


def rank_baselines(baselines: list[Baseline]) -> list[Baseline]:
    """Return baselines sorted shortest-to-longest by measured distance."""
    return sorted(baselines, key=lambda b: b.distance_km)


def shortest_available_baseline(baselines: list[Baseline]) -> Baseline | None:
    """Return the shortest baseline, or None if the matrix is empty."""
    ranked = rank_baselines(baselines)
    return ranked[0] if ranked else None


def eligible_station_count(registry: dict[str, dict[str, Any]]) -> int:
    """Number of stations with a scientifically-valid verified coordinate."""
    return sum(
        1
        for entry in registry.values()
        if entry.get("scientifically_valid") and isinstance(entry.get("ecef"), dict)
    )


def control_source_tag(experiment_id: str) -> str:
    """Tag an experiment as the shorter-baseline control or a milestone run.

    The single follow-on control is rooted at EKAK; the original milestone runs
    are all rooted at ABFC.  This is used only to label the comparison, never to
    change any measured value.
    """
    eid = experiment_id.lower()
    if "d026-ekak-" in eid or eid.startswith("sb-2024d026-ekak"):
        return "control_shortest_available"
    return "milestone_long_baseline"


def build_comparison_rows(
    results: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Flatten completed result manifests into tagged comparison rows.

    Only experiments with ``execution_status == complete`` and metrics are
    included; missing/blocked/failed experiments are preserved in the caller's
    table but never contribute to accuracy aggregates.  TTFF is reported as
    ``None`` when no FIX was attained (never coerced to zero).
    """
    rows: list[dict[str, Any]] = []
    for eid, manifest in sorted(results.items()):
        if manifest.get("execution_status") != "complete":
            continue
        metrics = manifest.get("validation_metrics") or {}
        distance_m = manifest.get("baseline_distance_m")
        if distance_m is None:
            continue
        stations = manifest.get("stations") or ["", ""]
        rows.append(
            {
                "experiment_id": eid,
                "base": stations[0],
                "rover": stations[1],
                "source": control_source_tag(eid),
                "baseline_distance_km": distance_m / 1000.0,
                "solution_epoch_count": metrics.get("solution_epoch_count"),
                "solution_availability": metrics.get("solution_availability"),
                "fix_epoch_count": metrics.get("fix_epoch_count"),
                "fix_rate": metrics.get("fix_rate_solution_epochs"),
                "float_rate": metrics.get("float_rate_solution_epochs"),
                "ttff_seconds": metrics.get("ttff_seconds"),
                "ttff_to_fix": _ttff_to_fix(
                    metrics.get("ttff_seconds"), metrics.get("fix_epoch_count")
                ),
                "horizontal_rmse_m": metrics.get("horizontal_rmse_m"),
                "vertical_rmse_m": metrics.get("up_rmse_m"),
                "three_d_rmse_m": metrics.get("three_d_rmse_m"),
                "east_rmse_m": metrics.get("east_rmse_m"),
                "north_rmse_m": metrics.get("north_rmse_m"),
            }
        )
    return rows


def _ttff_to_fix(ttff_seconds: Any, fix_epoch_count: Any) -> str:
    """Describe time-to-first-FIX without coercing 'not achieved' to zero."""
    if fix_epoch_count and fix_epoch_count > 0:
        return f"{float(ttff_seconds):.1f}" if ttff_seconds is not None else "achieved"
    return "not achieved"


def rank_rows_by_distance(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return comparison rows sorted shortest-to-longest baseline."""
    return sorted(rows, key=lambda r: r["baseline_distance_km"])
