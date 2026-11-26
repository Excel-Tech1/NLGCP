"""Software provenance, secret-safe environment capture, and lineage graph (Stage 4)."""

from __future__ import annotations

import os
import platform
import subprocess
import sys
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from nlgcp_research_archive.hash_verifier import compute_sha256, is_valid_sha256_hex
from nlgcp_research_archive.models import MISSING_TOKENS, IntegrityStatus

SAFE_ENV_ALLOWLIST: frozenset[str] = frozenset(
    {
        "LANG",
        "LC_ALL",
        "TZ",
        "NLGCP_DATA_ROOT",
        "RTKLIB_SOURCE",
        "VIRTUAL_ENV",
    }
)

SECRET_ENV_SUBSTRINGS: tuple[str, ...] = (
    "PASSWORD",
    "PASSWD",
    "SECRET",
    "TOKEN",
    "API_KEY",
    "ACCESS_KEY",
    "PRIVATE_KEY",
    "CREDENTIAL",
    "AUTH",
    "COOKIE",
    "BEARER",
    "DSN",
    "NTRIP_USER",
    "NTRIP_PASS",
)


def utc_now_iso() -> str:
    """Return canonical UTC ISO-8601 timestamp."""
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def sanitize_environment_vars(env: Mapping[str, str]) -> dict[str, str]:
    """Capture ONLY allow-listed non-secret environment variables; never archive secrets."""
    safe: dict[str, str] = {}
    for key in sorted(env):
        upper = key.upper()
        if any(pat in upper for pat in SECRET_ENV_SUBSTRINGS):
            continue
        if key not in SAFE_ENV_ALLOWLIST:
            continue
        val = env[key]
        if any(pat in val.upper() for pat in ("BEGIN PRIVATE KEY", "BEARER ", "BASIC ")):
            continue
        safe[key] = val
    return safe


def _probe_cmd(cmd: list[str], *, cwd: Path | None = None, timeout_s: float = 5.0) -> str:
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout_s,
        )
    except (OSError, subprocess.TimeoutExpired):
        return "NOT_AVAILABLE"
    out = (proc.stdout or proc.stderr).strip().splitlines()
    if proc.returncode != 0 or not out:
        return "NOT_AVAILABLE"
    return out[0].strip()


def capture_git_provenance(repo_root: Path) -> dict[str, Any]:
    """Capture Git repository branch, HEAD commit, and dirty state read-only."""
    branch = _probe_cmd(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=repo_root)
    head = _probe_cmd(["git", "rev-parse", "HEAD"], cwd=repo_root)
    try:
        st_proc = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            check=False,
            timeout=5.0,
        )
        dirty: bool | str = bool(st_proc.stdout.strip()) if st_proc.returncode == 0 else "UNKNOWN"
    except (OSError, subprocess.TimeoutExpired):
        dirty = "UNKNOWN"
    return {
        "repository_root": str(repo_root),
        "branch": branch,
        "head_commit": head,
        "git_dirty": dirty,
    }


