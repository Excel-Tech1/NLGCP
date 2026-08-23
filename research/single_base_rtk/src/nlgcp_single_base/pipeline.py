"""End-to-end preparation and execution for Phase 3 single-base RTK experiments."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from nlgcp_single_base.coordinates import baseline_distance_m
from nlgcp_single_base.io import (
    ensure_experiment_dirs,
    git_provenance,
    read_json,
    sha256_file,
    sha256_text,
    write_json,
)
from nlgcp_single_base.models import (
    BLOCKED_MESSAGE,
    ExperimentDefinition,
    ScientificExecutionBlocked,
)
from nlgcp_single_base.rtklib import (
    assert_recorded_rtklib,
    capture_rtklib_provenance,
    execution_json,
    render_rtklib_config,
    run_rnx2rtkp,
)
from nlgcp_single_base.solution import (
    assert_epochs_within_window,
    parse_solution_pos,
    residuals_against_control,
    solution_epochs_json,
    summarise_accuracy_metrics,
    summarise_solution_state_metrics,
    write_epoch_csv,
)

REPO_ROOT = Path(__file__).resolve().parents[4]


def prepare_or_run_experiment(
    definition: ExperimentDefinition,
    data_root: Path,
    *,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Prepare an experiment directory and optionally run RTKLIB."""

    provenance = capture_rtklib_provenance()
    input_manifest = _build_input_manifest(definition)
    config_text = _render_config_or_placeholder(definition)
    config_hash = sha256_text(config_text)
    material_fingerprint = _material_fingerprint(definition, input_manifest, config_hash)
    _assert_no_collision(data_root, definition.experiment_id, material_fingerprint)

    dirs = ensure_experiment_dirs(data_root, definition.experiment_id)
    config_path = dirs["config"] / "rtklib.conf"
    config_path.write_text(config_text, encoding="utf-8")
    write_json(dirs["inputs"] / "input-manifest.json", input_manifest)

    baseline_m = _scientific_baseline_or_none(definition)
    manifest: dict[str, Any] = {
        "experiment_id": definition.experiment_id,
        "research_question": definition.research_question,
        "stations": [definition.base.station_id, definition.rover.station_id],
        "rover_or_control": definition.rover.station_id,
        "start": definition.start_time_utc,
        "end": definition.end_time_utc,
        "sampling_rate_hz": definition.sampling_rate_hz,
        "input_objects": input_manifest["input_objects"],
        "station_metadata_versions": [
            definition.base.metadata_version,
            definition.rover.metadata_version,
        ],
        "rtklib_build": {
            "repository": provenance.repository,
            "tag": provenance.tag,
            "commit": provenance.commit,
            "binary_path": provenance.binary_path,
            "binary_sha256": provenance.binary_sha256,
            "matches_recorded_phase1_binary": provenance.matches_recorded_phase1_binary,
        },
        "nlgcp_software": git_provenance(REPO_ROOT),
        "pride_version": None,
        "custom_engine_commit": None,
        "configuration_hash": config_hash,
        "material_input_fingerprint": material_fingerprint,
        "precise_products": [],
        "interpolation_model": "none",
        "baseline_distance_m": baseline_m,
        "baseline_status": "available" if baseline_m is not None else "unavailable",
        "base_coordinate_used_by_rtklib": {
            "ecef_m": definition.base.coordinate.ecef,
            "reference_frame": definition.base.coordinate.reference_frame,
            "coordinate_epoch": definition.base.coordinate.coordinate_epoch,
            "metadata_version": definition.base.metadata_version,
            "provenance": definition.base.coordinate.provenance,
            "rtklib_mechanism": "rnx2rtkp -r x y z and ant2-postype=xyz/ant2-pos*",
        },
        "output_objects": [],
        "validation_metrics": {},
        "notes": definition.notes,
        "phase2_gate": definition.phase2_gate,
    }

    try:
        _assert_input_integrity(definition, input_manifest)
        _assert_coordinate_integrity(definition)
        definition.assert_scientifically_runnable()
        assert_recorded_rtklib(provenance)
    except ScientificExecutionBlocked as exc:
        _write_status(dirs, manifest, "blocked", str(exc))
        if dry_run:
            return manifest
        raise

    if dry_run:
        manifest["execution_status"] = "dry_run_ready"
        write_json(dirs["root"] / "manifest.json", manifest)
        _write_report(dirs["report"] / "experiment-report.md", manifest)
        return manifest

    solution_path = dirs["raw_output"] / "solution.pos"
    execution = run_rnx2rtkp(
        provenance,
        config_path,
        definition.rover.observation_path,
        definition.base.observation_path,
        [item.path for item in definition.navigation],
        solution_path,
        dirs["raw_output"] / "stdout.log",
        dirs["raw_output"] / "stderr.log",
        definition.start_time_utc,
        definition.end_time_utc,
        definition.base.coordinate,
    )
    manifest["rtklib_execution"] = execution_json(execution)
    if execution.return_code != 0:
        _write_status(dirs, manifest, "failed_rtklib", f"rnx2rtkp exit {execution.return_code}")
        return manifest

    try:
        parsed = parse_solution_pos(solution_path)
        assert_epochs_within_window(
            parsed.epochs,
            definition.start_time_utc,
            definition.end_time_utc,
        )
    except ScientificExecutionBlocked as exc:
        _write_status(dirs, manifest, "failed_output_format", str(exc))
        return manifest

    if not parsed.epochs:
        _write_status(
            dirs,
            manifest,
            "failed_no_solution",
            "RTKLIB output contained zero valid epochs",
        )
        return manifest

    solution_state_metrics = summarise_solution_state_metrics(
        parsed.epochs,
        start_time_utc=definition.start_time_utc,
        end_time_utc=definition.end_time_utc,
        sampling_rate_hz=definition.sampling_rate_hz,
    )
    write_json(
        dirs["results"] / "solution-epochs.json",
        {"epochs": solution_epochs_json(parsed.epochs)},
    )
    metrics: dict[str, Any] = dict(solution_state_metrics)

    if definition.rover.coordinate.geodetic is None:
        metrics["accuracy_metrics_status"] = "blocked"
        metrics["accuracy_metrics_block_reason"] = (
            "trusted rover geodetic control coordinate unavailable"
        )
    else:
        residuals = residuals_against_control(parsed.epochs, definition.rover.coordinate.geodetic)
        metrics.update(summarise_accuracy_metrics(residuals))
        metrics["accuracy_metrics_status"] = "available"
        write_epoch_csv(dirs["results"] / "epochs.csv", residuals)

    write_json(dirs["results"] / "metrics.json", metrics)
    write_json(
        dirs["results"] / "summary.json",
        {"baseline_distance_m": baseline_m, **metrics},
    )
    manifest["execution_status"] = "complete"
    manifest["validation_metrics"] = metrics
    manifest["output_objects"] = [
        str(solution_path),
        str(dirs["results"] / "solution-epochs.json"),
        str(dirs["results"] / "metrics.json"),
    ]
    write_json(dirs["root"] / "manifest.json", manifest)
    _write_report(dirs["report"] / "experiment-report.md", manifest)
    return manifest


