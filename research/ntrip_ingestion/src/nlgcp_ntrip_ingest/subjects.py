"""Downstream delivery subjects for live frames.

Live ingestion publishes — when a transport is attached — under::

    correction.live.<STATION_ID>

mirroring the Phase 9 ``correction.replay.<STATION_ID>`` family so a
single consumer contract covers both origins.  No transport is opened
by this module; names only.
"""

from __future__ import annotations

from nlgcp_ntrip_ingest.models import LiveFrame

SUBJECT_FAMILY = "correction"
LIVE_SUBJECT_PREFIX = "correction.live"


def live_subject(station_id: str) -> str:
    """Subject for live frames of one station (no transport attached)."""
    station = station_id.strip().upper()
    if not station:
        raise ValueError("station_id must be non-empty")
    if any(c not in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for c in station):
        raise ValueError(f"unsafe station_id for subject: {station_id}")
    return f"{LIVE_SUBJECT_PREFIX}.{station}"


def ordering_key(frame: LiveFrame) -> tuple[str, str, int]:
    """Stable ordering key: (connection_id, capture order, sequence)."""
    return (frame.connection_id, frame.provenance.get("capture_id", ""), frame.sequence)


def envelope(frame: LiveFrame) -> dict[str, object]:
    """Delivery envelope: ordering key + provenance, no file internals."""
    return {
        "subject": live_subject(frame.station_id),
        "ordering_key": list(ordering_key(frame)),
        "frame": frame.as_dict(),
    }
