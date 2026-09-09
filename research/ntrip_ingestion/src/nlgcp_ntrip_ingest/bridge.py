"""Phase 9 compatibility bridge.

A live ``LiveFrame`` converts losslessly onto the Phase 9
``CorrectionFrame`` consumer contract: replay timestamp carries the
delivery instant, source timestamp carries the genuine arrival
instant, and the live-only fields (connection, CRC state, provider,
arrival monotonic/offset, capture) travel inside ``provenance``.
Downstream consumers therefore cannot tell live apart from replay.
"""

from __future__ import annotations

from typing import Any

from nlgcp_ntrip_ingest.models import LiveFrame


def live_to_phase9(frame: LiveFrame, *, replay_timestamp: str, cycle: int = 0) -> Any:
    """Convert a live frame to the Phase 9 ``CorrectionFrame`` contract."""
    from nlgcp_rtcm_replay.models import CorrectionFrame

    provenance = dict(frame.provenance)
    provenance.update(
        {
            "origin": "LIVE_NTRIP",
            "provider": frame.provider,
            "connection_id": frame.connection_id,
            "crc_status": frame.crc_status,
            "arrival_timestamp": frame.arrival_timestamp,
            "gnss_epoch": frame.gnss_epoch,
        }
    )
    return CorrectionFrame(
        sequence=frame.sequence,
        cycle=cycle,
        source_id=provenance.get("capture_id", frame.connection_id),
        station_id=frame.station_id,
        mountpoint=frame.mountpoint,
        message_number=frame.message_number,
        raw_bytes=frame.raw_bytes,
        source_timestamp=frame.arrival_timestamp,
        replay_timestamp=replay_timestamp,
        provenance=provenance,
    )


def capture_source_for_phase9(
    *,
    source_id: str,
    source_path: str,
    station_id: str,
    mountpoint: str,
    byte_size: int,
    sha256: str,
    capture_method: str,
    capture_provenance: str,
) -> Any:
    """Build a Phase 9 ``RTCMSource`` of type NTRIP_CAPTURE for a capture."""
    from nlgcp_rtcm_replay.models import SourceType, source_from_dict

    return source_from_dict(
        {
            "source_id": source_id,
            "source_type": str(SourceType.NTRIP_CAPTURE),
            "source_path": source_path,
            "station_id": station_id,
            "mountpoint": mountpoint,
            "start_time": "",
            "end_time": "",
            "byte_size": byte_size,
            "sha256": sha256,
            "capture_method": capture_method,
            "capture_provenance": capture_provenance,
            "rtcm_version": "3.x",
            "message_types": [],
            "timestamp_source": "capture",
            "verified": False,
        }
    )


def admit_capture_for_phase9(source: Any, **kwargs: Any) -> Any:
    """Run Phase 9 admission unchanged on a Phase 10 capture (no rule changes)."""
    from nlgcp_rtcm_replay.admission import admit_source

    return admit_source(source, **kwargs)
