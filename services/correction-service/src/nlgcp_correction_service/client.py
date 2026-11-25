"""Local authenticated NTRIP v2/v1 client for Phase 12 lab integration.

Reuses Phase 10 framing (``StreamingFramer``), handshake response validation
(``split_head``, ``parse_head``, ``validate_stream_response``), Basic auth
encoding/redaction, and bounded exponential backoff (``ReconnectPolicy``).

Never silently accepts corrupted CRC frames, stray/bad-preamble bytes, or
truncated trailing bytes.  Terminal HTTP errors (401/403/404) stop immediately
without retrying; transient disconnects reconnect within bounded limits.
"""

from __future__ import annotations

import logging
import socket
import threading
import time
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from typing import Any

from nlgcp_ntrip_ingest.backoff import is_terminal
from nlgcp_ntrip_ingest.framing import StreamedFrame, StreamingFramer
from nlgcp_ntrip_ingest.handshake import (
    HandshakeResult,
    parse_head,
    split_head,
    validate_stream_response,
)
from nlgcp_ntrip_ingest.models import FailureClass

from nlgcp_correction_service.auth import basic_auth_header
from nlgcp_correction_service.config import ClientConfig
from nlgcp_correction_service.diagnostics import ClientDiagnostics, StructuredEventLogger


@dataclass(frozen=True, slots=True)
class ClientReceiveResult:
    """Deterministic outcome of a local NTRIP client stream session."""

    ok: bool
    status_code: int | None
    failure: FailureClass | None
    reason: str
    valid_frames: tuple[StreamedFrame, ...]
    invalid_frames: tuple[StreamedFrame, ...]
    findings: tuple[str, ...]
    reconnection_attempts: int
    diagnostics: dict[str, Any]


def _build_client_request(config: ClientConfig, *, path: str) -> bytes:
    target = path if path.startswith("/") else "/" + path
    if config.ntrip_version == "2.0":
        lines = [
            f"GET {target} HTTP/1.1",
            f"Host: {config.host}:{config.port}",
            "Ntrip-Version: Ntrip/2.0",
            f"User-Agent: {config.user_agent}",
            "Accept: */*",
            "Connection: close",
        ]
    else:
        lines = [
            f"GET {target} HTTP/1.0",
            f"Host: {config.host}:{config.port}",
            f"User-Agent: {config.user_agent}",
            "Accept: */*",
            "Connection: close",
        ]
    if config.username or config.password:
        lines.append(f"Authorization: {basic_auth_header(config.username, config.password)}")
    return ("\r\n".join(lines) + "\r\n\r\n").encode("ascii", errors="replace")


def _read_http_head(
    sock: socket.socket, *, max_header_bytes: int
) -> tuple[bytes, bytes] | None:
    buf = bytearray()
    while True:
        split = split_head(bytes(buf), max_header_bytes=max_header_bytes)
        if split is not None:
            return split
        if len(buf) > max_header_bytes:
            return None
        chunk = sock.recv(4096)
        if not chunk:
            return None
        buf.extend(chunk)