def _build_input_manifest(definition: ExperimentDefinition) -> dict[str, Any]:
    objects = []
    for role, path, recorded_hash in [
        ("base_observation", definition.base.observation_path, definition.base.observation_sha256),
        (
            "rover_observation",
            definition.rover.observation_path,
            definition.rover.observation_sha256,
        ),
    ]:
        objects.append(_input_object(role, path, recorded_hash))
    for navigation in definition.navigation:
        objects.append(_input_object(navigation.product_type, navigation.path, navigation.sha256))
    return {"input_objects": objects}


def _input_object(role: str, path: Path, recorded_hash: str | None) -> dict[str, Any]:
    exists = path.exists()
    is_file = path.is_file()
    observed_hash = sha256_file(path) if exists and is_file else None
    return {
        "role": role,
        "uri": str(path),
        "recorded_sha256": recorded_hash,
        "observed_sha256": observed_hash,
        "sha256": observed_hash,
        "exists": exists,
        "is_file": is_file,
    }


def _assert_input_integrity(
    definition: ExperimentDefinition,
    input_manifest: dict[str, Any],
) -> None:
    if not definition.navigation:
        raise ScientificExecutionBlocked(f"{BLOCKED_MESSAGE}: navigation input missing")
    for item in input_manifest["input_objects"]:
        role = item["role"]
        if not item["exists"] or not item["is_file"]:
            raise ScientificExecutionBlocked(f"{BLOCKED_MESSAGE}: input file unavailable: {role}")
        if definition.phase2_gate.hashes_verified and not item["recorded_sha256"]:
            raise ScientificExecutionBlocked(
                f"{BLOCKED_MESSAGE}: recorded checksum missing: {role}"
            )
        if item["recorded_sha256"] and item["recorded_sha256"] != item["observed_sha256"]:
            raise ScientificExecutionBlocked(f"{BLOCKED_MESSAGE}: checksum mismatch: {role}")


