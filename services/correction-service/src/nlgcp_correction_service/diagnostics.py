"""Structured logging and separated health diagnostics for Phase 12.

Explicitly separates five health dimensions:
- SERVICE_HEALTH
- CONNECTION_HEALTH
- STREAM_HEALTH
- RTCM_FRAME_HEALTH
- SCIENTIFIC_READINESS (always NOT_VALID_SYNTHETIC_TEST_ONLY)

Never logs or exposes credentials.
"""

from __future__ import annotations

import json
import logging
import threading
from collections import deque
from datetime import UTC, datetime
from typing import Any

from nlgcp_correction_service import SCIENTIFIC_READINESS_STATUS
from nlgcp_correction_service.auth import redact_text


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


class StructuredEventLogger:
    """JSON structured logger that redacts secrets before emitting records."""

    def __init__(
        self,
        name: str = "nlgcp.correction_service",
        *,
        secrets: tuple[str, ...] = (),
    ) -> None:
        self._logger = logging.getLogger(name)
        self._secrets = tuple(s for s in secrets if s)

    def emit(self, level: int, event: str, **fields: Any) -> str:
        payload: dict[str, Any] = {
            "timestamp_utc": utc_now_iso(),
            "event": event,
            "scientific_readiness": SCIENTIFIC_READINESS_STATUS,
        }
        for key, value in fields.items():
            lowered = key.lower()
            if any(tok in lowered for tok in ("password", "secret", "token", "authorization")):
                payload[key] = "***REDACTED***"
            elif isinstance(value, str):
                payload[key] = redact_text(value, self._secrets)
            else:
                payload[key] = value
        encoded = json.dumps(payload, sort_keys=True, default=str)
        self._logger.log(level, encoded)
        return encoded


