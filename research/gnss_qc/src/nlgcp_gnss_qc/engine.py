"""Resumable Phase 4 session and dataset execution."""

from __future__ import annotations

import csv
import hashlib
import json
import os
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import IO, Any

from nlgcp_api.rinex_inventory import sha256_file
from nlgcp_single_base.conversion import (
    ConversionError,
    ObservationConversion,
    convert_observation,
)

from nlgcp_gnss_qc import ENGINE_VERSION, RESULT_SCHEMA_VERSION
from nlgcp_gnss_qc.classify import classify_session
from nlgcp_gnss_qc.dataset import (
    CoordinateEligibility,
    NavigationProduct,
    inventory_navigation_products,
    load_coordinate_eligibility,
    load_session_inputs,
    navigation_for_session,
    parse_filename,
    resolve_identity,
)
from nlgcp_gnss_qc.models import (
    Finding,
    FindingSeverity,
    SessionInput,
    overall_classification,
)
from nlgcp_gnss_qc.profiles import QCProfile, load_profiles
from nlgcp_gnss_qc.rinex import RinexParseError, analyse_rinex2


class QCExecutionError(RuntimeError):
    """Raised for a dataset-level setup error, not a scientific rejection."""


def resolve_data_root(explicit: Path | None = None) -> Path:
    """Resolve the external vault without embedding a host-specific path."""

    value = explicit or (
        Path(os.environ["NLGCP_DATA_ROOT"]) if "NLGCP_DATA_ROOT" in os.environ else None
    )
    if value is None:
        raise QCExecutionError("NLGCP_DATA_ROOT is not configured")
    root = value.expanduser().resolve()
    if not root.is_dir():
        raise QCExecutionError(f"NLGCP_DATA_ROOT is not a directory: {root}")
    return root


def select_sessions(
    sessions: list[SessionInput],
    *,
    station_ids: set[str] | None = None,
    start_doy: int | None = None,
    end_doy: int | None = None,
) -> list[SessionInput]:
    """Select a deterministic subset for session/station/range/dataset commands."""

    return [
        session
        for session in sessions
        if (station_ids is None or session.station_id in station_ids)
        and (start_doy is None or session.day_of_year >= start_doy)
        and (end_doy is None or session.day_of_year <= end_doy)
    ]


def plan_dataset(
    data_root: Path,
    sessions: list[SessionInput],
    profiles: list[QCProfile],
    *,
    convert: bool,
) -> dict[str, Any]:
    """Report planned work without creating directories or converting data."""

    conversions_required = 0
    existing_conversions = 0
    cached_results = 0
    navigation = inventory_navigation_products(data_root)
    for session in sessions:
        converted = _converted_path(data_root, session)
        if convert and converted.is_file():
            existing_conversions += 1
        elif convert:
            conversions_required += 1
        for profile in profiles:
            if _result_path(data_root, profile, session).is_file():
                cached_results += 1
    return {
        "mode": "dry-run",
        "files_selected": len(sessions),
        "files_excluded": len(load_session_inputs(data_root)) - len(sessions),
        "profiles": [profile.name for profile in profiles],
        "conversions_required": conversions_required,
        "existing_conversions_reusable_after_fingerprint_check": existing_conversions,
        "existing_profile_results_reusable_after_fingerprint_check": cached_results,
        "navigation_products_catalogued": len(navigation),
        "navigation_covered_sessions": sum(
            navigation_for_session(navigation, row.year, row.day_of_year) is not None
            for row in sessions
        ),
        "expected_profile_results": len(sessions) * len(profiles),
        "output_root": str(data_root / "processed" / "qc" / "profiles"),
        "conversion_root": str(data_root / "working" / "qc-converted"),
    }


