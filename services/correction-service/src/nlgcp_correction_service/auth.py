"""Authentication and credential redaction for the Phase 12 local caster.

Uses constant-time comparisons (``hmac.compare_digest``) and reuses Phase 10
Basic-auth and redaction helpers so credentials are never logged or leaked.

SECURITY NOTE:
HTTP Basic authentication transmits base64-encoded credentials in plaintext
and is ONLY acceptable on the isolated loopback interface (127.0.0.1) during
Phase 12 laboratory integration.  It is NOT suitable for untrusted networks
without TLS transport protection and Phase 15 production identity controls.
"""

from __future__ import annotations

import base64
import binascii
import hmac
from collections.abc import Mapping
from dataclasses import dataclass

from nlgcp_ntrip_ingest.auth import (
    basic_auth_header,
    redact_headers,
    redact_text,
)

__all__ = [
    "AuthResult",
    "CredentialStore",
    "basic_auth_header",
    "parse_basic_authorization",
    "redact_headers",
    "redact_text",
]


@dataclass(frozen=True, slots=True)
class AuthResult:
    authenticated: bool
    username: str | None
    reason: str


def parse_basic_authorization(header_value: str | None) -> tuple[str, str] | None:
    """Decode an ``Authorization: Basic <b64>`` value without raising on malformed input."""
    if not header_value:
        return None
    parts = header_value.strip().split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "basic":
        return None
    token = parts[1].strip()
    if not token:
        return None
    try:
        decoded = base64.b64decode(token.encode("ascii"), validate=True).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError, ValueError):
        return None
    if ":" not in decoded:
        return None
    username, password = decoded.split(":", 1)
    if not username:
        return None
    return username, password


class CredentialStore:
    """In-memory constant-time credential verifier for local lab testing."""

    def __init__(self, credentials: Mapping[str, str]) -> None:
        self._credentials: dict[str, str] = dict(credentials)

    def verify_basic(self, authorization_header: str | None) -> AuthResult:
        """Verify an HTTP Basic Authorization header using constant-time comparison."""
        parsed = parse_basic_authorization(authorization_header)
        if parsed is None:
            return AuthResult(False, None, "missing_or_malformed_basic_auth")
        provided_user, provided_pass = parsed
        matched_user: str | None = None
        matched_pass = False
        # Iterate all configured accounts to avoid timing leaks on username lookup.
        for candidate_user, expected_pass in self._credentials.items():
            user_ok = hmac.compare_digest(
                provided_user.encode("utf-8"), candidate_user.encode("utf-8")
            )
            pass_ok = hmac.compare_digest(
                provided_pass.encode("utf-8"), expected_pass.encode("utf-8")
            )
            if user_ok and pass_ok:
                matched_user = candidate_user
                matched_pass = True
        if matched_pass and matched_user is not None:
            return AuthResult(True, matched_user, "authenticated")
        return AuthResult(False, None, "invalid_credentials")

    def verify_v1_source_password(self, password: str) -> AuthResult:
        """Verify an NTRIP v1 ``SOURCE <password> /<mount>`` password."""
        if not password or not self._credentials:
            return AuthResult(False, None, "missing_source_password")
        matched_user: str | None = None
        matched = False
        for candidate_user, expected_pass in self._credentials.items():
            if hmac.compare_digest(password.encode("utf-8"), expected_pass.encode("utf-8")):
                matched_user = candidate_user
                matched = True
        if matched and matched_user is not None:
            return AuthResult(True, matched_user, "source_authenticated")
        return AuthResult(False, None, "invalid_source_password")

    def secrets_tuple(self) -> tuple[str, ...]:
        """Return secret values for log redaction (never exposed in API responses)."""
        return tuple(self._credentials.values())
