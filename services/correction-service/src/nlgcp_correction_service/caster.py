"""Loopback-only (127.0.0.1) NTRIP v2/v1 local test caster for Phase 12.

Protocol behavior implemented and tested:
- Explicit IPv4 loopback bind (``127.0.0.1`` only; non-loopback rejected).
- NTRIP v2 (``Ntrip-Version: Ntrip/2.0``):
  - ``GET / HTTP/1.1`` -> ``HTTP/1.1 200 OK`` + ``Content-Type: gnss/sourcetable``
  - ``GET /<mountpoint> HTTP/1.1`` + Basic auth -> ``HTTP/1.1 200 OK`` +
    ``Ntrip-Version: Ntrip/2.0`` + ``Content-Type: gnss/data`` + raw RTCM frames
  - ``POST /<mountpoint> HTTP/1.1`` + Basic source auth -> validates pushed
    RTCM frames incrementally via ``StreamingFramer`` before broadcast.
- NTRIP v1 compatibility (no ``Ntrip-Version: Ntrip/2.0`` header):
  - ``GET / HTTP/1.0`` -> ``SOURCETABLE 200 OK``
  - ``GET /<mountpoint> HTTP/1.0`` + Basic auth -> ``ICY 200 OK`` + RTCM frames
  - ``SOURCE <password> /<mountpoint>`` -> ``ICY 200 OK`` or ``ERROR - Bad Password``
- Fail-closed rejections: ``400 Bad Request``, ``401 Unauthorized``,
  ``404 Not Found``, ``405 Method Not Allowed``, ``503 Service Unavailable``.

Unsupported protocol features (explicitly documented, not claimed):
- HTTP/1.1 chunked Transfer-Encoding (uses identity binary streaming);
- TLS / HTTPS termination (loopback-only lab caster);
- NMEA GGA rover position parsing / VRS routing (operational VRS blocked);
- Digest auth, OAuth, or Phase 15 production identity/entitlements.
"""

from __future__ import annotations

import logging
import queue
import select
import socket
import threading
import uuid
from contextlib import suppress
from types import TracebackType
from typing import Any

from nlgcp_ntrip_ingest.framing import StreamingFramer
from nlgcp_ntrip_ingest.handshake import parse_head, split_head
from nlgcp_rtcm_generation.handoff import CorrectionStreamArtifact
from nlgcp_rtcm_generation.models import CorrectionGenerationResult, OutputClassification

from nlgcp_correction_service import SERVICE_VERSION
from nlgcp_correction_service.auth import CredentialStore
from nlgcp_correction_service.config import CasterConfig
from nlgcp_correction_service.diagnostics import CasterDiagnostics, StructuredEventLogger
from nlgcp_correction_service.mountpoints import MountpointDefinition, MountpointRegistry
from nlgcp_correction_service.publisher import (
    ClientSubscription,
    MountpointBroker,
    PublicationError,
)
from nlgcp_correction_service.validation import ValidatedRtcmFrame


def _sendall_loop(sock: socket.socket, data: bytes) -> None:
    """Write every byte safely across partial socket writes."""
    view = memoryview(data)
    sent = 0
    total = len(data)
    while sent < total:
        n = sock.send(view[sent:])
        if n <= 0:
            raise ConnectionResetError("socket closed during send")
        sent += n


def _peer_closed(sock: socket.socket) -> bool:
    """Return True if the remote TCP peer has closed (FIN/RST)."""
    try:
        readable, _, errored = select.select([sock], [], [sock], 0.0)
    except (OSError, ValueError):
        return True
    if errored:
        return True
    if not readable:
        return False
    try:
        peek = sock.recv(1, socket.MSG_PEEK)
        return peek == b""
    except OSError:
        return True


