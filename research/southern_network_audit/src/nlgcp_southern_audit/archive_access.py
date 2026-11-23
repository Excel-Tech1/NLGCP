"""Authenticated, bounded access to public GNSS broadcast-navigation archives.

Network access is isolated behind :class:`Transport` so planning, validation,
and reporting tests never require a live archive. Credentials are read only
from documented environment variables and are never written to manifests.
"""

from __future__ import annotations

import base64
import hashlib
import os
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

MAX_RESPONSE_BYTES = 64 * 1024 * 1024
RETRYABLE_HTTP_STATUS = frozenset({408, 425, 429, 500, 502, 503, 504})
HTML_MARKERS = (
    b"<!doctype html",
    b"<html",
    b"<head",
    b"<title>",
    b"<form",
)


class TransportError(RuntimeError):
    """A connection-level failure that did not produce an HTTP response."""


@dataclass(frozen=True)
class FetchResponse:
    """One transport response, including error bodies for classification."""

    status_code: int
    headers: Mapping[str, str]
    body: bytes
    final_url: str


class Transport(Protocol):
    """Minimal HTTP transport used by the downloader and its tests."""

    def fetch(
        self,
        url: str,
        headers: Mapping[str, str],
        timeout: float,
        range_start: int | None = None,
    ) -> FetchResponse: ...


@dataclass(frozen=True)
class Credentials:
    """Earthdata credentials supplied through the process environment."""

    token: str = field(default="", repr=False)
    username: str = field(default="", repr=False)
    password: str = field(default="", repr=False)

    @property
    def ready(self) -> bool:
        """Return whether a complete CDDIS authentication method is present."""
        return bool(self.token or (self.username and self.password))

    def headers(self) -> dict[str, str]:
        """Build an authorization header without logging secret values."""
        if self.token:
            return {"Authorization": f"Bearer {self.token}"}
        if self.username and self.password:
            encoded = base64.b64encode(f"{self.username}:{self.password}".encode()).decode()
            return {"Authorization": f"Basic {encoded}"}
        return {}

    @classmethod
    def from_environment(cls, env: Mapping[str, str] | None = None) -> Credentials:
        """Read documented Earthdata credential variables, if present."""
        values = os.environ if env is None else env
        token = values.get("CDDIS_TOKEN") or values.get("EARTHDATA_TOKEN") or ""
        username = values.get("CDDIS_USERNAME") or values.get("EARTHDATA_USERNAME") or ""
        password = values.get("CDDIS_PASSWORD") or values.get("EARTHDATA_PASSWORD") or ""
        return cls(token=token, username=username, password=password)


class UrllibTransport:
    """Standard-library HTTPS transport with redirect handling."""

    def __init__(self, opener: urllib.request.OpenerDirector | None = None) -> None:
        self._opener = opener or urllib.request.build_opener()

    def fetch(
        self,
        url: str,
        headers: Mapping[str, str],
        timeout: float,
        range_start: int | None = None,
    ) -> FetchResponse:
        request = urllib.request.Request(url, headers=dict(headers))
        if range_start is not None:
            request.add_header("Range", f"bytes={range_start}-")
        try:
            with self._opener.open(request, timeout=timeout) as response:
                body = response.read(MAX_RESPONSE_BYTES + 1)
                if len(body) > MAX_RESPONSE_BYTES:
                    raise TransportError("response exceeds maximum download size")
                response_headers = {
                    key.lower(): value for key, value in response.headers.items()
                }
                status = int(getattr(response, "status", 0) or 0)
                return FetchResponse(
                    status_code=status,
                    headers=response_headers,
                    body=body,
                    final_url=response.geturl(),
                )
        except urllib.error.HTTPError as exc:
            body = exc.read(MAX_RESPONSE_BYTES + 1)
            response_headers = (
                {key.lower(): value for key, value in exc.headers.items()}
                if exc.headers is not None
                else {}
            )
            return FetchResponse(
                status_code=int(exc.code),
                headers=response_headers,
                body=body,
                final_url=exc.geturl(),
            )
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise TransportError(f"{type(exc).__name__}: {exc}") from exc


@dataclass(frozen=True)
class DownloadConfig:
    """Bounded retry and size behaviour for one download run."""

    timeout_seconds: float = 60.0
    max_retries: int = 3
    retry_backoff_seconds: float = 1.0
    max_bytes: int = MAX_RESPONSE_BYTES
    user_agent: str = "NLGCP-southern-navigation-recovery/1.0"