class LocalNtripClient:
    """Loopback-only authenticated NTRIP client with bounded reconnection."""

    def __init__(
        self,
        config: ClientConfig,
        *,
        sleep_fn: Callable[[float], None] = time.sleep,
    ) -> None:
        config.validate()
        self.config = config
        self._sleep = sleep_fn
        self.diagnostics = ClientDiagnostics(
            host=config.host, port=config.port, mountpoint=config.mountpoint
        )
        self.logger = StructuredEventLogger(
            "nlgcp.correction_service.client",
            secrets=(config.password,) if config.password else (),
        )

    def fetch_sourcetable(self) -> tuple[int | None, str]:
        """Request ``GET /`` from the loopback caster and return ``(status, body)``."""
        sock = socket.create_connection(
            (self.config.host, self.config.port), timeout=self.config.connect_timeout_s
        )
        try:
            sock.settimeout(self.config.read_timeout_s)
            sock.sendall(_build_client_request(self.config, path="/"))
            raw = bytearray()
            while True:
                try:
                    chunk = sock.recv(self.config.read_chunk_bytes)
                except TimeoutError:
                    break
                if not chunk:
                    break
                raw.extend(chunk)
                if len(raw) > 262_144:
                    break
        finally:
            with suppress(OSError):
                sock.close()
        split = split_head(bytes(raw), max_header_bytes=self.config.max_header_bytes)
        if split is None:
            return (None, "")
        head, body = split
        status_line, _ = parse_head(head)
        parts = status_line.split()
        code = int(parts[1]) if len(parts) >= 2 and parts[1].isdigit() else None
        return (code, body.decode("utf-8", errors="replace"))

    def receive_frames(
        self,
        *,
        max_frames: int = 3,
        stop_event: threading.Event | None = None,
        allow_reconnect: bool = True,
    ) -> ClientReceiveResult:
        """Connect, authenticate, reconstruct frames, and reconnect cleanly if interrupted."""
        valid_frames: list[StreamedFrame] = []
        invalid_frames: list[StreamedFrame] = []
        findings: list[str] = []
        last_status: int | None = None
        last_failure: FailureClass | None = None
        last_reason = "no_attempt"
        attempts_made = 0
        reconnects = 0

        while True:
            if stop_event is not None and stop_event.is_set():
                self.diagnostics.set_state("CANCELLED")
                return ClientReceiveResult(
                    ok=len(valid_frames) >= max_frames and len(invalid_frames) == 0,
                    status_code=last_status,
                    failure=last_failure,
                    reason="cancelled",
                    valid_frames=tuple(valid_frames),
                    invalid_frames=tuple(invalid_frames),
                    findings=tuple(findings),
                    reconnection_attempts=reconnects,
                    diagnostics=self.diagnostics.snapshot(),
                )

            attempts_made += 1
            handshake, session_valid, session_invalid, session_findings, session_err = (
                self._run_single_session(
                    remaining_frames=max(0, max_frames - len(valid_frames)),
                    stop_event=stop_event,
                )
            )
            valid_frames.extend(session_valid)
            invalid_frames.extend(session_invalid)
            findings.extend(session_findings)

            if handshake is not None:
                last_status = handshake.status_code
                last_failure = handshake.failure
                last_reason = handshake.reason
            if session_err is not None:
                last_failure = session_err[0]
                last_reason = session_err[1]

            if len(valid_frames) >= max_frames:
                self.diagnostics.set_state("COMPLETED")
                return ClientReceiveResult(
                    ok=len(invalid_frames) == 0,
                    status_code=last_status,
                    failure=None if len(invalid_frames) == 0 else FailureClass.PROTOCOL_ERROR,
                    reason="target_frames_received"
                    if len(invalid_frames) == 0
                    else "crc_failures_observed",
                    valid_frames=tuple(valid_frames),
                    invalid_frames=tuple(invalid_frames),
                    findings=tuple(findings),
                    reconnection_attempts=reconnects,
                    diagnostics=self.diagnostics.snapshot(),
                )

            # Never retry terminal HTTP rejections (401/403/404) or when disabled.
            if last_failure is not None and is_terminal(last_failure):
                self.diagnostics.set_state("REJECTED")
                return ClientReceiveResult(
                    ok=False,
                    status_code=last_status,
                    failure=last_failure,
                    reason=last_reason,
                    valid_frames=tuple(valid_frames),
                    invalid_frames=tuple(invalid_frames),
                    findings=tuple(findings),
                    reconnection_attempts=reconnects,
                    diagnostics=self.diagnostics.snapshot(),
                )

            if not allow_reconnect or self.config.reconnect_policy.attempts_exhausted(
                reconnects
            ):
                self.diagnostics.set_state("DISCONNECTED")
                return ClientReceiveResult(
                    ok=False,
                    status_code=last_status,
                    failure=last_failure or FailureClass.CONNECTION_LOST,
                    reason=last_reason,
                    valid_frames=tuple(valid_frames),
                    invalid_frames=tuple(invalid_frames),
                    findings=tuple(findings),
                    reconnection_attempts=reconnects,
                    diagnostics=self.diagnostics.snapshot(),
                )

            reconnects += 1
            self.diagnostics.record_reconnect()
            delay = self.config.reconnect_policy.delay_for_attempt(reconnects)
            self.logger.emit(
                logging.INFO,
                "client_reconnecting",
                attempt=reconnects,
                delay_s=delay,
                mountpoint=self.config.mountpoint,
            )
            if stop_event is not None:
                if stop_event.wait(timeout=delay):
                    continue
            else:
                self._sleep(delay)

    def _run_single_session(
        self,
        *,
        remaining_frames: int,
        stop_event: threading.Event | None,
    ) -> tuple[
        HandshakeResult | None,
        list[StreamedFrame],
        list[StreamedFrame],
        list[str],
        tuple[FailureClass, str] | None,
    ]:
        valid: list[StreamedFrame] = []
        invalid: list[StreamedFrame] = []
        findings: list[str] = []
        sock: socket.socket | None = None
        try:
            sock = socket.create_connection(
                (self.config.host, self.config.port),
                timeout=self.config.connect_timeout_s,
            )
            sock.settimeout(self.config.read_timeout_s)
            sock.sendall(_build_client_request(self.config, path=self.config.mountpoint))
            split = _read_http_head(sock, max_header_bytes=self.config.max_header_bytes)
            if split is None:
                self.diagnostics.record_error("empty_or_malformed_handshake")
                return (
                    None,
                    valid,
                    invalid,
                    findings,
                    (FailureClass.EMPTY_RESPONSE, "empty or malformed HTTP handshake"),
                )
            head_bytes, initial_body = split
            status_line, headers = parse_head(head_bytes)
            handshake = validate_stream_response(status_line, headers, initial_body)
            if not handshake.ok:
                self.diagnostics.record_error(handshake.reason)
                return (handshake, valid, invalid, findings, None)

            self.diagnostics.set_state("CONNECTED")
            framer = StreamingFramer()

            def _consume(chunk: bytes) -> None:
                if not chunk:
                    return
                self.diagnostics.record_bytes(len(chunk))
                for frame in framer.feed(chunk):
                    if frame.crc_ok:
                        valid.append(frame)
                        self.diagnostics.record_valid_frame(frame.message_number)
                    else:
                        invalid.append(frame)
                        self.diagnostics.record_crc_failure()
                new_findings = framer.flush_findings()
                if new_findings:
                    findings.extend(new_findings)

            if initial_body:
                _consume(initial_body)

            while len(valid) < remaining_frames:
                if stop_event is not None and stop_event.is_set():
                    break
                try:
                    chunk = sock.recv(self.config.read_chunk_bytes)
                except TimeoutError:
                    self.diagnostics.record_error("read_timeout")
                    if framer.pending_bytes > 0:
                        self.diagnostics.record_truncated_trailing(framer.pending_bytes)
                        findings.append(f"TRUNCATED_TRAILING_BYTES count={framer.pending_bytes}")
                    if framer.stray_bytes > 0:
                        self.diagnostics.record_stray_bytes(framer.stray_bytes)
                    return (
                        handshake,
                        valid,
                        invalid,
                        findings,
                        (FailureClass.TIMEOUT, "read timeout waiting for RTCM frames"),
                    )
                if not chunk:
                    if framer.pending_bytes > 0:
                        self.diagnostics.record_truncated_trailing(framer.pending_bytes)
                        findings.append(f"TRUNCATED_TRAILING_BYTES count={framer.pending_bytes}")
                    if framer.stray_bytes > 0:
                        self.diagnostics.record_stray_bytes(framer.stray_bytes)
                    return (
                        handshake,
                        valid,
                        invalid,
                        findings,
                        (FailureClass.CONNECTION_LOST, "stream closed by caster"),
                    )
                _consume(chunk)

            if framer.stray_bytes > 0:
                self.diagnostics.record_stray_bytes(framer.stray_bytes)
            if framer.pending_bytes > 0:
                self.diagnostics.record_truncated_trailing(framer.pending_bytes)
                findings.append(f"TRUNCATED_TRAILING_BYTES count={framer.pending_bytes}")
            return (handshake, valid, invalid, findings, None)
        except TimeoutError:
            self.diagnostics.record_error("connect_timeout")
            return (
                None,
                valid,
                invalid,
                findings,
                (FailureClass.TIMEOUT, "connection timed out"),
            )
        except OSError as exc:
            self.diagnostics.record_error(type(exc).__name__)
            return (
                None,
                valid,
                invalid,
                findings,
                (FailureClass.CONNECTION_LOST, f"connection error: {type(exc).__name__}"),
            )
        finally:
            if sock is not None:
                with suppress(OSError):
                    sock.close()