def run_dataset(
    data_root: Path,
    sessions: list[SessionInput],
    profiles: list[QCProfile],
    *,
    convert: bool = True,
    progress_every: int = 25,
    workers: int = 1,
) -> list[dict[str, Any]]:
    """Process sessions independently so one bad file cannot terminate a batch."""

    products = inventory_navigation_products(data_root)
    coordinates = load_coordinate_eligibility(data_root)
    provenance = git_provenance(Path.cwd())
    results: list[dict[str, Any]] = []
    unexpected = 0
    if workers < 1:
        raise QCExecutionError("workers must be at least 1")

    def execute(session: SessionInput) -> tuple[list[dict[str, Any]], bool]:
        try:
            rows = process_session(
                data_root,
                session,
                profiles,
                products=products,
                coordinates=coordinates,
                provenance=provenance,
                convert=convert,
            )
            return rows, False
        except Exception as exc:  # batch isolation is intentional; details are persisted
            return (
                _failure_results(data_root, session, profiles, provenance, exc, convert),
                True,
            )

    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="nlgcp-qc") as executor:
        completed = executor.map(execute, sessions)
        for index, (rows, failed) in enumerate(completed, start=1):
            unexpected += int(failed)
            results.extend(rows)
            if progress_every > 0 and (index % progress_every == 0 or index == len(sessions)):
                print(
                    f"QC progress: {index}/{len(sessions)} sessions; "
                    f"unexpected_failures={unexpected}; workers={workers}",
                    flush=True,
                )
    return results


def process_session(
    data_root: Path,
    session: SessionInput,
    profiles: list[QCProfile],
    *,
    products: list[NavigationProduct],
    coordinates: dict[str, CoordinateEligibility],
    provenance: dict[str, Any],
    convert: bool,
) -> list[dict[str, Any]]:
    """Verify, convert, analyse once, then classify under every requested profile."""

    source_path = data_root / session.relative_path
    if not source_path.is_file():
        raise FileNotFoundError(f"canonical observation unavailable: {source_path}")
    observed_sha256 = sha256_file(source_path)
    fingerprints = {
        profile.name: _fingerprint(session, profile, provenance, convert) for profile in profiles
    }
    cached = _load_cached(data_root, session, profiles, fingerprints, observed_sha256)
    if cached is not None:
        return cached

    if observed_sha256 != session.sha256:
        return _integrity_failure_results(
            data_root, session, profiles, provenance, observed_sha256, fingerprints
        )
    filename_marker, filename_year, filename_doy, filename_kind = parse_filename(source_path.name)
    if (filename_year, filename_doy) != (session.year, session.day_of_year):
        raise RinexParseError("filename date disagrees with canonical manifest")
    if filename_kind not in {"D", "O"}:
        raise RinexParseError(f"unexpected observation file type: {filename_kind}")

    conversion_payload: dict[str, Any]
    handle: IO[str]
    if convert:
        conversion = _convert_verified(data_root, session, source_path)
        analysis_path = conversion.converted_path
        conversion_payload = conversion.as_dict()
        _atomic_json(_conversion_manifest_path(data_root, session), conversion_payload)
        handle = analysis_path.open(encoding="ascii", errors="replace")
    else:
        handle, conversion_payload = _stream_converted(source_path)
    try:
        analysis = analyse_rinex2(handle, year=session.year, day_of_year=session.day_of_year)
    finally:
        handle.close()
        processes = conversion_payload.pop("_processes", None)
        if isinstance(processes, tuple):
            converter, uncompress = processes
            stderr = converter.stderr.read() if converter.stderr is not None else ""
            return_code = converter.wait()
            uncompress_stderr = (
                uncompress.stderr.read().decode(errors="replace")
                if uncompress.stderr is not None
                else ""
            )
            uncompress_code = uncompress.wait()
            conversion_payload["converter_exit_code"] = return_code
            conversion_payload["uncompress_exit_code"] = uncompress_code
            conversion_payload["converter_stderr"] = stderr.strip()
            conversion_payload["uncompress_stderr"] = uncompress_stderr.strip()
            if return_code not in {0, 2} or uncompress_code != 0:
                raise ConversionError(
                    "streaming conversion failed: "
                    f"uncompress_rc={uncompress_code}, CRX2RNX_rc={return_code}; "
                    f"{uncompress_stderr.strip()} {stderr.strip()}"
                )

    identity = resolve_identity(session.station_id, filename_marker, analysis.header.marker_name)
    navigation = navigation_for_session(products, session.year, session.day_of_year)
    results: list[dict[str, Any]] = []
    for profile in profiles:
        findings = classify_session(
            session,
            analysis,
            profile,
            identity_status=identity,
            source_path=source_path,
            observed_sha256=observed_sha256,
            navigation=navigation,
            coordinate=coordinates.get(session.station_id),
        )
        result = _result_payload(
            session=session,
            profile=profile,
            analysis=analysis.as_dict(),
            findings=findings,
            fingerprint=fingerprints[profile.name],
            observed_sha256=observed_sha256,
            identity=identity,
            conversion=conversion_payload,
            navigation=navigation.as_dict() if navigation else None,
            coordinate=(
                asdict(coordinates[session.station_id])
                if session.station_id in coordinates
                else None
            ),
            provenance=provenance,
            reused=False,
        )
        _write_session_outputs(data_root, session, profile, result)
        results.append(result)
    return results


