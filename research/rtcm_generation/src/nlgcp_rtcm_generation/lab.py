"""Synthetic-only Phase 9/10 composition helpers.

This adapter is intentionally local and in-memory. It does not open a socket,
connect to NATS, or publish to a caster.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from nlgcp_rtcm_generation.models import GeneratedCorrectionFrame, OutputClassification
from nlgcp_rtcm_replay.models import CorrectionFrame


def to_phase9_frame(
    frame: GeneratedCorrectionFrame,
    *,
    source_id: str = "phase11-synthetic-source",
    station_id: str = "SYNA00SYN",
    mountpoint: str = "SYNTHETIC",
) -> CorrectionFrame:
    if frame.classification != OutputClassification.SYNTHETIC_TEST_ONLY:
        raise ValueError("local lab adapter accepts synthetic frames only")
    return CorrectionFrame(
        sequence=0,
        cycle=0,
        source_id=source_id,
        station_id=station_id,
        mountpoint=mountpoint,
        message_number=frame.message_number,
        raw_bytes=frame.raw_bytes,
        source_timestamp=None,
        replay_timestamp="2026-01-01T00:00:00Z",
        provenance={
            "classification": str(frame.classification),
            "frame_sha256": frame.frame_sha256,
            "request_fingerprint": frame.request_fingerprint,
        },
    )


@dataclass(slots=True)
class LocalLabConsumer:
    frames: list[CorrectionFrame] = field(default_factory=list)

    def consume(self, frame: CorrectionFrame) -> None:
        self.frames.append(frame)
