"""Domain models, controlled vocabularies, and identifier contracts for NLGCP B-00."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from enum import IntEnum, StrEnum
from typing import Any

MISSING_TOKENS: frozenset[str] = frozenset(
    {
        "UNKNOWN",
        "NOT_RECORDED",
        "NOT_VERIFIED",
        "NOT_AVAILABLE",
        "NOT_APPLICABLE",
        "BLOCKED",
    }
)

DATASET_ID_RE = re.compile(r"^NLGCP-DATA-\d{4}-\d{3}$")
EXPERIMENT_ID_RE = re.compile(r"^NLGCP-EXP-\d{4}-\d{3}$")
ARTIFACT_ID_RE = re.compile(r"^NLGCP-ART-\d{4}-\d{3}$")
SOFTWARE_ID_RE = re.compile(r"^NLGCP-SW-[A-Z0-9-]+$")
FINDING_ID_RE = re.compile(r"^NLGCP-FIND-\d{3}$")
LIMITATION_ID_RE = re.compile(r"^NLGCP-LIM-\d{3}$")
CLAIM_ID_RE = re.compile(r"^NLGCP-CLM-\d{3}$")
REPRO_ID_RE = re.compile(r"^NLGCP-REPRO-\d{4}-\d{3}$")
SHA256_HEX_RE = re.compile(r"^[0-9a-f]{64}$")


class ExitCode(IntEnum):
    """Deterministic CLI exit codes per B-00 Section 11.7."""

    OK = 0
    INTEGRITY_OR_VALIDATION_FAILURE = 1
    INVALID_ARGUMENTS_OR_CONFIG = 2
    EXTERNAL_STORAGE_OR_DEPENDENCY_UNAVAILABLE = 3


class DatasetClassification(StrEnum):
    """Controlled dataset source classifications (Section 5.3)."""

    AUTHENTIC_LIVE_CORS = "AUTHENTIC_LIVE_CORS"
    AUTHENTIC_RECORDED_CORS = "AUTHENTIC_RECORDED_CORS"
    THIRD_PARTY_CORRECTION_STREAM = "THIRD_PARTY_CORRECTION_STREAM"
    SYNTHETIC_TEST_DATA = "SYNTHETIC_TEST_DATA"
    SIMULATED_DATA = "SIMULATED_DATA"
    MODELLED_DATA = "MODELLED_DATA"
    DERIVED_DATA = "DERIVED_DATA"
    UNKNOWN = "UNKNOWN"


class StorageType(StrEnum):
    """Supported storage backends for datasets and artifacts."""

    REPOSITORY = "REPOSITORY"
    EXTERNAL_FILESYSTEM = "EXTERNAL_FILESYSTEM"
    UNAVAILABLE = "UNAVAILABLE"


class IntegrityStatus(StrEnum):
    """SHA-256 verification outcomes (Section 5.5)."""

    VERIFIED = "VERIFIED"
    MISSING = "MISSING"
    HASH_MISMATCH = "HASH_MISMATCH"
    NOT_CHECKED = "NOT_CHECKED"
    ACCESS_DENIED = "ACCESS_DENIED"
    INVALID_MANIFEST = "INVALID_MANIFEST"


class ExperimentStatus(StrEnum):
    """Controlled experiment lifecycle states (Section 6.3)."""

    PLANNED = "PLANNED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"
    SUPERSEDED = "SUPERSEDED"
    REQUIRES_REVALIDATION = "REQUIRES_REVALIDATION"


class ValidationLevel(StrEnum):
    """Strict non-auto-promoted validation evidence levels (Section 9.1)."""

    IMPLEMENTED = "IMPLEMENTED"
    UNIT_TESTED = "UNIT_TESTED"
    INTEGRATION_TESTED = "INTEGRATION_TESTED"
    INDEPENDENTLY_VALIDATED = "INDEPENDENTLY_VALIDATED"
    SCIENTIFICALLY_VALIDATED = "SCIENTIFICALLY_VALIDATED"
    HARDWARE_VALIDATED = "HARDWARE_VALIDATED"
    OPERATIONALLY_APPROVED = "OPERATIONALLY_APPROVED"


class ReproducibilityStatus(StrEnum):
    """Experiment / reproduction outcomes (Section 13)."""

    REPRODUCED = "REPRODUCED"
    PARTIALLY_REPRODUCED = "PARTIALLY_REPRODUCED"
    PARTIAL = "PARTIAL"
    NOT_REPRODUCED = "NOT_REPRODUCED"
    BLOCKED = "BLOCKED"
    NOT_ATTEMPTED = "NOT_ATTEMPTED"


class ReproductionLevel(StrEnum):
    """Four-tier reproduction maturity levels (Section 13)."""

    LEVEL_0_NONE = "LEVEL_0_NONE"
    LEVEL_1_RECORD_COMPLETE = "LEVEL_1_RECORD_COMPLETE"
    LEVEL_2_COMPUTATIONAL = "LEVEL_2_COMPUTATIONAL"
    LEVEL_3_NUMERICAL = "LEVEL_3_NUMERICAL"
    LEVEL_4_INDEPENDENT = "LEVEL_4_INDEPENDENT"


class RelationType(StrEnum):
    """Directed scientific lineage relationships (Section 6.4)."""

    USES_DATASET = "USES_DATASET"
    PRODUCES_DATASET = "PRODUCES_DATASET"
    DEPENDS_ON = "DEPENDS_ON"
    VALIDATES = "VALIDATES"
    SUPERSEDES = "SUPERSEDES"
    REPRODUCES = "REPRODUCES"


class ClaimStatus(StrEnum):
    """Publication claim evidential support classifications (Section 9.3)."""

    SUPPORTED = "SUPPORTED"
    SUPPORTED_WITH_LIMITATIONS = "SUPPORTED_WITH_LIMITATIONS"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    REFUTED_OR_NEGATIVE = "REFUTED_OR_NEGATIVE"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True, slots=True)
class HashCheckResult:
    """Read-only SHA-256 verification outcome for one file reference."""

    record_id: str
    record_kind: str
    storage_type: str
    location: str
    resolved_path: str | None
    expected_hash: str
    observed_hash: str | None
    expected_size_bytes: int | None
    observed_size_bytes: int | None
    status: IntegrityStatus
    detail: str = ""

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["status"] = str(self.status)
        return payload


@dataclass(frozen=True, slots=True)
class ExperimentValidationResult:
    """Structured schema, reference, and provenance completeness check for one experiment."""

    experiment_id: str
    manifest_path: str
    status: str
    valid: bool
    provenance_complete: bool
    errors: tuple[str, ...] = ()
    provenance_gaps: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "experiment_id": self.experiment_id,
            "manifest_path": self.manifest_path,
            "status": self.status,
            "valid": self.valid,
            "provenance_complete": self.provenance_complete,
            "errors": list(self.errors),
            "provenance_gaps": list(self.provenance_gaps),
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True, slots=True)
class ArchiveStatusSummary:
    """Top-level archive integrity and completeness counters (Section 11.1)."""

    registered_datasets: int
    verified_datasets: int
    missing_datasets: int
    hash_mismatch_datasets: int
    access_denied_datasets: int
    not_checked_datasets: int
    invalid_dataset_manifests: int
    registered_experiments: int
    completed_experiments: int
    experiments_with_complete_provenance: int
    experiments_with_incomplete_provenance: int
    invalid_experiments: int
    registered_artifacts: int
    verified_artifacts: int
    missing_artifacts: int
    hash_mismatch_artifacts: int
    access_denied_artifacts: int
    not_checked_artifacts: int
    registered_software: int
    verified_software: int
    registered_findings: int
    registered_limitations: int
    registered_claims: int
    registered_security_findings: int
    registered_reproductions: int
    overall_status: str
    exit_code: int

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ArchiveVerifyReport:
    """Complete read-only verification report across all archive entities."""

    schema_version: str
    archive_version: str
    generated_utc: str
    archive_root: str
    repo_root: str
    data_root: str
    read_only: bool
    summary: ArchiveStatusSummary
    parse_errors: tuple[str, ...] = ()
    duplicate_id_errors: tuple[str, ...] = ()
    dataset_schema_errors: dict[str, list[str]] = field(default_factory=dict)
    dataset_integrity: tuple[HashCheckResult, ...] = ()
    experiment_validations: tuple[ExperimentValidationResult, ...] = ()
    artifact_schema_errors: dict[str, list[str]] = field(default_factory=dict)
    artifact_integrity: tuple[HashCheckResult, ...] = ()
    nested_artifact_checks: dict[str, dict[str, Any]] = field(default_factory=dict)
    software_checks: tuple[dict[str, Any], ...] = ()
    register_errors: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "archive_version": self.archive_version,
            "generated_utc": self.generated_utc,
            "archive_root": self.archive_root,
            "repo_root": self.repo_root,
            "data_root": self.data_root,
            "read_only": self.read_only,
            "summary": self.summary.as_dict(),
            "parse_errors": list(self.parse_errors),
            "duplicate_id_errors": list(self.duplicate_id_errors),
            "dataset_schema_errors": dict(self.dataset_schema_errors),
            "dataset_integrity": [c.as_dict() for c in self.dataset_integrity],
            "experiment_validations": [e.as_dict() for e in self.experiment_validations],
            "artifact_schema_errors": dict(self.artifact_schema_errors),
            "artifact_integrity": [a.as_dict() for a in self.artifact_integrity],
            "nested_artifact_checks": dict(self.nested_artifact_checks),
            "software_checks": list(self.software_checks),
            "register_errors": list(self.register_errors),
        }
