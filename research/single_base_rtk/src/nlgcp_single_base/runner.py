"""Top-level orchestration for Phase 3 single-base RTK.

:func:`run_phase3` sequences preparation, execution, analysis and reporting
so the phase is reproducible from a single call while preserving each
sub-stage's independent fail-closed gate checks.

Because Nigeria's operational NIGNET reference spacing puts every available
pair in the very-long-baseline range (see :mod:`nlgcp_single_base.baselines`),
the experiment set emitted here reflects exactly that geometry rather than a
presumed short-range network.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from nlgcp_single_base.analysis import (
    baseline_analysis_rows,
    load_experiment_results,
    per_baseline_aggregates,
)
from nlgcp_single_base.coordinates import EcefCoordinate, ecef_to_geodetic
from nlgcp_single_base.coordinates_derive import is_usable_pride_solution, load_coordinate_registry
from nlgcp_single_base.gate import assemble_phase2_audit, write_audit_record
from nlgcp_single_base.io import sha256_file, write_json
from nlgcp_single_base.models import (
    ExperimentDefinition,
    NavigationInput,
    Phase2Gate,
    ProcessingMode,
    ScientificExecutionBlocked,
    StationCoordinate,
    StationInput,
)
from nlgcp_single_base.pipeline import prepare_or_run_experiment
from nlgcp_single_base.sessions import (
    OverlapWindow,
    common_overlap_window,
    load_session_qc,
)
from nlgcp_single_base.stations import (
    canonical_station_id_for_marker,
    markers_for_canonical_station,
)

# The stations with a scientifically usable authoritative coordinate for the
# representative full-window session on DOY 026.  BKFP is excluded because its
# PRIDE solution is not usable (Sig0 ~12.6 m, only 64 observations) and UNEC is
# excluded because its PRIDE run reported "no resolvable ambiguities" and
# produced no coordinate.  Neither is silently substituted.
FULL_WINDOW_STATIONS = [
    "ABFC00NGA",
    "EKAK00NGA",
    "MGBO00NGA",
    "PHRI00NGA",
]


@dataclass(frozen=True)
class Phase3Plan:
    """A resolved, runnable Phase 3 plan for one experiment day."""

    year: int
    doy: int
    base_station: str
    full_window_stations: list[str]
    per_gap_stations: list[str]
    window: OverlapWindow
    coordinate_registry_path: Path
    observation_paths: dict[str, Path]
    observation_sha256: dict[str, str]
    navigation_path: Path
    navigation_sha256: str


def resolve_plan(
    data_root: Path,
    *,
    year: int,
    doy: int,
    base_station: str,
    per_gap_stations: list[str] | None = None,
) -> Phase3Plan:
    """Resolve the runnable plan, fail-closing on the real QC and registry."""
    coordinate_registry = load_coordinate_registry(
        data_root / "processed" / "single-base" / "derived-coordinates.json"
    )
    if not coordinate_registry:
        raise ScientificExecutionBlocked(
            "Phase 3 blocked: derived-coordinates.json is empty or missing"
        )

    full_window = list(FULL_WINDOW_STATIONS)
    if canonical_station_id_for_marker(base_station) not in full_window:
        raise ScientificExecutionBlocked(
            f"Phase 3 blocked: base station {base_station} not in the full-window set"
        )
    per_gap = list(per_gap_stations or [])

    observation_paths: dict[str, Path] = {}
    observation_sha256: dict[str, str] = {}
    conversion_manifest = _load_conversion_manifest(data_root, year, doy)
    for station in full_window + per_gap:
        marker = markers_for_canonical_station(station)[0]
        path = (
            data_root
            / "working" / "sessions" / str(year) / f"{doy:03d}"
            / station / f"{marker}{doy:03d}0.24O"
        )
        if not path.is_file():
            raise ScientificExecutionBlocked(
                f"Phase 3 blocked: converted observation missing for {station}: {path}"
            )
        observation_paths[station] = path
        entry = conversion_manifest.get(station, {})
        sha256 = entry.get("converted_sha256")
        if not sha256:
            raise ScientificExecutionBlocked(
                f"Phase 3 blocked: converted_sha256 missing for {station} in conversion manifest"
            )
        observation_sha256[station] = sha256

    session_qc = load_session_qc(data_root / "processed" / "qc" / "2024" / "sessions.csv")
    window = common_overlap_window(session_qc, doy, full_window)

    navigation = _find_navigation(data_root, year, doy)
    return Phase3Plan(
        year=year,
        doy=doy,
        base_station=canonical_station_id_for_marker(base_station),
        full_window_stations=full_window,
        per_gap_stations=per_gap,
        window=window,
        coordinate_registry_path=data_root
        / "processed" / "single-base" / "derived-coordinates.json",
        observation_paths=observation_paths,
        observation_sha256=observation_sha256,
        navigation_path=navigation,
        navigation_sha256=sha256_file(navigation),
    )


def experiment_definitions(
    plan: Phase3Plan,
    coordinate_registry: dict[str, dict[str, object]],
    phase2_gate: Phase2Gate,
    *,
    research_question: str,
) -> list[ExperimentDefinition]:
    """Materialise the Phase 3 experiment definitions (base to each rover)."""
    definitions: list[ExperimentDefinition] = []
    base_station = plan.base_station
    for rover_station in plan.full_window_stations:
        if rover_station == base_station:
            continue
        defs = _experiment_definition(
            plan,
            coordinate_registry,
            phase2_gate,
            base_station=base_station,
            rover_station=rover_station,
            research_question=research_question,
        )
        definitions.append(defs)
    for rover_station in plan.per_gap_stations:
        defs = _experiment_definition(
            plan,
            coordinate_registry,
            phase2_gate,
            base_station=base_station,
            rover_station=rover_station,
            research_question=research_question,
            per_gap=True,
        )
        definitions.append(defs)
    return definitions


def _experiment_definition(
    plan: Phase3Plan,
    coordinate_registry: dict[str, dict[str, object]],
    phase2_gate: Phase2Gate,
    *,
    base_station: str,
    rover_station: str,
    research_question: str,
    per_gap: bool = False,
) -> ExperimentDefinition:
    base_entry = coordinate_registry[base_station]
    rover_entry = coordinate_registry[rover_station]
    if not is_usable_pride_solution(Path(str(base_entry["pos_file_path"]))):
        raise ScientificExecutionBlocked(
            f"Phase 3 blocked: base coordinate for {base_station} is not scientifically usable"
        )
    valid_rover = is_usable_pride_solution(Path(str(rover_entry["pos_file_path"])))
    if not valid_rover:
        raise ScientificExecutionBlocked(
            f"Phase 3 blocked: rover coordinate for {rover_station} is not scientifically usable"
        )

    from nlgcp_single_base.experiments import experiment_id

    window_start = plan.window.iso_start()
    window_end = plan.window.iso_end()
    eid = experiment_id(plan.year, plan.doy, base_station, rover_station, ProcessingMode.STATIC)
    notes = f"{plan.window.iso_start()} to {plan.window.iso_end()}"
    if per_gap:
        notes += " [PER-GAP SESSION - BKFP has documented internal gaps; handled per-gap]"

    return ExperimentDefinition(
        experiment_id=eid,
        research_question=research_question,
        processing_mode=ProcessingMode.STATIC,
        start_time_utc=window_start,
        end_time_utc=window_end,
        sampling_rate_hz=1.0 / plan.window.sampling_interval_seconds,
        base=_station_input(
            base_station,
            base_entry,
            plan.observation_paths[base_station],
            plan.observation_sha256[base_station],
        ),
        rover=_station_input(
            rover_station,
            rover_entry,
            plan.observation_paths[rover_station],
            plan.observation_sha256[rover_station],
        ),
        navigation=[
            NavigationInput(
                plan.navigation_path,
                sha256=plan.navigation_sha256,
                product_type="broadcast_navigation",
            )
        ],
        phase2_gate=phase2_gate,
        notes=notes,
    )


def _station_input(
    station_id: str,
    entry: dict[str, Any],
    observation_path: Path,
    observation_sha256: str,
) -> StationInput:
    ecef = EcefCoordinate(
        x_m=entry["ecef"]["x_m"],
        y_m=entry["ecef"]["y_m"],
        z_m=entry["ecef"]["z_m"],
    )
    geodetic = ecef_to_geodetic(ecef)
    coordinate = StationCoordinate(
        reference_frame=str(entry["reference_frame"]),
        coordinate_epoch=str(entry["coordinate_epoch"]),
        ecef=ecef,
        geodetic=geodetic,
        provenance=str(entry["pos_file_path"]),
    )
    return StationInput(
        station_id=station_id,
        coordinate=coordinate,
        observation_path=observation_path,
        metadata_version="v1",
        observation_sha256=observation_sha256,
    )


def assemble_gate_with_evidence(
    data_root: Path,
    plan: Phase3Plan,
    *,
    audit_reviewed: bool,
) -> tuple[Phase2Gate, Any]:
    """Assemble the Phase 2 gate from the real Phase 2/3 artefacts.

    Writing the audit record is required before ``phase2_audit_approved`` can
    open; the caller controls ``audit_reviewed`` to reflect human review.
    """
    header_registry = data_root / "metadata" / "stations" / "osgof-2024-rinex-header-registry.csv"
    audit = assemble_phase2_audit(
        station_registry=header_registry,
        header_registry=header_registry,
        canonical_manifest=data_root / "manifests" / "canonical-raw-archive-2024.json",
        anomalies=data_root / "manifests" / "anomalies.csv",
        session_qc=data_root / "processed" / "qc" / "2024" / "sessions.csv",
        conversion_manifest=_find_conversion_manifest(data_root, plan.year, plan.doy),
        navigation_product=plan.navigation_path,
        derived_coordinates=plan.coordinate_registry_path,
        audit_reviewed=audit_reviewed,
    )
    if audit_reviewed:
        audit_record_path = (
            data_root / "validation" / "reports" / "phase3-phase2-audit.md"
        )
        write_audit_record(audit, audit_record_path)
    return audit.gate, audit


def run_phase3(
    data_root: Path,
    *,
    year: int,
    doy: int,
    base_station: str,
    research_question: str,
    per_gap_stations: list[str] | None = None,
    audit_reviewed: bool = True,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Resolve, gate, execute and finalise the Phase 3 experiment plan."""
    plan = resolve_plan(
        data_root,
        year=year,
        doy=doy,
        base_station=base_station,
        per_gap_stations=per_gap_stations,
    )
    coordinate_registry = load_coordinate_registry(plan.coordinate_registry_path)
    phase2_gate, _audit = assemble_gate_with_evidence(
        data_root, plan, audit_reviewed=audit_reviewed
    )
    phase2_gate.assert_open()

    definitions = experiment_definitions(
        plan,
        coordinate_registry,
        phase2_gate,
        research_question=research_question,
    )
    executed = [definition.experiment_id for definition in definitions]

    for definition in definitions:
        prepare_or_run_experiment(definition, data_root, dry_run=dry_run)

    if not dry_run and executed:
        _finalise_analysis(data_root, executed)

    return {
        "year": year,
        "doy": doy,
        "base_station": plan.base_station,
        "full_window_stations": plan.full_window_stations,
        "per_gap_stations": plan.per_gap_stations,
        "window": {"start": plan.window.iso_start(), "end": plan.window.iso_end()},
        "experiment_ids": executed,
        "phase2_gate_open": assigned(phase2_gate),
        "dry_run": dry_run,
    }