class CasterDiagnostics:
    """Thread-safe counters and five-dimension health view for the local caster."""

    def __init__(self, *, listen_host: str, listen_port: int) -> None:
        self._lock = threading.Lock()
        self.caster_status: str = "STOPPED"
        self.listen_host: str = listen_host
        self.listen_port: int = listen_port
        self.active_clients: int = 0
        self.authenticated_clients_total: int = 0
        self.failed_auth_attempts: int = 0
        self.requested_mountpoints: dict[str, int] = {}
        self.bytes_transmitted: int = 0
        self.bytes_received: int = 0
        self.rtcm_frames_transmitted: int = 0
        self.rtcm_frames_received: int = 0
        self.message_types_observed: dict[int, int] = {}
        self.crc_failures: int = 0
        self.rejected_frames: int = 0
        self.queue_overflow_drops: int = 0
        self.connection_errors: int = 0
        self.last_stream_activity_utc: str | None = None
        self._active_sessions: dict[str, dict[str, Any]] = {}
        self._recent_faults: deque[dict[str, Any]] = deque(maxlen=200)

    def set_running(self, port: int) -> None:
        with self._lock:
            self.caster_status = "RUNNING"
            self.listen_port = port

    def set_stopped(self) -> None:
        with self._lock:
            self.caster_status = "STOPPED"

    def record_mountpoint_request(self, mountpoint: str) -> None:
        with self._lock:
            self.requested_mountpoints[mountpoint] = (
                self.requested_mountpoints.get(mountpoint, 0) + 1
            )

    def record_auth_success(self) -> None:
        with self._lock:
            self.authenticated_clients_total += 1

    def record_auth_failure(self) -> None:
        with self._lock:
            self.failed_auth_attempts += 1

    def client_connected(self) -> None:
        with self._lock:
            self.active_clients += 1

    def try_acquire_client_slot(self, max_clients: int) -> bool:
        """Atomically check capacity and increment active_clients under lock."""
        with self._lock:
            if self.active_clients >= max_clients:
                return False
            self.active_clients += 1
            self.authenticated_clients_total += 1
            return True

    def client_disconnected(self) -> None:
        with self._lock:
            self.active_clients = max(0, self.active_clients - 1)

    def record_frame_received(self, message_number: int, nbytes: int) -> None:
        with self._lock:
            self.rtcm_frames_received += 1
            self.bytes_received += nbytes
            self.message_types_observed[message_number] = (
                self.message_types_observed.get(message_number, 0) + 1
            )
            self.last_stream_activity_utc = utc_now_iso()

    def record_frame_transmitted(self, nbytes: int) -> None:
        with self._lock:
            self.rtcm_frames_transmitted += 1
            self.bytes_transmitted += nbytes
            self.last_stream_activity_utc = utc_now_iso()

    def record_crc_failure(self) -> None:
        with self._lock:
            self.crc_failures += 1
            self.rejected_frames += 1

    def record_rejected_frame(self) -> None:
        with self._lock:
            self.rejected_frames += 1

    def record_queue_overflow(self) -> None:
        with self._lock:
            self.queue_overflow_drops += 1

    def record_connection_error(self) -> None:
        with self._lock:
            self.connection_errors += 1

    def register_client_session(
        self,
        *,
        client_id: str,
        mountpoint: str,
        ntrip_version: str,
    ) -> None:
        """Record a secret-free active session summary (never stores passwords)."""
        with self._lock:
            self._active_sessions[client_id] = {
                "client_id": client_id,
                "mountpoint": mountpoint,
                "ntrip_version": ntrip_version,
                "connected_utc": utc_now_iso(),
                "frames_sent": 0,
            }

    def note_client_frame_sent(self, client_id: str) -> None:
        with self._lock:
            sess = self._active_sessions.get(client_id)
            if sess is not None:
                sess["frames_sent"] = int(sess["frames_sent"]) + 1

    def unregister_client_session(self, client_id: str) -> None:
        with self._lock:
            self._active_sessions.pop(client_id, None)

    def active_sessions_snapshot(self) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(v) for v in self._active_sessions.values()]

    def record_fault_event(
        self,
        *,
        event_type: str,
        reason_code: str,
        detail: str = "",
        secrets: tuple[str, ...] = (),
    ) -> None:
        """Append a redacted fault summary into the bounded ring buffer."""
        with self._lock:
            self._recent_faults.append(
                {
                    "timestamp_utc": utc_now_iso(),
                    "event_type": event_type,
                    "reason_code": reason_code,
                    "detail": redact_text(detail, secrets),
                }
            )

    def recent_faults_snapshot(self, *, limit: int = 50) -> list[dict[str, Any]]:
        with self._lock:
            items = list(self._recent_faults)
        return items[-max(1, limit) :]

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            service_health = "HEALTHY" if self.caster_status == "RUNNING" else "STOPPED"
            if self.active_clients > 0:
                connection_health = "ACTIVE_CLIENTS"
            elif self.connection_errors > 0:
                connection_health = "DEGRADED_ERRORS_OBSERVED"
            else:
                connection_health = "IDLE"
            if self.rtcm_frames_transmitted > 0:
                stream_health = "STREAMING"
            elif self.rtcm_frames_received > 0:
                stream_health = "PUBLISHED_WAITING_CLIENTS"
            else:
                stream_health = "IDLE"
            if self.crc_failures > 0:
                frame_health = "CRC_FAILURES_OBSERVED"
            elif self.rtcm_frames_received > 0:
                frame_health = "VALID_TRANSPORT_FRAMES"
            else:
                frame_health = "NO_FRAMES"
            return {
                "caster_status": self.caster_status,
                "listen_host": self.listen_host,
                "listen_port": self.listen_port,
                "active_clients": self.active_clients,
                "authenticated_clients_total": self.authenticated_clients_total,
                "failed_auth_attempts": self.failed_auth_attempts,
                "requested_mountpoints": dict(self.requested_mountpoints),
                "bytes_transmitted": self.bytes_transmitted,
                "bytes_received": self.bytes_received,
                "rtcm_frames_transmitted": self.rtcm_frames_transmitted,
                "rtcm_frames_received": self.rtcm_frames_received,
                "message_types_observed": dict(self.message_types_observed),
                "crc_failures": self.crc_failures,
                "rejected_frames": self.rejected_frames,
                "queue_overflow_drops": self.queue_overflow_drops,
                "connection_errors": self.connection_errors,
                "last_stream_activity_utc": self.last_stream_activity_utc,
                "health": {
                    "SERVICE_HEALTH": service_health,
                    "CONNECTION_HEALTH": connection_health,
                    "STREAM_HEALTH": stream_health,
                    "RTCM_FRAME_HEALTH": frame_health,
                    "SCIENTIFIC_READINESS": SCIENTIFIC_READINESS_STATUS,
                },
            }


