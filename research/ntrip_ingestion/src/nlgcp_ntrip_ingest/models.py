"""Typed live-ingestion models (Phase 10).

Frozen dataclasses with JSON-serialisable ``as_dict()`` payloads and
fail-closed parsing.  Field names are chosen so a ``LiveFrame`` maps
losslessly onto the Phase 9 ``CorrectionFrame`` consumer contract
(see ``bridge.py``).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any


class ConnectionState(StrEnum):
    """Observable connection lifecycle states."""

    DISCONNECTED = "DISCONNECTED"
    CONNECTING = "CONNECTING"
    AUTHENTICATING = "AUTHENTICATING"
    STREAMING = "STREAMING"
    DEGRADED = "DEGRADED"
    RECONNECTING = "RECONNECTING"
    STOPPED = "STOPPED"
    BLOCKED = "BLOCKED"


class AdmissionStatus(StrEnum):
    """Mountpoint admission outcome."""

    ACCEPT = "ACCEPT"
    WARN = "WARN"
    REJECT = "REJECT"
    BLOCKED = "BLOCKED"


class FailureClass(StrEnum):
    """Machine-readable handshake/stream failure classification."""

    AUTH_FAILURE = "AUTH_FAILURE"
    MOUNTPOINT_NOT_FOUND = "MOUNTPOINT_NOT_FOUND"
    AUTHORIZATION_REJECTED = "AUTHORIZATION_REJECTED"
    CONFIG_INVALID = "CONFIG_INVALID"
    PROTOCOL_ERROR = "PROTOCOL_ERROR"
    WRONG_CONTENT = "WRONG_CONTENT"
    EMPTY_RESPONSE = "EMPTY_RESPONSE"
    TIMEOUT = "TIMEOUT"
    STALLED = "STALLED"
    CONNECTION_LOST = "CONNECTION_LOST"
    NMEA_POSITION_REQUIRED = "NMEA_POSITION_REQUIRED"
    STATION_IDENTITY_UNVERIFIED = "STATION_IDENTITY_UNVERIFIED"


TERMINAL_FAILURES: tuple[FailureClass, ...] = (
    FailureClass.AUTH_FAILURE,
    FailureClass.MOUNTPOINT_NOT_FOUND,
    FailureClass.AUTHORIZATION_REJECTED,
    FailureClass.CONFIG_INVALID,
)

STATION_IDENTITY_UNVERIFIED = "STATION_IDENTITY_UNVERIFIED"
NMEA_POSITION_REQUIRED = "NMEA_POSITION_REQUIRED"
SOURCE_ACCESS_BLOCKED = "SOURCE_ACCESS_BLOCKED"
AUTH_REQUIRED = "AUTH_REQUIRED"

DEFAULT_NTRIP_PORT = 2101
DEFAULT_USER_AGENT = "NLGCP-Phase10/1.0"


@dataclass(frozen=True, slots=True)
class NtripConfig:
    """Secure NTRIP client configuration (secrets via environment only)."""

    host: str = ""
    port: int = DEFAULT_NTRIP_PORT
    mountpoint: str = ""
    username: str = ""
    password: str = ""
    use_tls: bool = False
    user_agent: str = DEFAULT_USER_AGENT
    gga_sentence: str = ""
    dial_timeout_s: float = 5.0
    tls_timeout_s: float = 5.0
    handshake_timeout_s: float = 10.0
    read_timeout_s: float = 10.0
    idle_timeout_s: float = 30.0
    max_reconnects: int = 8
    reconnect_base_delay_s: float = 1.0
    reconnect_max_delay_s: float = 30.0
    buffer_capacity: int = 64
    max_frame_length: int = 1023
    max_header_bytes: int = 8192
    max_sourcetable_bytes: int = 65536
    max_capture_bytes: int = 64 * 1024 * 1024
    max_capture_seconds: float = 60.0
    allow_insecure_tls: bool = False

    def as_dict_redacted(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["password"] = "***REDACTED***" if self.password else ""
        return payload

    def validate(self) -> list[str]:
        problems: list[str] = []
        if not self.host:
            problems.append("host must be non-empty")
        if not 1 <= self.port <= 65535:
            problems.append(f"port out of range: {self.port}")
        if not self.mountpoint or self.mountpoint == "/":
            problems.append("mountpoint must be non-empty")
        if self.mountpoint.startswith("/") and len(self.mountpoint) < 2:
            problems.append("mountpoint must name a stream")
        for name in (
            "dial_timeout_s",
            "tls_timeout_s",
            "handshake_timeout_s",
            "read_timeout_s",
            "idle_timeout_s",
        ):
            if getattr(self, name) <= 0:
                problems.append(f"{name} must be > 0")
        if self.max_reconnects < 0:
            problems.append("max_reconnects must be >= 0")
        if self.reconnect_base_delay_s <= 0 or self.reconnect_max_delay_s <= 0:
            problems.append("reconnect delays must be > 0")
        if self.buffer_capacity < 1:
            problems.append("buffer_capacity must be >= 1")
        if not 1 <= self.max_frame_length <= 1023:
            problems.append("max_frame_length must be within 1..1023")
        if self.max_capture_bytes < 1:
            problems.append("max_capture_bytes must be >= 1")
        return problems


def config_from_env(env: dict[str, str]) -> NtripConfig:
    """Build configuration from environment mapping (no secrets invented)."""

    def _float(key: str, default: float) -> float:
        try:
            return float(env.get(key, str(default)))
        except ValueError:
            return default

    def _int(key: str, default: int) -> int:
        try:
            return int(float(env.get(key, str(default))))
        except ValueError:
            return default

    tls_raw = env.get("NLGCP_NTRIP_TLS", "").strip().lower()
    insecure_raw = env.get("NLGCP_NTRIP_INSECURE_TLS", "").strip().lower()
    return NtripConfig(
        host=env.get("NLGCP_NTRIP_HOST", "").strip(),
        port=_int("NLGCP_NTRIP_PORT", DEFAULT_NTRIP_PORT),
        mountpoint=env.get("NLGCP_NTRIP_MOUNTPOINT", "").strip(),
        username=env.get("NLGCP_NTRIP_USERNAME", ""),
        password=env.get("NLGCP_NTRIP_PASSWORD", ""),
        use_tls=tls_raw in ("1", "true", "yes", "on"),
        user_agent=env.get("NLGCP_NTRIP_USER_AGENT", DEFAULT_USER_AGENT),
        gga_sentence=env.get("NLGCP_NTRIP_GGA", ""),
        allow_insecure_tls=insecure_raw in ("1", "true", "yes", "on"),
    )


@dataclass(frozen=True, slots=True)
class MountpointAdmission:
    """Mountpoint admission record (fail-closed)."""

    provider: str
    caster_host: str
    caster_port: int
    mountpoint: str
    station_mapping: str
    source_table_format: str
    gnss_systems: tuple[str, ...]
    requires_nmea: bool
    authentication_mode: str
    configured_authorization: str
    admission_status: AdmissionStatus
    reason_codes: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["admission_status"] = str(self.admission_status)
        payload["gnss_systems"] = list(self.gnss_systems)
        payload["reason_codes"] = list(self.reason_codes)
        return payload


@dataclass(frozen=True, slots=True)
class StationMapping:
    """Explicit provider-mountpoint to registry-station mapping."""

    mountpoint: str
    station_id: str
    verified: bool
    reason: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ArrivalRecord:
    """Genuine network arrival timing for one frame (not a GNSS epoch)."""

    connection_id: str
    sequence: int
    arrival_monotonic_ns: int
    arrival_utc: str
    byte_offset: int
    frame_length: int
    message_number: int | None
    crc_status: str
    frame_sha256: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class LiveFrame:
    """Live correction frame; maps onto the Phase 9 CorrectionFrame."""

    sequence: int
    source_type: str
    provider: str
    station_id: str
    mountpoint: str
    message_number: int | None
    raw_bytes: bytes
    crc_status: str
    arrival_timestamp: str
    gnss_epoch: str | None
    connection_id: str
    provenance: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["raw_bytes"] = self.raw_bytes.hex()
        return payload


@dataclass(frozen=True, slots=True)
class StreamMetrics:
    """Live transport metrics (measured only, never fabricated)."""

    connections_attempted: int = 0
    connections_successful: int = 0
    authentication_failures: int = 0
    reconnects: int = 0
    bytes_received: int = 0
    frames_received: int = 0
    frames_crc_valid: int = 0
    frames_crc_invalid: int = 0
    message_type_counts: dict[str, int] = field(default_factory=dict)
    idle_events: int = 0
    capture_duration_s: float = 0.0
    buffer_high_water_mark: int = 0
    frames_dropped: int = 0
    producer_waits: int = 0
    consumer_waits: int = 0

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class CaptureMetadata:
    """Immutable capture description (never carries passwords)."""

    capture_id: str
    provider: str
    caster_host: str
    caster_port: int
    mountpoint: str
    station_mapping: str
    start_utc: str
    end_utc: str
    duration_s: float
    bytes_received: int
    valid_frames: int
    invalid_frames: int
    observed_message_types: tuple[str, ...]
    disconnects: int
    reconnects: int
    tls_mode: str
    software_commit: str
    source_table_sha256: str
    stream_sha256: str
    authorization_provenance: str
    capture_status: str

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["observed_message_types"] = list(self.observed_message_types)
        return payload
