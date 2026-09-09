"""NTRIP live client: handshake, streaming, stall/reconnect, capture.

Single home for the §7 pipeline: connection admission → NTRIP
handshake → RTCM byte stream → streaming framer → CRC-24Q validation →
arrival timestamp → LiveFrame → bounded buffer/backpressure → consumer
frames + immutable capture + metrics + provenance.

Timeouts are all bounded and configurable; TLS certificates validate
by default; passwords never reach logs or capture metadata.
"""

from __future__ import annotations

import hashlib
import socket
import ssl
import time
import uuid
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from typing import Any

from nlgcp_ntrip_ingest.admission import admit_mountpoint, map_station
from nlgcp_ntrip_ingest.backoff import ReconnectPolicy, is_terminal
from nlgcp_ntrip_ingest.capture import CaptureWriter
from nlgcp_ntrip_ingest.framing import StreamingFramer
from nlgcp_ntrip_ingest.handshake import (
    build_sourcetable_request,
    build_stream_request,
    parse_head,
    split_head,
    validate_stream_response,
)
from nlgcp_ntrip_ingest.models import (
    AdmissionStatus,
    ConnectionState,
    FailureClass,
    LiveFrame,
    MountpointAdmission,
    NtripConfig,
    StreamMetrics,
)
from nlgcp_ntrip_ingest.provenance import (
    get_software_commit,
    provenance_envelope,
)
from nlgcp_ntrip_ingest.sourcetable import (
    SourceTable,
    find_stream,
    parse_sourcetable,
    stream_needs_auth,
    stream_requires_nmea,
)
from nlgcp_ntrip_ingest.timing import ArrivalRecorder, Clock, SystemClock

ConnectFn = Callable[[str, int, bool, float], socket.socket]


def default_connect(host: str, port: int, use_tls: bool, timeout_s: float) -> socket.socket:
    """Default TCP (+TLS) dial with certificate validation by default."""
    raw = socket.create_connection((host, port), timeout=timeout_s)
    if not use_tls:
        return raw
    context = ssl.create_default_context()
    return context.wrap_socket(raw, server_hostname=host)


def insecure_connect(host: str, port: int, use_tls: bool, timeout_s: float) -> socket.socket:
    """DIAGNOSTIC-ONLY plaintext/TLS dial without verification. Unsafe; never default."""
    raw = socket.create_connection((host, port), timeout=timeout_s)
    if not use_tls:
        return raw
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    return context.wrap_socket(raw, server_hostname=host)


@dataclass(slots=True)
class ProbeResult:
    ok: bool
    failure: FailureClass | None
    reason: str
    bytes_received: int
    frames_received: int
    frames_crc_valid: int
    frames_crc_invalid: int
    message_types: dict[str, int]
    duration_s: float


@dataclass(slots=True)
class CaptureResult:
    capture_dir: str
    metadata: dict[str, Any]
    metrics: dict[str, Any]
    admission: dict[str, Any]
    frames_forwarded: int
    status: str


