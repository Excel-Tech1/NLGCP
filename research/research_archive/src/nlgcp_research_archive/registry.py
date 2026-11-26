"""Archive loader, end-to-end read-only verifier, and report renderers (B-00)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from nlgcp_research_archive import ARCHIVE_VERSION
from nlgcp_research_archive.hash_verifier import (
    verify_file_integrity,
    verify_nested_hash_manifest,
)
from nlgcp_research_archive.models import (
    ArchiveStatusSummary,
    ArchiveVerifyReport,
    ExitCode,
    ExperimentStatus,
    ExperimentValidationResult,
    HashCheckResult,
    IntegrityStatus,
)
from nlgcp_research_archive.provenance import (
    build_provenance_lineage,
    utc_now_iso,
    verify_software_inventory,
)
from nlgcp_research_archive.validator import (
    load_manifest_file,
    validate_artifact_manifest,
    validate_dataset_manifest,
    validate_experiment_manifest,
    validate_software_entry,
    validate_validation_registers,
)


@dataclass(slots=True)
class LoadedArchive:
    """In-memory view of all manifests loaded from ``research/archive/``."""

    archive_root: Path
    datasets: dict[str, dict[str, Any]] = field(default_factory=dict)
    dataset_paths: dict[str, Path] = field(default_factory=dict)
    experiments: dict[str, dict[str, Any]] = field(default_factory=dict)
    experiment_paths: dict[str, Path] = field(default_factory=dict)
    artifacts: dict[str, dict[str, Any]] = field(default_factory=dict)
    artifact_paths: dict[str, Path] = field(default_factory=dict)
    software: dict[str, dict[str, Any]] = field(default_factory=dict)
    findings: list[dict[str, Any]] = field(default_factory=list)
    limitations: list[dict[str, Any]] = field(default_factory=list)
    claims: list[dict[str, Any]] = field(default_factory=list)
    security_findings: list[dict[str, Any]] = field(default_factory=list)
    reproductions: list[dict[str, Any]] = field(default_factory=list)
    parse_errors: list[str] = field(default_factory=list)
    duplicate_id_errors: list[str] = field(default_factory=list)


def _iter_manifest_files(directory: Path) -> list[Path]:
    if not directory.is_dir():
        return []
    return sorted(
        p
        for p in directory.iterdir()
        if p.is_file() and p.suffix.lower() in (".json", ".yaml", ".yml")
    )


def _load_register_list(path: Path, key: str, parse_errors: list[str]) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    try:
        data = load_manifest_file(path)
    except Exception as exc:
        parse_errors.append(f"failed to parse {path}: {exc}")
        return []
    items = data.get(key, [])
    if not isinstance(items, list):
        parse_errors.append(f"{path}: expected list under '{key}'")
        return []
    return [i for i in items if isinstance(i, dict)]


def load_archive(archive_root: Path) -> LoadedArchive:
    """Load all datasets, experiments, artifacts, software, and registers read-only."""
    loaded = LoadedArchive(archive_root=archive_root)

    # Datasets
    for mf in _iter_manifest_files(archive_root / "datasets"):
        try:
            data = load_manifest_file(mf)
        except Exception as exc:
            loaded.parse_errors.append(f"{mf}: {exc}")
            continue
        did = str(data.get("dataset_id", "")).strip() or mf.stem
        if did in loaded.datasets:
            loaded.duplicate_id_errors.append(f"duplicate dataset_id '{did}' in {mf}")
            continue
        loaded.datasets[did] = data
        loaded.dataset_paths[did] = mf

    # Experiments
    for mf in _iter_manifest_files(archive_root / "experiments"):
        try:
            data = load_manifest_file(mf)
        except Exception as exc:
            loaded.parse_errors.append(f"{mf}: {exc}")
            continue
        eid = str(data.get("experiment_id", "")).strip() or mf.stem
        if eid in loaded.experiments:
            loaded.duplicate_id_errors.append(f"duplicate experiment_id '{eid}' in {mf}")
            continue
        loaded.experiments[eid] = data
        loaded.experiment_paths[eid] = mf

    # Artifacts (individual files OR bundle with "artifacts" list)
    for mf in _iter_manifest_files(archive_root / "artifacts"):
        try:
            data = load_manifest_file(mf)
        except Exception as exc:
            loaded.parse_errors.append(f"{mf}: {exc}")
            continue
        entries = data["artifacts"] if isinstance(data.get("artifacts"), list) else [data]
        bundle_schema = data.get("schema_version")
        for entry in entries:
            if not isinstance(entry, dict):
                loaded.parse_errors.append(f"{mf}: non-object artifact entry")
                continue
            if "schema_version" not in entry and isinstance(bundle_schema, str):
                entry = {"schema_version": bundle_schema, **entry}
            aid = str(entry.get("artifact_id", "")).strip() or mf.stem
            if aid in loaded.artifacts:
                loaded.duplicate_id_errors.append(f"duplicate artifact_id '{aid}' in {mf}")
                continue
            loaded.artifacts[aid] = entry
            loaded.artifact_paths[aid] = mf

    # Software inventory
    sw_items = _load_register_list(
        archive_root / "provenance" / "software_inventory.json",
        "software",
        loaded.parse_errors,
    )
    for entry in sw_items:
        sw_id = str(entry.get("software_id", "")).strip()
        if not sw_id:
            loaded.parse_errors.append("software_inventory.json: entry missing software_id")
            continue
        if sw_id in loaded.software:
            loaded.duplicate_id_errors.append(f"duplicate software_id '{sw_id}'")
            continue
        loaded.software[sw_id] = entry

    # Validation, findings, limitations, claims, security, reproducibility
    val_dir = archive_root / "validation"
    loaded.findings = _load_register_list(
        val_dir / "findings_register.json", "findings", loaded.parse_errors
    )
    loaded.limitations = _load_register_list(
        val_dir / "limitations_register.json", "limitations", loaded.parse_errors
    )
    loaded.claims = _load_register_list(
        val_dir / "publication_evidence_map.json", "claims", loaded.parse_errors
    )
    loaded.security_findings = _load_register_list(
        val_dir / "security_findings_register.json", "security_findings", loaded.parse_errors
    )
    loaded.reproductions = _load_register_list(
        archive_root / "reproducibility" / "repro_records.json",
        "reproductions",
        loaded.parse_errors,
    )
    return loaded


def verify_archive(
    archive_root: Path,
    *,
    repo_root: Path,
    data_root: Path,
    verify_hashes: bool = True,
    max_hash_bytes: int | None = None,
    verify_nested: bool = False,
) -> ArchiveVerifyReport:
    """Execute full read-only validation and integrity verification across the archive."""
    loaded = load_archive(archive_root)
    known_datasets = set(loaded.datasets)
    known_experiments = set(loaded.experiments)
    known_artifacts = set(loaded.artifacts)
    known_software = set(loaded.software)
    ds_classes = {
        did: str(d.get("source_classification", "")) for did, d in loaded.datasets.items()
    }

    # 1. Dataset schema + SHA-256 verification
    ds_schema_errors: dict[str, list[str]] = {}
    ds_checks: list[HashCheckResult] = []
    for did in sorted(loaded.datasets):
        ds = loaded.datasets[did]
        errs = validate_dataset_manifest(ds, known_datasets=known_datasets)
        if errs:
            ds_schema_errors[did] = errs
        storage = ds.get("storage", {}) if isinstance(ds.get("storage"), dict) else {}
        integrity = ds.get("integrity", {}) if isinstance(ds.get("integrity"), dict) else {}
        size_val = storage.get("file_size_bytes")
        ds_checks.append(
            verify_file_integrity(
                record_id=did,
                record_kind="dataset",
                location=str(storage.get("location", "NOT_RECORDED")),
                storage_type=str(storage.get("storage_type", "UNKNOWN")),
                expected_hash=str(integrity.get("expected_hash", "NOT_RECORDED")),
                expected_size_bytes=size_val if isinstance(size_val, int) else None,
                repo_root=repo_root,
                data_root=data_root,
                verify_hashes=verify_hashes,
                max_hash_bytes=max_hash_bytes,
            )
        )

    # 2. Experiment schema + reference + provenance validation
    exp_results: list[ExperimentValidationResult] = []
    for eid in sorted(loaded.experiments):
        exp = loaded.experiments[eid]
        exp_results.append(
            validate_experiment_manifest(
                exp,
                manifest_path=str(loaded.experiment_paths[eid]),
                known_datasets=known_datasets,
                known_experiments=known_experiments,
                known_software=known_software,
                dataset_classifications=ds_classes,
            )
        )

    # 3. Artifact schema + SHA-256 verification (+ optional nested B-02 311-file check)
    art_schema_errors: dict[str, list[str]] = {}
    art_checks: list[HashCheckResult] = []
    nested_checks: dict[str, dict[str, Any]] = {}
    for aid in sorted(loaded.artifacts):
        art = loaded.artifacts[aid]
        errs = validate_artifact_manifest(
            art, known_experiments=known_experiments, known_datasets=known_datasets
        )
        if errs:
            art_schema_errors[aid] = errs
        size_val = art.get("file_size_bytes")
        chk = verify_file_integrity(
            record_id=aid,
            record_kind="artifact",
            location=str(art.get("file_path", "NOT_RECORDED")),
            storage_type=str(art.get("storage_type", "UNKNOWN")),
            expected_hash=str(art.get("sha256", "NOT_RECORDED")),
            expected_size_bytes=size_val if isinstance(size_val, int) else None,
            repo_root=repo_root,
            data_root=data_root,
            verify_hashes=verify_hashes,
            max_hash_bytes=max_hash_bytes,
        )
        art_checks.append(chk)
        if (
            verify_nested
            and art.get("contains_nested_hash_manifest") is True
            and chk.resolved_path is not None
            and chk.status is IntegrityStatus.VERIFIED
        ):
            nested_checks[aid] = verify_nested_hash_manifest(Path(chk.resolved_path))

    # 4. Software inventory verification + register cross-reference validation
    reg_errors: list[str] = []
    for sw_id in sorted(loaded.software):
        reg_errors.extend(validate_software_entry(loaded.software[sw_id]))
    sw_checks = verify_software_inventory(
        [loaded.software[k] for k in sorted(loaded.software)]
    )
    reg_errors.extend(
        validate_validation_registers(
            findings=loaded.findings,
            limitations=loaded.limitations,
            claims=loaded.claims,
            reproductions=loaded.reproductions,
            known_experiments=known_experiments,
            known_datasets=known_datasets,
            known_artifacts=known_artifacts,
        )
    )

    # Aggregate status & exit code
    def _cnt(checks: list[HashCheckResult], st: IntegrityStatus) -> int:
        return sum(1 for c in checks if c.status is st)

    ds_ver = _cnt(ds_checks, IntegrityStatus.VERIFIED)
    ds_mis = _cnt(ds_checks, IntegrityStatus.MISSING)
    ds_bad = _cnt(ds_checks, IntegrityStatus.HASH_MISMATCH)
    ds_den = _cnt(ds_checks, IntegrityStatus.ACCESS_DENIED)
    ds_nc = _cnt(ds_checks, IntegrityStatus.NOT_CHECKED)
    ds_inv = len(ds_schema_errors) + _cnt(ds_checks, IntegrityStatus.INVALID_MANIFEST)

    art_ver = _cnt(art_checks, IntegrityStatus.VERIFIED)
    art_mis = _cnt(art_checks, IntegrityStatus.MISSING)
    art_bad = _cnt(art_checks, IntegrityStatus.HASH_MISMATCH)
    art_den = _cnt(art_checks, IntegrityStatus.ACCESS_DENIED)
    art_nc = _cnt(art_checks, IntegrityStatus.NOT_CHECKED)
    art_inv = len(art_schema_errors) + _cnt(art_checks, IntegrityStatus.INVALID_MANIFEST)

    nested_fail = any(
        nc.get("status") != str(IntegrityStatus.VERIFIED) for nc in nested_checks.values()
    )
    sw_bad = sum(
        1 for sc in sw_checks if sc["status"] == str(IntegrityStatus.HASH_MISMATCH)
    )
    sw_ver = sum(1 for sc in sw_checks if sc["status"] == str(IntegrityStatus.VERIFIED))

    completed_exp = sum(
        1 for e in exp_results if e.status == str(ExperimentStatus.COMPLETED)
    )
    complete_prov = sum(1 for e in exp_results if e.provenance_complete)
    incomplete_prov = sum(1 for e in exp_results if e.valid and not e.provenance_complete)
    invalid_exp = sum(1 for e in exp_results if not e.valid)

    has_integrity_failure = bool(
        loaded.parse_errors
        or loaded.duplicate_id_errors
        or ds_schema_errors
        or art_schema_errors
        or reg_errors
        or ds_mis
        or ds_bad
        or ds_inv
        or art_mis
        or art_bad
        or art_inv
        or invalid_exp
        or sw_bad
        or nested_fail
    )
    has_external_inaccessible = bool(ds_den or art_den)

    if has_integrity_failure:
        exit_code = int(ExitCode.INTEGRITY_OR_VALIDATION_FAILURE)
        overall = "INTEGRITY_OR_VALIDATION_FAILURE"
    elif has_external_inaccessible:
        exit_code = int(ExitCode.EXTERNAL_STORAGE_OR_DEPENDENCY_UNAVAILABLE)
        overall = "EXTERNAL_STORAGE_INACCESSIBLE"
    else:
        exit_code = int(ExitCode.OK)
        overall = (
            "VERIFIED_WITH_RECORDED_PROVENANCE_GAPS"
            if incomplete_prov > 0
            else "VERIFIED_COMPLETE"
        )

    summary = ArchiveStatusSummary(
        registered_datasets=len(loaded.datasets),
        verified_datasets=ds_ver,
        missing_datasets=ds_mis,
        hash_mismatch_datasets=ds_bad,
        access_denied_datasets=ds_den,
        not_checked_datasets=ds_nc,
        invalid_dataset_manifests=ds_inv,
        registered_experiments=len(loaded.experiments),
        completed_experiments=completed_exp,
        experiments_with_complete_provenance=complete_prov,
        experiments_with_incomplete_provenance=incomplete_prov,
        invalid_experiments=invalid_exp,
        registered_artifacts=len(loaded.artifacts),
        verified_artifacts=art_ver,
        missing_artifacts=art_mis,
        hash_mismatch_artifacts=art_bad,
        access_denied_artifacts=art_den,
        not_checked_artifacts=art_nc,
        registered_software=len(loaded.software),
        verified_software=sw_ver,
        registered_findings=len(loaded.findings),
        registered_limitations=len(loaded.limitations),
        registered_claims=len(loaded.claims),
        registered_security_findings=len(loaded.security_findings),
        registered_reproductions=len(loaded.reproductions),
        overall_status=overall,
        exit_code=exit_code,
    )

    return ArchiveVerifyReport(
        schema_version="nlgcp.archive.verification_report.v1",
        archive_version=ARCHIVE_VERSION,
        generated_utc=utc_now_iso(),
        archive_root=str(archive_root),
        repo_root=str(repo_root),
        data_root=str(data_root),
        read_only=True,
        summary=summary,
        parse_errors=tuple(loaded.parse_errors),
        duplicate_id_errors=tuple(loaded.duplicate_id_errors),
        dataset_schema_errors=ds_schema_errors,
        dataset_integrity=tuple(ds_checks),
        experiment_validations=tuple(exp_results),
        artifact_schema_errors=art_schema_errors,
        artifact_integrity=tuple(art_checks),
        nested_artifact_checks=nested_checks,
        software_checks=tuple(sw_checks),
        register_errors=tuple(reg_errors),
    )


def render_status_text(report: ArchiveVerifyReport) -> str:
    """Render concise human-readable archive status summary (Section 11.1)."""
    s = report.summary
    lines = [
        f"NLGCP Research Archive Status ({report.archive_version})",
        f"  Overall status:       {s.overall_status} (exit={s.exit_code})",
        f"  Archive root:         {report.archive_root}",
        f"  Data root:            {report.data_root}",
        f"  Datasets:             {s.registered_datasets} registered | {s.verified_datasets} "
        f"verified | {s.missing_datasets} missing | {s.hash_mismatch_datasets} mismatch | "
        f"{s.access_denied_datasets} access_denied | {s.not_checked_datasets} not_checked",
        f"  Experiments:          {s.registered_experiments} registered | "
        f"{s.completed_experiments} completed | "
        f"{s.experiments_with_complete_provenance} complete_prov | "
        f"{s.experiments_with_incomplete_provenance} incomplete_prov | "
        f"{s.invalid_experiments} invalid",
        f"  Artifacts:            {s.registered_artifacts} registered | {s.verified_artifacts} "
        f"verified | {s.missing_artifacts} missing | {s.hash_mismatch_artifacts} mismatch | "
        f"{s.access_denied_artifacts} access_denied | {s.not_checked_artifacts} not_checked",
        f"  Software provenance:  {s.registered_software} registered | "
        f"{s.verified_software} verified",
        f"  Evidence registers:   {s.registered_findings} findings | "
        f"{s.registered_limitations} limitations | {s.registered_claims} claims | "
        f"{s.registered_security_findings} security | {s.registered_reproductions} reproductions",
    ]
    if report.parse_errors or report.duplicate_id_errors or report.register_errors:
        lines.append("  Errors:")
        for err in (*report.parse_errors, *report.duplicate_id_errors, *report.register_errors):
            lines.append(f"    - {err}")
    return "\n".join(lines)


def render_markdown_report(
    report: ArchiveVerifyReport,
    loaded: LoadedArchive,
) -> str:
    """Render complete human-readable archive verification & completeness report."""
    s = report.summary
    lineage = build_provenance_lineage(
        datasets=loaded.datasets,
        experiments=loaded.experiments,
        artifacts=loaded.artifacts,
        software=loaded.software,
        findings=loaded.findings,
        limitations=loaded.limitations,
        claims=loaded.claims,
        reproductions=loaded.reproductions,
    )
    lines = [
        "# NLGCP Research Archive Verification & Completeness Report",
        "",
        f"- **Generated UTC:** `{report.generated_utc}`",
        f"- **Archive Version:** `{report.archive_version}`",
        f"- **Overall Status:** `{s.overall_status}` (exit `{s.exit_code}`)",
        f"- **Read-Only Mode:** `{report.read_only}`",
        f"- **External Data Root:** `{report.data_root}`",
        "",
        "## Summary Counters",
        "",
        f"- Datasets: `{s.registered_datasets}` registered, `{s.verified_datasets}` verified, "
        f"`{s.missing_datasets}` missing, `{s.hash_mismatch_datasets}` hash mismatches, "
        f"`{s.access_denied_datasets}` inaccessible, `{s.not_checked_datasets}` not checked",
        f"- Experiments: `{s.registered_experiments}` registered, `{s.completed_experiments}` "
        f"completed, `{s.experiments_with_complete_provenance}` complete provenance, "
        f"`{s.experiments_with_incomplete_provenance}` incomplete provenance, "
        f"`{s.invalid_experiments}` invalid",
        f"- Artifacts: `{s.registered_artifacts}` registered, `{s.verified_artifacts}` verified, "
        f"`{s.missing_artifacts}` missing, `{s.hash_mismatch_artifacts}` hash mismatches",
        f"- Software: `{s.registered_software}` registered, `{s.verified_software}` verified",
        f"- Registers: `{s.registered_findings}` findings, `{s.registered_limitations}` "
        f"limitations, `{s.registered_claims}` publication claims, "
        f"`{s.registered_security_findings}` security findings, "
        f"`{s.registered_reproductions}` reproduction records",
        "",
        "## Dataset Integrity",
        "",
        "| Dataset ID | Storage Type | Status | Expected Hash (prefix) | Detail |",
        "|---|---|---|---|---|",
    ]
    for chk in report.dataset_integrity:
        lines.append(
            f"| `{chk.record_id}` | `{chk.storage_type}` | `{chk.status}` | "
            f"`{chk.expected_hash[:16]}` | {chk.detail} |"
        )
    lines.extend(
        [
            "",
            "## Experiment Provenance",
            "",
            "| Experiment ID | Status | Schema Valid | Provenance Complete | Gaps / Warnings |",
            "|---|---|---|---|---|",
        ]
    )
    for exp in report.experiment_validations:
        notes = "; ".join((*exp.errors, *exp.provenance_gaps, *exp.warnings)) or "None"
        lines.append(
            f"| `{exp.experiment_id}` | `{exp.status}` | `{exp.valid}` | "
            f"`{exp.provenance_complete}` | {notes} |"
        )
    lines.extend(
        [
            "",
            "## Publication Evidence Chains",
            "",
            "| Claim ID | Status | Findings | Experiments | Datasets |",
            "|---|---|---|---|---|",
        ]
    )
    for chain in lineage["publication_claim_chains"]:
        lines.append(
            f"| `{chain['claim_id']}` | `{chain['status']}` | "
            f"`{', '.join(chain['supporting_findings']) or 'NONE'}` | "
            f"`{', '.join(chain['supporting_experiments']) or 'NONE'}` | "
            f"`{', '.join(chain['supporting_datasets']) or 'NONE'}` |"
        )
    return "\n".join(lines) + "\n"