def _load_cached(
    data_root: Path,
    session: SessionInput,
    profiles: list[QCProfile],
    fingerprints: dict[str, str],
    observed_sha256: str,
) -> list[dict[str, Any]] | None:
    rows: list[dict[str, Any]] = []
    for profile in profiles:
        path = _result_path(data_root, profile, session)
        if not path.is_file():
            return None
        payload: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("result_fingerprint") != fingerprints[profile.name]:
            return None
        if payload.get("source", {}).get("observed_sha256") != observed_sha256:
            return None
        payload["reused_verified_result"] = True
        rows.append(payload)
    return rows


def _stream_converted(source_path: Path) -> tuple[IO[str], dict[str, Any]]:
    uncompress = subprocess.Popen(
        ["uncompress", "-c", str(source_path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if uncompress.stdout is None:
        raise ConversionError("failed to open uncompress output")
    converter = subprocess.Popen(
        ["CRX2RNX"],
        stdin=uncompress.stdout,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="ascii",
        errors="replace",
    )
    uncompress.stdout.close()
    if converter.stdout is None:
        raise ConversionError("failed to open streaming converter output")
    return converter.stdout, {
        "mode": "stream_only",
        "source_path": str(source_path),
        "commands": [["uncompress", "-c", str(source_path)], ["CRX2RNX"]],
        "_processes": (converter, uncompress),
    }


def _convert_verified(
    data_root: Path, session: SessionInput, source_path: Path
) -> ObservationConversion:
    """Reuse only hash-verified conversion outputs; atomically replace stale derivatives."""

    output_dir = _conversion_dir(data_root, session)
    manifest_path = _conversion_manifest_path(data_root, session)
    if manifest_path.is_file():
        try:
            manifest: dict[str, Any] = json.loads(manifest_path.read_text(encoding="utf-8"))
            converted = Path(str(manifest["converted_path"]))
            decompressed = Path(str(manifest["decompressed_path"]))
            valid = (
                manifest.get("source_sha256") == session.sha256
                and converted.is_file()
                and decompressed.is_file()
                and sha256_file(converted) == manifest.get("converted_sha256")
                and sha256_file(decompressed) == manifest.get("decompressed_sha256")
            )
            if valid:
                return ObservationConversion(
                    source_path=source_path,
                    source_sha256=str(manifest["source_sha256"]),
                    decompressed_path=decompressed,
                    decompressed_sha256=str(manifest["decompressed_sha256"]),
                    converted_path=converted,
                    converted_sha256=str(manifest["converted_sha256"]),
                    crx2rnx_version=str(manifest["crx2rnx_version"]),
                    uncompress_tool=str(manifest["uncompress_tool"]),
                    started_at=str(manifest["started_at"]),
                    duration_seconds=float(manifest["duration_seconds"]),
                    crx2rnx_rc=int(manifest["crx2rnx_rc"]),
                )
        except (KeyError, OSError, ValueError, json.JSONDecodeError):
            pass

    output_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".conversion-build-", dir=output_dir) as temporary:
        staged = convert_observation(source_path, Path(temporary))
        decompressed_target = output_dir / staged.decompressed_path.name
        converted_target = output_dir / staged.converted_path.name
        staged.decompressed_path.replace(decompressed_target)
        staged.converted_path.replace(converted_target)
        return replace(
            staged,
            decompressed_path=decompressed_target,
            converted_path=converted_target,
        )


def _result_payload(
    *,
    session: SessionInput,
    profile: QCProfile,
    analysis: dict[str, Any] | None,
    findings: list[Finding],
    fingerprint: str,
    observed_sha256: str | None,
    identity: str | None,
    conversion: dict[str, Any] | None,
    navigation: dict[str, Any] | None,
    coordinate: dict[str, Any] | None,
    provenance: dict[str, Any],
    reused: bool,
) -> dict[str, Any]:
    return {
        "schema_version": RESULT_SCHEMA_VERSION,
        "engine_version": ENGINE_VERSION,
        "result_fingerprint": fingerprint,
        "station_identity": {
            "canonical_station_id": session.station_id,
            "year": session.year,
            "day_of_year": session.day_of_year,
            "resolution": identity,
        },
        "source": {
            "relative_path": session.relative_path,
            "delivery_relative_path": session.source_relative_path,
            "manifest_sha256": session.sha256,
            "observed_sha256": observed_sha256,
            "size_bytes": session.size_bytes,
            "exact_duplicate_sources": list(session.exact_duplicate_sources),
        },
        "conversion": conversion,
        "rinex": analysis,
        "navigation": navigation,
        "coordinate_eligibility": coordinate,
        "findings": [finding.as_dict() for finding in findings],
        "overall_classification": overall_classification(findings).value,
        "qc_profile": {
            "name": profile.name,
            "version": profile.version,
            "status": profile.status,
            "configuration_sha256": profile.config_sha256,
        },
        "software_provenance": provenance,
        "execution_timestamp": datetime.now(UTC).isoformat(timespec="seconds"),
        "reused_verified_result": reused,
    }


def _integrity_failure_results(
    data_root: Path,
    session: SessionInput,
    profiles: list[QCProfile],
    provenance: dict[str, Any],
    observed_sha256: str,
    fingerprints: dict[str, str],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for profile in profiles:
        finding = _failure_finding(
            session,
            "HASH_MISMATCH",
            FindingSeverity.REJECT,
            "Observed SHA-256 does not match the canonical manifest",
            {"observed": observed_sha256, "expected": session.sha256},
        )
        result = _result_payload(
            session=session,
            profile=profile,
            analysis=None,
            findings=[finding],
            fingerprint=fingerprints[profile.name],
            observed_sha256=observed_sha256,
            identity=None,
            conversion=None,
            navigation=None,
            coordinate=None,
            provenance=provenance,
            reused=False,
        )
        _write_session_outputs(data_root, session, profile, result)
        rows.append(result)
    return rows


def _failure_results(
    data_root: Path,
    session: SessionInput,
    profiles: list[QCProfile],
    provenance: dict[str, Any],
    error: Exception,
    convert: bool,
) -> list[dict[str, Any]]:
    missing = isinstance(error, FileNotFoundError)
    severity = FindingSeverity.BLOCKED if missing else FindingSeverity.REJECT
    code = "SOURCE_FILE_UNAVAILABLE" if missing else "SESSION_PROCESSING_FAILED"
    rows: list[dict[str, Any]] = []
    for profile in profiles:
        finding = _failure_finding(
            session,
            code,
            severity,
            str(error),
            {"exception_type": type(error).__name__},
        )
        result = _result_payload(
            session=session,
            profile=profile,
            analysis=None,
            findings=[finding],
            fingerprint=_fingerprint(session, profile, provenance, convert),
            observed_sha256=None,
            identity=None,
            conversion=None,
            navigation=None,
            coordinate=None,
            provenance=provenance,
            reused=False,
        )
        _write_session_outputs(data_root, session, profile, result)
        rows.append(result)
    return rows


def _failure_finding(
    session: SessionInput,
    code: str,
    severity: FindingSeverity,
    message: str,
    evidence: dict[str, Any],
) -> Finding:
    return Finding(
        finding_code=code,
        severity=severity,
        category="execution" if code == "SESSION_PROCESSING_FAILED" else "file_integrity",
        station_id=session.station_id,
        year=session.year,
        day_of_year=session.day_of_year,
        file=session.relative_path,
        message=message,
        evidence=evidence,
    )


def _write_session_outputs(
    data_root: Path,
    session: SessionInput,
    profile: QCProfile,
    result: dict[str, Any],
) -> None:
    directory = _result_path(data_root, profile, session).parent
    directory.mkdir(parents=True, exist_ok=True)
    _atomic_json(directory / "qc-result.json", result)
    analysis = result.get("rinex")
    if not isinstance(analysis, dict):
        return
    gaps = analysis.get("gaps", [])
    _atomic_csv(
        directory / "gaps.csv",
        ["start", "end", "elapsed_seconds", "expected_interval_seconds", "missing_epochs"],
        gaps,
    )
    constellations = analysis.get("constellation_statistics", {})
    satellite_rows = [
        {"constellation": name, **values} for name, values in sorted(constellations.items())
    ]
    _atomic_csv(
        directory / "satellite-summary.csv",
        [
            "constellation",
            "epochs_present",
            "minimum_per_epoch",
            "median_per_epoch",
            "maximum_per_epoch",
        ],
        satellite_rows,
    )
    conversion = result.get("conversion")
    if isinstance(conversion, dict):
        _atomic_json(directory / "conversion-manifest.json", conversion)


def _fingerprint(
    session: SessionInput,
    profile: QCProfile,
    provenance: dict[str, Any],
    convert: bool,
) -> str:
    material = {
        "engine_version": ENGINE_VERSION,
        "source_sha256": session.sha256,
        "profile": profile.name,
        "profile_version": profile.version,
        "profile_sha256": profile.config_sha256,
        "git_commit": provenance.get("git_commit"),
        "implementation_sha256": provenance.get("implementation_sha256"),
        "conversion_mode": "retained" if convert else "stream_only",
    }
    return hashlib.sha256(
        json.dumps(material, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def git_provenance(repository: Path) -> dict[str, Any]:
    """Capture commit and dirty paths without mutating Git state."""

    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    status = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    implementation_hasher = hashlib.sha256()
    implementation_paths = sorted(
        [
            *(
                path
                for path in (repository / "research" / "gnss_qc").rglob("*")
                if path.is_file() and "__pycache__" not in path.parts
            ),
            repository / "scripts" / "run_gnss_qc.py",
        ]
    )
    for path in implementation_paths:
        relative = path.relative_to(repository).as_posix()
        implementation_hasher.update(relative.encode())
        implementation_hasher.update(b"\0")
        implementation_hasher.update(path.read_bytes())
        implementation_hasher.update(b"\0")
    return {
        "git_commit": commit,
        "working_tree_dirty": bool(status),
        "dirty_paths": status,
        "engine_version": ENGINE_VERSION,
        "implementation_sha256": implementation_hasher.hexdigest(),
    }


def profile_objects(names: list[str], path: Path | None = None) -> list[QCProfile]:
    available = load_profiles(path)
    unknown = sorted(set(names) - set(available))
    if unknown:
        raise QCExecutionError(f"unknown QC profiles: {', '.join(unknown)}")
    return [available[name] for name in names]


def _conversion_dir(data_root: Path, session: SessionInput) -> Path:
    return (
        data_root
        / "working"
        / "qc-converted"
        / str(session.year)
        / session.station_id
        / f"{session.day_of_year:03d}"
    )


def _converted_path(data_root: Path, session: SessionInput) -> Path:
    name = Path(session.relative_path).name
    return _conversion_dir(data_root, session) / f"{name[:-3]}O"


def _conversion_manifest_path(data_root: Path, session: SessionInput) -> Path:
    return _conversion_dir(data_root, session) / "conversion-manifest.json"


def _result_path(data_root: Path, profile: QCProfile, session: SessionInput) -> Path:
    return (
        data_root
        / "processed"
        / "qc"
        / "profiles"
        / profile.name
        / "sessions"
        / str(session.year)
        / session.station_id
        / f"{session.day_of_year:03d}"
        / "qc-result.json"
    )


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def _atomic_csv(path: Path, fields: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)
