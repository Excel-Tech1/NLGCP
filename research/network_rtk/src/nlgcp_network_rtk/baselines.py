"""Deterministic per-baseline RTKLIB execution for network experiments.

Each ``REF -> TEST`` pair is an independent single-base solution and is
labelled a network input/baseline solution.  Running several baselines
does NOT produce a network correction; that claim requires a genuine
network methodology (Phase 6/7).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from nlgcp_single_base.coordinates import EcefCoordinate, GeodeticCoordinate
from nlgcp_single_base.models import Phase2Gate, ProcessingMode, StationCoordinate
from nlgcp_single_base.rtklib import (
    capture_rtklib_provenance,
    render_rtklib_config,
    run_rnx2rtkp,
)
from nlgcp_single_base.solution import (
    parse_solution_pos,
    residuals_against_control,
    solution_epochs_json,
    summarise_accuracy_metrics,
    summarise_solution_state_metrics,
    write_epoch_csv,
)

from nlgcp_network_rtk.io import sha256_text, write_json


@dataclass(frozen=True, slots=True)
class BaselineRequest:
    baseline_id: str
    reference_station: str
    test_station: str
    reference_observation: Path
    test_observation: Path
    navigation_paths: tuple[Path, ...]
    reference_ecef: tuple[float, float, float]
    reference_frame: str
    coordinate_epoch: str
    test_geodetic: tuple[float, float, float] | None
    start_time_utc: str
    end_time_utc: str
    sampling_rate_hz: float
    processing_mode: str
    baseline_distance_m: float


@dataclass(frozen=True, slots=True)
class BaselineResult:
    baseline_id: str
    reference_station: str
    test_station: str
    outcome: str
    detail: str
    solution_metrics: dict[str, Any]
    rtklib_provenance: dict[str, Any]
    config_hash: str
    baseline_distance_m: float
    solution_path: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def baseline_id_for(reference: str, test: str) -> str:
    return f"{reference}-to-{test}"


def execute_baseline(
    request: BaselineRequest,
    output_dir: Path,
    *,
    dry_run: bool = False,
) -> BaselineResult:
    """Execute one REF->TEST baseline with Phase 3 provenance infrastructure."""
    output_dir.mkdir(parents=True, exist_ok=True)
    provenance = capture_rtklib_provenance()
    mode = ProcessingMode(request.processing_mode)
    base_coordinate = StationCoordinate(
        reference_frame=request.reference_frame,
        coordinate_epoch=request.coordinate_epoch,
        ecef=EcefCoordinate(*request.reference_ecef),
    )
    config_text = render_rtklib_config(mode, base_coordinate)
    config_hash = sha256_text(config_text)
    config_path = output_dir / "rtklib.conf"
    provenance_payload = {
        "repository": provenance.repository,
        "tag": provenance.tag,
        "commit": provenance.commit,
        "binary_path": str(provenance.binary_path),
        "binary_sha256": provenance.binary_sha256,
        "matches_recorded_phase1_binary": provenance.matches_recorded_phase1_binary,
    }
    if dry_run:
        return BaselineResult(
            baseline_id=request.baseline_id,
            reference_station=request.reference_station,
            test_station=request.test_station,
            outcome="DRY_RUN",
            detail="dry run: RTKLIB not executed",
            solution_metrics={},
            rtklib_provenance=provenance_payload,
            config_hash=config_hash,
            baseline_distance_m=request.baseline_distance_m,
        )
    inputs = (request.reference_observation, request.test_observation, *request.navigation_paths)
    for path in inputs:
        if not path.is_file():
            return BaselineResult(
                baseline_id=request.baseline_id,
                reference_station=request.reference_station,
                test_station=request.test_station,
                outcome="BLOCKED",
                detail=f"input file unavailable: {path}",
                solution_metrics={},
                rtklib_provenance=provenance_payload,
                config_hash=config_hash,
                baseline_distance_m=request.baseline_distance_m,
            )
    if not provenance.matches_recorded_phase1_binary:
        return BaselineResult(
            baseline_id=request.baseline_id,
            reference_station=request.reference_station,
            test_station=request.test_station,
            outcome="BLOCKED",
            detail="installed rnx2rtkp SHA-256 does not match recorded Phase 1 provenance",
            solution_metrics={},
            rtklib_provenance=provenance_payload,
            config_hash=config_hash,
            baseline_distance_m=request.baseline_distance_m,
        )
    config_path.write_text(config_text, encoding="utf-8")
    solution_path = output_dir / "solution.pos"
    stdout_path = output_dir / "stdout.log"
    stderr_path = output_dir / "stderr.log"
    execution = run_rnx2rtkp(
        provenance,
        config_path,
        request.test_observation,
        request.reference_observation,
        list(request.navigation_paths),
        solution_path,
        stdout_path,
        stderr_path,
        request.start_time_utc,
        request.end_time_utc,
        base_coordinate,
    )
    execution_payload: dict[str, Any] = {
        "command": execution.command,
        "return_code": execution.return_code,
        "duration_seconds": execution.duration_seconds,
        "timeout_seconds": execution.timeout_seconds,
    }
    if execution.return_code != 0:
        return BaselineResult(
            baseline_id=request.baseline_id,
            reference_station=request.reference_station,
            test_station=request.test_station,
            outcome="FAILED_RTKLB",
            detail=f"rnx2rtkp exit {execution.return_code}",
            solution_metrics={"rtklib_execution": execution_payload},
            rtklib_provenance=provenance_payload,
            config_hash=config_hash,
            baseline_distance_m=request.baseline_distance_m,
            solution_path=str(solution_path) if solution_path.exists() else None,
        )
    try:
        parsed = parse_solution_pos(solution_path)
    except Exception as exc:  # parser failure is a scientific output failure, not unexpected
        return BaselineResult(
            baseline_id=request.baseline_id,
            reference_station=request.reference_station,
            test_station=request.test_station,
            outcome="FAILED_OUTPUT",
            detail=f"RTKLIB output parse failed: {exc}",
            solution_metrics={"rtklib_execution": execution_payload},
            rtklib_provenance=provenance_payload,
            config_hash=config_hash,
            baseline_distance_m=request.baseline_distance_m,
            solution_path=str(solution_path),
        )
    if not parsed.epochs:
        return BaselineResult(
            baseline_id=request.baseline_id,
            reference_station=request.reference_station,
            test_station=request.test_station,
            outcome="FAILED_OUTPUT",
            detail="RTKLIB output contained zero valid epochs",
            solution_metrics={"rtklib_execution": execution_payload},
            rtklib_provenance=provenance_payload,
            config_hash=config_hash,
            baseline_distance_m=request.baseline_distance_m,
            solution_path=str(solution_path),
        )
    state_metrics = summarise_solution_state_metrics(
        parsed.epochs,
        start_time_utc=request.start_time_utc,
        end_time_utc=request.end_time_utc,
        sampling_rate_hz=request.sampling_rate_hz,
    )
    metrics: dict[str, Any] = dict(state_metrics)
    metrics["rtklib_execution"] = execution_payload
    metrics["quality_counts"] = _quality_counts(parsed)
    if request.test_geodetic is None:
        metrics["accuracy_metrics_status"] = "blocked"
        metrics["accuracy_metrics_block_reason"] = "trusted rover geodetic control unavailable"
    else:
        control = GeodeticCoordinate(*request.test_geodetic)
        residuals = residuals_against_control(parsed.epochs, control)
        metrics.update(summarise_accuracy_metrics(residuals))
        metrics["accuracy_metrics_status"] = "available"
        write_epoch_csv(output_dir / "epochs.csv", residuals)
    write_json(
        output_dir / "solution-epochs.json", {"epochs": solution_epochs_json(parsed.epochs)}
    )
    write_json(output_dir / "metrics.json", metrics)
    return BaselineResult(
        baseline_id=request.baseline_id,
        reference_station=request.reference_station,
        test_station=request.test_station,
        outcome="COMPLETE",
        detail=(
            "network input/baseline solution "
            "(independent single-base; not a network correction)"
        ),
        solution_metrics=metrics,
        rtklib_provenance=provenance_payload,
        config_hash=config_hash,
        baseline_distance_m=request.baseline_distance_m,
        solution_path=str(solution_path),
    )


def build_phase3_gate() -> Phase2Gate:
    return Phase2Gate(
        base_station_verified=True,
        rover_station_verified=True,
        coordinates_verified=True,
        reference_frame_verified=True,
        coordinate_epoch_verified=True,
        equipment_interval_verified=True,
        real_observations_present=True,
        navigation_present=True,
        overlapping_interval_verified=True,
        sampling_interval_verified=True,
        file_provenance_verified=True,
        hashes_verified=False,
        phase2_audit_approved=True,
    )


def _quality_counts(parsed: Any) -> dict[str, int]:
    counts: dict[str, int] = {}
    for epoch in parsed.epochs:
        counts[epoch.quality.value] = counts.get(epoch.quality.value, 0) + 1
    return counts
