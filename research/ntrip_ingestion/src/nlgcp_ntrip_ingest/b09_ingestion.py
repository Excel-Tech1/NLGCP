"""Stage A recorded and loopback RTCM ingestion wired to B-08 event contracts (B-09).

Connects Phase 10 ``StreamingFramer``, fail-closed mountpoint-to-station mapping,
and CRC-24Q quarantine directly to Milestone B-08's ``BoundedEventBus`` using
versioned ``nlgcp.events.v1`` envelopes (``correction.replay.<STATION>`` for
recorded files; ``correction.live.<STATION>`` for loopback client streams).

Strictly enforces:
- Zero raw-file mutation (read-only ingestion of recorded `.rtcm3` streams);
- Corrupt CRC-24Q frames are quarantined (counted, never forwarded to event bus);
- Unmapped mountpoints remain ``STATION_IDENTITY_UNVERIFIED`` (fail-closed);
- Operational approval remains ``False`` and scientific validity remains
  ``NOT_ASSESSED_TRANSPORT_ONLY``.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from nlgcp_correction_service.events import (
    BoundedEventBus,
    EventEnvelope,
    build_ingested_frame_event,
    build_security_audit_event,
)

from nlgcp_ntrip_ingest.admission import STATION_IDENTITY_UNVERIFIED, map_station
from nlgcp_ntrip_ingest.framing import StreamingFramer


@dataclass(frozen=True, slots=True)
class StageAIngestionSummary:
    """Machine-readable audit summary for one Stage A ingestion run."""

    session_uuid: str
    provider_code: str
    mountpoint: str
    station_id: str
    station_identity_verified: bool
    origin: str
    data_classification: str
    source_path: str | None
    source_sha256: str
    bytes_read: int
    frames_parsed: int
    frames_crc_valid: int
    frames_crc_invalid_quarantined: int
    events_published: int
    message_type_counts: dict[str, int]
    scientific_validity: str = "NOT_ASSESSED_TRANSPORT_ONLY"
    operational_approved: bool = False

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def ingest_rtcm_bytes_to_event_bus(
    raw_bytes: bytes,
    *,
    event_bus: BoundedEventBus,
    provider_code: str = "NLGCP_LOCAL_STAGE_A",
    mountpoint: str = "NLGCP_TEST",
    station_registry: dict[str, str] | None = None,
    origin: str = "replay",
    data_classification: str = "SYNTHETIC_TEST_ONLY",
    source_path: str | None = None,
    chunk_size: int = 256,
    allow_unverified_station_events: bool = False,
) -> tuple[StageAIngestionSummary, list[EventEnvelope]]:
    """Parse RTCM 3.x bytes incrementally and emit versioned B-08 frame events."""
    if data_classification == "OPERATIONAL_APPROVED":
        raise ValueError("OPERATIONAL_APPROVED classification is forbidden in Stage A ingestion")
    if origin not in ("replay", "live"):
        raise ValueError(f"origin must be 'replay' or 'live', got {origin!r}")

    session_uuid = str(uuid.uuid4())
    mapping = map_station(mountpoint, station_registry or {})
    station_id = mapping.station_id
    source_sha256 = hashlib.sha256(raw_bytes).hexdigest()

    framer = StreamingFramer()
    frames_parsed = 0
    frames_valid = 0
    frames_invalid = 0
    msg_counts: dict[str, int] = {}
    published_events: list[EventEnvelope] = []

    step = max(1, chunk_size)
    for offset in range(0, len(raw_bytes), step):
        chunk = raw_bytes[offset : offset + step]
        for streamed in framer.feed(chunk):
            frames_parsed += 1
            if not streamed.crc_ok:
                frames_invalid += 1
                event_bus.publish(
                    build_security_audit_event(
                        event_id=f"{session_uuid}:crc:{frames_parsed}",
                        service="nlgcp-ingestor",
                        severity="WARNING",
                        reason_code="RTCM_CRC24Q_QUARANTINED",
                        message=(
                            f"quarantined corrupt frame seq={frames_parsed} "
                            f"mountpoint={mountpoint} len={len(streamed.raw)}"
                        ),
                    )
                )
                continue

            frames_valid += 1
            msg_no = streamed.message_number or 0
            msg_key = str(msg_no)
            msg_counts[msg_key] = msg_counts.get(msg_key, 0) + 1

            # Fail closed on unverified station identity unless diagnostic explicitly requested
            if not mapping.verified and not allow_unverified_station_events:
                continue

            target_station = (
                station_id if station_id != STATION_IDENTITY_UNVERIFIED else "UNVERIFIED"
            )
            ev = build_ingested_frame_event(
                event_id=f"{session_uuid}:f:{frames_valid}",
                station_id=target_station,
                origin=origin,
                message_number=msg_no,
                frame_sha256=hashlib.sha256(streamed.raw).hexdigest(),
                frame_length=len(streamed.raw),
                crc_status="PASS",
                provider=provider_code,
                data_classification=data_classification,
            )
            event_bus.publish(ev)
            published_events.append(ev)

    summary = StageAIngestionSummary(
        session_uuid=session_uuid,
        provider_code=provider_code,
        mountpoint=mountpoint,
        station_id=station_id,
        station_identity_verified=mapping.verified,
        origin=origin,
        data_classification=data_classification,
        source_path=source_path,
        source_sha256=source_sha256,
        bytes_read=len(raw_bytes),
        frames_parsed=frames_parsed,
        frames_crc_valid=frames_valid,
        frames_crc_invalid_quarantined=frames_invalid,
        events_published=len(published_events),
        message_type_counts=msg_counts,
    )
    return summary, published_events


def ingest_recorded_rtcm_file_to_event_bus(
    rtcm_path: Path,
    *,
    event_bus: BoundedEventBus,
    provider_code: str = "NLGCP_LOCAL_STAGE_A",
    mountpoint: str = "NLGCP_VRS_EXP",
    station_registry: dict[str, str] | None = None,
    data_classification: str = "RESEARCH_VALIDATION",
    allow_unverified_station_events: bool = False,
) -> tuple[StageAIngestionSummary, list[EventEnvelope]]:
    """Read-only Stage A recorded RTCM ingestion into B-08 BoundedEventBus."""
    if not rtcm_path.is_file():
        raise FileNotFoundError(f"recorded RTCM file not found: {rtcm_path}")
    raw = rtcm_path.read_bytes()
    return ingest_rtcm_bytes_to_event_bus(
        raw,
        event_bus=event_bus,
        provider_code=provider_code,
        mountpoint=mountpoint,
        station_registry=station_registry,
        origin="replay",
        data_classification=data_classification,
        source_path=str(rtcm_path),
        allow_unverified_station_events=allow_unverified_station_events,
    )
