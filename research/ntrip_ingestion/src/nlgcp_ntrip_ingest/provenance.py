"""Capture provenance: redacted, reproducible, password-free."""

from __future__ import annotations

import subprocess
from typing import Any

from nlgcp_ntrip_ingest import ENGINE_VERSION, LIVE_SCHEMA_VERSION
from nlgcp_ntrip_ingest.models import NtripConfig


def get_software_commit() -> str:
    """Best-effort repository commit for provenance (never fails closed)."""
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        commit = out.stdout.strip()
        return commit if commit else "unknown"
    except Exception:
        return "unknown"


def redacted_config_snapshot(config: NtripConfig) -> dict[str, Any]:
    """Configuration snapshot safe for capture metadata and logs."""
    return config.as_dict_redacted()


def provenance_envelope(
    *,
    capture_id: str,
    provider: str,
    authorization_basis: str,
    config: NtripConfig,
    admission_status: str,
    software_commit: str | None = None,
) -> dict[str, Any]:
    """Per-frame/capture provenance envelope (no secrets, no passwords)."""
    return {
        "capture_id": capture_id,
        "provider": provider,
        "authorization_basis": authorization_basis,
        "admission_status": admission_status,
        "engine_version": ENGINE_VERSION,
        "schema_version": LIVE_SCHEMA_VERSION,
        "software_commit": software_commit or get_software_commit(),
        "caster": f"{config.host}:{config.port}",
        "mountpoint": config.mountpoint,
        "tls": bool(config.use_tls),
    }
