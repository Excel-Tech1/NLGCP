"""Versioned internal runtime event contracts and bounded NATS JetStream boundary (B-08).

Implements ADR-005 (NATS JetStream internal real-time event backbone) with:
- Versioned immutable event envelopes (``schema_version = "nlgcp.events.v1"``);
- Strict subject grammar validation (``correction.live.<STATION>``,
  ``correction.replay.<STATION>``, ``correction.decision.<STATION>``,
  ``correction.rtcm.<MOUNTPOINT>``, ``audit.security.<SERVICE>``);
- Bounded JetStream retention configuration (``max_msgs``, ``max_bytes``, ``max_age_s``)
  enforcing loopback-only defaults during laboratory integration;
- Deterministic ``BoundedEventBus`` for in-process / offline testing with explicit
  overflow accounting (never silent drops) and secret redaction;
- Honest ``probe_nats_endpoint()`` that reports ``UNAVAILABLE`` when no local NATS
  server is running rather than fabricating bus connectivity.
"""

from __future__ import annotations

import hashlib
import json
import re
import socket
import threading
from collections import deque
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from nlgcp_correction_service import LOOPBACK_HOST
from nlgcp_correction_service.auth import redact_text

EVENT_SCHEMA_VERSION = "nlgcp.events.v1"
_SUBJECT_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_ALLOWED_SUBJECT_PREFIXES = (
    "correction.live.",
    "correction.replay.",
    "correction.decision.",
    "correction.rtcm.",
    "audit.security.",
)


class EventContractError(ValueError):
    """Raised when an event envelope, subject, or JetStream config violates invariants."""


class EventType(StrEnum):
    INGESTED_FRAME = "INGESTED_FRAME"
    DECISION_MADE = "DECISION_MADE"
    RTCM_GENERATED = "RTCM_GENERATED"
    AUDIT_SECURITY = "AUDIT_SECURITY"


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def validate_subject(subject: str) -> str:
    """Validate a canonical NLGCP NATS subject name fail-closed."""
    cleaned = subject.strip()
    if not cleaned or any(ch.isspace() for ch in cleaned):
        raise EventContractError(f"invalid event subject: {subject!r}")
    if not cleaned.startswith(_ALLOWED_SUBJECT_PREFIXES):
        raise EventContractError(
            f"subject {cleaned!r} outside allowed prefixes {_ALLOWED_SUBJECT_PREFIXES}"
        )
    parts = cleaned.split(".")
    if len(parts) != 3 or not all(_SUBJECT_TOKEN_RE.match(p) for p in parts):
        raise EventContractError(
            f"subject {cleaned!r} must have exactly 3 safe dot-separated tokens"
        )
    return cleaned


@dataclass(frozen=True, slots=True)
class EventEnvelope:
    """Canonical immutable runtime event envelope (schema nlgcp.events.v1)."""

    event_id: str
    event_type: EventType
    subject: str
    producer: str
    emitted_utc: str
    data_classification: str
    operational_approved: bool
    payload: dict[str, Any]
    schema_version: str = EVENT_SCHEMA_VERSION
    payload_sha256: str = ""

    def __post_init__(self) -> None:
        validate_subject(self.subject)
        if not self.event_id or not self.producer:
            raise EventContractError("event_id and producer are required")
        if self.operational_approved:
            raise EventContractError(
                "operational_approved=True is strictly forbidden on B-08 lab event envelopes"
            )
        if self.data_classification == "OPERATIONAL_APPROVED":
            raise EventContractError(
                "OPERATIONAL_APPROVED classification is forbidden on B-08 lab event envelopes"
            )
        if not self.payload_sha256:
            canonical = json.dumps(self.payload, sort_keys=True, separators=(",", ":")).encode(
                "utf-8"
            )
            object.__setattr__(self, "payload_sha256", hashlib.sha256(canonical).hexdigest())

    def as_dict(self) -> dict[str, Any]:
        out = asdict(self)
        out["event_type"] = str(self.event_type)
        return out

    def to_json_bytes(self) -> bytes:
        return json.dumps(self.as_dict(), sort_keys=True, separators=(",", ":")).encode("utf-8")


