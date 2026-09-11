"""Operational status semantics for the Phase 10 service boundary."""

from __future__ import annotations

import shutil
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from nlgcp_ntrip_ingest.models import ConnectionState, NtripConfig


@dataclass(frozen=True, slots=True)
class Liveness:
    status: str = "ALIVE"
    service: str = "gnss-ingestor"
    scientific_validity: str = "NOT_ASSESSED"


@dataclass(frozen=True, slots=True)
class Readiness:
    status: str
    reason_codes: tuple[str, ...]
    configured_stream: bool
    stream_state: str
    scientific_validity: str = "NOT_ASSESSED"


@dataclass(frozen=True, slots=True)
class ServiceStatus:
    liveness: Liveness
    readiness: Readiness
    stream_state: ConnectionState

    def as_dict(self) -> dict[str, Any]:
        return {
            "liveness": asdict(self.liveness),
            "readiness": asdict(self.readiness),
            "stream_state": str(self.stream_state),
        }


def readiness(
    config: NtripConfig,
    *,
    required_directories: tuple[Path, ...] = (),
    stream_state: ConnectionState = ConnectionState.DISCONNECTED,
) -> Readiness:
    """Report service readiness, never GNSS or positioning validity."""
    configured = bool(config.host or config.mountpoint or config.username)
    reasons: list[str] = []
    if configured:
        reasons.extend(config.validate())
    for path in required_directories:
        if not path.exists() or not path.is_dir():
            reasons.append(f"DIRECTORY_UNAVAILABLE:{path}")
        elif not bool(path.stat().st_mode & 0o222):
            reasons.append(f"DIRECTORY_NOT_WRITABLE:{path}")
    if not configured and not reasons:
        reasons.append("INGESTION_DISABLED_NO_CASTER_CONFIGURED")
        return Readiness("READY", tuple(reasons), False, str(stream_state))
    return Readiness(
        "NOT_READY" if reasons else "READY", tuple(reasons), configured, str(stream_state)
    )


def service_status(
    config: NtripConfig,
    *,
    required_directories: tuple[Path, ...] = (),
    stream_state: ConnectionState = ConnectionState.DISCONNECTED,
) -> ServiceStatus:
    return ServiceStatus(
        Liveness(),
        readiness(config, required_directories=required_directories, stream_state=stream_state),
        stream_state,
    )


def disk_state(path: Path, *, minimum_free_bytes: int) -> dict[str, int | bool]:
    usage = shutil.disk_usage(path)
    return {
        "free_bytes": usage.free,
        "minimum_free_bytes": minimum_free_bytes,
        "acceptable": usage.free >= minimum_free_bytes,
    }
