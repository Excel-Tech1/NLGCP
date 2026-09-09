"""Deterministic replay controller (§11-§13, §20-§21, §24-§27).

Given identical source bytes, config, speed mode, and range, the
logical emitted frame sequence (sequence / offset / message number /
hash / provenance) is identical.  Wall-clock replay timestamps may
differ; sequence and provenance must not.

Speeds: ``speed > 0`` paces scheduled delays as
``relative_time_ms / speed``; ``speed == 0`` means unpaced
(max-throughput) and is the deterministic default for tests.
With a FakeClock no real sleeping occurs: pacing advances the fake
clock arithmetically, keeping tests deterministic.

Pause/resume/restart: ``pause()`` freezes emission; ``resume()``
continues from the next un-emitted event without duplication or gaps;
``run()`` executes to completion or until paused/stopped.  Checkpoints
persist ``(source, config)`` fingerprints with the resume position.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from nlgcp_rtcm_replay.buffer import BoundedBuffer
from nlgcp_rtcm_replay.clock import FakeClock, ReplayClock
from nlgcp_rtcm_replay.models import (
    AdmissionBlocked,
    BackpressurePolicy,
    Checkpoint,
    CorrectionFrame,
    ReplayConfig,
    ReplayEvent,
    ReplayMetrics,
)

Consumer = Callable[[CorrectionFrame], None]


@dataclass(slots=True)
class FaultPlan:
    """Controlled test faults (§21). Synthetic fixtures only; real
    evidence files are never corrupted."""

    corrupt_sequence: int | None = None
    truncate_after_sequence: int | None = None
    stall_consumer_after: int | None = None


@dataclass(slots=True)
class PlannedReplay:
    events: list[ReplayEvent]
    findings: list[str]
    config_fingerprint: str


def apply_plan(
    timeline: list[ReplayEvent],
    config: ReplayConfig,
    *,
    config_fingerprint: str,
) -> PlannedReplay:
    """Apply range slicing, time slicing, message filtering, and loop
    expansion deterministically.  Filtering preserves ordering among
    retained messages; every loop cycle carries a unique cycle index
    so repetition is never confused with captured data."""
    config.assert_valid()
    findings: list[str] = []
    selected = list(timeline)
    if config.start_sequence is not None:
        selected = [e for e in selected if e.sequence >= config.start_sequence]
    if config.end_sequence is not None:
        selected = [e for e in selected if e.sequence <= config.end_sequence]
    if config.start_time is not None or config.end_time is not None:
        timed = [e for e in selected if e.original_timestamp is not None]
        if len(timed) != len(selected):
            raise AdmissionBlocked(
                "RTCM REPLAY BLOCKED - SOURCE ADMISSION REQUIREMENTS NOT MET: "
                "time-based slicing requires original timestamps for every event"
            )
        if config.start_time is not None:
            timed = [e for e in timed if (e.original_timestamp or "") >= config.start_time]
        if config.end_time is not None:
            timed = [e for e in timed if (e.original_timestamp or "") <= config.end_time]
        selected = timed
    if config.message_filter:
        wanted = set(config.message_filter)
        before = len(selected)
        selected = [e for e in selected if e.message_number in wanted]
        findings.append(
            f"FILTER retained={len(selected)} removed={before - len(selected)} "
            f"types={sorted(wanted)}"
        )
    if len(selected) > config.max_events:
        raise AdmissionBlocked(
            "RTCM REPLAY BLOCKED - SOURCE ADMISSION REQUIREMENTS NOT MET: "
            f"planned events {len(selected)} exceed max_events {config.max_events}"
        )
    expanded: list[ReplayEvent] = []
    for _cycle in range(config.loop_cycles):
        expanded.extend(selected)
    if config.loop_cycles > 1:
        findings.append(f"LOOP cycles={config.loop_cycles} base_events={len(selected)}")
    return PlannedReplay(events=expanded, findings=findings, config_fingerprint=config_fingerprint)


def scheduled_delay_ms(event: ReplayEvent, previous: ReplayEvent | None, speed: float) -> int:
    """Deterministic scheduled pacing delay (integer ms, no float drift)."""
    if speed == 0:
        return 0
    if previous is None:
        return 0
    delta = event.relative_time_ms - previous.relative_time_ms
    if delta < 0:
        delta = 0
    return int(delta / speed)


class ReplayController:
    """Controlled playback over a planned event list."""

    def __init__(
        self,
        *,
        plan: PlannedReplay,
        config: ReplayConfig,
        source_id: str,
        station_id: str,
        mountpoint: str,
        source_bytes: bytes,
        clock: ReplayClock | None = None,
        faults: FaultPlan | None = None,
        provenance: dict[str, object] | None = None,
    ) -> None:
        self._plan = plan
        self._config = config
        self._source_id = source_id
        self._station_id = station_id
        self._mountpoint = mountpoint
        self._source_bytes = source_bytes
        self._clock: ReplayClock = clock or FakeClock()
        self._faults = faults or FaultPlan()
        self._provenance: dict[str, object] = dict(provenance or {})
        self._buffer = BoundedBuffer[CorrectionFrame](
            config.buffer_capacity, policy=config.backpressure_policy
        )
        self._position = 0  # next event index to emit
        self._cycle_of: list[int] = self._assign_cycles(len(plan.events), config.loop_cycles)
        self._paused = False
        self._stopped = False
        self._previous: ReplayEvent | None = None
        self._emitted_hashes: list[str] = []
        self._emitted_keys: list[tuple[int, int, str]] = []
        self._scheduled_delays: list[int] = []
        self._consumer_delays: list[int] = []
        self._consumer_frames = 0
        self._checkpoint_resumes = 0
        self._frames_dropped = 0
        self._findings: list[str] = list(plan.findings)

    @staticmethod
    def _assign_cycles(count: int, loop_cycles: int) -> list[int]:
        if loop_cycles <= 1 or count == 0:
            return [0] * count
        base = count // loop_cycles
        cycles: list[int] = []
        for cycle in range(loop_cycles):
            cycles.extend([cycle] * base)
        cycles.extend([loop_cycles - 1] * (count - len(cycles)))
        return cycles

    @property
    def position(self) -> int:
        return self._position

    @property
    def paused(self) -> bool:
        return self._paused

    @property
    def findings(self) -> list[str]:
        return list(self._findings)

    def start(self) -> None:
        self._paused = False
        self._stopped = False

    def pause(self) -> None:
        self._paused = True

    def resume(self) -> None:
        self._paused = False

    def stop(self) -> None:
        self._stopped = True

    def resume_from_checkpoint(
        self, checkpoint: Checkpoint, *, source_fingerprint: str, config_fingerprint: str
    ) -> bool:
        """Continue from a checkpoint; changed fingerprints invalidate."""
        from nlgcp_rtcm_replay.checkpoint import validate_checkpoint

        check = validate_checkpoint(
            checkpoint,
            source_fingerprint=source_fingerprint,
            config_fingerprint=config_fingerprint,
        )
        if not check.valid:
            self._findings.append(check.reason)
            return False
        target = checkpoint.last_emitted_sequence + 1
        if target < 0 or target > len(self._plan.events):
            self._findings.append(
                f"CHECKPOINT_POSITION_INVALID last={checkpoint.last_emitted_sequence}"
            )
            return False
        self._position = target
        self._checkpoint_resumes += 1
        self._paused = False
        self._stopped = False
        return True

    def make_checkpoint(
        self, *, source_fingerprint: str, config_fingerprint: str
    ) -> Checkpoint:
        last = self._position - 1
        offset = self._plan.events[last].source_offset if last >= 0 else 0
        return Checkpoint(
            source_fingerprint=source_fingerprint,
            config_fingerprint=config_fingerprint,
            last_emitted_sequence=last,
            source_byte_offset=offset,
            last_replay_timestamp=str(self._clock.now_ms()),
            cycle=self._cycle_of[last] if last >= 0 else 0,
        )

    def _read_raw(self, event: ReplayEvent) -> bytes:
        total = 3 + event.frame_length + 3
        raw = self._source_bytes[event.source_offset : event.source_offset + total]
        if len(raw) != total:
            raise AdmissionBlocked(
                "RTCM REPLAY BLOCKED - SOURCE ADMISSION REQUIREMENTS NOT MET: "
                f"source truncation at offset {event.source_offset}"
            )
        return raw

    def _emit_one(self, consumer: Consumer, event: ReplayEvent, cycle: int) -> bool:
        """Emit one event through the bounded buffer. Returns False when
        BLOCK/BACKPRESSURE policy must wait (caller retries deterministically)."""
        if (
            self._faults.truncate_after_sequence is not None
            and event.sequence > self._faults.truncate_after_sequence
        ):
            self._findings.append(
                f"FAULT_TRUNCATION stopped_before_sequence={event.sequence}"
            )
            self._stopped = True
            return True
        raw = self._read_raw(event)
        if self._faults.corrupt_sequence == event.sequence:
            raw = raw[:5] + bytes([raw[5] ^ 0x01]) + raw[6:] if len(raw) > 6 else raw
            self._findings.append(f"FAULT_CORRUPT injected_sequence={event.sequence}")
        delay = scheduled_delay_ms(event, self._previous, self._config.speed)
        self._clock.advance_ms(delay)
        self._scheduled_delays.append(delay)
        frame = CorrectionFrame(
            sequence=event.sequence,
            cycle=cycle,
            source_id=self._source_id,
            station_id=self._station_id,
            mountpoint=self._mountpoint,
            message_number=event.message_number,
            raw_bytes=raw,
            source_timestamp=event.original_timestamp,
            replay_timestamp=str(self._clock.now_ms()),
            provenance=dict(self._provenance),
        )
        accepted = self._buffer.try_put(frame)
        if not accepted:
            if self._config.backpressure_policy == BackpressurePolicy.DROP_NEWEST_EXPLICIT:
                self._frames_dropped += 1
                self._findings.append(f"DROP sequence={event.sequence} policy=explicit")
                self._previous = event
                self._position += 1
                return True
            # BLOCK / BACKPRESSURE: deterministic wait, retry same event.
            self._clock.advance_ms(1)
            return False
        # Drain immediately through the consumer (bounded occupancy preserved).
        pending = self._buffer.drain()
        for item in pending:
            before = self._clock.now_ms()
            if (
                self._faults.stall_consumer_after is not None
                and self._consumer_frames >= self._faults.stall_consumer_after
            ):
                self._findings.append(
                    f"FAULT_CONSUMER_STALL after={self._consumer_frames}"
                )
                raise ConsumerStalled(f"synthetic consumer stall after {self._consumer_frames}")
            consumer(item)
            self._consumer_frames += 1
            self._consumer_delays.append(self._clock.now_ms() - before)
        self._emitted_hashes.append(event.raw_hash)
        self._emitted_keys.append((cycle, event.sequence, event.raw_hash))
        self._previous = event
        self._position += 1
        return True

    def run(self, consumer: Consumer, *, max_steps: int | None = None) -> ReplayMetrics:
        """Run until plan exhausted, paused, or stopped."""
        self.start()
        steps = 0
        while self._position < len(self._plan.events):
            if self._paused or self._stopped:
                break
            if max_steps is not None and steps >= max_steps:
                self.pause()
                break
            event = self._plan.events[self._position]
            cycle = self._cycle_of[self._position]
            self._emit_one(consumer, event, cycle)
            steps += 1
        return self.metrics()

    def metrics(self) -> ReplayMetrics:
        emitted = self._plan.events[: self._position]
        cycles = self._cycle_of[: self._position]
        gaps = 0
        for i in range(1, len(emitted)):
            prev, cur = emitted[i - 1], emitted[i]
            if cycles[i] != cycles[i - 1]:
                continue  # loop restart is repetition, not a gap
            if cur.sequence != prev.sequence + 1 and cur.sequence != prev.sequence:
                gaps += 1
        # Duplicates are unintended repeats within one cycle; loop
        # repetition across distinct cycles is expected, not duplication.
        duplicates = len(self._emitted_keys) - len(set(self._emitted_keys))
        source_duration = 0
        if self._plan.events:
            source_duration = self._plan.events[-1].relative_time_ms
        replay_duration = sum(self._scheduled_delays)
        effective = 0.0
        if replay_duration > 0:
            effective = source_duration / replay_duration
        elif self._config.speed == 0 and source_duration >= 0:
            effective = float("inf") if source_duration > 0 else 0.0
        counts: dict[str, int] = {}
        for event in self._plan.events[: self._position]:
            key = str(event.message_number)
            counts[key] = counts.get(key, 0) + 1
        return ReplayMetrics(
            frames_emitted=self._consumer_frames,
            frames_dropped=self._frames_dropped + self._buffer.dropped_frames,
            duplicates=duplicates,
            sequence_gaps=gaps,
            checkpoint_resumes=self._checkpoint_resumes,
            producer_frames=self._position,
            consumer_frames=self._consumer_frames,
            buffer_waits=self._buffer.buffer_waits,
            maximum_queue_depth=self._buffer.maximum_queue_depth,
            replay_duration_ms=replay_duration,
            source_duration_ms=source_duration,
            effective_speed=effective,
            message_type_counts=counts,
            scheduled_replay_delays_ms=list(self._scheduled_delays),
            consumer_processing_delays_ms=list(self._consumer_delays),
        )


class ConsumerStalled(RuntimeError):
    """Synthetic consumer-stall fault (§21)."""


@dataclass(slots=True)
class CollectedRun:
    frames: list[CorrectionFrame] = field(default_factory=list)

    def consumer(self, frame: CorrectionFrame) -> None:
        self.frames.append(frame)