def build_ingested_frame_event(
    *,
    event_id: str,
    station_id: str,
    origin: str,
    message_number: int,
    frame_sha256: str,
    frame_length: int,
    crc_status: str,
    provider: str,
    data_classification: str,
    arrival_utc: str | None = None,
) -> EventEnvelope:
    """Construct a versioned frame-ingestion event (live or replay)."""
    if origin not in ("live", "replay"):
        raise EventContractError(f"origin must be 'live' or 'replay', got {origin!r}")
    subject = validate_subject(f"correction.{origin}.{station_id.upper()}")
    return EventEnvelope(
        event_id=event_id,
        event_type=EventType.INGESTED_FRAME,
        subject=subject,
        producer=f"nlgcp-ingestor:{provider}",
        emitted_utc=arrival_utc or utc_now_iso(),
        data_classification=data_classification,
        operational_approved=False,
        payload={
            "station_id": station_id.upper(),
            "origin": origin,
            "provider": provider,
            "message_number": message_number,
            "frame_sha256": frame_sha256,
            "frame_length": frame_length,
            "crc_status": crc_status,
            "scientific_validity": "NOT_ASSESSED_TRANSPORT_ONLY",
        },
    )


def build_decision_event(
    *,
    event_id: str,
    station_id: str,
    decision_id: str,
    decision_fingerprint: str,
    mode: str,
    status: str,
    reason_code: str,
    data_classification: str,
) -> EventEnvelope:
    """Construct a versioned Phase 8 hybrid-decision event."""
    subject = validate_subject(f"correction.decision.{station_id.upper()}")
    return EventEnvelope(
        event_id=event_id,
        event_type=EventType.DECISION_MADE,
        subject=subject,
        producer="nlgcp-hybrid-decision-engine",
        emitted_utc=utc_now_iso(),
        data_classification=data_classification,
        operational_approved=False,
        payload={
            "station_id": station_id.upper(),
            "decision_id": decision_id,
            "decision_fingerprint": decision_fingerprint,
            "mode": mode,
            "status": status,
            "reason_code": reason_code,
        },
    )


def build_rtcm_generated_event(
    *,
    event_id: str,
    mountpoint: str,
    request_id: str,
    decision_id: str,
    message_families: tuple[str, ...],
    frame_count: int,
    stream_sha256: str,
    data_classification: str,
) -> EventEnvelope:
    """Construct a versioned Phase 11/12 RTCM generation summary event."""
    subject = validate_subject(f"correction.rtcm.{mountpoint}")
    return EventEnvelope(
        event_id=event_id,
        event_type=EventType.RTCM_GENERATED,
        subject=subject,
        producer="nlgcp-correction-service",
        emitted_utc=utc_now_iso(),
        data_classification=data_classification,
        operational_approved=False,
        payload={
            "mountpoint": mountpoint,
            "request_id": request_id,
            "decision_id": decision_id,
            "message_families": list(message_families),
            "frame_count": frame_count,
            "stream_sha256": stream_sha256,
        },
    )


def build_security_audit_event(
    *,
    event_id: str,
    service: str,
    severity: str,
    reason_code: str,
    message: str,
    secrets: tuple[str, ...] = (),
) -> EventEnvelope:
    """Construct a redacted control-plane security audit event."""
    subject = validate_subject(f"audit.security.{service}")
    return EventEnvelope(
        event_id=event_id,
        event_type=EventType.AUDIT_SECURITY,
        subject=subject,
        producer=service,
        emitted_utc=utc_now_iso(),
        data_classification="CONTROL_PLANE_AUDIT",
        operational_approved=False,
        payload={
            "service": service,
            "severity": severity,
            "reason_code": reason_code,
            "message": redact_text(message, secrets),
        },
    )


