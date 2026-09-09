"""Tests for handshake validation and mountpoint admission/station mapping.

SYNTHETIC TEST DATA — NOT VALID FOR SCIENTIFIC RESULTS.
"""

from __future__ import annotations

from nlgcp_ntrip_ingest.admission import admit_mountpoint, map_station
from nlgcp_ntrip_ingest.handshake import (
    parse_head,
    parse_status_line,
    split_head,
    validate_stream_response,
)
from nlgcp_ntrip_ingest.models import (
    STATION_IDENTITY_UNVERIFIED,
    AdmissionStatus,
    FailureClass,
    NtripConfig,
)


def test_accept_http200_v2() -> None:
    result = validate_stream_response("HTTP/1.1 200 OK", {}, b"\xd3\x00\x05hello")
    assert result.ok and result.failure is None and result.status_code == 200


def test_accept_icy200_v1_tolerance() -> None:
    result = validate_stream_response("ICY 200 OK", {}, b"\xd3\x00\x05hello")
    assert result.ok


def test_reject_401_terminal() -> None:
    result = validate_stream_response("HTTP/1.1 401 Unauthorized", {}, b"")
    assert not result.ok and result.failure == FailureClass.AUTH_FAILURE


def test_reject_403_terminal() -> None:
    result = validate_stream_response("HTTP/1.1 403 Forbidden", {}, b"")
    assert not result.ok and result.failure == FailureClass.AUTHORIZATION_REJECTED


def test_reject_404_terminal() -> None:
    result = validate_stream_response("HTTP/1.1 404 Not Found", {}, b"")
    assert not result.ok and result.failure == FailureClass.MOUNTPOINT_NOT_FOUND


def test_reject_html_body() -> None:
    result = validate_stream_response(
        "HTTP/1.1 200 OK", {"Content-Type": "text/html"}, b"<html><body>oops</body></html>"
    )
    assert not result.ok and result.failure == FailureClass.WRONG_CONTENT


def test_reject_sourcetable_when_stream_expected() -> None:
    result = validate_stream_response(
        "HTTP/1.1 200 OK", {}, b"STR;TEST;id;RTCM 3.2\r\nENDSOURCETABLE\r\n"
    )
    assert not result.ok and result.failure == FailureClass.WRONG_CONTENT


def test_reject_empty_response() -> None:
    result = validate_stream_response("", {}, b"")
    assert not result.ok and result.failure == FailureClass.EMPTY_RESPONSE


def test_reject_malformed_status_line() -> None:
    result = validate_stream_response("GARBAGE-NO-CODE", {}, b"")
    assert not result.ok and result.failure == FailureClass.PROTOCOL_ERROR


def test_reject_unexpected_status() -> None:
    result = validate_stream_response("HTTP/1.1 500 Server Error", {}, b"")
    assert not result.ok and result.failure == FailureClass.PROTOCOL_ERROR


def test_parse_status_line_codes() -> None:
    assert parse_status_line("HTTP/1.1 200 OK")[1] == 200
    assert parse_status_line("ICY 200 OK")[1] == 200
    assert parse_status_line("broken")[1] is None


def test_split_head_round_trip() -> None:
    raw = b"HTTP/1.1 200 OK\r\nContent-Type: x\r\n\r\nPAYLOAD"
    split = split_head(raw)
    assert split is not None
    head, rest = split
    assert rest == b"PAYLOAD"
    status, headers = parse_head(head)
    assert status == "HTTP/1.1 200 OK"
    assert headers["Content-Type"] == "x"


def test_split_head_incomplete_returns_none() -> None:
    assert split_head(b"HTTP/1.1 200 OK\r\npartial") is None


def _config(**overrides: object) -> NtripConfig:
    fields: dict[str, object] = {"host": "caster.example.invalid", "mountpoint": "TEST00SYN"}
    fields.update(overrides)
    return NtripConfig(**fields)  # type: ignore[arg-type]


def test_station_mapping_verified() -> None:
    mapping = map_station("TEST00SYN", {"TEST00SYN": "EKAK00NGA"})
    assert mapping.verified and mapping.station_id == "EKAK00NGA"


def test_station_mapping_unverified_without_registry() -> None:
    mapping = map_station("TEST00SYN", {})
    assert not mapping.verified
    assert mapping.station_id == STATION_IDENTITY_UNVERIFIED


def test_mountpoint_not_equal_station_identity() -> None:
    # A registry entry may map a mountpoint to a *different* station id.
    mapping = map_station("Lagos01", {"Lagos01": "EKAK00NGA"})
    assert mapping.station_id == "EKAK00NGA"


def test_admission_accept_open_verified() -> None:
    mapping = map_station("OPEN00SYN", {"OPEN00SYN": "EKAK00NGA"})
    admission = admit_mountpoint(
        provider="test", config=_config(mountpoint="OPEN00SYN"),
        source_table_format="RTCM 3.2", gnss_systems=("GPS",),
        requires_nmea=False, needs_auth=False, mapping=mapping,
    )
    assert admission.admission_status == AdmissionStatus.ACCEPT


def test_admission_warn_unverified_identity() -> None:
    mapping = map_station("MYSTERY", {})
    admission = admit_mountpoint(
        provider="test", config=_config(mountpoint="MYSTERY"),
        source_table_format="RTCM 3.2", gnss_systems=("GPS",),
        requires_nmea=False, needs_auth=False, mapping=mapping,
    )
    assert admission.admission_status == AdmissionStatus.WARN
    assert any("STATION_IDENTITY_UNVERIFIED" in r for r in admission.reason_codes)


def test_admission_blocked_nmea_without_gga() -> None:
    mapping = map_station("TEST00SYN", {"TEST00SYN": "EKAK00NGA"})
    admission = admit_mountpoint(
        provider="test", config=_config(mountpoint="TEST00SYN"),
        source_table_format="RTCM 3.2", gnss_systems=("GPS",),
        requires_nmea=True, needs_auth=False, mapping=mapping,
    )
    assert admission.admission_status == AdmissionStatus.BLOCKED
    assert any("NMEA_POSITION_REQUIRED" in r for r in admission.reason_codes)


def test_admission_blocked_auth_without_username() -> None:
    mapping = map_station("TEST00SYN", {"TEST00SYN": "EKAK00NGA"})
    admission = admit_mountpoint(
        provider="test", config=_config(mountpoint="TEST00SYN"),
        source_table_format="RTCM 3.2", gnss_systems=("GPS",),
        requires_nmea=False, needs_auth=True, mapping=mapping,
    )
    assert admission.admission_status == AdmissionStatus.BLOCKED
    assert any("AUTH_REQUIRED" in r for r in admission.reason_codes)


def test_admission_blocked_empty_host() -> None:
    mapping = map_station("TEST00SYN", {"TEST00SYN": "EKAK00NGA"})
    admission = admit_mountpoint(
        provider="test", config=_config(host="", mountpoint="TEST00SYN"),
        source_table_format="RTCM 3.2", gnss_systems=("GPS",),
        requires_nmea=False, needs_auth=False, mapping=mapping,
    )
    assert admission.admission_status == AdmissionStatus.BLOCKED
