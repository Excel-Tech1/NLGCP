"""Tests for CRC-24Q and RTCM 3.x framing.

SYNTHETIC TEST DATA — NOT VALID FOR SCIENTIFIC RESULTS.
"""

from __future__ import annotations

from nlgcp_rtcm_replay import fixtures
from nlgcp_rtcm_replay.crc import crc24q
from nlgcp_rtcm_replay.framing import (
    PREAMBLE,
    encode_frame,
    extract_message_number,
    parse_stream,
)
from nlgcp_rtcm_replay.models import CRCStatus


def test_crc24q_reference_vector() -> None:
    # Standard CRC-24Q check value for ASCII "123456789".
    assert crc24q(b"123456789") == 0xCDE703


def test_valid_frame_round_trip() -> None:
    raw = encode_frame(1077, fixtures.payload_for(1077))
    result = parse_stream(raw)
    assert result.findings == []
    assert len(result.frames) == 1
    record = result.frames[0].record
    assert record.message_number == 1077
    assert record.crc_status == CRCStatus.PASS
    assert record.offset == 0


def test_valid_fixture_all_frames_pass() -> None:
    stream, sequence = fixtures.valid_fixture_stream()
    result = parse_stream(stream)
    assert result.findings == []
    assert [p.record.message_number for p in result.frames] == sequence
    assert all(p.record.crc_status == CRCStatus.PASS for p in result.frames)


def test_bad_preamble_produces_stray_finding() -> None:
    stream, _ = fixtures.valid_fixture_stream()
    result = parse_stream(b"\x00\x01\x02" + stream)
    assert len(result.frames) == 8
    assert any("STRAY_BYTES" in f for f in result.findings)


def test_truncated_frame_finding() -> None:
    stream = fixtures.truncated_fixture_stream()
    result = parse_stream(stream)
    assert any("TRUNCATED_FRAME" in f for f in result.findings)
    assert len(result.frames) == 7


def test_truncated_header_finding() -> None:
    result = parse_stream(bytes([PREAMBLE, 0x01]))
    assert any("TRUNCATED_HEADER" in f for f in result.findings)
    assert result.frames == []


def test_oversized_length_rejected() -> None:
    raw = bytearray(encode_frame(1005, fixtures.payload_for(1005)))
    # Forge an oversized 10-bit length (1023) with a small max limit.
    raw[1] = (raw[1] & 0xFC) | 0x03
    raw[2] = 0xFF
    result = parse_stream(bytes(raw), max_frame_length=16)
    assert any("OVERSIZED_LENGTH" in f for f in result.findings)


def test_crc_fail_detected() -> None:
    stream, _ = fixtures.corrupt_fixture_stream()
    result = parse_stream(stream)
    assert len(result.frames) == 8
    assert result.frames[3].record.crc_status == CRCStatus.FAIL
    assert any("CRC_FAIL" in f for f in result.findings)


def test_message_number_extraction() -> None:
    for number in (1005, 1006, 1077, 1087, 1230):
        raw = encode_frame(number, fixtures.payload_for(number))
        result = parse_stream(raw)
        assert result.frames[0].record.message_number == number


def test_message_number_short_payload_none() -> None:
    assert extract_message_number(b"\x00") is None
    assert extract_message_number(b"") is None


def test_garbage_prefix_resync() -> None:
    stream, sequence = fixtures.garbage_prefix_stream()
    result = parse_stream(stream)
    assert [p.record.message_number for p in result.frames] == sequence
    assert any("STRAY_BYTES" in f for f in result.findings)


def test_empty_stream_no_frames_no_findings() -> None:
    result = parse_stream(b"")
    assert result.frames == []
    assert result.bytes_processed == 0


def test_event_limit_guards_memory() -> None:
    stream, _ = fixtures.valid_fixture_stream()
    result = parse_stream(stream * 4, max_events=5)
    assert len(result.frames) == 5
    assert any("EVENT_LIMIT" in f for f in result.findings)


def test_frame_offsets_monotonic() -> None:
    stream, _ = fixtures.valid_fixture_stream()
    result = parse_stream(stream)
    offsets = [p.record.offset for p in result.frames]
    assert offsets == sorted(offsets)
