"""Credential handling: environment-only secrets with log redaction."""

from __future__ import annotations

import base64
import re

_REDACTED = "***REDACTED***"

_PASSWORD_KEYS = ("password", "passwd", "pwd", "secret", "token")


def basic_auth_header(username: str, password: str) -> str:
    """Build an NTRIP Basic authorization header value (no logging)."""
    raw = f"{username}:{password}".encode()
    return "Basic " + base64.b64encode(raw).decode("ascii")


def redact_url(url: str) -> str:
    """Redact ``user:pass@`` credentials embedded in a URL."""
    return re.sub(r"://[^/@\s]*@", "://" + _REDACTED + "@", url)


def redact_text(text: str, secrets: tuple[str, ...]) -> str:
    """Replace known secret values in free text (never prints passwords)."""
    redacted = text
    for secret in secrets:
        if secret:
            redacted = redacted.replace(secret, _REDACTED)
    redacted = re.sub(
        r"(?i)(password\s*[:=]\s*)\S+", r"\1" + _REDACTED, redacted
    )
    return redacted


def redact_headers(headers: dict[str, str], secrets: tuple[str, ...]) -> dict[str, str]:
    """Redact authorization headers and embedded secrets for logs."""
    out: dict[str, str] = {}
    for key, value in headers.items():
        if key.lower() in ("authorization", "proxy-authorization"):
            out[key] = _REDACTED
        else:
            out[key] = redact_text(value, secrets)
    return out


def is_sensitive_key(key: str) -> bool:
    lowered = key.lower()
    return any(token in lowered for token in _PASSWORD_KEYS)


def sanitize_mapping(payload: dict[str, str]) -> dict[str, str]:
    """Copy a string mapping while redacting sensitive values."""
    return {
        key: (_REDACTED if is_sensitive_key(key) else value)
        for key, value in payload.items()
    }