@dataclass(frozen=True)
class DownloadRequest:
    """One archive product to fetch."""

    url: str
    filename: str
    provider: str
    requires_auth: bool
    expected_magic: tuple[bytes, ...] = ()
    applicable: bool = True
    not_applicable_reason: str = ""


@dataclass(frozen=True)
class DownloadOutcome:
    """Result of one download attempt sequence."""

    status: str
    url: str
    final_url: str = ""
    http_status: int = 0
    size_bytes: int = 0
    sha256: str = ""
    retrieved_utc: str = ""
    content_type: str = ""
    stored_path: str = ""
    error: str = ""
    cached: bool = False


def sha256_bytes(payload: bytes) -> str:
    """Return the lowercase SHA-256 digest of a payload."""
    return hashlib.sha256(payload).hexdigest()


def expected_magic_for(filename: str) -> tuple[bytes, ...]:
    """Return the documented compression signatures for a filename."""
    lower = filename.lower()
    if lower.endswith(".z"):
        return (b"\x1f\x9d",)
    if lower.endswith(".gz"):
        return (b"\x1f\x8b",)
    if lower.endswith(".rnx"):
        return ()
    return ()


def looks_like_html(payload: bytes) -> bool:
    """Detect an HTML error or login page before it can be admitted as data."""
    prefix = payload[:2048].lstrip().lower()
    return any(prefix.startswith(marker) for marker in HTML_MARKERS)


def _content_length(headers: Mapping[str, str]) -> int | None:
    value = headers.get("content-length", "").strip()
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _content_range_total(headers: Mapping[str, str]) -> int | None:
    value = headers.get("content-range", "").strip()
    if "/" not in value:
        return None
    total = value.rsplit("/", 1)[1].strip()
    if not total or total == "*":
        return None
    try:
        return int(total)
    except ValueError:
        return None


