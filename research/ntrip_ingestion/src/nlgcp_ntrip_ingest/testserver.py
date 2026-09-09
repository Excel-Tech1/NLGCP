"""Deterministic local NTRIP test server (no internet required).

Simulates: valid streams, 401 auth rejection, 404 mountpoint,
source tables, chunked/split RTCM delivery, CRC corruption, stalls,
disconnects, partial frames, HTML errors, and source-table-instead-of
stream responses.  Used by the automated suite and bounded CLI pilots.
"""

from __future__ import annotations

import base64
import socket
import threading
import time
from contextlib import suppress

SOURCETABLE_BODY = (
    "CAS;127.0.0.1;2101;TEST-CASTER;Test Operator;0;NGA;0.0;0.0;Test\r\n"
    "NET;TEST-NET;Test Operator;B;N;http://example.invalid;http://example.invalid;;\r\n"
    "STR;TEST00SYN;Test Station;RTCM 3.2;1005(1),1077(1);2;GPS+GLO;TEST-NET;NGA;"
    "6.45;3.39;1;0;TestGen;None;B;N;9600;\r\n"
    "STR;OPEN00SYN;Open Station;RTCM 3.2;1005(1);2;GPS;TEST-NET;NGA;"
    "6.45;3.39;0;0;TestGen;None;N;N;9600;\r\n"
    "ENDSOURCETABLE\r\n"
)


class NtripTestServer:
    """Threaded single-connection-at-a-time fake NTRIP caster."""

    def __init__(
        self,
        scenario: str = "valid",
        *,
        stream_bytes: bytes = b"",
        username: str = "",
        password: str = "",
        mountpoint: str = "TEST00SYN",
        split_size: int = 1,
        stall_silence_s: float = 30.0,
    ) -> None:
        self.scenario = scenario
        self.stream_bytes = stream_bytes
        self.username = username
        self.password = password
        self.mountpoint = mountpoint
        self.split_size = max(1, split_size)
        self.stall_silence_s = stall_silence_s
        self.requests: list[bytes] = []
        self._sock: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self.port = 0

    def start(self) -> tuple[str, int]:
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind(("127.0.0.1", 0))
        self._sock.listen(16)
        self.port = int(self._sock.getsockname()[1])
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()
        return ("127.0.0.1", self.port)

    def stop(self) -> None:
        if self._sock is not None:
            with suppress(OSError):
                self._sock.close()
            self._sock = None

    def _serve(self) -> None:
        assert self._sock is not None
        while self._sock is not None:
            try:
                conn, _ = self._sock.accept()
            except OSError:
                return
            threading.Thread(target=self._handle, args=(conn,), daemon=True).start()

    def _read_request(self, conn: socket.socket) -> bytes:
        conn.settimeout(5.0)
        data = b""
        try:
            while b"\r\n\r\n" not in data and b"\n\n" not in data:
                chunk = conn.recv(4096)
                if not chunk:
                    break
                data += chunk
                if len(data) > 16384:
                    break
        except TimeoutError:
            pass
        return data

    def _authorized(self, request: bytes) -> bool:
        if not self.username:
            return True
        want = base64.b64encode(f"{self.username}:{self.password}".encode()).decode()
        for line in request.decode("latin-1", errors="replace").splitlines():
            if line.lower().startswith("authorization:"):
                return want in line
        return False

    def _wants_sourcetable(self, request: bytes) -> bool:
        first = request.decode("latin-1", errors="replace").splitlines()
        if not first:
            return False
        return first[0].upper().startswith("GET / ") or "GET / HTTP" in first[0].upper()

    def _send(self, conn: socket.socket, data: bytes) -> None:
        with suppress(OSError):
            conn.sendall(data)

    def _handle(self, conn: socket.socket) -> None:
        with conn:
            request = self._read_request(conn)
            self.requests.append(request)
            scenario = self.scenario
            if scenario == "empty":
                return
            if scenario == "sourcetable":
                body = SOURCETABLE_BODY.encode()
                self._send(
                    conn,
                    b"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\n"
                    + f"Content-Length: {len(body)}\r\nConnection: close\r\n\r\n".encode()
                    + body,
                )
                return
            if scenario == "notfound":
                self._send(conn, b"HTTP/1.1 404 Not Found\r\nConnection: close\r\n\r\n")
                return
            if scenario == "html":
                body = b"<html><body>caster error</body></html>"
                self._send(
                    conn,
                    b"HTTP/1.1 200 OK\r\nContent-Type: text/html\r\nConnection: close\r\n\r\n"
                    + body,
                )
                return
            if scenario == "sourcetable-instead":
                body = SOURCETABLE_BODY.encode()
                self._send(
                    conn,
                    b"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nConnection: close\r\n\r\n"
                    + body,
                )
                return
            if scenario == "auth" and not self._authorized(request):
                self._send(
                    conn,
                    b"HTTP/1.1 401 Unauthorized\r\n"
                    b"WWW-Authenticate: Basic realm=\"NTRIP\"\r\n"
                    b"Connection: close\r\n\r\n",
                )
                return
            if not self._wants_sourcetable(request):
                # Stream request: enforce mountpoint match.
                first = request.decode("latin-1", errors="replace").splitlines()
                path = first[0].split()[1] if first and len(first[0].split()) > 1 else ""
                if path.lstrip("/").upper() != self.mountpoint.upper():
                    self._send(conn, b"HTTP/1.1 404 Not Found\r\nConnection: close\r\n\r\n")
                    return
            if scenario == "auth" and self._wants_sourcetable(request) and not self._authorized(
                request
            ):
                self._send(conn, b"HTTP/1.1 401 Unauthorized\r\nConnection: close\r\n\r\n")
                return
            payload = self.stream_bytes
            if scenario == "corrupt":
                payload = self.stream_bytes  # already corrupted by caller
            header = (
                b"HTTP/1.1 200 OK\r\nContent-Type: gnss/data\r\n"
                b"Connection: close\r\n\r\n"
            )
            if scenario == "v1":
                header = (
                    b"ICY 200 OK\r\nContent-Type: gnss/data\r\n\r\n"
                )
            self._send(conn, header)
            if scenario == "stall":
                time.sleep(self.stall_silence_s)
                return
            if scenario == "partial":
                self._send(conn, payload[: max(1, len(payload) // 2)])
                return
            if scenario == "disconnect":
                # One frame then an abrupt close.
                half = payload[: max(1, len(payload) // 3)]
                self._send(conn, half)
                return
            # valid / auth / v1 / corrupt / split: chunked delivery.
            step = self.split_size if scenario == "split" else 4096
            for offset in range(0, len(payload), step):
                self._send(conn, payload[offset : offset + step])
                if scenario == "split":
                    time.sleep(0.001)
