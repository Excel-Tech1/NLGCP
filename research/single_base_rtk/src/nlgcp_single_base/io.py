"""File, hashing and manifest helpers for Phase 3 experiments."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any


def resolve_data_root(env: dict[str, str] | None = None) -> Path:
    """Resolve NLGCP_DATA_ROOT without inventing a local scientific dataset."""

    source = os.environ if env is None else env
    raw_value = source.get("NLGCP_DATA_ROOT")
    if not raw_value:
        raise RuntimeError("NLGCP_DATA_ROOT is required for Phase 3 experiment outputs")
    root = Path(raw_value).expanduser().resolve()
    if not root.exists():
        raise RuntimeError(f"NLGCP_DATA_ROOT does not exist: {root}")
    if not root.is_dir():
        raise RuntimeError(f"NLGCP_DATA_ROOT is not a directory: {root}")
    return root


def sha256_file(path: Path) -> str:
    """Hash a file with SHA-256."""

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_text(text: str) -> str:
    """Hash UTF-8 text with SHA-256."""

    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def json_ready(value: Any) -> Any:
    """Convert dataclasses and paths into stable JSON-serialisable objects."""

    if is_dataclass(value) and not isinstance(value, type):
        return json_ready(asdict(value))
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): json_ready(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [json_ready(item) for item in value]
    return value


def write_json(path: Path, payload: dict[str, Any]) -> None:
    """Write canonical-ish indented JSON for reviewable experiment artefacts."""

    content = json.dumps(json_ready(payload), indent=2, sort_keys=True) + "\n"
    path.write_text(content, encoding="utf-8")


def read_json(path: Path) -> dict[str, Any]:
    """Read a JSON object from disk."""

    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object in {path}")
    return value


def git_provenance(repo_root: Path) -> dict[str, Any]:
    """Capture the NLGCP software state without pretending dirty trees are clean."""

    commit = _git(repo_root, "rev-parse", "HEAD")
    status = _git(repo_root, "status", "--porcelain")
    return {
        "commit": commit,
        "working_tree_dirty": bool(status),
        "dirty_status": status.splitlines(),
    }


def ensure_experiment_dirs(root: Path, experiment_id: str) -> dict[str, Path]:
    """Create the external processed/single-base experiment directory layout."""

    experiment_root = root / "processed" / "single-base" / experiment_id
    dirs = {
        "root": experiment_root,
        "inputs": experiment_root / "inputs",
        "config": experiment_root / "config",
        "raw_output": experiment_root / "raw-output",
        "results": experiment_root / "results",
        "figures": experiment_root / "figures",
        "report": experiment_root / "report",
    }
    for directory in dirs.values():
        directory.mkdir(parents=True, exist_ok=True)
    return dirs


def _git(repo_root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        check=True,
        text=True,
        capture_output=True,
    )
    return result.stdout.strip()
