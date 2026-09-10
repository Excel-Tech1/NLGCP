"""Batch reproducibility envelopes and deterministic CSV/Markdown reporting."""

from __future__ import annotations

import csv
import hashlib
import json
import os
import subprocess
from datetime import UTC, datetime

from nlgcp_scientific_expansion.models import BatchManifest


def utc_now() -> str:
    """Current UTC time in ISO-8601 seconds precision."""
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def git_commit(repo_dir: str) -> tuple[str, bool]:
    """Return (commit hash, dirty flag); never raises."""
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_dir,
            capture_output=True,
            text=True,
            check=False,
        ).stdout.strip()
        status = subprocess.run(
            ["git", "status", "--short"],
            cwd=repo_dir,
            capture_output=True,
            text=True,
            check=False,
        ).stdout.strip()
        return commit or "UNKNOWN", bool(status)
    except OSError:
        return "UNKNOWN", True


def fingerprint_mapping(mapping: dict[str, str]) -> str:
    """Deterministic SHA-256 over a sorted string mapping."""
    canonical = json.dumps(mapping, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def fingerprint_file(path: str) -> str:
    """SHA-256 of a file's bytes (empty string when missing)."""
    if not os.path.exists(path):
        return ""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while True:
            chunk = handle.read(65536)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def write_csv(path: str, fieldnames: list[str], rows: list[dict[str, object]]) -> str:
    """Write rows deterministically; returns the file SHA-256."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fieldnames})
    return fingerprint_file(path)


def write_markdown(path: str, title: str, lines: list[str]) -> str:
    """Write a Markdown report; returns the file SHA-256."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(f"# {title}\n\n")
        for line in lines:
            handle.write(f"{line}\n")
    return fingerprint_file(path)


def manifest_to_dict(manifest: BatchManifest) -> dict[str, object]:
    """Serialize a batch manifest to plain JSON-compatible data."""
    return {
        "batch_id": manifest.batch_id,
        "batch_type": manifest.batch_type,
        "input_manifest_fingerprint": manifest.input_manifest_fingerprint,
        "config_fingerprint": manifest.config_fingerprint,
        "software_commit": manifest.software_commit,
        "software_dirty": manifest.software_dirty,
        "rtklib_version": manifest.rtklib_version,
        "rtklib_sha256": manifest.rtklib_sha256,
        "data_root": manifest.data_root,
        "utc_execution_time": manifest.utc_execution_time,
        "worker_count": manifest.worker_count,
        "experiment_ids": list(manifest.experiment_ids),
        "extra": dict(manifest.extra),
    }


def write_manifest(path: str, manifest: BatchManifest) -> str:
    """Persist a batch manifest as strict JSON; returns the file SHA-256."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(manifest_to_dict(manifest), handle, indent=2, sort_keys=True)
        handle.write("\n")
    return fingerprint_file(path)