def _assert_coordinate_integrity(definition: ExperimentDefinition) -> None:
    if not definition.phase2_gate.coordinates_verified:
        return
    definition.base.coordinate.require_verified_ecef()
    definition.rover.coordinate.require_verified_ecef()
    definition.base.coordinate.assert_ecef_geodetic_consistent()
    definition.rover.coordinate.assert_ecef_geodetic_consistent()


def _scientific_baseline_or_none(definition: ExperimentDefinition) -> float | None:
    gate = definition.phase2_gate
    if not (
        gate.coordinates_verified
        and gate.reference_frame_verified
        and gate.coordinate_epoch_verified
    ):
        return None
    try:
        return baseline_distance_m(
            definition.base.coordinate.require_verified_ecef(),
            definition.rover.coordinate.require_verified_ecef(),
        )
    except ScientificExecutionBlocked:
        return None


def _render_config_or_placeholder(definition: ExperimentDefinition) -> str:
    if not (
        definition.phase2_gate.coordinates_verified
        and definition.phase2_gate.reference_frame_verified
        and definition.phase2_gate.coordinate_epoch_verified
    ):
        return "\n".join(
            [
                "# NLGCP Phase 3 RTKLIB configuration unavailable",
                "# Verified Phase 2 coordinate/reference-frame gates are required",
                "# before execution.",
                "",
            ]
        )
    try:
        return render_rtklib_config(definition.processing_mode, definition.base.coordinate)
    except ScientificExecutionBlocked:
        return "\n".join(
            [
                "# NLGCP Phase 3 RTKLIB configuration unavailable",
                "# Verified Phase 2 base ECEF coordinate is required before execution.",
                "",
            ]
        )


def _material_fingerprint(
    definition: ExperimentDefinition,
    input_manifest: dict[str, Any],
    config_hash: str,
) -> str:
    payload = {
        "station_ids": [definition.base.station_id, definition.rover.station_id],
        "start_time_utc": definition.start_time_utc,
        "end_time_utc": definition.end_time_utc,
        "input_sha256": [item["observed_sha256"] for item in input_manifest["input_objects"]],
        "processing_mode": definition.processing_mode.value,
        "configuration_hash": config_hash,
        "station_metadata_versions": [
            definition.base.metadata_version,
            definition.rover.metadata_version,
        ],
    }
    return sha256_text(str(sorted(payload.items())))


def _assert_no_collision(data_root: Path, experiment_id: str, fingerprint: str) -> None:
    manifest_path = data_root / "processed" / "single-base" / experiment_id / "manifest.json"
    if not manifest_path.exists():
        return
    existing = read_json(manifest_path)
    if existing.get("material_input_fingerprint") != fingerprint:
        raise ScientificExecutionBlocked(
            f"{BLOCKED_MESSAGE}: experiment_id already exists with different material inputs"
        )


def _write_status(
    dirs: dict[str, Path],
    manifest: dict[str, Any],
    status: str,
    reason: str,
) -> None:
    manifest["execution_status"] = status
    manifest["block_reason" if status == "blocked" else "failure_reason"] = reason
    write_json(dirs["root"] / "manifest.json", manifest)
    _write_report(dirs["report"] / "experiment-report.md", manifest)


def _write_report(path: Path, manifest: dict[str, Any]) -> None:
    status = manifest.get("execution_status", "unknown")
    lines = [
        f"# {manifest['experiment_id']} Single-Base RTK Experiment",
        "",
        f"Status: {status}",
        "",
        f"Research question: {manifest['research_question']}",
        "",
        f"Stations: {', '.join(manifest['stations'])}",
        "",
        f"Baseline distance (m): {manifest['baseline_distance_m']}",
        "",
    ]
    if status == "blocked":
        lines.extend(
            ["Scientific execution is blocked.", "", str(manifest.get("block_reason", "")), ""]
        )
    path.write_text("\n".join(lines), encoding="utf-8")
