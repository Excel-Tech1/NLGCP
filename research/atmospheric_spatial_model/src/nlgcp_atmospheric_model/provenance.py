"""Provenance, hashing, and fingerprint-gated resumability (Phase 6)."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from . import PIPELINE_VERSION


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def canonical_json(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def fingerprint(payload: Any) -> str:
    return sha256_text(canonical_json(payload))


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def code_fingerprint(repo_root: Path) -> str:
    """Fingerprint of the Phase 6 source tree (algorithm/config identity)."""
    src = repo_root / "research" / "atmospheric_spatial_model"
    parts: list[str] = [PIPELINE_VERSION]
    for path in sorted(src.rglob("*.py")):
        parts.append(f"{path.relative_to(src)}:{sha256_file(path)}")
    config = repo_root / "research" / "atmospheric_spatial_model" / "config"
    if config.is_dir():
        for path in sorted(config.rglob("*.json")):
            parts.append(f"{path.relative_to(src)}:{sha256_file(path)}")
    script = repo_root / "scripts" / "run_atmospheric_model.py"
    if script.is_file():
        parts.append(f"scripts/run_atmospheric_model.py:{sha256_file(script)}")
    return sha256_text("\n".join(parts))


def provenance_record(
    *,
    inputs: dict[str, Any],
    algorithm: str,
    parameters: dict[str, Any],
    code_fingerprint_value: str,
    git_commit: str,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    record: dict[str, Any] = {
        "inputs": inputs,
        "algorithm": algorithm,
        "algorithm_parameters": parameters,
        "algorithm_version": PIPELINE_VERSION,
        "code_fingerprint": code_fingerprint_value,
        "git_commit": git_commit,
        "execution_timestamp": utc_now_iso(),
    }
    if extra:
        record.update(extra)
    record["provenance_fingerprint"] = fingerprint(record)
    return record


def fingerprint_matches(record: dict[str, Any]) -> bool:
    """Verify a stored provenance record is internally consistent."""
    expected = record.get("provenance_fingerprint")
    if not isinstance(expected, str):
        return False
    payload = {k: v for k, v in record.items() if k != "provenance_fingerprint"}
    return fingerprint(payload) == expected