class NtripClient:
    """Fail-closed live NTRIP client with observable lifecycle states."""

    def __init__(
        self,
        config: NtripConfig,
        *,
        provider: str = "unknown",
        station_registry: dict[str, str] | None = None,
        authorization_basis: str = "",
        clock: Clock | None = None,
        connect_fn: ConnectFn | None = None,
    ) -> None:
        self._config = config
        self._provider = provider
        self._registry = station_registry or {}
        self._authorization_basis = authorization_basis
        self._clock: Clock = clock or SystemClock()
        if connect_fn is not None:
            self._connect_fn = connect_fn
        elif config.allow_insecure_tls:
            self._connect_fn = insecure_connect
        else:
            self._connect_fn = default_connect
        self.state = ConnectionState.DISCONNECTED
        self.transitions: list[str] = []
        self._global_sequence = 0
        self._metrics = StreamMetrics()
        self._connection_id = ""
        self._set_state(ConnectionState.DISCONNECTED)

    def _set_state(self, state: ConnectionState) -> None:
        self.state = state
        self.transitions.append(state.value)

    def _dial(self) -> socket.socket:
        return self._connect_fn(
            self._config.host,
            self._config.port,
            self._config.use_tls,
            self._config.dial_timeout_s,
        )

    def _read_head(
        self, sock: socket.socket, deadline_s: float
    ) -> tuple[str, dict[str, str], bytes]:
        sock.settimeout(max(0.1, deadline_s - time.monotonic()))
        data = b""
        while True:
            try:
                chunk = sock.recv(4096)
            except TimeoutError as exc:
                raise TimeoutError("handshake timeout") from exc
            if not chunk:
                break
            data += chunk
            split = split_head(data, self._config.max_header_bytes)
            if split is not None:
                head, rest = split
                status, headers = parse_head(head)
                return status, headers, rest
            if len(data) > self._config.max_header_bytes:
                raise ValueError("response header exceeds max_header_bytes")
        status, headers = ("", {}) if not data else parse_head(data)
        return status, headers, b""

    def dry_run(self) -> dict[str, Any]:
        """Validate configuration + admission without network (never claims link)."""
        problems = self._config.validate()
        mapping = map_station(self._config.mountpoint, self._registry)
        admission = admit_mountpoint(
            provider=self._provider,
            config=self._config,
            source_table_format="not-fetched(dry-run)",
            gnss_systems=(),
            requires_nmea=False,
            needs_auth=bool(self._config.username),
            mapping=mapping,
        )
        return {
            "dry_run": True,
            "connectivity_claimed": False,
            "config_problems": problems,
            "admission": admission.as_dict(),
            "mapping": mapping.as_dict(),
        }

    def fetch_sourcetable(self) -> tuple[SourceTable, dict[str, Any]]:
        """Retrieve and parse the caster source table (bounded, safe)."""
        self._set_state(ConnectionState.CONNECTING)
        self._metrics = StreamMetrics(
            connections_attempted=self._metrics.connections_attempted + 1
        )
        sock = self._dial()
        try:
            self._set_state(ConnectionState.AUTHENTICATING)
            sock.settimeout(self._config.handshake_timeout_s)
            sock.sendall(build_sourcetable_request(self._config))
            deadline = time.monotonic() + self._config.handshake_timeout_s
            data = b""
            while time.monotonic() < deadline:
                try:
                    chunk = sock.recv(4096)
                except TimeoutError:
                    break
                if not chunk:
                    break
                data += chunk
                if len(data) > self._config.max_sourcetable_bytes + 8192:
                    break
                if b"ENDSOURCETABLE" in data:
                    break
            split = split_head(data, self._config.max_header_bytes)
            body = split[1] if split is not None else data
            body = body[: self._config.max_sourcetable_bytes]
            text = body.decode("utf-8", errors="replace")
            table = parse_sourcetable(
                text, max_bytes=self._config.max_sourcetable_bytes
            )
            self._metrics = StreamMetrics(
                connections_attempted=self._metrics.connections_attempted,
                connections_successful=self._metrics.connections_successful + 1,
                bytes_received=self._metrics.bytes_received + len(body),
            )
            self._set_state(ConnectionState.STOPPED)
            provenance = {
                "caster": f"{self._config.host}:{self._config.port}",
                "sha256": table.sha256,
                "streams": len(table.streams),
                "provider": self._provider,
            }
            return table, provenance
        finally:
            with suppress(OSError):
                sock.close()

    def _admit_for_stream(
        self, table: SourceTable | None
    ) -> tuple[MountpointAdmission, Any]:
        entry = find_stream(table, self._config.mountpoint) if table is not None else None
        mapping = map_station(self._config.mountpoint, self._registry)
        if table is None:
            return admit_mountpoint(
                provider=self._provider,
                config=self._config,
                source_table_format="unavailable",
                gnss_systems=(),
                requires_nmea=False,
                needs_auth=bool(self._config.username),
                mapping=mapping,
            ), None
        if entry is None:
            blocked = MountpointAdmission(
                provider=self._provider,
                caster_host=self._config.host,
                caster_port=self._config.port,
                mountpoint=self._config.mountpoint,
                station_mapping=mapping.station_id,
                source_table_format="NTRIP-STR",
                gnss_systems=(),
                requires_nmea=False,
                authentication_mode="unknown",
                configured_authorization="configured" if self._config.username else "anonymous",
                admission_status=AdmissionStatus.REJECT,
                reason_codes=("MOUNTPOINT_NOT_IN_SOURCE_TABLE",),
            )
            return blocked, None
        systems = tuple(s for s in entry.nav_systems.split("+") if s) or (
            entry.nav_systems.strip(),
        )
        admission = admit_mountpoint(
            provider=self._provider,
            config=self._config,
            source_table_format=entry.format or "NTRIP-STR",
            gnss_systems=tuple(systems),
            requires_nmea=stream_requires_nmea(entry),
            needs_auth=stream_needs_auth(entry),
            mapping=mapping,
        )
        return admission, entry

    def _open_stream(self) -> tuple[socket.socket, bytes]:
        sock = self._dial()
        sock.sendall(build_stream_request(self._config))
        return sock, b""

    def probe_stream(
        self, *, duration_s: float = 5.0, max_bytes: int = 65536
    ) -> ProbeResult:
        """Bounded non-invasive stream probe (never indefinite)."""
        problems = self._config.validate()
        if problems:
            return ProbeResult(False, FailureClass.CONFIG_INVALID, "; ".join(problems),
                               0, 0, 0, 0, {}, 0.0)
        mapping = map_station(self._config.mountpoint, self._registry)
        if not mapping.verified:
            pass  # probe may still run; correction use stays gated
        started = time.monotonic()
        self._set_state(ConnectionState.CONNECTING)
        framer = StreamingFramer(max_frame_length=self._config.max_frame_length)
        received = 0
        valid = 0
        invalid = 0
        types: dict[str, int] = {}
        try:
            sock = self._dial()
        except (OSError, TimeoutError) as exc:
            self._set_state(ConnectionState.BLOCKED)
            return ProbeResult(False, FailureClass.CONNECTION_LOST, f"dial failed: {exc}",
                               0, 0, 0, 0, {}, 0.0)
        try:
            self._set_state(ConnectionState.AUTHENTICATING)
            try:
                sock.sendall(build_stream_request(self._config))
                status, headers, rest = self._read_head(
                    sock, started + self._config.handshake_timeout_s
                )
            except (TimeoutError, ValueError) as exc:
                self._set_state(ConnectionState.BLOCKED)
                return ProbeResult(False, FailureClass.TIMEOUT, str(exc),
                                   0, 0, 0, 0, {}, time.monotonic() - started)
            except OSError as exc:
                self._set_state(ConnectionState.BLOCKED)
                return ProbeResult(False, FailureClass.CONNECTION_LOST, f"handshake read: {exc}",
                                   0, 0, 0, 0, {}, time.monotonic() - started)
            sock.settimeout(self._config.read_timeout_s)
            try:
                first = sock.recv(4096)
            except TimeoutError:
                self._set_state(ConnectionState.BLOCKED)
                return ProbeResult(False, FailureClass.TIMEOUT, "no stream data after handshake",
                                   0, 0, 0, 0, {}, time.monotonic() - started)
            except OSError as exc:
                self._set_state(ConnectionState.BLOCKED)
                return ProbeResult(False, FailureClass.CONNECTION_LOST, str(exc),
                                   0, 0, 0, 0, {}, time.monotonic() - started)
            body_prefix = rest + first
            check = validate_stream_response(status, headers, body_prefix)
            if not check.ok:
                self._set_state(ConnectionState.BLOCKED)
                if check.failure in (FailureClass.AUTH_FAILURE,
                                     FailureClass.AUTHORIZATION_REJECTED):
                    self._metrics = StreamMetrics(
                        connections_attempted=self._metrics.connections_attempted + 1,
                        authentication_failures=self._metrics.authentication_failures + 1,
                    )
                return ProbeResult(False, check.failure, check.reason,
                                   0, 0, 0, 0, {}, time.monotonic() - started)
            self._set_state(ConnectionState.STREAMING)
            data = body_prefix
            deadline = started + duration_s
            while time.monotonic() < deadline and received < max_bytes:
                if data:
                    chunk, data = data[:4096], data[4096:]
                else:
                    try:
                        chunk = sock.recv(4096)
                    except TimeoutError:
                        break
                    if not chunk:
                        break
                received += len(chunk)
                for sframe in framer.feed(chunk):
                    if sframe.crc_ok:
                        valid += 1
                    else:
                        invalid += 1
                    if sframe.message_number is not None:
                        key = str(sframe.message_number)
                        types[key] = types.get(key, 0) + 1
                if received >= max_bytes:
                    break
            self._set_state(ConnectionState.STOPPED)
            return ProbeResult(True, None, "probe_complete", received, valid + invalid,
                               valid, invalid, types, time.monotonic() - started)
        finally:
            with suppress(OSError):
                sock.close()

    def capture_stream(
        self,
        output_root: Any,
        *,
        capture_id: str,
        duration_s: float | None = None,
        max_bytes: int | None = None,
        source_table_text: str = "",
        source_table_sha256: str = "",
        fetch_table_first: bool = False,
    ) -> CaptureResult:
        """Run a bounded capture with reconnect, stall detection and provenance."""
        from pathlib import Path

        root = Path(output_root)
        problems = self._config.validate()
        if problems:
            raise ValueError(f"invalid configuration: {'; '.join(problems)}")
        table: SourceTable | None = None
        if fetch_table_first:
            table, _ = self.fetch_sourcetable()
            source_table_text = "\n".join(
                [f"STR;{s.mountpoint};{s.identifier}" for s in table.streams]
                + ["ENDSOURCETABLE"]
            ) or source_table_text
            source_table_sha256 = table.sha256
        admission, _entry = self._admit_for_stream(table)
        if admission.admission_status == AdmissionStatus.BLOCKED:
            self._set_state(ConnectionState.BLOCKED)
            raise PermissionError(f"capture BLOCKED: {'; '.join(admission.reason_codes)}")
        mapping = map_station(self._config.mountpoint, self._registry)
        station_id = mapping.station_id
        writer = CaptureWriter.create(
            root,
            provider=self._provider,
            mountpoint=self._config.mountpoint,
            station_id=station_id,
            capture_id=capture_id or f"live-{uuid.uuid4().hex[:8]}",
            caster_host=self._config.host,
            caster_port=self._config.port,
            tls_mode="tls" if self._config.use_tls else "plain",
            authorization_provenance=self._authorization_basis or "anonymous",
            software_commit=get_software_commit(),
            source_table_sha256=source_table_sha256 or hashlib.sha256(
                source_table_text.encode()
            ).hexdigest(),
            source_table_text=source_table_text,
        )
        policy = ReconnectPolicy(
            base_delay_s=self._config.reconnect_base_delay_s,
            max_delay_s=self._config.reconnect_max_delay_s,
            max_attempts=self._config.max_reconnects,
        )
        # Bounded buffer/backpressure: BLOCK by default (never silent loss);
        # an explicit DROP mode counts every dropped frame.
        from nlgcp_rtcm_replay.buffer import BoundedBuffer
        from nlgcp_rtcm_replay.models import BackpressurePolicy

        buffer: BoundedBuffer[LiveFrame] = BoundedBuffer(
            self._config.buffer_capacity, policy=BackpressurePolicy.BLOCK
        )
        forwarded = 0
        attempts = 0
        budget_s = duration_s if duration_s is not None else self._config.max_capture_seconds
        budget_b = max_bytes if max_bytes is not None else self._config.max_capture_bytes
        capture_start = time.monotonic()
        reconnects = 0
        final_status = "COMPLETE"
        idle_events = 0
        while True:
            if time.monotonic() - capture_start >= budget_s or writer.bytes_received >= budget_b:
                break
            attempts += 1
            self._connection_id = f"conn-{uuid.uuid4().hex[:8]}"
            recorder = ArrivalRecorder(self._connection_id, self._clock)
            self._set_state(ConnectionState.CONNECTING)
            self._metrics = StreamMetrics(
                connections_attempted=self._metrics.connections_attempted + 1,
                connections_successful=self._metrics.connections_successful,
                authentication_failures=self._metrics.authentication_failures,
                reconnects=reconnects,
                bytes_received=self._metrics.bytes_received,
                frames_received=self._metrics.frames_received,
                frames_crc_valid=self._metrics.frames_crc_valid,
                frames_crc_invalid=self._metrics.frames_crc_invalid,
                message_type_counts=dict(self._metrics.message_type_counts),
                idle_events=idle_events,
                capture_duration_s=self._metrics.capture_duration_s,
                buffer_high_water_mark=self._metrics.buffer_high_water_mark,
                frames_dropped=self._metrics.frames_dropped,
                producer_waits=self._metrics.producer_waits,
                consumer_waits=self._metrics.consumer_waits,
            )
            try:
                sock = self._dial()
            except (OSError, TimeoutError):
                self._set_state(ConnectionState.RECONNECTING)
                if policy.attempts_exhausted(attempts):
                    final_status = "FAILED"
                    break
                time.sleep(policy.delay_for_attempt(attempts))
                reconnects += 1
                writer.note_reconnect()
                continue
            try:
                self._set_state(ConnectionState.AUTHENTICATING)
                sock.sendall(build_stream_request(self._config))
                try:
                    status, headers, rest = self._read_head(
                        sock, time.monotonic() + self._config.handshake_timeout_s
                    )
                except (TimeoutError, ValueError):
                    self._set_state(ConnectionState.RECONNECTING)
                    if policy.attempts_exhausted(attempts):
                        final_status = "FAILED"
                        break
                    time.sleep(policy.delay_for_attempt(attempts))
                    reconnects += 1
                    writer.note_reconnect()
                    continue
                sock.settimeout(self._config.read_timeout_s)
                try:
                    first = sock.recv(4096)
                except TimeoutError:
                    self._set_state(ConnectionState.RECONNECTING)
                    idle_events += 1
                    if policy.attempts_exhausted(attempts):
                        final_status = "PARTIAL" if writer.bytes_received else "FAILED"
                        break
                    time.sleep(policy.delay_for_attempt(attempts))
                    reconnects += 1
                    writer.note_reconnect()
                    continue
                check = validate_stream_response(status, headers, rest + first)
                if not check.ok:
                    if check.failure is not None and is_terminal(check.failure):
                        self._set_state(ConnectionState.BLOCKED)
                        final_status = "PARTIAL" if writer.bytes_received else "FAILED"
                        if check.failure in (FailureClass.AUTH_FAILURE,
                                             FailureClass.AUTHORIZATION_REJECTED):
                            self._metrics = StreamMetrics(
                                connections_attempted=self._metrics.connections_attempted,
                                authentication_failures=self._metrics.authentication_failures + 1,
                            )
                        break
                    self._set_state(ConnectionState.RECONNECTING)
                    if policy.attempts_exhausted(attempts):
                        final_status = "PARTIAL" if writer.bytes_received else "FAILED"
                        break
                    time.sleep(policy.delay_for_attempt(attempts))
                    reconnects += 1
                    writer.note_reconnect()
                    continue
                self._set_state(ConnectionState.STREAMING)
                self._metrics = StreamMetrics(
                    connections_attempted=self._metrics.connections_attempted,
                    connections_successful=self._metrics.connections_successful + 1,
                    authentication_failures=self._metrics.authentication_failures,
                    reconnects=reconnects,
                    bytes_received=self._metrics.bytes_received,
                    frames_received=self._metrics.frames_received,
                    frames_crc_valid=self._metrics.frames_crc_valid,
                    frames_crc_invalid=self._metrics.frames_crc_invalid,
                    message_type_counts=dict(self._metrics.message_type_counts),
                    idle_events=idle_events,
                    capture_duration_s=self._metrics.capture_duration_s,
                    buffer_high_water_mark=self._metrics.buffer_high_water_mark,
                    frames_dropped=self._metrics.frames_dropped,
                    producer_waits=self._metrics.producer_waits,
                    consumer_waits=self._metrics.consumer_waits,
                )
                framer = StreamingFramer(max_frame_length=self._config.max_frame_length)
                data = rest + first
                last_byte = time.monotonic()
                stalled = False
                while True:
                    if time.monotonic() - capture_start >= budget_s:
                        break
                    if writer.bytes_received >= budget_b:
                        break
                    if time.monotonic() - last_byte > self._config.idle_timeout_s:
                        idle_events += 1
                        self._set_state(ConnectionState.RECONNECTING)
                        stalled = True
                        break
                    if data:
                        chunk, data = data[:4096], data[4096:]
                    else:
                        try:
                            chunk = sock.recv(4096)
                        except TimeoutError:
                            continue
                        if not chunk:
                            break  # clean EOF: reconnect (transient)
                    if chunk:
                        last_byte = time.monotonic()
                    for sframe in framer.feed(chunk):
                        crc_status = "PASS" if sframe.crc_ok else "FAIL"
                        arrival = recorder.next(
                            byte_offset=sframe.byte_offset,
                            frame_length=len(sframe.raw),
                            message_number=sframe.message_number,
                            crc_status=crc_status,
                            frame_sha256=sframe.frame_sha256,
                        )
                        # Global capture sequence continues across reconnects;
                        # connection-local sequence restarts per connection.
                        arrival = _with_global_sequence(arrival, self._global_sequence)
                        self._global_sequence += 1
                        writer.write_frame(sframe.raw, arrival)
                        counts = dict(self._metrics.message_type_counts)
                        if sframe.message_number is not None:
                            key = str(sframe.message_number)
                            counts[key] = counts.get(key, 0) + 1
                        self._metrics = StreamMetrics(
                            connections_attempted=self._metrics.connections_attempted,
                            connections_successful=self._metrics.connections_successful,
                            authentication_failures=self._metrics.authentication_failures,
                            reconnects=reconnects,
                            bytes_received=self._metrics.bytes_received + len(sframe.raw),
                            frames_received=self._metrics.frames_received + 1,
                            frames_crc_valid=self._metrics.frames_crc_valid
                            + (1 if sframe.crc_ok else 0),
                            frames_crc_invalid=self._metrics.frames_crc_invalid
                            + (0 if sframe.crc_ok else 1),
                            message_type_counts=counts,
                            idle_events=idle_events,
                            capture_duration_s=self._metrics.capture_duration_s,
                            buffer_high_water_mark=self._metrics.buffer_high_water_mark,
                            frames_dropped=self._metrics.frames_dropped,
                            producer_waits=self._metrics.producer_waits,
                            consumer_waits=self._metrics.consumer_waits,
                        )
                        if not sframe.crc_ok:
                            continue  # quarantine: captured + indexed, never forwarded
                        live = LiveFrame(
                            sequence=arrival.sequence,
                            source_type="LIVE_NTRIP",
                            provider=self._provider,
                            station_id=station_id,
                            mountpoint=self._config.mountpoint,
                            message_number=sframe.message_number,
                            raw_bytes=sframe.raw,
                            crc_status="PASS",
                            arrival_timestamp=arrival.arrival_utc,
                            gnss_epoch=None,
                            connection_id=self._connection_id,
                            provenance=provenance_envelope(
                                capture_id=capture_id,
                                provider=self._provider,
                                authorization_basis=self._authorization_basis or "anonymous",
                                config=self._config,
                                admission_status=admission.admission_status.value,
                            ),
                        )
                        if not buffer.try_put(live):
                            # BLOCK/BACKPRESSURE: drain one to the consumer
                            # path (counted wait) then insert; DROP policies
                            # count the drop explicitly. Never silent loss.
                            if buffer.policy.value == "DROP_NEWEST_EXPLICIT":
                                buffer.dropped_frames += 1
                            else:
                                buffer.buffer_waits += 1
                                drained = buffer.take()
                                if drained is not None:
                                    forwarded += 1
                                buffer.force_put(live)
                        if buffer.occupancy > self._metrics.buffer_high_water_mark:
                            self._metrics = StreamMetrics(
                                connections_attempted=self._metrics.connections_attempted,
                                connections_successful=self._metrics.connections_successful,
                                authentication_failures=self._metrics.authentication_failures,
                                reconnects=self._metrics.reconnects,
                                bytes_received=self._metrics.bytes_received,
                                frames_received=self._metrics.frames_received,
                                frames_crc_valid=self._metrics.frames_crc_valid,
                                frames_crc_invalid=self._metrics.frames_crc_invalid,
                                message_type_counts=dict(self._metrics.message_type_counts),
                                idle_events=self._metrics.idle_events,
                                capture_duration_s=self._metrics.capture_duration_s,
                                buffer_high_water_mark=buffer.occupancy,
                                frames_dropped=self._metrics.frames_dropped,
                                producer_waits=self._metrics.producer_waits,
                                consumer_waits=self._metrics.consumer_waits,
                            )
                # EOF or stall: transient → reconnect within budget.
                if (
                    time.monotonic() - capture_start >= budget_s
                    or writer.bytes_received >= budget_b
                ):
                    break
                if policy.attempts_exhausted(attempts):
                    if stalled or writer.bytes_received == 0:
                        final_status = "PARTIAL" if writer.bytes_received else "FAILED"
                    break
                self._set_state(ConnectionState.RECONNECTING)
                time.sleep(policy.delay_for_attempt(attempts))
                reconnects += 1
                writer.note_reconnect()
                continue
            finally:
                with suppress(OSError):
                    sock.close()
            break
        self._metrics = StreamMetrics(
            connections_attempted=self._metrics.connections_attempted,
            connections_successful=self._metrics.connections_successful,
            authentication_failures=self._metrics.authentication_failures,
            reconnects=reconnects,
            bytes_received=self._metrics.bytes_received,
            frames_received=self._metrics.frames_received,
            frames_crc_valid=self._metrics.frames_crc_valid,
            frames_crc_invalid=self._metrics.frames_crc_invalid,
            message_type_counts=dict(self._metrics.message_type_counts),
            idle_events=idle_events,
            capture_duration_s=time.monotonic() - capture_start,
            buffer_high_water_mark=max(
                self._metrics.buffer_high_water_mark, buffer.high_water_mark
            ),
            frames_dropped=buffer.dropped_frames,
            producer_waits=buffer.buffer_waits,
            consumer_waits=self._metrics.consumer_waits,
        )
        # Drain remaining buffered frames to the counted consumer path.
        while buffer.take() is not None:
            forwarded += 1
        self._set_state(ConnectionState.STOPPED)
        metadata = writer.close(final_status)
        return CaptureResult(
            capture_dir=str(writer.capture_dir),
            metadata=metadata.as_dict(),
            metrics=self._metrics.as_dict(),
            admission=admission.as_dict(),
            frames_forwarded=forwarded,
            status=final_status,
        )


def _with_global_sequence(arrival: Any, global_sequence: int) -> Any:
    """Re-stamp an arrival record with the global capture sequence."""
    from nlgcp_ntrip_ingest.models import ArrivalRecord

    return ArrivalRecord(
        connection_id=arrival.connection_id,
        sequence=global_sequence,
        arrival_monotonic_ns=arrival.arrival_monotonic_ns,
        arrival_utc=arrival.arrival_utc,
        byte_offset=arrival.byte_offset,
        frame_length=arrival.frame_length,
        message_number=arrival.message_number,
        crc_status=arrival.crc_status,
        frame_sha256=arrival.frame_sha256,
    )