def capture_environment_snapshot(
    repo_root: Path,
    data_root: Path,
    *,
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Build a secret-free reproducibility environment snapshot (Section 7.3)."""
    lockfiles = (
        "pyproject.toml",
        "apps/web/package.json",
        "apps/web/package-lock.json",
        "services/gnss-ingestor/go.mod",
        "services/gnss-ingestor/go.sum",
        "services/nrtk-engine/CMakeLists.txt",
        "compose.yml",
    )
    lock_hashes: dict[str, str] = {}
    for rel in lockfiles:
        p = repo_root / rel
        if p.is_file():
            lock_hashes[rel] = compute_sha256(p)[0]
        else:
            lock_hashes[rel] = "NOT_AVAILABLE"

    return {
        "schema_version": "nlgcp.archive.environment.v1",
        "captured_utc": utc_now_iso(),
        "operating_system": {
            "system": platform.system(),
            "release": platform.release(),
            "version": platform.version(),
            "machine": platform.machine(),
        },
        "toolchains": {
            "python": sys.version.split()[0],
            "go": _probe_cmd(["go", "version"]),
            "node": _probe_cmd(["node", "--version"]),
            "npm": _probe_cmd(["npm", "--version"]),
            "gcc": _probe_cmd(["gcc", "--version"]),
            "g++": _probe_cmd(["g++", "--version"]),
            "cmake": _probe_cmd(["cmake", "--version"]),
            "docker": _probe_cmd(["docker", "--version"]),
            "docker_compose": _probe_cmd(["docker", "compose", "version"]),
        },
        "git": capture_git_provenance(repo_root),
        "data_root": {
            "path": str(data_root),
            "accessible": data_root.is_dir(),
        },
        "lockfiles_sha256": lock_hashes,
        "environment_variables": sanitize_environment_vars(env if env is not None else os.environ),
    }


def verify_software_inventory(
    software_entries: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Verify registered external scientific software binaries/sources read-only."""
    results: list[dict[str, Any]] = []
    for entry in software_entries:
        sw_id = str(entry.get("software_id", "UNKNOWN"))
        name = str(entry.get("name", "UNKNOWN"))
        version = str(entry.get("version", "UNKNOWN"))
        loc = str(entry.get("executable_or_source_path", "NOT_RECORDED"))
        exp_hash = str(entry.get("expected_sha256", "NOT_RECORDED"))
        status: IntegrityStatus
        observed_hash: str | None = None
        detail = ""

        if loc in MISSING_TOKENS:
            status = IntegrityStatus.NOT_CHECKED
            detail = f"path is {loc}"
        else:
            p = Path(loc)
            try:
                exists = p.exists()
            except PermissionError:
                exists = False
                status = IntegrityStatus.ACCESS_DENIED
                detail = f"permission denied accessing {loc}"
            else:
                if not exists:
                    # Distinguish inaccessible outside-workspace path vs genuine missing file
                    status = (
                        IntegrityStatus.ACCESS_DENIED
                        if not p.parent.exists()
                        else IntegrityStatus.MISSING
                    )
                    detail = f"path not accessible or absent: {loc}"
                elif p.is_dir():
                    status = IntegrityStatus.NOT_CHECKED
                    detail = "directory exists (source tree)"
                elif exp_hash in MISSING_TOKENS:
                    status = IntegrityStatus.NOT_CHECKED
                    detail = f"file exists; expected_sha256 is {exp_hash}"
                elif not is_valid_sha256_hex(exp_hash):
                    status = IntegrityStatus.INVALID_MANIFEST
                    detail = f"invalid expected_sha256 format: {exp_hash!r}"
                else:
                    observed_hash, _ = compute_sha256(p)
                    if observed_hash == exp_hash:
                        status = IntegrityStatus.VERIFIED
                        detail = "SHA-256 verified"
                    else:
                        status = IntegrityStatus.HASH_MISMATCH
                        detail = (
                            f"SHA-256 mismatch: expected {exp_hash[:16]}..., "
                            f"observed {observed_hash[:16]}..."
                        )

        results.append(
            {
                "software_id": sw_id,
                "name": name,
                "version": version,
                "path": loc,
                "expected_sha256": exp_hash,
                "observed_sha256": observed_hash,
                "status": str(status),
                "detail": detail,
                "linked_experiments": list(entry.get("linked_experiments", [])),
            }
        )
    return results


def build_provenance_lineage(
    *,
    datasets: dict[str, dict[str, Any]],
    experiments: dict[str, dict[str, Any]],
    artifacts: dict[str, dict[str, Any]],
    software: dict[str, dict[str, Any]],
    findings: list[dict[str, Any]],
    limitations: list[dict[str, Any]],
    claims: list[dict[str, Any]],
    reproductions: list[dict[str, Any]],
) -> dict[str, Any]:
    """Assemble end-to-end scientific lineage chains from datasets to publication claims."""
    findings_by_id = {str(f["finding_id"]): f for f in findings if "finding_id" in f}

    dataset_lineage: list[dict[str, Any]] = []
    for did in sorted(datasets):
        ds = datasets[did]
        rels = ds.get("relationships", {})
        used_by = sorted(
            eid for eid, exp in experiments.items() if did in exp.get("datasets", [])
        )
        dataset_lineage.append(
            {
                "dataset_id": did,
                "name": ds.get("name"),
                "classification": ds.get("source_classification"),
                "immutable_source": ds.get("immutable_source"),
                "derived_from_datasets": list(rels.get("derived_from_datasets", [])),
                "derived_datasets": list(rels.get("derived_datasets", [])),
                "used_by_experiments": used_by,
            }
        )

    experiment_lineage: list[dict[str, Any]] = []
    for eid in sorted(experiments):
        exp = experiments[eid]
        exp_arts = sorted(
            aid for aid, art in artifacts.items() if art.get("experiment_id") == eid
        )
        exp_findings = sorted(
            str(f["finding_id"])
            for f in findings
            if eid in f.get("supporting_experiments", [])
        )
        experiment_lineage.append(
            {
                "experiment_id": eid,
                "title": exp.get("title"),
                "milestone": exp.get("milestone"),
                "status": exp.get("status"),
                "datasets": list(exp.get("datasets", [])),
                "software_ids": list(exp.get("software", {}).get("software_ids", [])),
                "config_sha256": exp.get("configuration", {}).get("sha256"),
                "artifacts": exp_arts,
                "findings": exp_findings,
                "relationships": list(exp.get("relationships", [])),
                "reproducibility": exp.get("reproducibility", {}),
            }
        )

    claim_chains: list[dict[str, Any]] = []
    for clm in claims:
        f_ids = list(clm.get("supporting_findings", []))
        exp_ids: set[str] = set()
        ds_ids: set[str] = set()
        art_ids: set[str] = set()
        sw_ids: set[str] = set()
        for fid in f_ids:
            frec = findings_by_id.get(fid, {})
            exp_ids.update(frec.get("supporting_experiments", []))
            ds_ids.update(frec.get("supporting_datasets", []))
            art_ids.update(frec.get("result_artifacts", []))
        for eid in exp_ids:
            erec = experiments.get(eid, {})
            ds_ids.update(erec.get("datasets", []))
            sw_ids.update(erec.get("software", {}).get("software_ids", []))
        claim_chains.append(
            {
                "claim_id": clm.get("claim_id"),
                "claim": clm.get("claim"),
                "status": clm.get("status"),
                "supporting_findings": f_ids,
                "supporting_experiments": sorted(exp_ids),
                "supporting_datasets": sorted(ds_ids),
                "supporting_software": sorted(sw_ids),
                "supporting_artifacts": sorted(art_ids),
                "limitations": list(clm.get("limitations", [])),
            }
        )

    return {
        "schema_version": "nlgcp.archive.provenance_lineage.v1",
        "generated_utc": utc_now_iso(),
        "counts": {
            "datasets": len(datasets),
            "experiments": len(experiments),
            "artifacts": len(artifacts),
            "software": len(software),
            "findings": len(findings),
            "limitations": len(limitations),
            "claims": len(claims),
            "reproductions": len(reproductions),
        },
        "dataset_lineage": dataset_lineage,
        "experiment_lineage": experiment_lineage,
        "publication_claim_chains": claim_chains,
    }
