"""Provenance file resolution for station metadata imports."""

from __future__ import annotations

import hashlib
from pathlib import Path

from nlgcp_api.station_metadata.models import (
    MetadataSource,
    ResolvedMetadataSource,
    StationImportPackage,
)


class ProvenanceError(RuntimeError):
    """Raised when a provenance source cannot be verified."""


def resolve_package_sources(
    package: StationImportPackage,
    data_root: Path,
) -> dict[str, ResolvedMetadataSource]:
    """Resolve and hash all package sources under ``data_root``."""

    root = data_root.expanduser().resolve()
    return {
        source.key: resolve_metadata_source(source, root)
        for source in package.sources
    }


def resolve_metadata_source(
    source: MetadataSource,
    data_root: Path,
) -> ResolvedMetadataSource:
    """Resolve one source file and verify any expected checksum."""

    if source.path.is_absolute() or ".." in source.path.parts:
        raise ProvenanceError(
            f"source path {source.path} must be relative and must not traverse"
        )

    candidate = data_root.joinpath(*source.path.parts).resolve()
    if not candidate.is_relative_to(data_root):
        raise ProvenanceError(
            f"source path {source.path} resolves outside NLGCP_DATA_ROOT"
        )
    if not candidate.exists():
        raise ProvenanceError(f"source file does not exist: {source.path}")
    if not candidate.is_file():
        raise ProvenanceError(f"source path is not a regular file: {source.path}")

    checksum = sha256_file(candidate)
    if source.expected_sha256 is not None and checksum != source.expected_sha256:
        raise ProvenanceError(
            f"checksum mismatch for {source.path}: expected "
            f"{source.expected_sha256}, computed {checksum}"
        )

    return ResolvedMetadataSource(source=source, sha256=checksum)


def sha256_file(path: Path) -> str:
    """Return the SHA256 digest of a file."""

    digest = hashlib.sha256()
    with path.open("rb") as source_file:
        for chunk in iter(lambda: source_file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
