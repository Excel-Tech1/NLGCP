"""Tests for replay ordering, determinism, speeds, fake clock,
pause/resume, range replay, filtering, and loop mode.

SYNTHETIC TEST DATA — NOT VALID FOR SCIENTIFIC RESULTS.
"""

from __future__ import annotations

from pathlib import Path

from nlgcp_rtcm_replay import fixtures
from nlgcp_rtcm_replay.clock import FakeClock
from nlgcp_rtcm_replay.framing import parse_stream
from nlgcp_rtcm_replay.models import ReplayConfig
from nlgcp_rtcm_replay.provenance import config_fingerprint
from nlgcp_rtcm_replay.replay import (
    CollectedRun,
    ReplayController,
    apply_plan,
    scheduled_delay_ms,
)
from nlgcp_rtcm_replay.timing import build_timeline
from phase9_fixtures import make_valid_source


def _controller(
    tmp_path: Path, config: ReplayConfig
) -> tuple[ReplayController, CollectedRun, bytes, str]:
    path, source, _ = make_valid_source(tmp_path)
    raw = path.read_bytes()
    frames = parse_stream(raw).frames
    schedule = fixtures.synthetic_schedule(len(frames))
    events, _ = build_timeline(frames, arrival_ms=schedule)
    plan = apply_plan(events, config, config_fingerprint=config_fingerprint(config))
    collected = CollectedRun()
    controller = ReplayController(
        plan=plan,
        config=config,
        source_id=source.source_id,
        station_id=source.station_id,
        mountpoint=source.mountpoint,
        source_bytes=raw,
        clock=FakeClock(),
    )
    return controller, collected, raw, source.source_id


def test_replay_ordering_and_no_gaps(tmp_path: Path) -> None:
    controller, collected, _, _ = _controller(
        tmp_path, ReplayConfig(speed=0.0, buffer_capacity=16)
    )
    metrics = controller.run(collected.consumer)
    assert [f.sequence for f in collected.frames] == list(range(8))
    assert metrics.frames_emitted == 8
    assert metrics.frames_dropped == 0
    assert metrics.duplicates == 0
    assert metrics.sequence_gaps == 0


def test_deterministic_replay_identical(tmp_path: Path) -> None:
    first_ctrl, first_run, _, _ = _controller(
        tmp_path, ReplayConfig(speed=0.0, buffer_capacity=16)
    )
    first_ctrl.run(first_run.consumer)
    second_ctrl, second_run, _, _ = _controller(
        tmp_path, ReplayConfig(speed=0.0, buffer_capacity=16)
    )
    second_ctrl.run(second_run.consumer)
    first_keys = [
        (f.sequence, f.message_number, f.raw_bytes, f.source_timestamp)
        for f in first_run.frames
    ]
    second_keys = [
        (f.sequence, f.message_number, f.raw_bytes, f.source_timestamp)
        for f in second_run.frames
    ]
    assert first_keys == second_keys


def test_speed_configuration_pacing() -> None:
    from nlgcp_rtcm_replay.models import ReplayEvent

    prev = ReplayEvent(0, 0, 1077, 10, "0", 0, "a")
    cur = ReplayEvent(1, 20, 1077, 10, "1000", 1000, "b")
    assert scheduled_delay_ms(cur, None, 1.0) == 0
    assert scheduled_delay_ms(cur, prev, 1.0) == 1000
    assert scheduled_delay_ms(cur, prev, 10.0) == 100
    assert scheduled_delay_ms(cur, prev, 0.0) == 0


def test_fake_clock_no_sleeping() -> None:
    clock = FakeClock(start_ms=100)
    assert clock.now_ms() == 100
    clock.advance_ms(50)
    assert clock.now_ms() == 150
    try:
        clock.advance_ms(-1)
    except ValueError:
        pass
    else:
        raise AssertionError("clock must not go backwards")


def test_pause_resume_continues_exactly(tmp_path: Path) -> None:
    controller, collected, _, _ = _controller(
        tmp_path, ReplayConfig(speed=0.0, buffer_capacity=16)
    )
    controller.run(collected.consumer, max_steps=3)
    assert controller.paused
    assert controller.position == 3
    checkpoint = controller.make_checkpoint(
        source_fingerprint="src", config_fingerprint="cfg"
    )
    assert checkpoint.last_emitted_sequence == 2
    controller.resume()
    metrics = controller.run(collected.consumer)
    assert [f.sequence for f in collected.frames] == list(range(8))
    assert metrics.frames_emitted == 8
    assert metrics.duplicates == 0
    assert metrics.sequence_gaps == 0


def test_stop_halts_replay(tmp_path: Path) -> None:
    controller, collected, _, _ = _controller(
        tmp_path, ReplayConfig(speed=0.0, buffer_capacity=16)
    )

    def stopping_consumer(frame: object) -> None:
        collected.consumer(frame)  # type: ignore[arg-type]
        if len(collected.frames) == 2:
            controller.stop()

    controller.run(stopping_consumer)
    assert controller.position == 2
    assert [f.sequence for f in collected.frames] == [0, 1]


def test_range_replay_sequence_slice(tmp_path: Path) -> None:
    controller, collected, _, _ = _controller(
        tmp_path, ReplayConfig(speed=0.0, start_sequence=2, end_sequence=4)
    )
    metrics = controller.run(collected.consumer)
    assert [f.sequence for f in collected.frames] == [2, 3, 4]
    assert metrics.frames_emitted == 3


def test_range_replay_time_slice(tmp_path: Path) -> None:
    controller, collected, _, _ = _controller(
        tmp_path, ReplayConfig(speed=0.0, start_time="2000", end_time="4000")
    )
    metrics = controller.run(collected.consumer)
    assert metrics.frames_emitted == 3


def test_message_filtering_preserves_order(tmp_path: Path) -> None:
    controller, collected, _, _ = _controller(
        tmp_path, ReplayConfig(speed=0.0, message_filter=(1077,))
    )
    controller.run(collected.consumer)
    assert [f.message_number for f in collected.frames] == [1077, 1077]
    assert any("FILTER" in f for f in controller.findings)


def test_loop_mode_unique_cycles(tmp_path: Path) -> None:
    controller, collected, _, _ = _controller(
        tmp_path, ReplayConfig(speed=0.0, loop_cycles=2)
    )
    metrics = controller.run(collected.consumer)
    assert metrics.frames_emitted == 16
    assert [f.cycle for f in collected.frames] == [0] * 8 + [1] * 8
    assert metrics.duplicates == 0  # cross-cycle repetition is not duplication
    assert any("LOOP" in f for f in controller.findings)


def test_consumer_frame_contract_fields(tmp_path: Path) -> None:
    controller, collected, _, _ = _controller(
        tmp_path, ReplayConfig(speed=0.0, buffer_capacity=16)
    )
    controller.run(collected.consumer)
    frame = collected.frames[0]
    payload = frame.as_dict()
    for key in (
        "sequence",
        "source_id",
        "station_id",
        "mountpoint",
        "message_number",
        "raw_bytes",
        "source_timestamp",
        "replay_timestamp",
        "provenance",
    ):
        assert key in payload
