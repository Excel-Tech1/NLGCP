"""Tests for the streaming RTCM framer, CRC handling, timing, and backoff.

SYNTHETIC TEST DATA — NOT VALID FOR SCIENTIFIC RESULTS.
"""

from __future__ import annotations

import pytest
from nlgcp_ntrip_ingest.backoff import ReconnectPolicy, classify_status_code, is_terminal
from nlgcp_ntrip_ingest.framing import StreamingFramer
from nlgcp_ntrip_ingest.models import FailureClass
from nlgcp_ntrip_ingest.timing import ArrivalRecorder, FakeClock
from nlgcp_rtcm_replay import fixtures as replay_fixtures
from nlgcp_rtcm_replay.framing import encode_frame


def _stream(messages: list[int]) -> bytes:
    return replay_fixtures.build_stream(messages)


def test_split_frame_across_single_byte_reads() -> None:
    data = _stream([1077])
    framer = StreamingFramer()
    emitted = []
    for index in range(len(data)):
        emitted.extend(framer.feed(data[index : index + 1]))
    assert len(emitted) == 1
    assert emitted[0].message_number == 1077
    assert emitted[0].crc_ok
    assert emitted[0].byte_offset == 0


def test_multiple_frames_in_one_read() -> None:
    data = _stream([1005, 1077, 1087])
    framer = StreamingFramer()
    frames = framer.feed(data)
    assert [f.message_number for f in frames] == [1005, 1077, 1087]
    assert all(f.crc_ok for f in frames)
    assert frames[1].byte_offset == len(frames[0].raw)


def test_frame_split_across_two_reads() -> None:
    data = _stream([1005, 1230])
    framer = StreamingFramer()
    first = framer.feed(data[:4])
    assert first == []
    rest = framer.feed(data[4:])
    assert [f.message_number for f in rest] == [1005, 1230]


def test_crc_failure_quarantined_with_finding() -> None:
    good, _ = replay_fixtures.valid_fixture_stream()
    bad_frames = [encode_frame(m, replay_fixtures.payload_for(m)) for m in [1005, 1077]]
    corrupted = bytearray(bad_frames[1])
    corrupted[5] ^= 0x01
    data = bad_frames[0] + bytes(corrupted)
    framer = StreamingFramer()
    frames = framer.feed(data)
    assert len(frames) == 2
    assert frames[0].crc_ok and not frames[1].crc_ok
    assert any("CRC_FAIL" in f for f in framer.flush_findings())
    assert len(good) > 0  # fixture sanity


def test_stray_bytes_reported_not_silent() -> None:
    data = b"\x00\xff\xfe" + _stream([1005])
    framer = StreamingFramer()
    frames = framer.feed(data)
    assert len(frames) == 1
    assert framer.stray_bytes == 3
    assert any("STRAY_BYTES" in f for f in framer.flush_findings())


def test_pending_stray_survives_across_feeds() -> None:
    data = _stream([1005])
    framer = StreamingFramer()
    assert framer.feed(b"\x00\xff") == []
    frames = framer.feed(data)
    assert len(frames) == 1
    assert framer.stray_bytes == 2


def test_oversize_length_refused() -> None:
    header = bytes([0xD3, 0x03, 0xFF])  # length 1023 with cap below it
    framer = StreamingFramer(max_frame_length=10)
    assert framer.feed(header + b"\x00" * 20) == []
    assert any("OVERSIZED_LENGTH" in f for f in framer.flush_findings())


def test_invalid_max_frame_length_rejected() -> None:
    with pytest.raises(ValueError):
        StreamingFramer(max_frame_length=0)


def test_frame_sha256_stable() -> None:
    data = _stream([1005])
    first = StreamingFramer().feed(data)[0]
    second = StreamingFramer().feed(data)[0]
    assert first.frame_sha256 == second.frame_sha256


def test_arrival_recorder_sequences_and_timestamps() -> None:
    clock = FakeClock()
    recorder = ArrivalRecorder("conn-1", clock)
    clock.advance_s(0.5)
    first = recorder.next(byte_offset=0, frame_length=10, message_number=1005,
                          crc_status="PASS", frame_sha256="a" * 64)
    clock.advance_s(0.25)
    second = recorder.next(byte_offset=10, frame_length=10, message_number=1077,
                           crc_status="PASS", frame_sha256="b" * 64)
    assert (first.sequence, second.sequence) == (0, 1)
    assert first.connection_id == "conn-1"
    assert first.arrival_utc == second.arrival_utc  # fake clock UTC frozen
    assert second.arrival_monotonic_ns > first.arrival_monotonic_ns


def test_fake_clock_rejects_time_travel() -> None:
    clock = FakeClock()
    with pytest.raises(ValueError):
        clock.advance_ns(-1)


def test_backoff_schedule_doubles_with_cap() -> None:
    policy = ReconnectPolicy(base_delay_s=1.0, max_delay_s=30.0, max_attempts=8)
    assert policy.delay_for_attempt(1) == 1.0
    assert policy.delay_for_attempt(2) == 2.0
    assert policy.delay_for_attempt(3) == 4.0
    assert policy.delay_for_attempt(10) == 30.0
    with pytest.raises(ValueError):
        policy.delay_for_attempt(0)


def test_backoff_jitter_deterministic_with_seed() -> None:
    policy = ReconnectPolicy()
    assert policy.delay_for_attempt(2, jitter_seed=7) == policy.delay_for_attempt(2, jitter_seed=7)


def test_backoff_exhaustion() -> None:
    policy = ReconnectPolicy(max_attempts=3)
    assert not policy.attempts_exhausted(2)
    assert policy.attempts_exhausted(3)


def test_terminal_failures_classified() -> None:
    for failure in (FailureClass.AUTH_FAILURE, FailureClass.MOUNTPOINT_NOT_FOUND,
                    FailureClass.AUTHORIZATION_REJECTED, FailureClass.CONFIG_INVALID):
        assert is_terminal(failure)
    for failure in (FailureClass.TIMEOUT, FailureClass.STALLED,
                    FailureClass.CONNECTION_LOST, FailureClass.PROTOCOL_ERROR):
        assert not is_terminal(failure)


def test_classify_status_code() -> None:
    assert classify_status_code(401) == FailureClass.AUTH_FAILURE
    assert classify_status_code(403) == FailureClass.AUTHORIZATION_REJECTED
    assert classify_status_code(404) == FailureClass.MOUNTPOINT_NOT_FOUND


def test_backoff_policy_validation() -> None:
    assert ReconnectPolicy(base_delay_s=0).validate() != []
    assert ReconnectPolicy(max_delay_s=0.5, base_delay_s=1.0).validate() != []
    assert ReconnectPolicy(max_attempts=-1).validate() != []
    assert ReconnectPolicy().validate() == []
