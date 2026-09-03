"""Deterministic experiment-matrix generation for Phase 3.

Phase 3 aims to answer how conventional single-base RTK performs under
Nigeria's sparse station geometry and how performance changes with baseline
distance.  Experiment definitions are generated programmatically from:

* verified station coordinates (frame + epoch);
* the common observation window for the chosen day;
* an explicitly spanned set of base->rover pairs.

Each generated definition is deterministic given the same inputs, so the
sprint does not hand-maintain hundreds of near-identical JSON files.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from nlgcp_single_base.baselines import Baseline, baseline_matrix
from nlgcp_single_base.coordinates import EcefCoordinate
from nlgcp_single_base.models import (
    ExperimentDefinition,
    NavigationInput,
    Phase2Gate,
    ProcessingMode,
    StationCoordinate,
    StationInput,
)
from nlgcp_single_base.sessions import OverlapWindow


@dataclass(frozen=True)
class StationExperimentInput:
    """Per-station inputs needed to build experiments for one day."""

    station_id: str
    coordinate: StationCoordinate
    observation_path: Path
    observation_sha256: str
    metadata_version: str


def experiment_id(
    year: int,
    doy: int,
    base_station_id: str,
    rover_station_id: str,
    processing_mode: ProcessingMode,
) -> str:
    """Deterministic, human-readable experiment identifier.

    Example: ``sb-2024d026-abfc-ekak-static``.
    """
    short_base = base_station_id[:4].lower()
    short_rover = rover_station_id[:4].lower()
    return f"sb-{year}d{doy:03d}-{short_base}-{short_rover}-{processing_mode.value}"


def plan_station_baselines(
    stations: dict[str, EcefCoordinate],
) -> list[Baseline]:
    """Compute all unordered station-pair baselines from verified coordinates."""
    return baseline_matrix(stations)


def generate_experiments(
    *,
    year: int,
    doy: int,
    stations: dict[str, StationExperimentInput],
    nav: NavigationInput,
    window: OverlapWindow,
    pairs: list[tuple[str, str]],
    phase2_gate: Phase2Gate,
    research_question: str,
    processing_mode: ProcessingMode = ProcessingMode.STATIC,
    notes: str = "",
) -> list[ExperimentDefinition]:
    """Build experiment definitions for the requested base->rover pairs.

    ``pairs`` are ordered ``(base_station_id, rover_station_id)`` tuples.
    The common observation window constrains start/end so every experiment
    runs only over genuinely overlapping data.
    """
    definitions: list[ExperimentDefinition] = []
    for base_id, rover_id in pairs:
        if base_id == rover_id:
            raise ValueError("base and rover must differ")
        base = stations[base_id]
        rover = stations[rover_id]
        base_ecef = base.coordinate.require_verified_ecef()
        rover_ecef = rover.coordinate.require_verified_ecef()
        definitions.append(
            ExperimentDefinition(
                experiment_id=experiment_id(year, doy, base_id, rover_id, processing_mode),
                research_question=research_question,
                processing_mode=processing_mode,
                start_time_utc=window.iso_start(),
                end_time_utc=window.iso_end(),
                sampling_rate_hz=window.sampling_interval_seconds
                and (1.0 / window.sampling_interval_seconds),
                base=StationInput(
                    station_id=base_id,
                    coordinate=base.coordinate,
                    observation_path=base.observation_path,
                    metadata_version=base.metadata_version,
                    observation_sha256=base.observation_sha256,
                ),
                rover=StationInput(
                    station_id=rover_id,
                    coordinate=rover.coordinate,
                    observation_path=rover.observation_path,
                    metadata_version=rover.metadata_version,
                    observation_sha256=rover.observation_sha256,
                ),
                navigation=[nav],
                phase2_gate=phase2_gate,
                notes=notes,
                extra_metadata={
                    "baseline_matrix": {
                        "base": base_id,
                        "rover": rover_id,
                        "distance_km": _distance_km(base_ecef, rover_ecef),
                    }
                },
            )
        )
    return definitions


def select_spanning_pairs(
    baselines: list[Baseline],
    stations: list[str],
    *,
    base_station_id: str,
    min_per_class: int = 1,
) -> list[tuple[str, str]]:
    """Select base->rover pairs spanning each distance class.

    Prefer a design that spans the available distance distribution rather
    than every permutation.  Returns ordered ``(base, rover)`` pairs rooted
    at ``base_station_id`` where possible, with additional pairs to cover
    distance classes not reachable from the chosen base.
    """
    from collections import defaultdict

    by_class: dict[str, list[Baseline]] = defaultdict(list)
    for baseline in baselines:
        by_class[baseline.distance_class].append(baseline)

    selected: list[tuple[str, str]] = []
    chosen_nodes: set[str] = set()

    # Prefer pairs with the chosen base as anchor to keep a common reference.
    for cls in ("short", "medium", "long", "very_long"):
        anchored = [
            b
            for b in by_class.get(cls, [])
            if b.base_station_id == base_station_id or b.rover_station_id == base_station_id
        ]
        pool = anchored or by_class.get(cls, [])
        picked = 0
        for baseline in sorted(pool, key=lambda b: b.distance_km):
            base_node, rover_node = (
                (baseline.base_station_id, baseline.rover_station_id)
                if baseline.base_station_id == base_station_id
                else (base_station_id, baseline.rover_station_id)
            )
            if rover_node == base_station_id:
                continue
            if rover_node in chosen_nodes:
                continue
            selected.append((base_station_id, rover_node))
            chosen_nodes.add(rover_node)
            picked += 1
            if picked >= max(min_per_class, 1):
                break

    return selected


def _distance_km(base: EcefCoordinate, rover: EcefCoordinate) -> float:
    from nlgcp_single_base.coordinates import baseline_distance_m

    return baseline_distance_m(base, rover) / 1000.0
