"""Strictly read-only SHA-256 verification and safe output scanning (Stages 2 & 5)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from nlgcp_research_archive.models import (
    MISSING_TOKENS,
    SHA256_HEX_RE,
    HashCheckResult,
    IntegrityStatus,
    StorageType,
)

DEFAULT_INCLUDE_EXTENSIONS: frozenset[str] = frozenset(
    {
        ".csv",
        ".json",
        ".yaml",
        ".yml",
        ".txt",
        ".md",
        ".pdf",
        ".obs",
        ".rnx",
        ".rtcm3",
        ".sp3",
        ".clk",
        ".pos",
        ".svg",
        ".png",
    }
)

DEFAULT_EXCLUDE_DIRS: frozenset[str] = frozenset(
    {
        ".git",
        ".venv",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        "node_modules",
        ".next",
        "build",
        "tmp",
        ".tmp",
    }
)

DEFAULT_EXCLUDE_SUFFIXES: frozenset[str] = frozenset(
    {".pyc", ".pyo", ".tmp", ".swp", ".bak", ".lock", ".log"}
)


def is_valid_sha256_hex(value: str) -> bool:
    """Return True iff ``value`` is a canonical 64-character lowercase SHA-256 hex digest."""
    return bool(SHA256_HEX_RE.match(value))


def compute_sha256(path: Path, chunk_bytes: int = 4 * 1024 * 1024) -> tuple[str, int]:
    """Stream-compute SHA-256 hex digest and byte length without modifying the file."""
    digest = hashlib.sha256()
    total = 0
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(chunk_bytes)
            if not chunk:
                break
            digest.update(chunk)
            total += len(chunk)
    return digest.hexdigest(), total


def _normalize_location(location: str, repo_root: Path, data_root: Path) -> Path:
    if location.startswith("${NLGCP_DATA_ROOT}/"):
        return data_root / location.removeprefix("${NLGCP_DATA_ROOT}/")
    raw = Path(location)
    if raw.is_absolute():
        return raw
    return repo_root / raw


def resolve_storage_path(
    *,
    location: str,
    storage_type: str,
    repo_root: Path,
    data_root: Path,
) -> tuple[Path | None, IntegrityStatus | None, str]:
    """Resolve a manifest storage location safely without altering the filesystem."""
    if storage_type == StorageType.UNAVAILABLE or location in MISSING_TOKENS:
        return None, IntegrityStatus.NOT_CHECKED, "external source explicitly unavailable"
    if storage_type == StorageType.REPOSITORY:
        target = _normalize_location(location, repo_root, data_root)
        return target, None, ""
    if storage_type == StorageType.EXTERNAL_FILESYSTEM:
        if not data_root.exists():
            return (
                _normalize_location(location, repo_root, data_root),
                IntegrityStatus.ACCESS_DENIED,
                f"external data root inaccessible: {data_root}",
            )
        target = _normalize_location(location, repo_root, data_root)
        # If target sits under a different external prefix whose root directory is absent
        try:
            parent_accessible = target.parent.exists()
        except PermissionError:
            return target, IntegrityStatus.ACCESS_DENIED, f"permission denied reading {target}"
        if not parent_accessible and not str(target).startswith(str(data_root)):
            return (
                target,
                IntegrityStatus.ACCESS_DENIED,
                f"external storage root inaccessible for {target}",
            )
        return target, None, ""
    return None, IntegrityStatus.INVALID_MANIFEST, f"unknown storage_type: {storage_type}"


def verify_file_integrity(
    *,
    record_id: str,
    record_kind: str,
    location: str,
    storage_type: str,
    expected_hash: str,
    expected_size_bytes: int | None,
    repo_root: Path,
    data_root: Path,
    verify_hashes: bool = True,
    max_hash_bytes: int | None = None,
) -> HashCheckResult:
    """Verify one registered dataset or artifact strictly read-only."""
    if expected_hash not in MISSING_TOKENS and not is_valid_sha256_hex(expected_hash):
        return HashCheckResult(
            record_id=record_id,
            record_kind=record_kind,
            storage_type=storage_type,
            location=location,
            resolved_path=None,
            expected_hash=expected_hash,
            observed_hash=None,
            expected_size_bytes=expected_size_bytes,
            observed_size_bytes=None,
            status=IntegrityStatus.INVALID_MANIFEST,
            detail=f"invalid SHA-256 hex format: {expected_hash!r}",
        )

    resolved, pre_status, pre_detail = resolve_storage_path(
        location=location,
        storage_type=storage_type,
        repo_root=repo_root,
        data_root=data_root,
    )
    if pre_status is not None or resolved is None:
        return HashCheckResult(
            record_id=record_id,
            record_kind=record_kind,
            storage_type=storage_type,
            location=location,
            resolved_path=str(resolved) if resolved else None,
            expected_hash=expected_hash,
            observed_hash=None,
            expected_size_bytes=expected_size_bytes,
            observed_size_bytes=None,
            status=pre_status or IntegrityStatus.INVALID_MANIFEST,
            detail=pre_detail,
        )

    try:
        exists = resolved.exists()
    except PermissionError:
        return HashCheckResult(
            record_id=record_id,
            record_kind=record_kind,
            storage_type=storage_type,
            location=location,
            resolved_path=str(resolved),
            expected_hash=expected_hash,
            observed_hash=None,
            expected_size_bytes=expected_size_bytes,
            observed_size_bytes=None,
            status=IntegrityStatus.ACCESS_DENIED,
            detail=f"permission denied accessing {resolved}",
        )

    if not exists:
        return HashCheckResult(
            record_id=record_id,
            record_kind=record_kind,
            storage_type=storage_type,
            location=location,
            resolved_path=str(resolved),
            expected_hash=expected_hash,
            observed_hash=None,
            expected_size_bytes=expected_size_bytes,
            observed_size_bytes=None,
            status=IntegrityStatus.MISSING,
            detail=f"file or directory does not exist: {resolved}",
        )

    if resolved.is_dir():
        return HashCheckResult(
            record_id=record_id,
            record_kind=record_kind,
            storage_type=storage_type,
            location=location,
            resolved_path=str(resolved),
            expected_hash=expected_hash,
            observed_hash=None,
            expected_size_bytes=expected_size_bytes,
            observed_size_bytes=None,
            status=(
                IntegrityStatus.NOT_CHECKED
                if expected_hash in MISSING_TOKENS
                else IntegrityStatus.INVALID_MANIFEST
            ),
            detail=(
                "directory reference exists; individual files verified via child manifest"
                if expected_hash in MISSING_TOKENS
                else "expected file SHA-256 on directory path"
            ),
        )

    try:
        size_bytes = resolved.stat().st_size
    except PermissionError:
        return HashCheckResult(
            record_id=record_id,
            record_kind=record_kind,
            storage_type=storage_type,
            location=location,
            resolved_path=str(resolved),
            expected_hash=expected_hash,
            observed_hash=None,
            expected_size_bytes=expected_size_bytes,
            observed_size_bytes=None,
            status=IntegrityStatus.ACCESS_DENIED,
            detail=f"permission denied stating {resolved}",
        )

    if not verify_hashes:
        return HashCheckResult(
            record_id=record_id,
            record_kind=record_kind,
            storage_type=storage_type,
            location=location,
            resolved_path=str(resolved),
            expected_hash=expected_hash,
            observed_hash=None,
            expected_size_bytes=expected_size_bytes,
            observed_size_bytes=size_bytes,
            status=IntegrityStatus.NOT_CHECKED,
            detail="file exists; SHA-256 check skipped by caller flag",
        )

    if expected_hash in MISSING_TOKENS:
        return HashCheckResult(
            record_id=record_id,
            record_kind=record_kind,
            storage_type=storage_type,
            location=location,
            resolved_path=str(resolved),
            expected_hash=expected_hash,
            observed_hash=None,
            expected_size_bytes=expected_size_bytes,
            observed_size_bytes=size_bytes,
            status=IntegrityStatus.NOT_CHECKED,
            detail=f"file exists ({size_bytes} B); expected_hash is {expected_hash}",
        )

    if max_hash_bytes is not None and size_bytes > max_hash_bytes:
        return HashCheckResult(
            record_id=record_id,
            record_kind=record_kind,
            storage_type=storage_type,
            location=location,
            resolved_path=str(resolved),
            expected_hash=expected_hash,
            observed_hash=None,
            expected_size_bytes=expected_size_bytes,
            observed_size_bytes=size_bytes,
            status=IntegrityStatus.NOT_CHECKED,
            detail=(
                f"file exists ({size_bytes} B > max_hash_bytes {max_hash_bytes}); "
                "re-run without --max-hash-mb for full SHA-256 verification"
            ),
        )

    try:
        observed_hash, observed_bytes = compute_sha256(resolved)
    except PermissionError:
        return HashCheckResult(
            record_id=record_id,
            record_kind=record_kind,
            storage_type=storage_type,
            location=location,
            resolved_path=str(resolved),
            expected_hash=expected_hash,
            observed_hash=None,
            expected_size_bytes=expected_size_bytes,
            observed_size_bytes=size_bytes,
            status=IntegrityStatus.ACCESS_DENIED,
            detail=f"permission denied reading {resolved}",
        )

    if observed_hash != expected_hash:
        return HashCheckResult(
            record_id=record_id,
            record_kind=record_kind,
            storage_type=storage_type,
            location=location,
            resolved_path=str(resolved),
            expected_hash=expected_hash,
            observed_hash=observed_hash,
            expected_size_bytes=expected_size_bytes,
            observed_size_bytes=observed_bytes,
            status=IntegrityStatus.HASH_MISMATCH,
            detail=(
                f"SHA-256 mismatch: expected {expected_hash[:16]}..., "
                f"observed {observed_hash[:16]}... (manifest NOT modified)"
            ),
        )

    return HashCheckResult(
        record_id=record_id,
        record_kind=record_kind,
        storage_type=storage_type,
        location=location,
        resolved_path=str(resolved),
        expected_hash=expected_hash,
        observed_hash=observed_hash,
        expected_size_bytes=expected_size_bytes,
        observed_size_bytes=observed_bytes,
        status=IntegrityStatus.VERIFIED,
        detail="SHA-256 verified",
    )


def verify_nested_hash_manifest(manifest_path: Path) -> dict[str, Any]:
    """Verify every output entry recorded in a nested B-02 style ``hashes_manifest.json``."""
    if not manifest_path.is_file():
        return {"status": str(IntegrityStatus.MISSING), "total": 0, "verified": 0}
    raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    outputs = raw.get("outputs", {})
    if not isinstance(outputs, dict):
        return {"status": str(IntegrityStatus.INVALID_MANIFEST), "total": 0, "verified": 0}
    base_dir = manifest_path.parent
    verified = 0
    missing: list[str] = []
    mismatches: list[str] = []
    for rel_path, expected in sorted(outputs.items()):
        target = base_dir / rel_path
        if not target.is_file():
            missing.append(rel_path)
            continue
        obs, _ = compute_sha256(target)
        if obs != expected:
            mismatches.append(rel_path)
        else:
            verified += 1
    status = (
        IntegrityStatus.VERIFIED
        if not missing and not mismatches
        else (IntegrityStatus.HASH_MISMATCH if mismatches else IntegrityStatus.MISSING)
    )
    return {
        "manifest_path": str(manifest_path),
        "status": str(status),
        "total": len(outputs),
        "verified": verified,
        "missing_count": len(missing),
        "mismatch_count": len(mismatches),
        "missing_sample": missing[:10],
        "mismatch_sample": mismatches[:10],
    }


def scan_unregistered_outputs(
    scan_dir: Path,
    registered_paths: set[Path],
    *,
    include_extensions: frozenset[str] = DEFAULT_INCLUDE_EXTENSIONS,
    exclude_dirs: frozenset[str] = DEFAULT_EXCLUDE_DIRS,
    exclude_suffixes: frozenset[str] = DEFAULT_EXCLUDE_SUFFIXES,
) -> list[str]:
    """Explicitly scan a directory for unregistered research outputs while ignoring temp/build."""
    if not scan_dir.is_dir():
        return []
    resolved_registered = {p.resolve() for p in registered_paths if p.exists()}
    unregistered: list[str] = []
    for item in sorted(scan_dir.rglob("*")):
        if not item.is_file():
            continue
        rel_parts = item.relative_to(scan_dir).parts
        if any(part in exclude_dirs for part in rel_parts[:-1]):
            continue
        if item.name.startswith(".") or item.suffix.lower() in exclude_suffixes:
            continue
        if item.suffix.lower() not in include_extensions:
            continue
        if item.resolve() not in resolved_registered:
            unregistered.append(str(item))
    return unregistered
