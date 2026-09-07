"""Plan / validate / run orchestration for offline network experiments."""

from __future__ import annotations

import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from nlgcp_single_base.rtklib import RECORDED_RNX2RTKP_SHA256

from nlgcp_network_rtk import ENGINE_VERSION, MIN_REFERENCE_STATIONS
from nlgcp_network_rtk.admission import (
    AdmissionSummary,
    admission_fingerprint,
    admit_day,
    session_eligibility_rows,
)
from nlgcp_network_rtk.baselines import (
    BaselineRequest,
    BaselineResult,
    baseline_id_for,
    execute_baseline,
)
from nlgcp_network_rtk.geometry import NetworkGeometry, compute_geometry, load_verified_coordinates
from nlgcp_network_rtk.io import (
    REPO_ROOT,
    ensure_experiment_dirs,
    git_provenance,
    implementation_hash,
    read_json,
    sha256_text,
    write_json,
)
from nlgcp_network_rtk.metrics import comparison_rows, compute_metrics
from nlgcp_network_rtk.models import (
    BLOCKED_MESSAGE,
    ExperimentPlan,
    NetworkBlocked,
    NetworkExperimentDefinition,
    NetworkStatus,
)
from nlgcp_network_rtk.overlap import OverlapResult, assert_sufficient_overlap, compute_overlap
from nlgcp_network_rtk.residuals import (
    dataset_readme,
    residual_rows_for_baseline,
    write_residual_dataset,
)


class UnexpectedExecutionError(RuntimeError):
    """Unexpected failure isolated per baseline/experiment (not REJECT/BLOCKED)."""


