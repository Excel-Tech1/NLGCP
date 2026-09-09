"""Timestamp model and deterministic replay timeline (§9-§10).

A binary RTCM stream carries no universal wall-clock timestamp per
frame, so timing is reconstructed only from declared sources and
classified honestly:

- ``capture`` + per-frame arrival schedule → EXACT_CAPTURE_TIMING
- ``message_epoch`` with epoch data → MESSAGE_EPOCH_DERIVED
- nominal interval only → APPROXIMATE
- nothing usable → UNAVAILABLE (time slicing then fails closed)

The same source/configuration always yields the same timeline:
relative offsets are integer milliseconds derived deterministically
from the schedule, never from wall-clock reads.
"""

from __future__ import annotations

from dataclasses import dataclass

from nlgcp_rtcm_replay.framing import ParsedFrame
from nlgcp_rtcm_replay.models import ReplayEvent, RTCMSource, TimingQuality


@dataclass(frozen=True, slots=True)
class TimingAssessment:
    quality: TimingQuality
    findings: tuple[str, ...]
    source_duration_ms: int


def classify_timing(
    source: RTCMSource,
    arrival_ms: list[int] | None,
    *,
    epoch_available: bool = False,
    nominal_interval_ms: int | None = None,
) -> TimingAssessment:
    """Decide timing quality without inventing timestamps."""
    findings: list[str] = []
    if source.timestamp_source == "capture" and arrival_ms:
        return TimingAssessment(
            quality=TimingQuality.EXACT_CAPTURE_TIMING,
            findings=tuple(findings),
            source_duration_ms=arrival_ms[-1] - arrival_ms[0] if len(arrival_ms) > 1 else 0,
        )
    if source.timestamp_source == "message_epoch" and epoch_available:
        return TimingAssessment(
            quality=TimingQuality.MESSAGE_EPOCH_DERIVED,
            findings=tuple(findings),
            source_duration_ms=0,
        )
    if source.timestamp_source == "message_epoch" and not epoch_available:
        findings.append(
            "TIMING_EPOCH_UNAVAILABLE timestamp_source=message_epoch "
            "but no epoch data decoded in this phase"
        )
        return TimingAssessment(
            quality=TimingQuality.UNAVAILABLE,
            findings=tuple(findings),
            source_duration_ms=0,
        )
    if nominal_interval_ms is not None:
        findings.append(
            f"TIMING_APPROXIMATE nominal_interval_ms={nominal_interval_ms} "
            "no capture timestamps available"
        )
        return TimingAssessment(
            quality=TimingQuality.APPROXIMATE,
            findings=tuple(findings),
            source_duration_ms=0,
        )
    findings.append("TIMING_UNAVAILABLE no timestamp source usable")
    return TimingAssessment(
        quality=TimingQuality.UNAVAILABLE,
        findings=tuple(findings),
        source_duration_ms=0,
    )


def build_timeline(
    frames: list[ParsedFrame],
    *,
    arrival_ms: list[int] | None,
    nominal_interval_ms: int = 1000,
    only_valid_crc: bool = True,
) -> tuple[list[ReplayEvent], TimingAssessment | None]:
    """Build the deterministic replay timeline over parsed frames.

    Frames failing CRC are excluded from the timeline by default (they
    remain counted in inventory/metrics, never silently replayed).
    """
    eligible: list[tuple[int, ParsedFrame]] = [
        (original_index, parsed)
        for original_index, parsed in enumerate(frames)
        if (parsed.record.crc_status.value == "PASS" or not only_valid_crc)
    ]
    if arrival_ms is not None and len(arrival_ms) != len(frames):
        raise ValueError(
            f"arrival schedule length {len(arrival_ms)} != frame count {len(frames)}"
        )
    events: list[ReplayEvent] = []
    base: int | None = None
    for sequence, (original_index, parsed) in enumerate(eligible):
        record = parsed.record
        if arrival_ms is not None:
            stamp_ms = arrival_ms[original_index]
        else:
            stamp_ms = sequence * nominal_interval_ms
        if base is None:
            base = stamp_ms
        events.append(
            ReplayEvent(
                sequence=sequence,
                source_offset=record.offset,
                message_number=record.message_number,
                frame_length=record.frame_length,
                original_timestamp=str(stamp_ms),
                relative_time_ms=stamp_ms - base,
                raw_hash=record.raw_hash,
            )
        )
    return events, None
