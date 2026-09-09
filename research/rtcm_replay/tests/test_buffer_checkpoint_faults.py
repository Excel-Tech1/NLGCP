"""Tests for bounded buffering, backpressure, checkpoints,
fault injection, and consumer failure.

SYNTHETIC TEST DATA — NOT VALID FOR SCIENTIFIC RESULTS.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from nlgcp_rtcm_replay import fixtures
from nlgcp_rtcm_replay.buffer import BoundedBuffer
from nlgcp_rtcm_replay.checkpoint import checkpoint_from_dict, validate_checkpoint
from nlgcp_rtcm_replay.clock import FakeClock
from nlgcp_rtcm_replay.framing import parse_stream
from nlgcp_rtcm_replay.models import BackpressurePolicy, ReplayConfig
from nlgcp_rtcm_replay.provenance import config_fingerprint
from nlgcp_rtcm_replay.replay import (
    CollectedRun,
    ConsumerStalled,
    FaultPlan,
    PlannedReplay,
    ReplayController,
    apply_plan,
)
from nlgcp_rtcm_replay.timing import build_timeline
from phase9_fixtures import make_valid_source


def _planned(
    tmp_path: Path, config: ReplayConfig
) -> tuple[bytes, PlannedReplay, ReplayConfig]:
    path, source, _ = make_valid_source(tmp_path)
    raw = path.read_bytes()
    frames = parse_stream(raw).frames
    schedule = fixtures.synthetic_schedule(len(frames))
    events, _ = build_timeline(frames, arrival_ms=schedule)
    plan = apply_plan(events, config, config_fingerprint=config_fingerprint(config))
    return raw, plan, config


def test_buffer_capacity_and_high_water() -> None:
    buf: BoundedBuffer[int] = BoundedBuffer(2)
    assert buf.try_put(1)
    assert buf.try_put(2)
    assert buf.occupancy == 2
    assert buf.high_water_mark == 2
    # BLOCK policy: full buffer refuses without dropping.
    assert not buf.try_put(3)
    assert buf.dropped_frames == 0
    assert buf.buffer_waits == 1
    assert buf.take() == 1


def test_explicit_drop_policy_counts_drops() -> None:
    buf: BoundedBuffer[int] = BoundedBuffer(1, policy=BackpressurePolicy.DROP_NEWEST_EXPLICIT)
    assert buf.try_put(1)
    assert not buf.try_put(2)
    assert buf.dropped_frames == 1


def test_no_silent_drops_default_block(tmp_path: Path) -> None:
    raw, plan, config = _planned(tmp_path, ReplayConfig(speed=0.0, buffer_capacity=1))
    controller = ReplayController(
        plan=plan,
        config=config,
        source_id="s",
        station_id="SYN00TST",
        mountpoint="SYNTHETIC",
        source_bytes=raw,
        clock=FakeClock(),
    )
    collected = CollectedRun()
    metrics = controller.run(collected.consumer)
    # Immediate drain keeps occupancy bounded; nothing lost silently.
    assert metrics.frames_emitted == 8
    assert metrics.frames_dropped == 0


def test_backpressure_metrics_recorded(tmp_path: Path) -> None:
    raw, plan, config = _planned(
        tmp_path,
        ReplayConfig(
            speed=0.0, buffer_capacity=1, backpressure_policy=BackpressurePolicy.BACKPRESSURE
        ),
    )
    controller = ReplayController(
        plan=plan,
        config=config,
        source_id="s",
        station_id="SYN00TST",
        mountpoint="SYNTHETIC",
        source_bytes=raw,
        clock=FakeClock(),
    )
    collected = CollectedRun()
    metrics = controller.run(collected.consumer)
    assert metrics.maximum_queue_depth <= 1
    assert metrics.producer_frames == 8
    assert metrics.consumer_frames == 8


def test_checkpoint_resume_exact_continuation(tmp_path: Path) -> None:
    raw, plan, config = _planned(tmp_path, ReplayConfig(speed=0.0))
    fingerprint_cfg = config_fingerprint(config)
    first = ReplayController(
        plan=plan,
        config=config,
        source_id="s",
        station_id="SYN00TST",
        mountpoint="SYNTHETIC",
        source_bytes=raw,
        clock=FakeClock(),
    )
    collected = CollectedRun()
    first.run(collected.consumer, max_steps=5)
    checkpoint = first.make_checkpoint(
        source_fingerprint="src-fp", config_fingerprint=fingerprint_cfg
    )
    assert checkpoint.source_byte_offset == plan.events[4].source_offset

    second = ReplayController(
        plan=plan,
        config=config,
        source_id="s",
        station_id="SYN00TST",
        mountpoint="SYNTHETIC",
        source_bytes=raw,
        clock=FakeClock(),
    )
    assert second.resume_from_checkpoint(
        checkpoint, source_fingerprint="src-fp", config_fingerprint=fingerprint_cfg
    )
    second.run(collected.consumer)
    assert [f.sequence for f in collected.frames] == list(range(8))
    metrics = second.metrics()
    assert metrics.checkpoint_resumes == 1
    assert metrics.duplicates == 0


def test_checkpoint_invalidation_on_changed_source(tmp_path: Path) -> None:
    raw, plan, config = _planned(tmp_path, ReplayConfig(speed=0.0))
    controller = ReplayController(
        plan=plan,
        config=config,
        source_id="s",
        station_id="SYN00TST",
        mountpoint="SYNTHETIC",
        source_bytes=raw,
        clock=FakeClock(),
    )
    collected = CollectedRun()
    controller.run(collected.consumer, max_steps=2)
    checkpoint = controller.make_checkpoint(
        source_fingerprint="src-fp", config_fingerprint="cfg-fp"
    )
    fresh = ReplayController(
        plan=plan,
        config=config,
        source_id="s",
        station_id="SYN00TST",
        mountpoint="SYNTHETIC",
        source_bytes=raw,
        clock=FakeClock(),
    )
    assert not fresh.resume_from_checkpoint(
        checkpoint, source_fingerprint="CHANGED", config_fingerprint="cfg-fp"
    )
    assert any("CHECKPOINT_SOURCE_MISMATCH" in f for f in fresh.findings)


def test_checkpoint_invalidation_on_changed_config(tmp_path: Path) -> None:
    raw, plan, config = _planned(tmp_path, ReplayConfig(speed=0.0))
    controller = ReplayController(
        plan=plan,
        config=config,
        source_id="s",
        station_id="SYN00TST",
        mountpoint="SYNTHETIC",
        source_bytes=raw,
        clock=FakeClock(),
    )
    checkpoint = controller.make_checkpoint(
        source_fingerprint="src-fp", config_fingerprint="cfg-fp"
    )
    check = validate_checkpoint(
        checkpoint, source_fingerprint="src-fp", config_fingerprint="OTHER"
    )
    assert not check.valid
    assert "CHECKPOINT_CONFIG_MISMATCH" in check.reason


def test_checkpoint_round_trip_serialisation(tmp_path: Path) -> None:
    raw, plan, config = _planned(tmp_path, ReplayConfig(speed=0.0))
    controller = ReplayController(
        plan=plan,
        config=config,
        source_id="s",
        station_id="SYN00TST",
        mountpoint="SYNTHETIC",
        source_bytes=raw,
        clock=FakeClock(),
    )
    collected = CollectedRun()
    controller.run(collected.consumer, max_steps=1)
    checkpoint = controller.make_checkpoint(
        source_fingerprint="a", config_fingerprint="b"
    )
    restored = checkpoint_from_dict(checkpoint.as_dict())
    assert restored == checkpoint


def test_fault_corrupt_frame_recorded(tmp_path: Path) -> None:
    raw, plan, config = _planned(tmp_path, ReplayConfig(speed=0.0))
    controller = ReplayController(
        plan=plan,
        config=config,
        source_id="s",
        station_id="SYN00TST",
        mountpoint="SYNTHETIC",
        source_bytes=raw,
        clock=FakeClock(),
        faults=FaultPlan(corrupt_sequence=2),
    )
    collected = CollectedRun()
    controller.run(collected.consumer)
    assert any("FAULT_CORRUPT" in f for f in controller.findings)
    assert len(collected.frames) == 8


def test_fault_truncation_stops_replay(tmp_path: Path) -> None:
    raw, plan, config = _planned(tmp_path, ReplayConfig(speed=0.0))
    controller = ReplayController(
        plan=plan,
        config=config,
        source_id="s",
        station_id="SYN00TST",
        mountpoint="SYNTHETIC",
        source_bytes=raw,
        clock=FakeClock(),
        faults=FaultPlan(truncate_after_sequence=4),
    )
    collected = CollectedRun()
    controller.run(collected.consumer)
    assert [f.sequence for f in collected.frames] == [0, 1, 2, 3, 4]
    assert any("FAULT_TRUNCATION" in f for f in controller.findings)


def test_fault_consumer_stall_raises(tmp_path: Path) -> None:
    raw, plan, config = _planned(tmp_path, ReplayConfig(speed=0.0))
    controller = ReplayController(
        plan=plan,
        config=config,
        source_id="s",
        station_id="SYN00TST",
        mountpoint="SYNTHETIC",
        source_bytes=raw,
        clock=FakeClock(),
        faults=FaultPlan(stall_consumer_after=2),
    )
    collected = CollectedRun()
    with pytest.raises(ConsumerStalled):
        controller.run(collected.consumer)
    assert len(collected.frames) == 2
