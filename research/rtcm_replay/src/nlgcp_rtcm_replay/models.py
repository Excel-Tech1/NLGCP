"""Typed source / frame / replay models (Phase 9).

Conventions follow Phase 8: frozen dataclasses, JSON-serialisable
``as_dict()`` payloads, machine-readable enums, and fail-closed parsing
that never silently treats unknown binary data as RTCM.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any


class SourceType(StrEnum):
    """Admissible replay source kinds. Synthetic fixtures always labelled."""

    RECORDED_RTCM = "RECORDED_RTCM"
    NTRIP_CAPTURE = "NTRIP_CAPTURE"
    SYNTHETIC_TEST_FIXTURE = "SYNTHETIC_TEST_FIXTURE"
    UNKNOWN = "UNKNOWN"


class TimingQuality(StrEnum):
    """How replay timing was reconstructed. Never invented."""

    EXACT_CAPTURE_TIMING = "EXACT_CAPTURE_TIMING"
    MESSAGE_EPOCH_DERIVED = "MESSAGE_EPOCH_DERIVED"
    APPROXIMATE = "APPROXIMATE"
    UNAVAILABLE = "UNAVAILABLE"


class AdmissionVerdict(StrEnum):
    """Fail-closed source admission outcome."""

    ACCEPT = "ACCEPT"
    WARN = "WARN"
    REJECT = "REJECT"
    BLOCKED = "BLOCKED"


class BackpressurePolicy(StrEnum):
    """Bounded-buffer behaviour when the consumer cannot keep up."""

    BLOCK = "BLOCK"
    BACKPRESSURE = "BACKPRESSURE"
    DROP_NEWEST_EXPLICIT = "DROP_NEWEST_EXPLICIT"


class CRCStatus(StrEnum):
    """Per-frame integrity outcome."""

    PASS = "PASS"
    FAIL = "FAIL"
    UNCHECKED = "UNCHECKED"


BLOCKED_MESSAGE = "RTCM REPLAY BLOCKED - SOURCE ADMISSION REQUIREMENTS NOT MET"

# Reference stations with verified coordinates on the NLGCP line
# (Phase 3 verified set plus registered Phase 2 stations).
KNOWN_STATIONS: tuple[str, ...] = (
    "ABFC00NGA",
    "BKFP00NGA",
    "EKAK00NGA",
    "FUTY00NGA",
    "MGBO00NGA",
    "PHRI00NGA",
    "ULAG00NGA",
    "UNEC00NGA",
)

# Synthetic fixture station identifiers must carry one of these prefixes
# so test data can never be mistaken for field recordings.
SYNTHETIC_STATION_PREFIXES: tuple[str, ...] = ("SYN", "TEST")

# Phase 8 handoff failure reason when no compatible replay source exists.
SELECTED_CORRECTION_SOURCE_UNAVAILABLE = "SELECTED_CORRECTION_SOURCE_UNAVAILABLE"


class AdmissionBlocked(RuntimeError):
    """Raised when a replay request would violate admission requirements."""


@dataclass(frozen=True, slots=True)
class RTCMSource:
    """Formal recorded-correction source definition (§5)."""

    source_id: str
    source_type: SourceType
    source_path: str
    station_id: str
    mountpoint: str
    start_time: str
    end_time: str
    byte_size: int
    sha256: str
    capture_method: str
    capture_provenance: str
    rtcm_version: str
    message_types: tuple[str, ...]
    timestamp_source: str
    verified: bool

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["source_type"] = str(self.source_type)
        payload["message_types"] = list(self.message_types)
        return payload

    def validate(self) -> list[str]:
        problems: list[str] = []
        if not self.source_id:
            problems.append("source_id must be non-empty")
        if not self.source_path:
            problems.append("source_path must be non-empty")
        if not self.station_id:
            problems.append("station_id must be non-empty")
        if self.byte_size < 0:
            problems.append(f"byte_size must be non-negative: {self.byte_size}")
        if self.source_type not in (
            SourceType.RECORDED_RTCM,
            SourceType.NTRIP_CAPTURE,
            SourceType.SYNTHETIC_TEST_FIXTURE,
            SourceType.UNKNOWN,
        ):
            problems.append(f"unknown source_type: {self.source_type}")
        return problems

    def assert_valid(self) -> None:
        problems = self.validate()
        if problems:
            raise AdmissionBlocked(f"{BLOCKED_MESSAGE}: {'; '.join(problems)}")


def source_from_dict(payload: dict[str, Any]) -> RTCMSource:
    """Build a source definition from JSON, failing closed on malformed input."""
    try:
        source_type = SourceType(str(payload.get("source_type", "UNKNOWN")))
    except ValueError as exc:
        raise AdmissionBlocked(
            f"{BLOCKED_MESSAGE}: unknown source_type: {exc}"
        ) from exc
    try:
        return RTCMSource(
            source_id=str(payload["source_id"]),
            source_type=source_type,
            source_path=str(payload["source_path"]),
            station_id=str(payload.get("station_id", "")),
            mountpoint=str(payload.get("mountpoint", "")),
            start_time=str(payload.get("start_time", "")),
            end_time=str(payload.get("end_time", "")),
            byte_size=int(payload.get("byte_size", -1)),
            sha256=str(payload.get("sha256", "")),
            capture_method=str(payload.get("capture_method", "")),
            capture_provenance=str(payload.get("capture_provenance", "")),
            rtcm_version=str(payload.get("rtcm_version", "")),
            message_types=tuple(str(m) for m in payload.get("message_types", [])),
            timestamp_source=str(payload.get("timestamp_source", "")),
            verified=bool(payload.get("verified", False)),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise AdmissionBlocked(
            f"{BLOCKED_MESSAGE}: malformed source definition: {exc}"
        ) from exc


@dataclass(frozen=True, slots=True)
class FrameRecord:
    """One parsed RTCM 3.x frame (§7). Raw bytes live in the source file;
    the record carries the fingerprint, never the payload."""

    offset: int
    frame_length: int
    message_number: int | None
    crc_status: CRCStatus
    raw_hash: str

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["crc_status"] = str(self.crc_status)
        return payload


@dataclass(frozen=True, slots=True)
class ReplayEvent:
    """One deterministic replay timeline entry (§10)."""

    sequence: int
    source_offset: int
    message_number: int | None
    frame_length: int
    original_timestamp: str | None
    relative_time_ms: int
    raw_hash: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class CorrectionFrame:
    """Stable downstream consumer contract (§15, Phase 10 interface).

    Later live ingestion (Phase 10) must deliver this same record so
    downstream consumers cannot tell replay apart from live transport.
    """

    sequence: int
    cycle: int
    source_id: str
    station_id: str
    mountpoint: str
    message_number: int | None
    raw_bytes: bytes
    source_timestamp: str | None
    replay_timestamp: str
    provenance: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["raw_bytes"] = self.raw_bytes.hex()
        return payload


@dataclass(frozen=True, slots=True)
class ReplayConfig:
    """Deterministic replay configuration (§11, §25-§27, §42)."""

    speed: float = 1.0
    start_sequence: int | None = None
    end_sequence: int | None = None
    start_time: str | None = None
    end_time: str | None = None
    message_filter: tuple[int, ...] = ()
    loop_cycles: int = 1
    buffer_capacity: int = 16
    backpressure_policy: BackpressurePolicy = BackpressurePolicy.BLOCK
    max_frame_length: int = 1023
    max_events: int = 100000

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["message_filter"] = list(self.message_filter)
        payload["backpressure_policy"] = str(self.backpressure_policy)
        return payload

    def validate(self) -> list[str]:
        problems: list[str] = []
        if self.speed < 0:
            problems.append(f"speed must be >= 0 (0 = max throughput): {self.speed}")
        if self.loop_cycles < 1:
            problems.append(f"loop_cycles must be >= 1: {self.loop_cycles}")
        if self.buffer_capacity < 1:
            problems.append(f"buffer_capacity must be >= 1: {self.buffer_capacity}")
        if self.max_frame_length < 1 or self.max_frame_length > 1023:
            problems.append(
                f"max_frame_length must be within 1..1023: {self.max_frame_length}"
            )
        if self.max_events < 1:
            problems.append(f"max_events must be >= 1: {self.max_events}")
        if (
            self.start_sequence is not None
            and self.end_sequence is not None
            and self.start_sequence > self.end_sequence
        ):
            problems.append("start_sequence must not exceed end_sequence")
        return problems

    def assert_valid(self) -> None:
        problems = self.validate()
        if problems:
            raise AdmissionBlocked(f"{BLOCKED_MESSAGE}: {'; '.join(problems)}")


def config_from_dict(payload: dict[str, Any]) -> ReplayConfig:
    try:
        policy = BackpressurePolicy(str(payload.get("backpressure_policy", "BLOCK")))
    except ValueError as exc:
        raise AdmissionBlocked(
            f"{BLOCKED_MESSAGE}: unknown backpressure_policy: {exc}"
        ) from exc
    try:
        return ReplayConfig(
            speed=float(payload.get("speed", 1.0)),
            start_sequence=payload.get("start_sequence"),
            end_sequence=payload.get("end_sequence"),
            start_time=payload.get("start_time"),
            end_time=payload.get("end_time"),
            message_filter=tuple(int(m) for m in payload.get("message_filter", [])),
            loop_cycles=int(payload.get("loop_cycles", 1)),
            buffer_capacity=int(payload.get("buffer_capacity", 16)),
            backpressure_policy=policy,
            max_frame_length=int(payload.get("max_frame_length", 1023)),
            max_events=int(payload.get("max_events", 100000)),
        )
    except (TypeError, ValueError) as exc:
        raise AdmissionBlocked(
            f"{BLOCKED_MESSAGE}: malformed replay config: {exc}"
        ) from exc


@dataclass(frozen=True, slots=True)
class Checkpoint:
    """Restartable replay checkpoint (§14)."""

    source_fingerprint: str
    config_fingerprint: str
    last_emitted_sequence: int
    source_byte_offset: int
    last_replay_timestamp: str
    cycle: int

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class AdmissionResult:
    """Machine-readable source admission outcome (§6)."""

    verdict: AdmissionVerdict
    findings: tuple[str, ...]
    source_fingerprint: str
    frames_discovered: int = 0
    frames_valid: int = 0

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["verdict"] = str(self.verdict)
        payload["findings"] = list(self.findings)
        return payload


@dataclass(frozen=True, slots=True)
class ReplayMetrics:
    """Stream integrity and replay metrics (§22-§23). No fake latencies:
    offline replay reports scheduling delays, never network latency."""

    frames_discovered: int = 0
    frames_valid: int = 0
    frames_invalid: int = 0
    crc_failures: int = 0
    bytes_processed: int = 0
    message_type_counts: dict[str, int] = field(default_factory=dict)
    replay_duration_ms: int = 0
    source_duration_ms: int = 0
    effective_speed: float = 0.0
    frames_emitted: int = 0
    frames_dropped: int = 0
    duplicates: int = 0
    sequence_gaps: int = 0
    checkpoint_resumes: int = 0
    producer_frames: int = 0
    consumer_frames: int = 0
    buffer_waits: int = 0
    maximum_queue_depth: int = 0
    scheduled_replay_delays_ms: list[int] = field(default_factory=list)
    consumer_processing_delays_ms: list[int] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)