class ClientDiagnostics:
    """Counters and five-dimension health view for the local NTRIP client."""

    def __init__(self, *, host: str, port: int, mountpoint: str) -> None:
        self._lock = threading.Lock()
        self.host = host
        self.port = port
        self.mountpoint = mountpoint
        self.connection_state: str = "DISCONNECTED"
        self.bytes_received: int = 0
        self.rtcm_frames_received: int = 0
        self.message_types_observed: dict[int, int] = {}
        self.crc_failures: int = 0
        self.stray_bytes: int = 0
        self.truncated_trailing_bytes: int = 0
        self.connection_errors: int = 0
        self.reconnection_attempts: int = 0
        self.last_error: str | None = None
        self.last_stream_activity_utc: str | None = None

    def set_state(self, state: str) -> None:
        with self._lock:
            self.connection_state = state

    def record_bytes(self, count: int) -> None:
        with self._lock:
            self.bytes_received += count

    def record_valid_frame(self, message_number: int | None) -> None:
        with self._lock:
            self.rtcm_frames_received += 1
            if message_number is not None:
                self.message_types_observed[message_number] = (
                    self.message_types_observed.get(message_number, 0) + 1
                )
            self.last_stream_activity_utc = utc_now_iso()

    def record_crc_failure(self) -> None:
        with self._lock:
            self.crc_failures += 1

    def record_stray_bytes(self, count: int) -> None:
        with self._lock:
            self.stray_bytes += count

    def record_truncated_trailing(self, count: int) -> None:
        with self._lock:
            self.truncated_trailing_bytes += count

    def record_error(self, message: str) -> None:
        with self._lock:
            self.connection_errors += 1
            self.last_error = message

    def record_reconnect(self) -> None:
        with self._lock:
            self.reconnection_attempts += 1

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            service_health = (
                "CONNECTED" if self.connection_state == "CONNECTED" else self.connection_state
            )
            connection_health = (
                "HEALTHY"
                if self.connection_state == "CONNECTED"
                else ("ERROR" if self.connection_errors > 0 else "IDLE")
            )
            if self.rtcm_frames_received > 0:
                stream_health = "FRAMES_RECEIVED"
            elif self.bytes_received > 0:
                stream_health = "BYTES_WITHOUT_VALID_FRAMES"
            else:
                stream_health = "EMPTY"
            if self.crc_failures > 0 or self.stray_bytes > 0 or self.truncated_trailing_bytes > 0:
                frame_health = "CORRUPTION_OR_TRUNCATION_OBSERVED"
            elif self.rtcm_frames_received > 0:
                frame_health = "VALID_TRANSPORT_FRAMES"
            else:
                frame_health = "NO_FRAMES"
            return {
                "host": self.host,
                "port": self.port,
                "mountpoint": self.mountpoint,
                "connection_state": self.connection_state,
                "bytes_received": self.bytes_received,
                "rtcm_frames_received": self.rtcm_frames_received,
                "message_types_observed": dict(self.message_types_observed),
                "crc_failures": self.crc_failures,
                "stray_bytes": self.stray_bytes,
                "truncated_trailing_bytes": self.truncated_trailing_bytes,
                "connection_errors": self.connection_errors,
                "reconnection_attempts": self.reconnection_attempts,
                "last_error": self.last_error,
                "last_stream_activity_utc": self.last_stream_activity_utc,
                "health": {
                    "SERVICE_HEALTH": service_health,
                    "CONNECTION_HEALTH": connection_health,
                    "STREAM_HEALTH": stream_health,
                    "RTCM_FRAME_HEALTH": frame_health,
                    "SCIENTIFIC_READINESS": SCIENTIFIC_READINESS_STATUS,
                },
            }
