"""Configuration models for the loopback-only Phase 12 NTRIP lab service.

Security invariants enforced fail-closed:
- Listening and target hosts MUST be explicit IPv4 loopback ``127.0.0.1``.
  ``0.0.0.0``, ``::``, hostnames, and external interfaces are rejected.
- No hardcoded production credentials exist in code; credentials must be
  supplied explicitly by callers or loaded from environment variables.
- Bounded connection limits, request header limits, queue sizes, timeouts,
  and retry limits prevent uncontrolled resource consumption.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field

from nlgcp_ntrip_ingest.backoff import ReconnectPolicy

from nlgcp_correction_service import DEFAULT_MOUNTPOINT, LOOPBACK_HOST

ALLOWED_NTRIP_VERSIONS = frozenset({"1.0", "2.0"})


class ConfigurationError(ValueError):
    """Raised when caster or client configuration violates safety invariants."""


def _validate_loopback_host(host: str, field_name: str) -> None:
    if host != LOOPBACK_HOST:
        raise ConfigurationError(
            f"{field_name} must be explicit loopback {LOOPBACK_HOST!r}; "
            f"public/non-loopback bind {host!r} is forbidden in Phase 12 lab mode"
        )


def _validate_port(port: int, field_name: str, *, allow_ephemeral: bool) -> None:
    minimum = 0 if allow_ephemeral else 1
    if isinstance(port, bool) or not isinstance(port, int) or not minimum <= port <= 65535:
        raise ConfigurationError(
            f"{field_name} must be an integer in [{minimum}, 65535], got {port!r}"
        )


@dataclass(frozen=True, slots=True)
class CasterConfig:
    """Configuration for the local loopback-only NTRIP test caster."""

    host: str = LOOPBACK_HOST
    port: int = 0
    mountpoint: str = DEFAULT_MOUNTPOINT
    client_credentials: dict[str, str] = field(default_factory=dict)
    source_credentials: dict[str, str] = field(default_factory=dict)
    max_clients: int = 16
    max_request_bytes: int = 8192
    max_queue_frames: int = 256
    socket_timeout_s: float = 5.0
    client_write_timeout_s: float = 5.0
    allow_unauthenticated_sourcetable: bool = True

    def validate(self) -> None:
        _validate_loopback_host(self.host, "host")
        _validate_port(self.port, "port", allow_ephemeral=True)
        if not self.mountpoint or "/" in self.mountpoint or " " in self.mountpoint:
            raise ConfigurationError(
                f"mountpoint must be a non-empty token without slashes/spaces: {self.mountpoint!r}"
            )
        if not self.client_credentials:
            raise ConfigurationError(
                "at least one client credential must be configured; "
                "unauthenticated stream access is forbidden"
            )
        for username, password in self.client_credentials.items():
            if not username or ":" in username or not password:
                raise ConfigurationError(
                    "client credentials require non-empty username (without ':') and password"
                )
        for username, password in self.source_credentials.items():
            if not username or ":" in username or not password:
                raise ConfigurationError(
                    "source credentials require non-empty username (without ':') and password"
                )
        if not 1 <= self.max_clients <= 128:
            raise ConfigurationError("max_clients must be within [1, 128]")
        if not 512 <= self.max_request_bytes <= 65536:
            raise ConfigurationError("max_request_bytes must be within [512, 65536]")
        if not 1 <= self.max_queue_frames <= 4096:
            raise ConfigurationError("max_queue_frames must be within [1, 4096]")
        if self.socket_timeout_s <= 0 or self.client_write_timeout_s <= 0:
            raise ConfigurationError("socket timeouts must be positive")

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> CasterConfig:
        """Load local lab caster configuration from environment variables."""
        source = os.environ if env is None else env
        host = source.get("NLGCP_CASTER_HOST", LOOPBACK_HOST).strip()
        port_raw = source.get("NLGCP_CASTER_PORT", "2101").strip()
        try:
            port = int(port_raw)
        except ValueError as exc:
            raise ConfigurationError(f"NLGCP_CASTER_PORT must be an integer: {port_raw!r}") from exc
        mountpoint = source.get("NLGCP_CASTER_MOUNTPOINT", DEFAULT_MOUNTPOINT).strip()
        client_user = source.get("NLGCP_CASTER_CLIENT_USER", "").strip()
        client_pass = source.get("NLGCP_CASTER_CLIENT_PASSWORD", "")
        if not client_user or not client_pass:
            raise ConfigurationError(
                "NLGCP_CASTER_CLIENT_USER and NLGCP_CASTER_CLIENT_PASSWORD must be set"
            )
        source_creds: dict[str, str] = {}
        src_user = source.get("NLGCP_CASTER_SOURCE_USER", "").strip()
        src_pass = source.get("NLGCP_CASTER_SOURCE_PASSWORD", "")
        if src_user or src_pass:
            if not src_user or not src_pass:
                raise ConfigurationError(
                    "both NLGCP_CASTER_SOURCE_USER and NLGCP_CASTER_SOURCE_PASSWORD are required"
                )
            source_creds[src_user] = src_pass
        cfg = cls(
            host=host,
            port=port,
            mountpoint=mountpoint,
            client_credentials={client_user: client_pass},
            source_credentials=source_creds,
        )
        cfg.validate()
        return cfg


@dataclass(frozen=True, slots=True)
class ClientConfig:
    """Configuration for the local loopback-only NTRIP client."""

    host: str = LOOPBACK_HOST
    port: int = 2101
    mountpoint: str = DEFAULT_MOUNTPOINT
    username: str = ""
    password: str = ""
    ntrip_version: str = "2.0"
    user_agent: str = "NTRIP NLGCP-Phase12-LabClient/0.1"
    connect_timeout_s: float = 3.0
    read_timeout_s: float = 3.0
    max_header_bytes: int = 8192
    read_chunk_bytes: int = 4096
    reconnect_policy: ReconnectPolicy = field(
        default_factory=lambda: ReconnectPolicy(
            base_delay_s=0.1, max_delay_s=2.0, max_attempts=3
        )
    )

    def validate(self) -> None:
        _validate_loopback_host(self.host, "host")
        _validate_port(self.port, "port", allow_ephemeral=False)
        if not self.mountpoint or "/" in self.mountpoint or " " in self.mountpoint:
            raise ConfigurationError(
                f"mountpoint must be a non-empty token without slashes/spaces: {self.mountpoint!r}"
            )
        if self.ntrip_version not in ALLOWED_NTRIP_VERSIONS:
            raise ConfigurationError(
                f"ntrip_version must be one of {sorted(ALLOWED_NTRIP_VERSIONS)}, "
                f"got {self.ntrip_version!r}"
            )
        if self.connect_timeout_s <= 0 or self.read_timeout_s <= 0:
            raise ConfigurationError("connect_timeout_s and read_timeout_s must be positive")
        if not 512 <= self.max_header_bytes <= 65536:
            raise ConfigurationError("max_header_bytes must be within [512, 65536]")
        if not 1 <= self.read_chunk_bytes <= 65536:
            raise ConfigurationError("read_chunk_bytes must be within [1, 65536]")
        problems = self.reconnect_policy.validate()
        if problems:
            raise ConfigurationError("invalid reconnect_policy: " + "; ".join(problems))
        if self.reconnect_policy.max_attempts > 20:
            raise ConfigurationError(
                "reconnect_policy.max_attempts must be <= 20 to prevent unbounded retry loops"
            )
