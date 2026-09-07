"""Filesystem, hashing and provenance helpers for Phase 5."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from dataclasses import asdict as _asdict
from dataclasses import is_dataclass
from pathlib import Path
from typing import Any


def resolve_data_root(explicit: Path | None = None) -> Path:
    value = explicit or (
        Path(os.environ["NLGCP_DATA_ROOT"]) if "NLGCP_DATA_ROOT" in os.environ else None
    )
    if value is None:
        raise RuntimeError("NLGCP_DATA_ROOT is not configured")
    root = value.expanduser().resolve()
    if not root.is_dir():
        raise RuntimeError(f"NLGCP_DATA_ROOT is not a directory: {root}")
    return root


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def json_ready(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return json_ready(_asdict(value))
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): json_ready(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [json_ready(item) for item in value]
    return value


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(json_ready(payload), indent=2, sort_keys=True) + "\n"
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object in {path}")
    return value


def git_provenance(repo_root: Path) -> dict[str, Any]:
    commit = _git(repo_root, "rev-parse", "HEAD")
    status = _git(repo_root, "status", "--porcelain")
    return {
        "commit": commit,
        "working_tree_dirty": bool(status),
        "dirty_status": status.splitlines(),
    }


def implementation_hash(repo_root: Path) -> str:
    hasher = hashlib.sha256()
    candidates = [
        *(repo_root / "research" / "network_rtk").rglob("*"),
        repo_root / "scripts" / "run_network_rtk.py",
    ]
    for path in sorted(p for p in candidates if p.is_file() and "__pycache__" not in p.parts):
        relative = path.relative_to(repo_root).as_posix()
        hasher.update(relative.encode())
        hasher.update(b"\0")
        hasher.update(path.read_bytes())
        hasher.update(b"\0")
    return hasher.hexdigest()


def ensure_experiment_dirs(root: Path, experiment_id: str) -> dict[str, Path]:
    experiment_root = root / "processed" / "network-rtk" / "experiments" / experiment_id
    dirs = {
        "root": experiment_root,
        "baselines": experiment_root / "baselines",
        "config": experiment_root / "config",
    }
    for directory in dirs.values():
        directory.mkdir(parents=True, exist_ok=True)
    return dirs


def _git(repo_root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=repo_root, check=True, text=True, capture_output=True
    )
    return result.stdout.strip()


REPO_ROOT = Path(__file__).resolve().parents[4]