class ArchiveDownloader:
    """Download navigation products with retry, resume, and safe rejection."""

    def __init__(
        self,
        transport: Transport,
        config: DownloadConfig,
        credentials: Credentials,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._transport = transport
        self._config = config
        self._credentials = credentials
        self._now = now or (lambda: datetime.now(UTC))

    def download(self, request: DownloadRequest, dest_dir: Path) -> DownloadOutcome:
        """Download one product, returning an explicit non-success status on failure."""
        if not request.applicable:
            return self._outcome(
                "SOURCE_UNAVAILABLE",
                request,
                error=request.not_applicable_reason or "product not applicable",
            )
        if request.requires_auth and not self._credentials.ready:
            return self._outcome(
                "AUTHENTICATION_REQUIRED",
                request,
                error="CDDIS authentication credentials are not configured",
            )
        dest_dir.mkdir(parents=True, exist_ok=True)
        destination = dest_dir / request.filename
        if destination.exists() and destination.stat().st_size > 0:
            cached = self._cached(destination, request)
            if cached is not None:
                return cached
            destination.unlink()
        partial = dest_dir / f"{request.filename}.part"
        start = partial.stat().st_size if partial.exists() else 0
        last_error = ""
        http_status = 0
        for attempt in range(max(1, self._config.max_retries)):
            headers = {"User-Agent": self._config.user_agent}
            if request.requires_auth:
                headers.update(self._credentials.headers())
            try:
                response = self._transport.fetch(
                    request.url,
                    headers,
                    self._config.timeout_seconds,
                    start or None,
                )
            except TransportError as exc:
                last_error = str(exc)
                if attempt + 1 < self._config.max_retries:
                    time.sleep(self._config.retry_backoff_seconds * (attempt + 1))
                    continue
                return self._outcome("SOURCE_UNAVAILABLE", request, error=last_error)
            http_status = response.status_code
            if http_status in {401, 403}:
                return self._outcome(
                    "AUTHENTICATION_REQUIRED",
                    request,
                    http_status=http_status,
                    error=f"HTTP {http_status} from archive",
                )
            if http_status == 404:
                return self._outcome(
                    "MISSING",
                    request,
                    http_status=http_status,
                    error="HTTP 404 product not found",
                )
            if http_status in {301, 302, 303, 307, 308}:
                status = (
                    "AUTHENTICATION_REQUIRED"
                    if request.requires_auth
                    else "SOURCE_UNAVAILABLE"
                )
                return self._outcome(
                    status,
                    request,
                    http_status=http_status,
                    error="archive redirected to an unauthenticated location",
                )
            if http_status in RETRYABLE_HTTP_STATUS:
                last_error = f"HTTP {http_status}"
                if attempt + 1 < self._config.max_retries:
                    time.sleep(self._config.retry_backoff_seconds * (attempt + 1))
                    continue
                return self._outcome(
                    "SOURCE_UNAVAILABLE",
                    request,
                    http_status=http_status,
                    error=last_error,
                )
            if http_status == 416 and start:
                partial.unlink(missing_ok=True)
                start = 0
                continue
            if http_status not in {200, 206}:
                return self._outcome(
                    "SOURCE_UNAVAILABLE",
                    request,
                    http_status=http_status,
                    error=f"unexpected HTTP {http_status}",
                )
            if len(response.body) > self._config.max_bytes:
                return self._outcome(
                    "REJECTED",
                    request,
                    http_status=http_status,
                    error="payload exceeds configured maximum size",
                )
            if not response.body:
                return self._outcome(
                    "REJECTED",
                    request,
                    http_status=http_status,
                    error="empty payload",
                )
            if http_status == 206:
                if not start:
                    return self._outcome(
                        "REJECTED",
                        request,
                        http_status=http_status,
                        error="partial response without an existing partial file",
                    )
                payload = partial.read_bytes() + response.body
            else:
                payload = response.body
            if len(payload) > self._config.max_bytes:
                return self._outcome(
                    "REJECTED",
                    request,
                    http_status=http_status,
                    error="payload exceeds configured maximum size",
                )
            length = _content_length(response.headers)
            if http_status == 200 and length is not None and length != len(payload):
                return self._outcome(
                    "REJECTED",
                    request,
                    http_status=http_status,
                    error=f"content-length {length} does not match {len(payload)} bytes",
                )
            total = _content_range_total(response.headers)
            if http_status == 206 and total is not None and total != len(payload):
                return self._outcome(
                    "REJECTED",
                    request,
                    http_status=http_status,
                    error=f"content-range total {total} does not match {len(payload)} bytes",
                )
            if looks_like_html(payload):
                status = (
                    "AUTHENTICATION_REQUIRED"
                    if request.requires_auth
                    else "REJECTED"
                )
                return self._outcome(
                    status,
                    request,
                    http_status=http_status,
                    error="HTML/login/error page returned instead of navigation data",
                )
            if request.expected_magic and not any(
                payload.startswith(magic) for magic in request.expected_magic
            ):
                return self._outcome(
                    "REJECTED",
                    request,
                    http_status=http_status,
                    error="compression signature does not match filename",
                )
            partial.write_bytes(payload)
            os.replace(partial, destination)
            return DownloadOutcome(
                status="ACQUIRED",
                url=request.url,
                final_url=response.final_url,
                http_status=http_status,
                size_bytes=len(payload),
                sha256=sha256_bytes(payload),
                retrieved_utc=self._now().isoformat(),
                content_type=response.headers.get("content-type", ""),
                stored_path=str(destination),
            )
        return self._outcome("SOURCE_UNAVAILABLE", request, error=last_error)

    def _cached(self, path: Path, request: DownloadRequest) -> DownloadOutcome | None:
        payload = path.read_bytes()
        if len(payload) > self._config.max_bytes:
            return None
        if request.expected_magic and not any(
            payload.startswith(magic) for magic in request.expected_magic
        ):
            return None
        if looks_like_html(payload):
            return None
        return DownloadOutcome(
            status="CACHED",
            url=request.url,
            final_url=request.url,
            http_status=200,
            size_bytes=len(payload),
            sha256=sha256_bytes(payload),
            retrieved_utc=self._now().isoformat(),
            stored_path=str(path),
            cached=True,
        )

    def _outcome(
        self,
        status: str,
        request: DownloadRequest,
        *,
        http_status: int = 0,
        error: str = "",
    ) -> DownloadOutcome:
        return DownloadOutcome(
            status=status,
            url=request.url,
            http_status=http_status,
            retrieved_utc=self._now().isoformat(),
            error=error,
        )
