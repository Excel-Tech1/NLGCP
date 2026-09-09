"""Tests for source-table parsing and discovery safety.

SYNTHETIC TEST DATA — NOT VALID FOR SCIENTIFIC RESULTS.
"""

from __future__ import annotations

from nlgcp_ntrip_ingest.sourcetable import (
    find_stream,
    parse_sourcetable,
    stream_needs_auth,
    stream_requires_nmea,
)
from nlgcp_ntrip_ingest.testserver import SOURCETABLE_BODY


def test_parse_full_sourcetable() -> None:
    table = parse_sourcetable(SOURCETABLE_BODY)
    assert table.terminated
    assert len(table.streams) == 2
    assert len(table.casters) == 1
    assert len(table.networks) == 1
    assert table.findings == []
    first = table.streams[0]
    assert first.mountpoint == "TEST00SYN"
    assert first.format == "RTCM 3.2"
    assert first.country == "NGA"


def test_str_metadata_fields_extracted() -> None:
    table = parse_sourcetable(SOURCETABLE_BODY)
    auth_stream = find_stream(table, "TEST00SYN")
    open_stream = find_stream(table, "OPEN00SYN")
    assert auth_stream is not None and open_stream is not None
    assert stream_needs_auth(auth_stream)
    assert stream_requires_nmea(auth_stream)
    assert not stream_needs_auth(open_stream)
    assert not stream_requires_nmea(open_stream)


def test_find_stream_case_insensitive_slash_tolerant() -> None:
    table = parse_sourcetable(SOURCETABLE_BODY)
    assert find_stream(table, "/test00syn") is not None
    assert find_stream(table, "MISSING") is None


def test_missing_terminator_recorded() -> None:
    table = parse_sourcetable("STR;A;B\r\n")
    assert not table.terminated
    assert any("MISSING_ENDSOURCETABLE" in f for f in table.findings)


def test_unknown_records_recorded_not_trusted() -> None:
    table = parse_sourcetable("BOGUS;1;2\r\nENDSOURCETABLE\r\n")
    assert table.terminated
    assert any("UNKNOWN_RECORD" in f for f in table.findings)
    assert table.streams == []


def test_sourcetable_size_limit_enforced() -> None:
    big = ("STR;" + "X" * 100 + "\r\n") * 100 + "ENDSOURCETABLE\r\n"
    table = parse_sourcetable(big, max_bytes=500)
    assert any("SOURCETABLE_TOO_LARGE" in f for f in table.findings)


def test_entry_limit_enforced() -> None:
    many = "".join(f"STR;M{i};id\r\n" for i in range(50)) + "ENDSOURCETABLE\r\n"
    table = parse_sourcetable(many, max_entries=10)
    assert len(table.streams) == 10
    assert any("ENTRY_LIMIT" in f for f in table.findings)


def test_sourcetable_sha256_stable() -> None:
    first = parse_sourcetable(SOURCETABLE_BODY)
    second = parse_sourcetable(SOURCETABLE_BODY)
    assert first.sha256 == second.sha256
    assert len(first.sha256) == 64
