"""NTRIP v2-first HTTP handshake with v1 tolerance.

Accepted success responses: ``HTTP/1.x 200`` and ``ICY 200`` (v1
casters).  Everything else is classified fail-closed; binary parsers
must never consume HTTP error bodies as RTCM.
"""

from __future__ import annotations

from dataclasses import dataclass

from nlgcp_ntrip_ingest.auth import basic_auth_header
from nlgcp_ntrip_ingest.models import FailureClass, NtripConfig

NTRIP_V2 = "Ntrip-Version: Ntrip/2.0"


@dataclass(frozen=True, slots=True)
class HandshakeResult:
    ok: bool
    failure: FailureClass | None
    reason: str
    status_code: int | None


def build_stream_request(config: NtripConfig) -> bytes:
    """Build a GET request for the configured mountpoint (NTRIP v2 first)."""
    mount = config.mountpoint if config.mountpoint.startswith("/") else "/" + config.mountpoint
    lines = [
        f"GET {mount} HTTP/1.1",
        f"Host: {config.host}:{config.port}",
        NTRIP_V2,
        f"User-Agent: {config.user_agent}",
        "Accept: */*",
        "Connection: close",
    ]
    if config.username:
        lines.append(f"Authorization: {basic_auth_header(config.username, config.password)}")
    if config.gga_sentence:
        lines.append(f"Ntrip-GGA: {config.gga_sentence.strip()}")
    return ("\r\n".join(lines) + "\r\n\r\n").encode("ascii", errors="replace")


def build_sourcetable_request(config: NtripConfig) -> bytes:
    """Build a source-table request (``GET /`` with Ntrip-Version)."""
    lines = [
        "GET / HTTP/1.1",
        f"Host: {config.host}:{config.port}",
        NTRIP_V2,
        f"User-Agent: {config.user_agent}",
        "Accept: */*",
        "Connection: close",
    ]
    if config.username:
        lines.append(f"Authorization: {basic_auth_header(config.username, config.password)}")
    return ("\r\n".join(lines) + "\r\n\r\n").encode("ascii", errors="replace")


def parse_status_line(line: str) -> tuple[str, int | None, str]:
    """Split a status line into (protocol, code, text); code may be None."""
    parts = line.strip().split(None, 2)
    if len(parts) < 2:
        return ("", None, line.strip())
    protocol = parts[0]
    try:
        return (protocol, int(parts[1]), parts[2] if len(parts) > 2 else "")
    except ValueError:
        return (protocol, None, line.strip())


def _looks_like_sourcetable(body_prefix: bytes) -> bool:
    text = body_prefix[:512].decode("latin-1", errors="replace")
    upper = text.upper()
    return (
        text.startswith("STR;")
        or "ENDSOURCETABLE" in upper
        or text.startswith("CAS;")
        or text.startswith("NET;")
    )


def _looks_like_html(body_prefix: bytes) -> bool:
    lowered = body_prefix[:1024].decode("latin-1", errors="replace").strip().lower()
    return lowered.startswith("<html") or lowered.startswith("<!doctype")


def validate_stream_response(
    status_line: str, headers: dict[str, str], body_prefix: bytes
) -> HandshakeResult:
    """Validate a stream handshake response, failing closed on misuse."""
    if not status_line.strip():
        return HandshakeResult(False, FailureClass.EMPTY_RESPONSE, "empty status line", None)
    protocol, code, _ = parse_status_line(status_line)
    normalised = status_line.strip().upper()
    known = protocol.upper() in ("HTTP/1.0", "HTTP/1.1", "ICY")
    if not known and not normalised.startswith("ICY "):
        return HandshakeResult(
            False, FailureClass.PROTOCOL_ERROR, f"malformed status line: {status_line!r}", code
        )
    if code is None:
        return HandshakeResult(
            False, FailureClass.PROTOCOL_ERROR, f"malformed status line: {status_line!r}", None
        )
    if code == 200:
        if _looks_like_html(body_prefix):
            return HandshakeResult(
                False, FailureClass.WRONG_CONTENT, "HTML body where RTCM expected", code
            )
        if _looks_like_sourcetable(body_prefix):
            return HandshakeResult(
                False,
                FailureClass.WRONG_CONTENT,
                "source-table body where RTCM stream expected",
                code,
            )
        return HandshakeResult(True, None, "handshake_success", code)
    if code in (401, 403):
        failure = (
            FailureClass.AUTH_FAILURE if code == 401 else FailureClass.AUTHORIZATION_REJECTED
        )
        return HandshakeResult(False, failure, f"authorization rejected: {code}", code)
    if code == 404:
        return HandshakeResult(
            False, FailureClass.MOUNTPOINT_NOT_FOUND, "mountpoint not found: 404", code
        )
    return HandshakeResult(
        False, FailureClass.PROTOCOL_ERROR, f"unexpected status: {code}", code
    )


def split_head(data: bytes, max_header_bytes: int = 8192) -> tuple[bytes, bytes] | None:
    """Split raw bytes into (head, rest) at the first blank line."""
    for sep in (b"\r\n\r\n", b"\n\n"):
        index = data.find(sep)
        if index >= 0:
            head = data[:index]
            if len(head) > max_header_bytes:
                return None
            return (head, data[index + len(sep):])
    if len(data) > max_header_bytes:
        return None
    return None


def parse_head(head: bytes) -> tuple[str, dict[str, str]]:
    """Parse a response head into (status_line, headers)."""
    text = head.decode("latin-1", errors="replace")
    lines = text.splitlines()
    status = lines[0] if lines else ""
    headers: dict[str, str] = {}
    for line in lines[1:]:
        if ":" in line:
            key, value = line.split(":", 1)
            headers[key.strip()] = value.strip()
    return status, headers
