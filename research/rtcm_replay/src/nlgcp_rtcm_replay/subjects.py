"""Downstream delivery subjects (§39-§40, Phase 10 interface).

Existing convention reserves ``correction.*`` (see
``docs/streaming-conventions.md``).  Replay publishes — when a transport
is attached in a later phase — under::

    correction.replay.<STATION_ID>

with the frame ordering key ``(source_id, cycle, sequence)`` and the
full provenance envelope retained on every ``CorrectionFrame``.  No
live NATS connection is opened in Phase 9; this module only standardises
names so Phase 10 live ingestion can reuse the same contract.  Tests
never require external infrastructure.
"""

from __future__ import annotations

from nlgcp_rtcm_replay.models import CorrectionFrame

SUBJECT_FAMILY = "correction"
REPLAY_SUBJECT_PREFIX = "correction.replay"


def replay_subject(station_id: str) -> str:
    """Subject for replayed frames of one station (no transport attached)."""
    station = station_id.strip().upper()
    if not station:
        raise ValueError("station_id must be non-empty")
    if any(c not in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for c in station):
        raise ValueError(f"unsafe station_id for subject: {station_id}")
    return f"{REPLAY_SUBJECT_PREFIX}.{station}"


def ordering_key(frame: CorrectionFrame) -> tuple[str, int, int]:
    """Stable ordering key retained across replay and live delivery."""
    return (frame.source_id, frame.cycle, frame.sequence)


def envelope(frame: CorrectionFrame) -> dict[str, object]:
    """Delivery envelope: ordering key + provenance, no file internals."""
    return {
        "subject": replay_subject(frame.station_id),
        "ordering_key": list(ordering_key(frame)),
        "frame": frame.as_dict(),
    }
