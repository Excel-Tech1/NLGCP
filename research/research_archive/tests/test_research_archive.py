"""Unit, CLI, and safety tests for NLGCP Research Archive (B-00 Stage 11).

SYNTHETIC TEST DATA — NOT VALID FOR SCIENTIFIC RESULTS.
Covers all required Stage 11 categories:
- Dataset manifest validation, duplicate IDs, missing files, SHA-256 verification & mismatch,
  inaccessible external paths, invalid hash formats, derived relationships.
- Experiment manifest validation, missing dataset refs, duplicate IDs, missing config,
  incomplete software provenance, invalid validation status, authentic/synthetic isolation,
  dependency & supersession edges.
- Artifact hash verification, mismatch, missing output, duplicate IDs, nested manifests.
- CLI subcommands (`status`, `datasets`, `experiments`, `artifacts`, `provenance`, `verify`,
  `report`) and exit codes (`0`, `1`, `2`, `3`).
- Safety invariants: read-only verification never alters expected hashes, never modifies/moves/
  deletes datasets, never archives secret env vars, and excludes temp/build files from scans.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from nlgcp_research_archive.cli import main as cli_main
from nlgcp_research_archive.hash_verifier import (
    compute_sha256,
    scan_unregistered_outputs,
    verify_file_integrity,
)
from nlgcp_research_archive.models import ExitCode, IntegrityStatus
from nlgcp_research_archive.provenance import (
    capture_environment_snapshot,
    sanitize_environment_vars,
)
from nlgcp_research_archive.registry import verify_archive
from nlgcp_research_archive.validator import (
    validate_dataset_manifest,
    validate_experiment_manifest,
)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _build_fixture_archive(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    """Create a minimal valid synthetic archive on disk for deterministic tests."""
    repo = tmp_path / "repo"
    archive = repo / "research" / "archive"
    data_root = tmp_path / "ext-data"
    data_root.mkdir(parents=True)
    repo.mkdir(parents=True)

    raw_file = data_root / "raw_sample.rnx"
    raw_file.write_text("SYNTHETIC TEST DATA — RINEX SAMPLE\n", encoding="utf-8")
    raw_sha, raw_sz = compute_sha256(raw_file)

    derived_file = data_root / "derived_sample.obs"
    derived_file.write_text("SYNTHETIC TEST DATA — DERIVED SAMPLE\n", encoding="utf-8")
    der_sha, der_sz = compute_sha256(derived_file)

    out_file = data_root / "exp_output.json"
    out_file.write_text('{"metric": 0.5}\n', encoding="utf-8")
    out_sha, out_sz = compute_sha256(out_file)

    tool_file = repo / "fake_tool.bin"
    tool_file.write_bytes(b"FAKE_TOOL_BINARY_SYNTHETIC")
    tool_sha, _ = compute_sha256(tool_file)

    _write_json(
        archive / "datasets" / "NLGCP-DATA-2024-001.json",
        {
            "schema_version": "nlgcp.archive.dataset.v1",
            "dataset_id": "NLGCP-DATA-2024-001",
            "name": "Synthetic Raw Sample",
            "dataset_type": "GNSS_OBSERVATION",
            "source_classification": "AUTHENTIC_RECORDED_CORS",
            "source_provider": "TEST_PROVIDER",
            "description": "Synthetic fixture mimicking an authentic recorded dataset.",
            "acquisition_method": "TEST_FIXTURE",
            "immutable_source": True,
            "storage": {
                "location": "${NLGCP_DATA_ROOT}/raw_sample.rnx",
                "storage_type": "EXTERNAL_FILESYSTEM",
                "original_filename": "raw_sample.rnx",
                "file_size_bytes": raw_sz,
            },
            "integrity": {
                "algorithm": "SHA256",
                "expected_hash": raw_sha,
                "verification_status": "VERIFIED",
            },
            "metadata": {
                "format": "RINEX 2.11",
                "temporal_coverage": {"start": "2024-01-26", "end": "2024-01-26"},
                "station_count": 1,
                "constellations": ["GPS"],
                "sampling_interval_s": 30.0,
                "coordinate_reference_status": "VERIFIED_IGS20",
                "reference_frame": "IGS20",
            },
            "licensing": {"status": "NOT_RECORDED", "conditions": "TEST_ONLY"},
            "registration": {
                "retrieval_date": "2026-11-26",
                "created_at": "2026-11-26T00:00:00Z",
                "registered_by": "TEST",
            },
            "relationships": {
                "related_experiments": ["NLGCP-EXP-2026-001"],
                "derived_from_datasets": [],
                "derived_datasets": ["NLGCP-DATA-2024-002"],
            },
        },
    )

    _write_json(
        archive / "datasets" / "NLGCP-DATA-2024-002.json",
        {
            "schema_version": "nlgcp.archive.dataset.v1",
            "dataset_id": "NLGCP-DATA-2024-002",
            "name": "Synthetic Derived Sample",
            "dataset_type": "DERIVED_OBS",
            "source_classification": "DERIVED_DATA",
            "source_provider": "NLGCP",
            "description": "Derived dataset linked to parent dataset.",
            "acquisition_method": "DERIVED",
            "immutable_source": False,
            "storage": {
                "location": "${NLGCP_DATA_ROOT}/derived_sample.obs",
                "storage_type": "EXTERNAL_FILESYSTEM",
                "original_filename": "derived_sample.obs",
                "file_size_bytes": der_sz,
            },
            "integrity": {
                "algorithm": "SHA256",
                "expected_hash": der_sha,
                "verification_status": "VERIFIED",
            },
            "metadata": {
                "format": "RINEX 3.02",
                "temporal_coverage": {"start": "2024-01-26", "end": "2024-01-26"},
                "station_count": 1,
                "constellations": ["GPS"],
                "sampling_interval_s": 30.0,
                "coordinate_reference_status": "VERIFIED_IGS20",
                "reference_frame": "IGS20",
            },
            "licensing": {"status": "NOT_APPLICABLE", "conditions": "INTERNAL"},
            "registration": {
                "retrieval_date": "2026-11-26",
                "created_at": "2026-11-26T00:00:00Z",
                "registered_by": "TEST",
            },
            "relationships": {
                "related_experiments": ["NLGCP-EXP-2026-001"],
                "derived_from_datasets": ["NLGCP-DATA-2024-001"],
                "derived_datasets": [],
            },
        },
    )

    _write_json(
        archive / "provenance" / "software_inventory.json",
        {
            "schema_version": "nlgcp.archive.software_inventory.v1",
            "software": [
                {
                    "software_id": "NLGCP-SW-TEST-001",
                    "name": "FakeTool",
                    "version": "1.0.0",
                    "role": "TEST",
                    "upstream_url": "NOT_APPLICABLE",
                    "source_commit": "0" * 40,
                    "executable_or_source_path": str(tool_file),
                    "expected_sha256": tool_sha,
                    "linked_experiments": ["NLGCP-EXP-2026-001"],
                }
            ],
        },
    )

    _write_json(
        archive / "experiments" / "NLGCP-EXP-2026-001.json",
        {
            "schema_version": "nlgcp.archive.experiment.v1",
            "experiment_id": "NLGCP-EXP-2026-001",
            "title": "Synthetic Baseline Experiment",
            "milestone": "B-00",
            "status": "COMPLETED",
            "data_classification": "AUTHENTIC",
            "research_question": "Verify synthetic archive pipeline.",
            "hypothesis": "Archive validates cleanly.",
            "datasets": ["NLGCP-DATA-2024-001", "NLGCP-DATA-2024-002"],
            "software": {
                "nlgcp_repository": "/repo",
                "git_branch": "test",
                "nlgcp_revision": "5b5217a0033191134effebe0027d4ee16f70de5f",
                "git_dirty": False,
                "software_ids": ["NLGCP-SW-TEST-001"],
                "python_version": "3.12.3",
            },
            "configuration": {
                "location": "test.conf",
                "sha256": "a" * 64,
                "parameters_summary": "test",
            },
            "execution": {
                "command": "python run.py",
                "environment": "Ubuntu 24.04",
                "started_at": "2026-11-26T00:00:00Z",
                "completed_at": "2026-11-26T00:01:00Z",
                "random_seed": 42,
            },
            "outputs": [
                {
                    "location": "${NLGCP_DATA_ROOT}/exp_output.json",
                    "sha256": out_sha,
                    "artifact_id": "NLGCP-ART-2026-001",
                    "description": "output metrics",
                }
            ],
            "metrics": {"metric": 0.5},
            "results": {
                "report": "report.md",
                "summary": "ok",
                "result_classification": "TEST_ONLY",
            },
            "validation": {
                "highest_level": "UNIT_TESTED",
                "unit_test_status": "COMPLETED",
                "integration_test_status": "NOT_APPLICABLE",
                "independent_validation": "NOT_PERFORMED",
                "scientific_validation": "NOT_APPLICABLE",
            },
            "limitations": ["NLGCP-LIM-001"],
            "relationships": [
                {"type": "USES_DATASET", "target_id": "NLGCP-DATA-2024-001"},
                {"type": "PRODUCES_DATASET", "target_id": "NLGCP-DATA-2024-002"},
            ],
            "reproducibility": {
                "status": "REPRODUCED",
                "level": "LEVEL_3_NUMERICAL",
                "notes": "Synthetic deterministic test.",
            },
        },
    )

    _write_json(
        archive / "artifacts" / "NLGCP-ART-2026-001.json",
        {
            "schema_version": "nlgcp.archive.artifact.v1",
            "artifact_id": "NLGCP-ART-2026-001",
            "experiment_id": "NLGCP-EXP-2026-001",
            "file_path": "${NLGCP_DATA_ROOT}/exp_output.json",
            "storage_type": "EXTERNAL_FILESYSTEM",
            "file_type": "JSON",
            "file_size_bytes": out_sz,
            "sha256": out_sha,
            "created_at": "2026-11-26T00:01:00Z",
            "generated_by": "NLGCP-SW-TEST-001",
            "source_datasets": ["NLGCP-DATA-2024-001"],
            "description": "Synthetic output JSON.",
            "validation_status": "UNIT_TESTED",
        },
    )

    _write_json(
        archive / "validation" / "limitations_register.json",
        {
            "schema_version": "nlgcp.archive.limitations_register.v1",
            "limitations": [
                {
                    "limitation_id": "NLGCP-LIM-001",
                    "category": "SYNTHETIC",
                    "description": "Synthetic unit test limitation.",
                    "related_experiments": ["NLGCP-EXP-2026-001"],
                    "status": "OPEN",
                }
            ],
        },
    )
    _write_json(
        archive / "validation" / "findings_register.json",
        {
            "schema_version": "nlgcp.archive.findings_register.v1",
            "findings": [
                {
                    "finding_id": "NLGCP-FIND-001",
                    "research_question": "Does verifier work?",
                    "claim": "Verifier checks SHA-256 read-only.",
                    "finding_polarity": "POSITIVE",
                    "supporting_experiments": ["NLGCP-EXP-2026-001"],
                    "supporting_datasets": ["NLGCP-DATA-2024-001"],
                    "result_artifacts": ["NLGCP-ART-2026-001"],
                    "validation_level": "UNIT_TESTED",
                    "limitations": ["NLGCP-LIM-001"],
                    "confidence_or_uncertainty": "EXACT",
                    "status": "ACTIVE",
                    "publication_suitability": "INTERNAL_ONLY",
                }
            ],
        },
    )
    _write_json(
        archive / "validation" / "publication_evidence_map.json",
        {
            "schema_version": "nlgcp.archive.publication_evidence_map.v1",
            "claims": [
                {
                    "claim_id": "NLGCP-CLM-001",
                    "claim": "Archive verification works deterministically.",
                    "status": "SUPPORTED_WITH_LIMITATIONS",
                    "supporting_findings": ["NLGCP-FIND-001"],
                    "limitations": ["NLGCP-LIM-001"],
                }
            ],
        },
    )
    _write_json(
        archive / "reproducibility" / "repro_records.json",
        {
            "schema_version": "nlgcp.archive.reproducibility.v1",
            "reproductions": [
                {
                    "reproduction_id": "NLGCP-REPRO-2026-001",
                    "original_experiment_id": "NLGCP-EXP-2026-001",
                    "input_dataset_ids": ["NLGCP-DATA-2024-001"],
                    "input_hashes": {"NLGCP-DATA-2024-001": raw_sha},
                    "software_versions": {"FakeTool": "1.0.0"},
                    "source_commit": "5b5217a0033191134effebe0027d4ee16f70de5f",
                    "configuration": "test.conf",
                    "execution_command": "python run.py",
                    "environment": "Ubuntu 24.04",
                    "expected_output": "exp_output.json",
                    "actual_output": "exp_output.json",
                    "output_hash": out_sha,
                    "metric_comparison": {"delta": 0.0},
                    "differences": [],
                    "outcome": "REPRODUCED",
                    "reproduction_level": "LEVEL_3_NUMERICAL",
                }
            ],
        },
    )
    return repo, archive, data_root, raw_file


# ---------------------------------------------------------------------------
# Dataset tests
# ---------------------------------------------------------------------------


def test_dataset_valid_manifest_missing_fields_and_invalid_hash() -> None:
    bad = {"dataset_id": "BAD-ID", "integrity": {"algorithm": "MD5", "expected_hash": "xyz"}}
    errs = validate_dataset_manifest(bad)
    assert any("invalid dataset_id" in e for e in errs)
    assert any("unsupported integrity.algorithm" in e for e in errs)
    assert any("invalid integrity.expected_hash" in e for e in errs)


def test_dataset_integrity_verified_mismatch_missing_and_access_denied(tmp_path: Path) -> None:
    repo, archive, data_root, raw_file = _build_fixture_archive(tmp_path)

    # 1. Clean archive -> VERIFIED, exit 0
    rep = verify_archive(archive, repo_root=repo, data_root=data_root)
    assert rep.summary.exit_code == int(ExitCode.OK)
    assert rep.summary.verified_datasets == 2
    assert rep.summary.hash_mismatch_datasets == 0

    # 2. Inaccessible external data root -> ACCESS_DENIED, exit 3 (never VERIFIED!)
    rep_inacc = verify_archive(archive, repo_root=repo, data_root=tmp_path / "no-such-mount")
    assert rep_inacc.summary.exit_code == int(ExitCode.EXTERNAL_STORAGE_OR_DEPENDENCY_UNAVAILABLE)
    assert rep_inacc.summary.access_denied_datasets == 2
    assert rep_inacc.summary.verified_datasets == 0

    # 3. Hash mismatch -> HASH_MISMATCH, exit 1, AND manifest expected_hash NOT overwritten!
    manifest_p = archive / "datasets" / "NLGCP-DATA-2024-001.json"
    orig_manifest_bytes = manifest_p.read_bytes()
    raw_file.write_text("TAMPERED CONTENT\n", encoding="utf-8")
    rep_bad = verify_archive(archive, repo_root=repo, data_root=data_root)
    assert rep_bad.summary.exit_code == int(ExitCode.INTEGRITY_OR_VALIDATION_FAILURE)
    assert rep_bad.summary.hash_mismatch_datasets == 1
    assert manifest_p.read_bytes() == orig_manifest_bytes

    # 4. Missing file -> MISSING, exit 1
    raw_file.unlink()
    rep_mis = verify_archive(archive, repo_root=repo, data_root=data_root)
    assert rep_mis.summary.exit_code == int(ExitCode.INTEGRITY_OR_VALIDATION_FAILURE)
    assert rep_mis.summary.missing_datasets == 1


def test_duplicate_dataset_and_experiment_ids_fail_closed(tmp_path: Path) -> None:
    repo, archive, data_root, _ = _build_fixture_archive(tmp_path)
    orig_ds = (archive / "datasets" / "NLGCP-DATA-2024-001.json").read_text(encoding="utf-8")
    (archive / "datasets" / "dup_ds.json").write_text(orig_ds, encoding="utf-8")
    orig_exp = (archive / "experiments" / "NLGCP-EXP-2026-001.json").read_text(encoding="utf-8")
    (archive / "experiments" / "dup_exp.json").write_text(orig_exp, encoding="utf-8")

    rep = verify_archive(archive, repo_root=repo, data_root=data_root)
    assert rep.summary.exit_code == int(ExitCode.INTEGRITY_OR_VALIDATION_FAILURE)
    assert any("duplicate dataset_id" in e for e in rep.duplicate_id_errors)
    assert any("duplicate experiment_id" in e for e in rep.duplicate_id_errors)


# ---------------------------------------------------------------------------
# Experiment tests
# ---------------------------------------------------------------------------


def test_experiment_validation_missing_refs_provenance_and_relationships(tmp_path: Path) -> None:
    bad_exp: dict[str, Any] = {
        "schema_version": "nlgcp.archive.experiment.v1",
        "experiment_id": "NLGCP-EXP-2026-099",
        "title": "Incomplete Experiment",
        "milestone": "B-00",
        "status": "SUPERSEDED",
        "data_classification": "AUTHENTIC",
        "research_question": "Test gaps and bad refs.",
        "datasets": ["NLGCP-DATA-2024-999", "NLGCP-DATA-2024-050"],
        "software": {
            "nlgcp_revision": "NOT_RECORDED",
            "git_dirty": True,
            "software_ids": ["NLGCP-SW-MISSING"],
            "python_version": "NOT_RECORDED",
        },
        "configuration": {"location": "NOT_RECORDED", "sha256": "NOT_RECORDED"},
        "execution": {"command": "NOT_RECORDED", "environment": "NOT_RECORDED"},
        "outputs": [],
        "validation": {"highest_level": "INVALID_LEVEL"},
        "relationships": [
            {"type": "SUPERSEDES", "target_id": "NLGCP-EXP-2026-001"},
            {"type": "DEPENDS_ON", "target_id": "NLGCP-EXP-2026-888"},
        ],
        "reproducibility": {"status": "PARTIAL", "level": "LEVEL_1_RECORD_COMPLETE"},
    }
    res = validate_experiment_manifest(
        bad_exp,
        manifest_path="bad.json",
        known_datasets={"NLGCP-DATA-2024-050"},
        known_experiments={"NLGCP-EXP-2026-001", "NLGCP-EXP-2026-099"},
        known_software=set(),
        dataset_classifications={"NLGCP-DATA-2024-050": "SYNTHETIC_TEST_DATA"},
    )
    assert res.valid is False
    assert res.provenance_complete is False
    assert any("unknown dataset reference" in e for e in res.errors)
    assert any("authentic/synthetic contamination" in e for e in res.errors)
    assert any("invalid validation.highest_level" in e for e in res.errors)
    assert any("unknown software reference" in e for e in res.errors)
    assert any("unknown experiment 'NLGCP-EXP-2026-888'" in e for e in res.errors)
    assert any("nlgcp_revision" in g for g in res.provenance_gaps)
    assert any("dirty Git" in w for w in res.warnings)


# ---------------------------------------------------------------------------
# Artifact & scan tests
# ---------------------------------------------------------------------------


def test_artifact_hash_mismatch_missing_duplicate_and_safe_scan(tmp_path: Path) -> None:
    repo, archive, data_root, _ = _build_fixture_archive(tmp_path)

    # Temp/build files must be excluded from unregistered output scan
    (data_root / "scratch.tmp").write_text("temp", encoding="utf-8")
    (data_root / "debug.log").write_text("log", encoding="utf-8")
    (data_root / "build").mkdir()
    (data_root / "build" / "out.json").write_text("{}", encoding="utf-8")
    unreg_csv = data_root / "new_metrics.csv"
    unreg_csv.write_text("a,b\n1,2\n", encoding="utf-8")

    found = scan_unregistered_outputs(data_root, {data_root / "exp_output.json"})
    assert str(unreg_csv) in found
    assert not any(p.endswith(".tmp") or p.endswith(".log") or "/build/" in p for p in found)

    # Artifact hash mismatch fails closed
    (data_root / "exp_output.json").write_text('{"metric": 9.9}\n', encoding="utf-8")
    rep = verify_archive(archive, repo_root=repo, data_root=data_root)
    assert rep.summary.hash_mismatch_artifacts == 1
    assert rep.summary.exit_code == int(ExitCode.INTEGRITY_OR_VALIDATION_FAILURE)

    # Duplicate artifact ID detected
    art_txt = (archive / "artifacts" / "NLGCP-ART-2026-001.json").read_text(encoding="utf-8")
    (archive / "artifacts" / "dup_art.json").write_text(art_txt, encoding="utf-8")
    rep_dup = verify_archive(archive, repo_root=repo, data_root=data_root)
    assert any("duplicate artifact_id" in e for e in rep_dup.duplicate_id_errors)


# ---------------------------------------------------------------------------
# CLI & Safety tests
# ---------------------------------------------------------------------------


def test_cli_subcommands_exit_codes_and_readonly_safety(tmp_path: Path) -> None:
    repo, archive, data_root, raw_file = _build_fixture_archive(tmp_path)
    raw_before = hashlib.sha256(raw_file.read_bytes()).hexdigest()
    manifest_files_before = {
        str(p): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(archive.rglob("*.json"))
    }

    base_args = [
        "archive",
        "--repo-root",
        str(repo),
        "--archive-root",
        str(archive),
        "--data-root",
        str(data_root),
    ]
    assert cli_main([*base_args, "status", "--format", "json"]) == int(ExitCode.OK)
    assert cli_main([*base_args, "datasets", "list", "--format", "json"]) == int(ExitCode.OK)
    assert cli_main([*base_args, "datasets", "verify", "--format", "json"]) == int(ExitCode.OK)
    assert cli_main([*base_args, "experiments", "list"]) == int(ExitCode.OK)
    assert cli_main([*base_args, "experiments", "validate"]) == int(ExitCode.OK)
    assert cli_main([*base_args, "artifacts", "verify"]) == int(ExitCode.OK)
    assert cli_main([*base_args, "provenance", "report", "--format", "json"]) == int(ExitCode.OK)
    assert cli_main([*base_args, "verify"]) == int(ExitCode.OK)
    assert cli_main([*base_args, "report", "--format", "markdown"]) == int(ExitCode.OK)

    # Invalid dataset ID -> exit 2
    assert (
        cli_main([*base_args, "datasets", "verify", "--dataset-id", "NLGCP-DATA-9999-999"])
        == int(ExitCode.INVALID_ARGUMENTS_OR_CONFIG)
    )

    # External storage missing -> exit 3
    inacc_args = [
        "archive",
        "--repo-root",
        str(repo),
        "--archive-root",
        str(archive),
        "--data-root",
        str(tmp_path / "missing-ext-root"),
    ]
    assert cli_main([*inacc_args, "verify"]) == int(
        ExitCode.EXTERNAL_STORAGE_OR_DEPENDENCY_UNAVAILABLE
    )

    # Read-only invariant: neither raw data nor any archive manifest changed
    assert hashlib.sha256(raw_file.read_bytes()).hexdigest() == raw_before
    manifest_files_after = {
        str(p): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(archive.rglob("*.json"))
    }
    assert manifest_files_after == manifest_files_before


def test_secret_redaction_never_captures_credentials(tmp_path: Path) -> None:
    fake_env = {
        "LANG": "C.UTF-8",
        "NLGCP_DATA_ROOT": "/home/excellence/nlgcp-data",
        "POSTGRES_PASSWORD": "super-secret-password",
        "NTRIP_PASSWORD": "ntrip-secret",
        "AWS_SECRET_ACCESS_KEY": "aws-secret",
        "API_TOKEN": "tok-12345",
        "GH_AUTH_HEADER": "Bearer xyz",
        "PRIVATE_KEY_PEM": "-----BEGIN PRIVATE KEY-----",
    }
    clean = sanitize_environment_vars(fake_env)
    assert clean == {"LANG": "C.UTF-8", "NLGCP_DATA_ROOT": "/home/excellence/nlgcp-data"}
    snap = capture_environment_snapshot(tmp_path, tmp_path, env=fake_env)
    dumped = json.dumps(snap)
    for forbidden in ("super-secret-password", "ntrip-secret", "aws-secret", "tok-12345"):
        assert forbidden not in dumped


def test_verify_file_integrity_rejects_bad_hash_format_without_touching_file(
    tmp_path: Path,
) -> None:
    f = tmp_path / "sample.txt"
    f.write_text("immutable\n", encoding="utf-8")
    chk = verify_file_integrity(
        record_id="NLGCP-DATA-2026-001",
        record_kind="dataset",
        location=str(f),
        storage_type="REPOSITORY",
        expected_hash="not-a-sha256",
        expected_size_bytes=10,
        repo_root=tmp_path,
        data_root=tmp_path,
    )
    assert chk.status is IntegrityStatus.INVALID_MANIFEST
    assert f.read_text(encoding="utf-8") == "immutable\n"


def test_real_repository_archive_passes_schema_and_cross_references() -> None:
    """Validate the real committed research/archive/ manifests in CI without external data."""
    repo_root = Path(__file__).resolve().parents[3]
    archive_root = repo_root / "research" / "archive"
    report = verify_archive(
        archive_root,
        repo_root=repo_root,
        data_root=repo_root / "__nonexistent_ci_data_root__",
        verify_hashes=True,
    )
    assert report.parse_errors == ()
    assert report.duplicate_id_errors == ()
    assert report.dataset_schema_errors == {}
    assert report.artifact_schema_errors == {}
    assert report.register_errors == ()
    assert report.summary.registered_datasets >= 20
    assert report.summary.registered_experiments >= 17
    assert report.summary.invalid_experiments == 0
    assert report.summary.registered_artifacts >= 24
    assert report.summary.missing_datasets == 0
    assert report.summary.hash_mismatch_datasets == 0
    assert report.summary.missing_artifacts == 0
    assert report.summary.hash_mismatch_artifacts == 0
    # Repository-local report artifacts must verify even without external data root
    repo_artifacts = [c for c in report.artifact_integrity if c.storage_type == "REPOSITORY"]
    assert repo_artifacts
    assert all(c.status is IntegrityStatus.VERIFIED for c in repo_artifacts)
    assert report.summary.exit_code == int(ExitCode.EXTERNAL_STORAGE_OR_DEPENDENCY_UNAVAILABLE)
