"""Tests for NTRIP request formation, Basic auth, and credential redaction.

SYNTHETIC TEST DATA — NOT VALID FOR SCIENTIFIC RESULTS.
"""

from __future__ import annotations

import base64

from nlgcp_ntrip_ingest import auth
from nlgcp_ntrip_ingest.handshake import build_sourcetable_request, build_stream_request
from nlgcp_ntrip_ingest.models import NtripConfig


def _config(**overrides: object) -> NtripConfig:
    fields: dict[str, object] = {
        "host": "caster.example.invalid",
        "port": 2101,
        "mountpoint": "TEST00SYN",
        "username": "",
        "password": "",
    }
    fields.update(overrides)
    return NtripConfig(**fields)  # type: ignore[arg-type]


def test_stream_request_v2_first() -> None:
    request = build_stream_request(_config()).decode()
    assert request.startswith("GET /TEST00SYN HTTP/1.1")
    assert "Ntrip-Version: Ntrip/2.0" in request
    assert "Host: caster.example.invalid:2101" in request
    assert "Authorization:" not in request


def test_stream_request_leading_slash_normalised() -> None:
    request = build_stream_request(_config(mountpoint="/TEST00SYN")).decode()
    assert request.startswith("GET /TEST00SYN HTTP/1.1")
    assert "GET //TEST" not in request


def test_stream_request_basic_auth() -> None:
    request = build_stream_request(_config(username="user", password="s3cret")).decode()
    expected = base64.b64encode(b"user:s3cret").decode()
    assert f"Authorization: Basic {expected}" in request


def test_stream_request_gga_forwarded() -> None:
    gga = "$GPGGA,120000,0615.00,N,00323.00,E,1,08,0.9,10.0,M,,,,*00"
    request = build_stream_request(_config(gga_sentence=gga)).decode()
    assert f"Ntrip-GGA: {gga}" in request


def test_sourcetable_request_targets_root() -> None:
    request = build_sourcetable_request(_config()).decode()
    assert request.startswith("GET / HTTP/1.1")
    assert "Ntrip-Version: Ntrip/2.0" in request


def test_basic_auth_header_format() -> None:
    assert auth.basic_auth_header("u", "p") == "Basic " + base64.b64encode(b"u:p").decode()


def test_redact_url_strips_credentials() -> None:
    redacted = auth.redact_url("http://user:s3cret@caster.example.invalid:2101/TEST")
    assert "s3cret" not in redacted
    assert "user" not in redacted
    assert "caster.example.invalid" in redacted


def test_redact_text_replaces_secrets() -> None:
    redacted = auth.redact_text("login with s3cret then proceed", ("s3cret",))
    assert "s3cret" not in redacted
    assert "***REDACTED***" in redacted


def test_redact_headers_hides_authorization() -> None:
    headers = {"Authorization": "Basic dXNlcjpzM2NyZXQ=", "Host": "caster.example.invalid"}
    redacted = auth.redact_headers(headers, ("s3cret",))
    assert redacted["Authorization"] == "***REDACTED***"
    assert redacted["Host"] == "caster.example.invalid"


def test_sanitize_mapping_redacts_password_keys() -> None:
    payload = {"username": "user", "password": "s3cret", "host": "caster"}
    clean = auth.sanitize_mapping(payload)
    assert clean["password"] == "***REDACTED***"
    assert clean["username"] == "user"


def test_config_redacted_dict_never_carries_password() -> None:
    config = _config(username="user", password="s3cret")
    snapshot = config.as_dict_redacted()
    assert snapshot["password"] == "***REDACTED***"
    assert "s3cret" not in json_dumps(snapshot)


def json_dumps(payload: object) -> str:
    import json

    return json.dumps(payload, default=str)