class LocalNtripCaster:
    """Loopback-only NTRIP caster for Phase 12 synthetic laboratory integration."""

    def __init__(
        self,
        config: CasterConfig,
        *,
        registry: MountpointRegistry | None = None,
    ) -> None:
        config.validate()
        self.config = config
        self.registry = registry or MountpointRegistry(
            (MountpointDefinition(name=config.mountpoint),)
        )
        self._client_auth = CredentialStore(config.client_credentials)
        self._source_auth = CredentialStore(config.source_credentials)
        self.diagnostics = CasterDiagnostics(
            listen_host=config.host, listen_port=config.port
        )
        self.logger = StructuredEventLogger(
            "nlgcp.correction_service.caster",
            secrets=(
                *self._client_auth.secrets_tuple(),
                *self._source_auth.secrets_tuple(),
            ),
        )
        self.broker = MountpointBroker(
            self.registry,
            self.diagnostics,
            max_queue_frames=config.max_queue_frames,
        )
        self._listen_sock: socket.socket | None = None
        self._accept_thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._active_sockets_lock = threading.Lock()
        self._active_sockets: set[socket.socket] = set()
        self._worker_threads: set[threading.Thread] = set()
        self._bound_port: int = config.port

    @property
    def host(self) -> str:
        return self.config.host

    @property
    def port(self) -> int:
        return self._bound_port

    @property
    def is_running(self) -> bool:
        return self._listen_sock is not None and not self._stop_event.is_set()

    def start(self) -> tuple[str, int]:
        """Bind explicitly to 127.0.0.1 and start accepting loopback connections."""
        if self._listen_sock is not None:
            return (self.config.host, self._bound_port)
        self._stop_event.clear()
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.settimeout(0.25)
        sock.bind((self.config.host, self.config.port))
        sock.listen(min(32, self.config.max_clients * 2))
        self._bound_port = int(sock.getsockname()[1])
        self._listen_sock = sock
        self.diagnostics.set_running(self._bound_port)
        self._accept_thread = threading.Thread(
            target=self._accept_loop, name="nlgcp-caster-accept", daemon=True
        )
        self._accept_thread.start()
        self.logger.emit(
            logging.INFO,
            "caster_started",
            host=self.config.host,
            port=self._bound_port,
            mountpoints=list(self.registry.names()),
        )
        return (self.config.host, self._bound_port)

    def stop(self) -> None:
        """Stop accepting connections, close client sockets, and release listener."""
        self._stop_event.set()
        self.broker.close_all()
        sock = self._listen_sock
        self._listen_sock = None
        if sock is not None:
            with suppress(OSError):
                sock.close()
        with self._active_sockets_lock:
            sockets = list(self._active_sockets)
            threads = list(self._worker_threads)
        for conn in sockets:
            with suppress(OSError):
                conn.shutdown(socket.SHUT_RDWR)
            with suppress(OSError):
                conn.close()
        if self._accept_thread is not None and self._accept_thread.is_alive():
            self._accept_thread.join(timeout=2.0)
        self._accept_thread = None
        for thread in threads:
            if thread.is_alive() and thread is not threading.current_thread():
                thread.join(timeout=2.0)
        self.diagnostics.set_stopped()
        self.logger.emit(
            logging.INFO,
            "caster_stopped",
            host=self.config.host,
            port=self._bound_port,
        )

    def __enter__(self) -> LocalNtripCaster:
        self.start()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        del exc_type, exc_val, exc_tb
        self.stop()

    def publish_phase11_result(
        self,
        result: CorrectionGenerationResult,
        *,
        mountpoint: str | None = None,
        artifact: CorrectionStreamArtifact | None = None,
        retain_in_backlog: bool = True,
    ) -> tuple[ValidatedRtcmFrame, ...]:
        target = mountpoint or self.config.mountpoint
        return self.broker.publish_phase11_result(
            target,
            result,
            artifact=artifact,
            retain_in_backlog=retain_in_backlog,
        )

    def publish_raw_frame(
        self,
        raw_bytes: bytes,
        *,
        mountpoint: str | None = None,
        classification: OutputClassification = OutputClassification.SYNTHETIC_TEST_ONLY,
        source_id: str = "phase12-direct",
        retain_in_backlog: bool = True,
    ) -> ValidatedRtcmFrame:
        target = mountpoint or self.config.mountpoint
        return self.broker.publish_raw_frame(
            target,
            raw_bytes,
            classification=classification,
            source_id=source_id,
            retain_in_backlog=retain_in_backlog,
        )

    def disconnect_clients(self, mountpoint: str | None = None) -> None:
        """Close active client streams (useful for controlled interruption tests)."""
        if mountpoint is None:
            self.broker.close_all()
        else:
            self.broker.close_mountpoint_clients(mountpoint)

    def status_snapshot(self) -> dict[str, Any]:
        return self.diagnostics.snapshot()

    def _accept_loop(self) -> None:
        while not self._stop_event.is_set():
            sock = self._listen_sock
            if sock is None:
                return
            try:
                conn, _addr = sock.accept()
            except TimeoutError:
                continue
            except OSError:
                return
            worker = threading.Thread(
                target=self._handle_connection,
                args=(conn,),
                name="nlgcp-caster-conn",
                daemon=True,
            )
            with self._active_sockets_lock:
                self._active_sockets.add(conn)
                self._worker_threads.add(worker)
            worker.start()

    def _read_request_head(self, conn: socket.socket) -> tuple[bytes, bytes] | None:
        conn.settimeout(self.config.socket_timeout_s)
        buf = bytearray()
        while not self._stop_event.is_set():
            split = split_head(bytes(buf), max_header_bytes=self.config.max_request_bytes)
            if split is not None:
                return split
            if len(buf) > self.config.max_request_bytes:
                return None
            try:
                chunk = conn.recv(4096)
            except (TimeoutError, OSError):
                return None
            if not chunk:
                return None
            buf.extend(chunk)
        return None

    def _send_http_error(
        self, conn: socket.socket, status: str, body: str, *, extra_headers: str = ""
    ) -> None:
        encoded = body.encode("ascii", errors="replace")
        response = (
            f"HTTP/1.1 {status}\r\n"
            f"Server: NLGCP-Phase12-LabCaster/{SERVICE_VERSION}\r\n"
            f"Content-Type: text/plain\r\n"
            f"Content-Length: {len(encoded)}\r\n"
            f"{extra_headers}"
            f"Connection: close\r\n\r\n"
        ).encode("ascii") + encoded
        with suppress(OSError):
            _sendall_loop(conn, response)

    def _handle_connection(self, conn: socket.socket) -> None:
        try:
            with conn:
                split = self._read_request_head(conn)
                if split is None:
                    self.diagnostics.record_connection_error()
                    self._send_http_error(
                        conn, "400 Bad Request", "Malformed or oversized request\n"
                    )
                    return
                head_bytes, trailing_bytes = split
                request_line, raw_headers = parse_head(head_bytes)
                headers = {k.lower(): v for k, v in raw_headers.items()}
                parts = request_line.strip().split()
                if len(parts) < 2:
                    self.diagnostics.record_connection_error()
                    self._send_http_error(conn, "400 Bad Request", "Malformed request line\n")
                    return
                method = parts[0].upper()
                is_v2 = "2.0" in headers.get("ntrip-version", "")

                if method == "SOURCE":
                    self._handle_v1_source(conn, parts, trailing_bytes)
                    return
                if method == "POST":
                    self._handle_v2_source(conn, parts[1], headers, trailing_bytes)
                    return
                if method != "GET":
                    self._send_http_error(
                        conn, "405 Method Not Allowed", "Only GET, POST, and SOURCE supported\n"
                    )
                    return
                if len(parts) < 3 or not parts[2].upper().startswith("HTTP/"):
                    self.diagnostics.record_connection_error()
                    self._send_http_error(conn, "400 Bad Request", "Invalid HTTP version\n")
                    return

                path = parts[1]
                if path == "/" or path == "":
                    self._handle_sourcetable(conn, headers, is_v2=is_v2)
                    return
                self._handle_client_stream(conn, path, headers, is_v2=is_v2)
        finally:
            with self._active_sockets_lock:
                self._active_sockets.discard(conn)
                self._worker_threads.discard(threading.current_thread())

    def _handle_sourcetable(
        self, conn: socket.socket, headers: dict[str, str], *, is_v2: bool
    ) -> None:
        self.diagnostics.record_mountpoint_request("/")
        if not self.config.allow_unauthenticated_sourcetable:
            auth = self._client_auth.verify_basic(headers.get("authorization"))
            if not auth.authenticated:
                self.diagnostics.record_auth_failure()
                self._send_http_error(
                    conn,
                    "401 Unauthorized",
                    "Authentication required\n",
                    extra_headers='WWW-Authenticate: Basic realm="NLGCP-LAB"\r\n',
                )
                return
        body = self.registry.render_sourcetable(port=self._bound_port).encode("utf-8")
        if is_v2:
            head = (
                "HTTP/1.1 200 OK\r\n"
                "Ntrip-Version: Ntrip/2.0\r\n"
                f"Server: NLGCP-Phase12-LabCaster/{SERVICE_VERSION}\r\n"
                "Content-Type: gnss/sourcetable\r\n"
                f"Content-Length: {len(body)}\r\n"
                "Connection: close\r\n\r\n"
            ).encode("ascii")
        else:
            head = (
                "SOURCETABLE 200 OK\r\n"
                f"Server: NLGCP-Phase12-LabCaster/{SERVICE_VERSION}\r\n"
                "Content-Type: text/plain\r\n"
                f"Content-Length: {len(body)}\r\n"
                "Connection: close\r\n\r\n"
            ).encode("ascii")
        with suppress(OSError):
            _sendall_loop(conn, head + body)

    def _handle_client_stream(
        self, conn: socket.socket, path: str, headers: dict[str, str], *, is_v2: bool
    ) -> None:
        mount_name = path.split("?", 1)[0].lstrip("/")
        self.diagnostics.record_mountpoint_request(mount_name)

        auth = self._client_auth.verify_basic(headers.get("authorization"))
        if not auth.authenticated or auth.username is None:
            self.diagnostics.record_auth_failure()
            self.logger.emit(
                logging.WARNING,
                "client_auth_failed",
                mountpoint=mount_name,
                reason=auth.reason,
            )
            self._send_http_error(
                conn,
                "401 Unauthorized",
                "Unauthorized\n",
                extra_headers='WWW-Authenticate: Basic realm="NLGCP-LAB"\r\n',
            )
            return

        if self.registry.get(mount_name) is None:
            self.logger.emit(
                logging.WARNING,
                "unknown_mountpoint_requested",
                mountpoint=mount_name,
                username=auth.username,
            )
            self._send_http_error(conn, "404 Not Found", "Unknown mountpoint\n")
            return

        if self.diagnostics.active_clients >= self.config.max_clients:
            self.diagnostics.record_connection_error()
            self._send_http_error(
                conn, "503 Service Unavailable", "Caster client capacity reached\n"
            )
            return

        self.diagnostics.record_auth_success()
        self.diagnostics.client_connected()
        client_id = str(uuid.uuid4())
        sub: ClientSubscription | None = None
        try:
            sub = self.broker.subscribe(client_id, mount_name, auth.username)
            conn.settimeout(self.config.client_write_timeout_s)
            if is_v2:
                response_head = (
                    "HTTP/1.1 200 OK\r\n"
                    "Ntrip-Version: Ntrip/2.0\r\n"
                    f"Server: NLGCP-Phase12-LabCaster/{SERVICE_VERSION}\r\n"
                    "Content-Type: gnss/data\r\n"
                    "Cache-Control: no-store\r\n"
                    "Connection: close\r\n\r\n"
                ).encode("ascii")
            else:
                response_head = b"ICY 200 OK\r\nContent-Type: gnss/data\r\n\r\n"
            _sendall_loop(conn, response_head)
            self.logger.emit(
                logging.INFO,
                "client_connected",
                client_id=client_id,
                username=auth.username,
                mountpoint=mount_name,
                ntrip_version="2.0" if is_v2 else "1.0",
            )
            while not self._stop_event.is_set():
                try:
                    frame = sub.queue.get(timeout=0.05)
                except queue.Empty:
                    if _peer_closed(conn):
                        break
                    continue
                if frame is None:
                    break
                if _peer_closed(conn):
                    break
                _sendall_loop(conn, frame.raw_bytes)
                self.diagnostics.record_frame_transmitted(len(frame.raw_bytes))
        except (BrokenPipeError, ConnectionResetError, TimeoutError, OSError):
            self.diagnostics.record_connection_error()
        finally:
            if sub is not None:
                self.broker.unsubscribe(sub)
            self.diagnostics.client_disconnected()
            self.logger.emit(
                logging.INFO,
                "client_disconnected",
                client_id=client_id,
                mountpoint=mount_name,
            )

    def _handle_v2_source(
        self,
        conn: socket.socket,
        path: str,
        headers: dict[str, str],
        trailing_bytes: bytes,
    ) -> None:
        mount_name = path.split("?", 1)[0].lstrip("/")
        self.diagnostics.record_mountpoint_request(mount_name)
        auth = self._source_auth.verify_basic(headers.get("authorization"))
        if not auth.authenticated or auth.username is None:
            self.diagnostics.record_auth_failure()
            self._send_http_error(
                conn,
                "401 Unauthorized",
                "Source authentication failed\n",
                extra_headers='WWW-Authenticate: Basic realm="NLGCP-LAB-SOURCE"\r\n',
            )
            return
        if self.registry.get(mount_name) is None:
            self._send_http_error(conn, "404 Not Found", "Unknown source mountpoint\n")
            return
        response = (
            "HTTP/1.1 200 OK\r\n"
            "Ntrip-Version: Ntrip/2.0\r\n"
            f"Server: NLGCP-Phase12-LabCaster/{SERVICE_VERSION}\r\n"
            "Connection: close\r\n\r\n"
        ).encode("ascii")
        try:
            _sendall_loop(conn, response)
        except OSError:
            self.diagnostics.record_connection_error()
            return
        self._ingest_source_stream(
            conn, mount_name, trailing_bytes, source_id=f"ntrip-v2-source:{auth.username}"
        )

    def _handle_v1_source(
        self, conn: socket.socket, parts: list[str], trailing_bytes: bytes
    ) -> None:
        if len(parts) < 3:
            self._send_http_error(conn, "400 Bad Request", "Malformed SOURCE request\n")
            return
        password, mount_path = parts[1], parts[2]
        mount_name = mount_path.lstrip("/")
        self.diagnostics.record_mountpoint_request(mount_name)
        auth = self._source_auth.verify_v1_source_password(password)
        if not auth.authenticated or auth.username is None:
            self.diagnostics.record_auth_failure()
            with suppress(OSError):
                _sendall_loop(conn, b"ERROR - Bad Password\r\n")
            return
        if self.registry.get(mount_name) is None:
            with suppress(OSError):
                _sendall_loop(conn, b"ERROR - Bad Mountpoint\r\n")
            return
        try:
            _sendall_loop(conn, b"ICY 200 OK\r\n")
        except OSError:
            self.diagnostics.record_connection_error()
            return
        self._ingest_source_stream(
            conn, mount_name, trailing_bytes, source_id=f"ntrip-v1-source:{auth.username}"
        )

    def _ingest_source_stream(
        self,
        conn: socket.socket,
        mount_name: str,
        initial_bytes: bytes,
        *,
        source_id: str,
    ) -> None:
        framer = StreamingFramer()
        conn.settimeout(self.config.socket_timeout_s)

        def _process_chunk(chunk: bytes) -> None:
            for streamed in framer.feed(chunk):
                if not streamed.crc_ok:
                    self.diagnostics.record_crc_failure()
                    continue
                with suppress(PublicationError):
                    self.broker.publish_raw_frame(
                        mount_name,
                        streamed.raw,
                        classification=OutputClassification.SYNTHETIC_TEST_ONLY,
                        source_id=source_id,
                    )

        if initial_bytes:
            _process_chunk(initial_bytes)
        while not self._stop_event.is_set():
            try:
                chunk = conn.recv(4096)
            except TimeoutError:
                continue
            except OSError:
                self.diagnostics.record_connection_error()
                return
            if not chunk:
                return
            _process_chunk(chunk)
