"""Tests for timing classification and deterministic timelines.

SYNTHETIC TEST DATA — NOT VALID FOR SCIENTIFIC RESULTS.
"""

from __future__ import annotations

from pathlib import Path

from nlgcp_rtcm_replay import fixtures
from nlgcp_rtcm_replay.framing import parse_stream
from nlgcp_rtcm_replay.models import TimingQuality
from nlgcp_rtcm_replay.timing import build_timeline, classify_timing
from phase9_fixtures import make_valid_source


def test_exact_capture_timing_with_schedule(tmp_path: Path) -> None:
    _, source, _ = make_valid_source(tmp_path)
    schedule = fixtures.synthetic_schedule(8)
    assessment = classify_timing(source, schedule)
    assert assessment.quality == TimingQuality.EXACT_CAPTURE_TIMING
    assert assessment.source_duration_ms == 7000


def test_unavailable_without_schedule(tmp_path: Path) -> None:
    _, source, _ = make_valid_source(tmp_path, timestamp_source="unknown")
    assessment = classify_timing(source, None)
    assert assessment.quality == TimingQuality.UNAVAILABLE


def test_approximate_with_nominal_interval(tmp_path: Path) -> None:
    _, source, _ = make_valid_source(tmp_path, timestamp_source="unknown")
    assessment = classify_timing(source, None, nominal_interval_ms=1000)
    assert assessment.quality == TimingQuality.APPROXIMATE


def test_message_epoch_without_decoder_unavailable(tmp_path: Path) -> None:
    path_source = make_valid_source(tmp_path, timestamp_source="message_epoch")
    _, source, _ = path_source
    assessment = classify_timing(source, None)
    assert assessment.quality == TimingQuality.UNAVAILABLE
    assert any("EPOCH" in f for f in assessment.findings)


def test_timeline_deterministic_and_relative(tmp_path: Path) -> None:
    stream, _ = fixtures.valid_fixture_stream()
    frames = parse_stream(stream).frames
    schedule = fixtures.synthetic_schedule(len(frames), interval_ms=500)
    first, _ = build_timeline(frames, arrival_ms=schedule)
    second, _ = build_timeline(frames, arrival_ms=schedule)
    assert [e.as_dict() for e in first] == [e.as_dict() for e in second]
    assert first[0].relative_time_ms == 0
    assert [e.relative_time_ms for e in first] == [i * 500 for i in range(8)]
    assert [e.sequence for e in first] == list(range(8))


def test_timeline_excludes_bad_crc_by_default() -> None:
    stream, _ = fixtures.corrupt_fixture_stream()
    frames = parse_stream(stream).frames
    schedule = fixtures.synthetic_schedule(len(frames))
    events, _ = build_timeline(frames, arrival_ms=schedule)
    assert len(events) == 7
    assert all(e.sequence == i for i, e in enumerate(events))


def test_timeline_schedule_mismatch_fails() -> None:
    stream, _ = fixtures.valid_fixture_stream()
    frames = parse_stream(stream).frames
    try:
        build_timeline(frames, arrival_ms=[0, 1])
    except ValueError as exc:
        assert "arrival schedule length" in str(exc)
    else:
        raise AssertionError("schedule mismatch must fail")