def _finalise_analysis(data_root: Path, experiment_ids: list[str]) -> None:
    results = load_experiment_results(
        data_root / "processed",
        experiment_ids,
    )
    rows = baseline_analysis_rows(results)
    aggregates = per_baseline_aggregates(rows)
    out = data_root / "processed" / "single-base" / "_phase3-summary"
    out.mkdir(parents=True, exist_ok=True)
    write_json(out / "baseline-analysis.json", {"rows": rows})
    write_json(out / "per-baseline-aggregates.json", aggregates)


def assigned(gate: Phase2Gate) -> bool:
    return gate.missing_items() == []


def _find_conversion_manifest(data_root: Path, year: int, doy: int) -> Path:
    session_dir = data_root / "working" / "sessions" / str(year) / f"{doy:03d}"
    candidate = session_dir / f"conversion-{doy:03d}.json"
    if candidate.is_file():
        return candidate
    raise ScientificExecutionBlocked(f"conversion manifest not found: {candidate}")


def _load_conversion_manifest(
    data_root: Path, year: int, doy: int
) -> dict[str, dict[str, Any]]:
    import json

    path = _find_conversion_manifest(data_root, year, doy)
    return json.loads(path.read_text(encoding="utf-8")) or {}


def _find_navigation(data_root: Path, year: int, doy: int) -> Path:
    from nlgcp_single_base.nav import brdc_filename

    candidate = data_root / "external-products" / "brdc" / str(year) / brdc_filename(year, doy)
    if candidate.is_file():
        return candidate
    candidates = sorted(
        (data_root / "external-products" / "brdc" / str(year)).glob(
            f"BRDC00IGS_R_{year}{doy:03d}*"
        )
    )
    if candidates:
        return candidates[0]
    raise ScientificExecutionBlocked(f"navigation product not found for {year}/{doy}")