@dataclass(frozen=True, slots=True)
class NatsJetStreamConfig:
    """Bounded JetStream client & stream policy configuration (loopback-first)."""

    host: str = LOOPBACK_HOST
    port: int = 4222
    stream_name: str = "NLGCP_CORRECTIONS"
    consumer_durable: str = "nlgcp_correction_worker"
    subjects: tuple[str, ...] = (
        "correction.live.>",
        "correction.replay.>",
        "correction.decision.>",
        "correction.rtcm.>",
        "audit.security.>",
    )
    max_msgs: int = 10_000
    max_bytes: int = 16 * 1024 * 1024
    max_age_s: int = 3600
    connect_timeout_s: float = 1.5
    allow_non_loopback: bool = False

    def validate(self) -> None:
        if not self.allow_non_loopback and self.host != LOOPBACK_HOST:
            raise EventContractError(
                f"NATS host must be {LOOPBACK_HOST!r} in lab mode, got {self.host!r}"
            )
        if not 1 <= self.port <= 65535:
            raise EventContractError(f"invalid NATS port: {self.port}")
        if not _SUBJECT_TOKEN_RE.match(self.stream_name):
            raise EventContractError(f"invalid stream_name: {self.stream_name!r}")
        if not _SUBJECT_TOKEN_RE.match(self.consumer_durable):
            raise EventContractError(f"invalid consumer_durable: {self.consumer_durable!r}")
        if not 1 <= self.max_msgs <= 1_000_000:
            raise EventContractError("max_msgs must be within [1, 1_000_000]")
        if not 4096 <= self.max_bytes <= 1024 * 1024 * 1024:
            raise EventContractError("max_bytes must be within [4096, 1 GiB]")
        if not 1 <= self.max_age_s <= 86400 * 7:
            raise EventContractError("max_age_s must be within [1, 604800]")
        if self.connect_timeout_s <= 0:
            raise EventContractError("connect_timeout_s must be positive")


def probe_nats_endpoint(config: NatsJetStreamConfig) -> dict[str, Any]:
    """Read-only TCP probe to check whether a local NATS server banner is reachable.

    Never fabricates connectivity; returns explicit ``UNAVAILABLE`` if unreachable.
    """
    config.validate()
    try:
        with socket.create_connection(
            (config.host, config.port), timeout=config.connect_timeout_s
        ) as s:
            s.settimeout(config.connect_timeout_s)
            banner = s.recv(512).decode("ascii", errors="replace").strip()
            is_nats = banner.startswith("INFO ")
            return {
                "reachable": is_nats,
                "status": "AVAILABLE" if is_nats else "UNEXPECTED_BANNER",
                "host": config.host,
                "port": config.port,
                "jetstream_stream": config.stream_name,
                "banner_prefix": banner[:80],
            }
    except OSError as exc:
        return {
            "reachable": False,
            "status": "UNAVAILABLE",
            "host": config.host,
            "port": config.port,
            "jetstream_stream": config.stream_name,
            "reason": type(exc).__name__,
        }


EventHandler = Callable[[EventEnvelope], None]


@dataclass
class BoundedEventBus:
    """Thread-safe bounded in-process event bus implementing NATS subject routing.

    Used for deterministic runtime integration and testing when external NATS is
    not running, preserving bounded retention and explicit overflow accounting.
    """

    max_retained: int = 1000
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)
    _history: deque[EventEnvelope] = field(init=False, repr=False)
    _subscribers: dict[str, list[EventHandler]] = field(
        default_factory=dict, init=False, repr=False
    )
    published_total: int = field(default=0, init=False)
    evicted_total: int = field(default=0, init=False)
    handler_errors_total: int = field(default=0, init=False)

    def __post_init__(self) -> None:
        if not 1 <= self.max_retained <= 100_000:
            raise EventContractError("max_retained must be within [1, 100_000]")
        self._history = deque(maxlen=self.max_retained)

    def subscribe(self, subject_prefix: str, handler: EventHandler) -> None:
        cleaned = subject_prefix.rstrip(">").strip()
        if not cleaned:
            raise EventContractError("subject_prefix must be non-empty")
        with self._lock:
            self._subscribers.setdefault(cleaned, []).append(handler)

    def publish(self, event: EventEnvelope) -> None:
        validate_subject(event.subject)
        with self._lock:
            if len(self._history) == self._history.maxlen:
                self.evicted_total += 1
            self._history.append(event)
            self.published_total += 1
            matched: list[EventHandler] = [
                h
                for prefix, handlers in self._subscribers.items()
                if event.subject == prefix or event.subject.startswith(prefix)
                for h in handlers
            ]
        for handler in matched:
            try:
                handler(event)
            except Exception:
                with self._lock:
                    self.handler_errors_total += 1

    def recent(self, *, prefix: str | None = None, limit: int = 50) -> list[EventEnvelope]:
        with self._lock:
            items = list(self._history)
        if prefix:
            items = [e for e in items if e.subject.startswith(prefix)]
        return items[-max(1, limit) :]

    def stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "schema_version": EVENT_SCHEMA_VERSION,
                "retained": len(self._history),
                "max_retained": self.max_retained,
                "published_total": self.published_total,
                "evicted_total": self.evicted_total,
                "handler_errors_total": self.handler_errors_total,
                "subscriber_prefixes": sorted(self._subscribers),
            }