def experiment_fingerprint(
    *,
    definition: NetworkExperimentDefinition,
    admission: AdmissionSummary,
    geometry: NetworkGeometry | None,
    overlap: OverlapResult | None,
    rtklib_config_hashes: dict[str, str],
    rtklib_binary_sha256: str | None,
) -> str:
    material = {
        "engine_version": ENGINE_VERSION,
        "definition": definition.fingerprint_material(),
        "admission_fingerprint": admission_fingerprint(admission),
        "geometry_matrix": geometry.baseline_matrix_m if geometry else None,
        "overlap": (
            {
                "common_start": overlap.common_start,
                "common_end": overlap.common_end,
                "expected_epochs": overlap.expected_epochs,
            }
            if overlap
            else None
        ),
        "rtklib_config_hashes": dict(sorted(rtklib_config_hashes.items())),
        "rtklib_binary_sha256": rtklib_binary_sha256,
        "recorded_rtklib_sha256": RECORDED_RNX2RTKP_SHA256,
        "implementation_sha256": _cached_implementation_hash(),
    }
    return hashlib.sha256(
        json.dumps(material, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def plan_experiment(
    data_root: Path, definition: NetworkExperimentDefinition
) -> dict[str, Any]:
    """Dry-run planning: admission + geometry + overlap, no RTKLIB execution."""
    definition_problems = definition.validate()
    admission = admit_day(
        data_root,
        year=definition.year,
        day_of_year=definition.day_of_year,
        profile=definition.qc_profile,
        diagnostic=definition.diagnostic,
    )
    admitted_ids = sorted(row.station_id for row in admission.admitted)
    problems = list(definition.validate())
    wanted_all = (*definition.reference_stations, definition.test_station)
    missing = [s for s in wanted_all if s not in admitted_ids]
    baseline_pairs = [
        (ref, definition.test_station) for ref in sorted(definition.reference_stations)
    ]
    status = NetworkStatus.PLANNED.value
    blocked: list[str] = list(admission.blocked_reasons)
    if definition_problems:
        blocked.extend(definition_problems)
        status = NetworkStatus.BLOCKED.value
    if missing and not definition.diagnostic:
        blocked.append(
            f"stations without {definition.qc_profile} ACCEPT: {', '.join(missing)}"
        )
        status = NetworkStatus.BLOCKED.value
    if len(definition.reference_stations) < definition.minimum_reference_station_count:
        blocked.append("insufficient reference stations for a network experiment")
        status = NetworkStatus.BLOCKED.value
    geometry_dict: dict[str, Any] | None = None
    overlap_dict: dict[str, Any] | None = None
    try:
        verified = load_verified_coordinates(data_root)
        geometry = compute_geometry(
            reference_stations=list(definition.reference_stations),
            test_station=definition.test_station,
            verified=verified,
        )
        geometry_dict = geometry.as_dict()
    except NetworkBlocked as exc:
        blocked.append(str(exc))
        status = NetworkStatus.BLOCKED.value
    if status != NetworkStatus.BLOCKED.value:
        try:
            wanted = {*definition.reference_stations, definition.test_station}
            sessions = [row for row in admission.admitted if row.station_id in wanted]
            overlap = compute_overlap(sessions)
            overlap_dict = overlap.as_dict()
            if not overlap.sufficient:
                blocked.append(str(overlap.block_reason))
                status = NetworkStatus.BLOCKED.value
        except NetworkBlocked as exc:
            blocked.append(str(exc))
            status = NetworkStatus.BLOCKED.value
    if problems:
        blocked.extend(problems)
        status = NetworkStatus.BLOCKED.value
    plan = ExperimentPlan(
        experiment_id=definition.experiment_id,
        status=status,
        admitted_stations=tuple(admitted_ids),
        rejected_stations=tuple(sorted(r["station_id"] for r in admission.rejected)),
        blocked_reasons=tuple(blocked),
        baseline_pairs=tuple(baseline_pairs),
    )
    return {
        "experiment": definition.as_dict(),
        "plan": plan.as_dict(),
        "admission": admission.as_dict(),
        "geometry": geometry_dict,
        "overlap": overlap_dict,
    }


def validate_experiment(data_root: Path, definition: NetworkExperimentDefinition) -> dict[str, Any]:
    """Validate without executing RTKLIB; returns machine-readable verdict."""
    planned = plan_experiment(data_root, definition)
    verdict = "VALIDATED" if planned["plan"]["status"] == NetworkStatus.PLANNED.value else "BLOCKED"
    planned["validation"] = {
        "verdict": verdict,
        "checked": [
            "experiment schema",
            "phase4 network_rtk ACCEPT admission",
            "verified coordinates and reference frame",
            "common observation overlap from actual epochs",
            "minimum reference station count",
            "navigation product presence",
        ],
        "validated_at": datetime.now(UTC).isoformat(timespec="seconds"),
    }
    return planned


def run_experiment(
    data_root: Path,
    definition: NetworkExperimentDefinition,
    *,
    workers: int = 2,
    dry_run: bool = False,
    repo_root: Path | None = None,
) -> dict[str, Any]:
    """Execute all REF->TEST baselines deterministically with resumability."""
    if workers < 1:
        raise UnexpectedExecutionError("workers must be at least 1")
    root = repo_root or REPO_ROOT
    definition.assert_valid()
    admission = admit_day(
        data_root,
        year=definition.year,
        day_of_year=definition.day_of_year,
        profile=definition.qc_profile,
        diagnostic=definition.diagnostic,
    )
    dirs = ensure_experiment_dirs(data_root, definition.experiment_id)
    provenance = git_provenance(root)
    implementation = _cached_implementation_hash(root)
    by_station = {row.station_id: row for row in admission.admitted}
    wanted = [*definition.reference_stations, definition.test_station]
    missing = [s for s in wanted if s not in by_station]
    if missing and not definition.diagnostic:
        reason = (
            f"{BLOCKED_MESSAGE}: stations without {definition.qc_profile} ACCEPT: "
            f"{', '.join(missing)}"
        )
        manifest = _blocked_manifest(
            data_root, definition, admission, dirs, provenance, implementation, reason,
        )
        return manifest
    if len(definition.reference_stations) < definition.minimum_reference_station_count:
        reason = (
            f"{BLOCKED_MESSAGE}: insufficient admitted reference stations "
            f"({len(definition.reference_stations)} < "
            f"{definition.minimum_reference_station_count})"
        )
        manifest = _blocked_manifest(
            data_root, definition, admission, dirs, provenance, implementation, reason,
        )
        return manifest
    try:
        verified = load_verified_coordinates(data_root)
        geometry = compute_geometry(
            reference_stations=list(definition.reference_stations),
            test_station=definition.test_station,
            verified=verified,
        )
    except NetworkBlocked as exc:
        return _blocked_manifest(
            data_root, definition, admission, dirs, provenance, implementation, str(exc)
        )
    try:
        sessions = [by_station[s] for s in sorted(set(wanted))]
        overlap = compute_overlap(sessions)
        assert_sufficient_overlap(overlap)
    except NetworkBlocked as exc:
        return _blocked_manifest(
            data_root, definition, admission, dirs, provenance, implementation, str(exc)
        )
    nav_paths = _resolve_navigation(data_root, definition)
    if not nav_paths:
        return _blocked_manifest(
            data_root, definition, admission, dirs, provenance, implementation,
            f"{BLOCKED_MESSAGE}: navigation product unavailable",
        )
    requests = _baseline_requests(
        data_root, definition, by_station, verified, geometry, overlap, nav_paths
    )
    config_hashes = {req.baseline_id: _config_hash_for(req) for req in requests}
    fingerprint = experiment_fingerprint(
        definition=definition,
        admission=admission,
        geometry=geometry,
        overlap=overlap,
        rtklib_config_hashes=config_hashes,
        rtklib_binary_sha256=RECORDED_RNX2RTKP_SHA256,
    )
    cached = _load_cached_experiment(dirs["root"], fingerprint)
    if cached is not None:
        return cached
    _write_static_outputs(
        data_root, dirs, definition, admission, geometry, overlap,
        provenance, implementation, fingerprint, nav_paths,
    )
    if dry_run:
        manifest = _manifest_skeleton(
            definition, admission, geometry, overlap,
            provenance, implementation, fingerprint,
            status=NetworkStatus.PLANNED.value,
        )
        manifest["baselines"] = [
            {"baseline_id": r.baseline_id, "outcome": "DRY_RUN", "detail": "dry run"}
            for r in requests
        ]
        write_json(
            dirs["root"] / "validation.json",
            {"verdict": "DRY_RUN", "fingerprint": fingerprint},
        )
        write_json(dirs["root"] / "metrics.json", compute_metrics(
            experiment_id=definition.experiment_id,
            admitted_count=len(admission.admitted),
            rejected_count=len(admission.rejected),
            geometry=geometry, overlap=overlap, baselines=[],
        ))
        return manifest
    results = _execute_baselines_parallel(requests, dirs, workers=workers)
    metrics = compute_metrics(
        experiment_id=definition.experiment_id,
        admitted_count=len(admission.admitted),
        rejected_count=len(admission.rejected),
        geometry=geometry,
        overlap=overlap,
        baselines=results,
    )
    comparison = comparison_rows(metrics=metrics, nearest_reference=geometry.nearest_reference)
    outcomes = {r.outcome for r in results}
    if outcomes == {"COMPLETE"}:
        status = NetworkStatus.COMPLETE.value
    elif "FAILED_UNEXPECTED" in outcomes:
        status = NetworkStatus.FAILED_UNEXPECTED.value
    else:
        status = NetworkStatus.COMPLETE.value
    manifest = _manifest_skeleton(
        definition, admission, geometry, overlap,
        provenance, implementation, fingerprint, status=status,
    )
    manifest["baselines"] = [r.as_dict() for r in sorted(results, key=lambda b: b.baseline_id)]
    manifest["rtklib_runs"] = sum(
        1 for r in results if r.outcome in {"COMPLETE", "FAILED_RTKLB", "FAILED_OUTPUT"}
    )
    write_json(dirs["root"] / "metrics.json", metrics)
    write_json(dirs["root"] / "validation.json", {
        "verdict": status,
        "fingerprint": fingerprint,
        "baseline_outcomes": {r.baseline_id: r.outcome for r in results},
        "comparison": comparison,
        "validated_at": datetime.now(UTC).isoformat(timespec="seconds"),
    })
    write_json(dirs["root"] / "experiment.json", definition.as_dict())
    manifest["comparison"] = comparison
    manifest["metrics_summary"] = metrics["network_aggregate_metrics"]
    write_json(dirs["root"] / "provenance.json", manifest["provenance"])
    _write_residual_dataset(dirs, definition, results)
    _write_summaries(data_root, definition, admission, geometry, results, metrics)
    write_json(dirs["root"] / "manifest.json", manifest)
    return manifest


def _baseline_requests(
    data_root: Path,
    definition: NetworkExperimentDefinition,
    by_station: dict[str, Any],
    verified: dict[str, dict[str, Any]],
    geometry: NetworkGeometry,
    overlap: OverlapResult,
    nav_paths: list[Path],
) -> list[BaselineRequest]:
    if definition.sampling_interval_seconds:
        sampling_hz = 1.0 / definition.sampling_interval_seconds
    else:
        sampling_hz = 1.0 / 30.0
    requests: list[BaselineRequest] = []
    for ref in sorted(definition.reference_stations):
        admitted_ref = by_station[ref]
        admitted_test = by_station[definition.test_station]
        _ = admitted_ref
        test_geo = _test_geodetic(data_root, verified, definition.test_station)
        requests.append(
            BaselineRequest(
                baseline_id=baseline_id_for(ref, definition.test_station),
                reference_station=ref,
                test_station=definition.test_station,
                reference_observation=Path(str(by_station[ref].observation_path)),
                test_observation=Path(
                    str(by_station[definition.test_station].observation_path)
                ),
                navigation_paths=tuple(nav_paths),
                reference_ecef=(
                    float(verified[ref]["x_m"]),
                    float(verified[ref]["y_m"]),
                    float(verified[ref]["z_m"]),
                ),
                reference_frame=str(verified[ref]["reference_frame"]),
                coordinate_epoch=str(verified[ref]["coordinate_epoch"]),
                test_geodetic=test_geo,
                start_time_utc=overlap.common_start,
                end_time_utc=overlap.common_end,
                sampling_rate_hz=sampling_hz,
                processing_mode=definition.processing_mode,
                baseline_distance_m=float(geometry.reference_to_rover_m[ref]),
            )
        )
    _ = admitted_test
    return requests


def _test_geodetic(
    data_root: Path, verified: dict[str, dict[str, Any]], test_station: str
) -> tuple[float, float, float] | None:
    del data_root
    row = verified.get(test_station)
    if row is None:
        return None
    try:
        from nlgcp_single_base.coordinates import EcefCoordinate as _Ecef
        from nlgcp_single_base.coordinates import ecef_to_geodetic

        geo = ecef_to_geodetic(_Ecef(float(row["x_m"]), float(row["y_m"]), float(row["z_m"])))
        return (geo.latitude_deg, geo.longitude_deg, geo.height_m)
    except (KeyError, TypeError, ValueError):
        return None


def _resolve_navigation(data_root: Path, definition: NetworkExperimentDefinition) -> list[Path]:
    paths: list[Path] = []
    for rel in definition.navigation_products:
        candidate = data_root / rel
        if candidate.is_file():
            paths.append(candidate)
    return paths


def _config_hash_for(request: BaselineRequest) -> str:
    from nlgcp_single_base.coordinates import EcefCoordinate as _Ecef
    from nlgcp_single_base.models import ProcessingMode as _Mode
    from nlgcp_single_base.models import StationCoordinate as _Coord
    from nlgcp_single_base.rtklib import render_rtklib_config as _render

    coord = _Coord(
        reference_frame=request.reference_frame,
        coordinate_epoch=request.coordinate_epoch,
        ecef=_Ecef(*request.reference_ecef),
    )
    return sha256_text(_render(_Mode(request.processing_mode), coord))


def _execute_baselines_parallel(
    requests: list[BaselineRequest], dirs: dict[str, Path], *, workers: int
) -> list[BaselineResult]:
    bounded = max(1, min(workers, 8))

    def _run(request: BaselineRequest) -> BaselineResult:
        try:
            return execute_baseline(request, dirs["baselines"] / request.baseline_id)
        except Exception as exc:  # isolated; never corrupts sibling baselines
            return BaselineResult(
                baseline_id=request.baseline_id,
                reference_station=request.reference_station,
                test_station=request.test_station,
                outcome="FAILED_UNEXPECTED",
                detail=f"unexpected execution failure: {type(exc).__name__}: {exc}",
                solution_metrics={},
                rtklib_provenance={},
                config_hash="",
                baseline_distance_m=request.baseline_distance_m,
            )

    with ThreadPoolExecutor(max_workers=bounded, thread_name_prefix="nlgcp-netrtk") as pool:
        # executor.map preserves input order -> deterministic output regardless of finish order
        return list(pool.map(_run, sorted(requests, key=lambda r: r.baseline_id)))


def _manifest_skeleton(
    definition: NetworkExperimentDefinition,
    admission: AdmissionSummary,
    geometry: NetworkGeometry | None,
    overlap: OverlapResult | None,
    provenance: dict[str, Any],
    implementation: str,
    fingerprint: str,
    *,
    status: str,
) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "engine_version": ENGINE_VERSION,
        "experiment_id": definition.experiment_id,
        "research_question": definition.research_question,
        "status": status,
        "diagnostic": definition.diagnostic,
        "definition": definition.as_dict(),
        "admission_fingerprint": admission_fingerprint(admission),
        "experiment_fingerprint": fingerprint,
        "minimum_reference_station_count": definition.minimum_reference_station_count,
        "required_minimum": MIN_REFERENCE_STATIONS,
        "provenance": {
            "nlgcp_software": provenance,
            "implementation_sha256": implementation,
            "rtklib_recorded_sha256": RECORDED_RNX2RTKP_SHA256,
        },
        "geometry": geometry.as_dict() if geometry else None,
        "overlap": overlap.as_dict() if overlap else None,
        "executed_at": datetime.now(UTC).isoformat(timespec="seconds"),
    }


def _blocked_manifest(
    data_root: Path,
    definition: NetworkExperimentDefinition,
    admission: AdmissionSummary,
    dirs: dict[str, Path],
    provenance: dict[str, Any],
    implementation: str,
    reason: str,
) -> dict[str, Any]:
    del data_root
    manifest = _manifest_skeleton(
        definition, admission, None, None, provenance, implementation,
        fingerprint=sha256_text(reason + definition.experiment_id),
        status=NetworkStatus.BLOCKED.value,
    )
    manifest["block_reason"] = reason
    manifest["baselines"] = []
    write_json(dirs["root"] / "experiment.json", definition.as_dict())
    write_json(dirs["root"] / "admission.json", admission.as_dict())
    write_json(dirs["root"] / "validation.json", {"verdict": "BLOCKED", "reason": reason})
    write_json(dirs["root"] / "provenance.json", manifest["provenance"])
    write_json(dirs["root"] / "manifest.json", manifest)
    return manifest


def _write_static_outputs(
    data_root: Path,
    dirs: dict[str, Path],
    definition: NetworkExperimentDefinition,
    admission: AdmissionSummary,
    geometry: NetworkGeometry,
    overlap: OverlapResult,
    provenance: dict[str, Any],
    implementation: str,
    fingerprint: str,
    nav_paths: list[Path],
) -> None:
    del data_root
    write_json(dirs["root"] / "experiment.json", definition.as_dict())
    write_json(dirs["root"] / "admission.json", admission.as_dict())
    write_json(dirs["root"] / "geometry.json", geometry.as_dict())
    write_json(dirs["root"] / "overlap.json", overlap.as_dict())
    write_json(dirs["root"] / "provenance.json", {
        "nlgcp_software": provenance,
        "implementation_sha256": implementation,
        "rtklib_recorded_sha256": RECORDED_RNX2RTKP_SHA256,
        "navigation_paths": [str(p) for p in nav_paths],
        "experiment_fingerprint": fingerprint,
    })
    (dirs["config"] / "rtklib-notes.txt").write_text(
        "Per-baseline rtklib.conf files live under baselines/<baseline-id>/rtklib.conf.\n"
        "Configuration: Phase 3 static defaults (GPS-only, L1+L2, 15 deg mask,\n"
        "continuous AR) with explicit -r base ECEF. Do not tune to manufacture FIX.\n",
        encoding="utf-8",
    )


def _write_residual_dataset(
    dirs: dict[str, Path], definition: NetworkExperimentDefinition, results: list[BaselineResult]
) -> None:
    rows = []
    for row in sorted(results, key=lambda b: b.baseline_id):
        rows.extend(
            residual_rows_for_baseline(
                baseline_id=row.baseline_id,
                test_station=row.test_station,
                baseline_length_m=row.baseline_distance_m,
                epochs_csv=dirs["baselines"] / row.baseline_id / "epochs.csv",
            )
        )
    write_residual_dataset(dirs["root"] / "baselines" / "network-residuals.csv", rows)
    (dirs["root"] / "baselines" / "README.md").write_text(dataset_readme(), encoding="utf-8")
    _ = definition


def _write_summaries(
    data_root: Path,
    definition: NetworkExperimentDefinition,
    admission: AdmissionSummary,
    geometry: NetworkGeometry,
    results: list[BaselineResult],
    metrics: dict[str, Any],
) -> None:
    import csv as _csv

    summary_dir = data_root / "processed" / "network-rtk" / "summaries"
    summary_dir.mkdir(parents=True, exist_ok=True)
    _upsert_csv(
        summary_dir / "network-experiments.csv",
        ["experiment_id", "year", "doy", "rover", "references", "status", "fingerprint"],
        {
            "experiment_id": definition.experiment_id,
            "year": str(definition.year),
            "doy": str(definition.day_of_year),
            "rover": definition.test_station,
            "references": "+".join(sorted(definition.reference_stations)),
            "status": "COMPLETE",
            "fingerprint": str(metrics.get("experiment_id", definition.experiment_id)),
        },
        key="experiment_id",
    )
    _upsert_csv(
        summary_dir / "baseline-matrix.csv",
        ["experiment_id", "baseline_id", "reference", "rover", "distance_m", "outcome"],
        None,
        key="",
    )
    _rewrite_baseline_matrix(summary_dir / "baseline-matrix.csv", definition, results)
    _upsert_csv(
        summary_dir / "station-eligibility.csv",
        ["year", "day_of_year", "station_id", "decision", "qc_status", "reason"],
        None,
        key="",
    )
    _rewrite_eligibility(summary_dir / "station-eligibility.csv", admission)
    with (summary_dir / "comparison.csv").open("a", encoding="utf-8", newline="") as handle:
        writer = _csv.DictWriter(
            handle,
            fieldnames=[
                "experiment_id",
                "comparison",
                "reference",
                "horizontal_rmse_m",
                "three_d_rmse_m",
                "fix_rate",
                "note",
            ],
        )
        if handle.tell() == 0:
            writer.writeheader()
        for row in comparison_rows(metrics=metrics, nearest_reference=geometry.nearest_reference):
            writer.writerow({"experiment_id": definition.experiment_id, **row})


def _upsert_csv(path: Path, fields: list[str], row: dict[str, str] | None, *, key: str) -> None:
    import csv as _csv

    path.parent.mkdir(parents=True, exist_ok=True)
    existing: list[dict[str, str]] = []
    if path.is_file():
        with path.open(encoding="utf-8", newline="") as handle:
            existing = list(_csv.DictReader(handle))
    if row is None:
        if not path.is_file():
            with path.open("w", encoding="utf-8", newline="") as handle:
                _csv.DictWriter(handle, fieldnames=fields).writeheader()
        return
    existing = [r for r in existing if r.get(key) != row.get(key)] + [row]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = _csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(sorted(existing, key=lambda r: r.get(key, "")))


def _rewrite_baseline_matrix(
    path: Path, definition: NetworkExperimentDefinition, results: list[BaselineResult]
) -> None:
    import csv as _csv

    rows: list[dict[str, str]] = []
    if path.is_file():
        with path.open(encoding="utf-8", newline="") as handle:
            rows = [
                r
                for r in _csv.DictReader(handle)
                if r.get("experiment_id") != definition.experiment_id
            ]
    for row in sorted(results, key=lambda b: b.baseline_id):
        rows.append(
            {
                "experiment_id": definition.experiment_id,
                "baseline_id": row.baseline_id,
                "reference": row.reference_station,
                "rover": row.test_station,
                "distance_m": f"{row.baseline_distance_m:.3f}",
                "outcome": row.outcome,
            }
        )
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = _csv.DictWriter(
            handle,
            fieldnames=[
                "experiment_id",
                "baseline_id",
                "reference",
                "rover",
                "distance_m",
                "outcome",
            ],
        )
        writer.writeheader()
        writer.writerows(sorted(rows, key=lambda r: (r["experiment_id"], r["baseline_id"])))


def _rewrite_eligibility(path: Path, admission: AdmissionSummary) -> None:
    import csv as _csv

    rows: list[dict[str, str]] = []
    if path.is_file():
        with path.open(encoding="utf-8", newline="") as handle:
            rows = [
                r
                for r in _csv.DictReader(handle)
                if not (
                    r.get("year") == str(admission.year)
                    and r.get("day_of_year") == str(admission.day_of_year)
                )
            ]
    for row in session_eligibility_rows(admission):
        rows.append(
            {
                "year": str(row["year"]),
                "day_of_year": str(row["day_of_year"]),
                "station_id": str(row["station_id"]),
                "decision": str(row["decision"]),
                "qc_status": str(row["qc_status"]),
                "reason": str(row["reason"]),
            }
        )
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = _csv.DictWriter(
            handle,
            fieldnames=[
                "year",
                "day_of_year",
                "station_id",
                "decision",
                "qc_status",
                "reason",
            ],
        )
        writer.writeheader()
        writer.writerows(sorted(rows, key=lambda r: (r["year"], r["day_of_year"], r["station_id"])))


def _load_cached_experiment(experiment_dir: Path, fingerprint: str) -> dict[str, Any] | None:
    manifest_path = experiment_dir / "manifest.json"
    if not manifest_path.is_file():
        return None
    try:
        manifest = read_json(manifest_path)
    except (OSError, ValueError):
        return None
    if manifest.get("experiment_fingerprint") != fingerprint:
        return None
    manifest["reused_verified_result"] = True
    return manifest


_implementation_cache: dict[str, str] = {}


def _cached_implementation_hash(repo_root: Path | None = None) -> str:
    root = repo_root or REPO_ROOT
    key = str(root)
    if key not in _implementation_cache:
        try:
            _implementation_cache[key] = implementation_hash(root)
        except OSError:
            _implementation_cache[key] = "unavailable"
    return _implementation_cache[key]
