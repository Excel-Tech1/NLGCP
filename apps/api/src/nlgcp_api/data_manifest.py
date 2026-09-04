"""Deterministic scientific-data manifest tooling."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

from nlgcp_api.rinex_inventory import (
    RinexInventoryRecord,
    discover_rinex_inventory,
    is_rinex_candidate,
    sha256_file,
)


@dataclass(frozen=True, slots=True)
class ManifestArtifact:
    """One file recorded in the scientific data manifest."""

    relative_vault_path: str
    filename: str
    file_size_bytes: int
    modified_time_utc: str
    sha256: str
    artifact_type: str
    parser_status: str | None
    warnings: list[str]
    errors: list[str]


@dataclass(frozen=True, slots=True)
class DuplicateChecksum:
    """Files with identical content checksums."""

    sha256: str
    relative_vault_paths: list[str]


@dataclass(frozen=True, slots=True)
class ConflictingPath:
    """Paths that normalize to the same manifest key."""

    normalized_path: str
    relative_vault_paths: list[str]


@dataclass(frozen=True, slots=True)
class DataManifest:
    """Deterministic report-only manifest for the external data vault."""

    schema_version: str
    data_root_name: str
    artifacts: list[ManifestArtifact]
    duplicate_checksums: list[DuplicateChecksum]
    conflicting_paths: list[ConflictingPath]
    malformed_artifacts: list[str]


DEFAULT_MANIFEST_NAME = "scientific-data-manifest.json"


def default_manifest_output_path(data_root: Path) -> Path:
    """Return the default Phase 2 scientific-data manifest path."""

    return data_root / "manifests" / DEFAULT_MANIFEST_NAME


def build_data_manifest(
    data_root: Path,
    *,
    exclude_paths: set[PurePosixPath] | None = None,
) -> DataManifest:
    """Build a deterministic report-only manifest for files under ``data_root``."""

    root = data_root.expanduser().resolve()
    excluded = exclude_paths or set()
    rinex_by_path = {
        PurePosixPath(record.relative_vault_path): record
        for record in discover_rinex_inventory(root)
    }
    artifacts = [
        artifact_for_path(path, root, rinex_by_path.get(_relative_posix(path, root)))
        for path in sorted(root.rglob("*"))
        if path.is_file() and _relative_posix(path, root) not in excluded
    ]
    return DataManifest(
        schema_version="1.0",
        data_root_name=root.name,
        artifacts=artifacts,
        duplicate_checksums=find_duplicate_checksums(artifacts),
        conflicting_paths=find_conflicting_paths(artifacts),
        malformed_artifacts=[
            artifact.relative_vault_path
            for artifact in artifacts
            if artifact.errors or artifact.parser_status == "error"
        ],
    )


def write_data_manifest(manifest: DataManifest, output_path: Path) -> None:
    """Write deterministic machine-readable JSON manifest output."""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(asdict(manifest), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def artifact_for_path(
    path: Path,
    data_root: Path,
    rinex_record: RinexInventoryRecord | None,
) -> ManifestArtifact:
    """Create an artifact record for one file."""

    relative_path = _relative_posix(path, data_root)
    stat = path.stat()
    warnings: list[str] = []
    errors: list[str] = []
    parser_status: str | None = None
    artifact_type = "file"
    if is_rinex_candidate(path):
        artifact_type = "rinex"
        if rinex_record is None:
            parser_status = "error"
            errors.append("RINEX candidate was not present in inventory results")
        else:
            parser_status = rinex_record.parser_status
            warnings = list(rinex_record.warnings)
            errors = list(rinex_record.errors)
    return ManifestArtifact(
        relative_vault_path=str(relative_path),
        filename=path.name,
        file_size_bytes=stat.st_size,
        modified_time_utc=datetime.fromtimestamp(stat.st_mtime, UTC).isoformat(),
        sha256=sha256_file(path),
        artifact_type=artifact_type,
        parser_status=parser_status,
        warnings=warnings,
        errors=errors,
    )


def find_duplicate_checksums(
    artifacts: list[ManifestArtifact],
) -> list[DuplicateChecksum]:
    """Return checksum groups containing more than one path."""

    by_checksum: dict[str, list[str]] = {}
    for artifact in artifacts:
        by_checksum.setdefault(artifact.sha256, []).append(artifact.relative_vault_path)
    return [
        DuplicateChecksum(sha256=checksum, relative_vault_paths=sorted(paths))
        for checksum, paths in sorted(by_checksum.items())
        if len(paths) > 1
    ]


def find_conflicting_paths(
    artifacts: list[ManifestArtifact],
) -> list[ConflictingPath]:
    """Return paths that collide after deterministic manifest normalization."""

    by_normalized_path: dict[str, list[str]] = {}
    for artifact in artifacts:
        normalized = artifact.relative_vault_path.casefold()
        by_normalized_path.setdefault(normalized, []).append(artifact.relative_vault_path)
    return [
        ConflictingPath(
            normalized_path=normalized,
            relative_vault_paths=sorted(set(paths)),
        )
        for normalized, paths in sorted(by_normalized_path.items())
        if len(set(paths)) > 1
    ]


def _relative_posix(path: Path, data_root: Path) -> PurePosixPath:
    return PurePosixPath(path.resolve().relative_to(data_root).as_posix())
