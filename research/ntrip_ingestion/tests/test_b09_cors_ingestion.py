"""SYNTHETIC TEST DATA — NOT VALID FOR SCIENTIFIC RESULTS.

Tests for Milestone B-09:
- Nigerian CORS provider catalogue & Stage B fail-closed BLOCKED_EXTERNAL_ACCESS
  (including SOGPOS / sacredioncors.com, NIGNET / OSGoF, CORSLocate);
- Stage A credential-free recorded RTCM ingestion -> CRC-24Q quarantine -> B-08
  BoundedEventBus (nlgcp.events.v1, correction.replay.<STATION>);
- Stage A local loopback NTRIP client -> B-08 BoundedEventBus
  (correction.live.<STATION>) end-to-end verification.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from nlgcp_correction_service import DEFAULT_MOUNTPOINT, LOOPBACK_HOST
from nlgcp_correction_service.caster import LocalNtripCaster
from nlgcp_correction_service.client import LocalNtripClient
from nlgcp_correction_service.config import CasterConfig, ClientConfig
from nlgcp_correction_service.events import BoundedEventBus, EventType
from nlgcp_ntrip_ingest.b09_ingestion import (
    ingest_recorded_rtcm_file_to_event_bus,
    ingest_rtcm_bytes_to_event_bus,
)
from nlgcp_ntrip_ingest.providers import (
    NIGERIAN_CORS_PROVIDERS,
    StageBStatus,
    evaluate_stage_b_provider_gate,
    get_provider_profile,
)
from nlgcp_rtcm_generation.framing import frame_message_payload
from nlgcp_rtcm_generation.messages import ReferenceStation1005


def _synthetic_1005_frame() -> bytes:
    msg = ReferenceStation1005(
        station_id=2001,
        itrf_realization_year=0,
        gps_indicator=True,
        glonass_indicator=False,
        galileo_indicator=False,
        reference_station_indicator=False,
        ecef_x_m=6296841.3252,
        ecef_y_m=875621.0042,
        ecef_z_m=512343.1243,
        oscillator_indicator=True,
        quarter_cycle_indicator=0,
    )
    return frame_message_payload(msg.encode())


def test_nigerian_provider_catalogue_and_stage_b_blocked_without_credentials() -> None:
    codes = {p.provider_code for p in NIGERIAN_CORS_PROVIDERS}
    assert {"NLGCP_LOCAL_STAGE_A", "SOGPOS_SACREDION", "NIGNET_OSGOF", "CORSLOCATE_NG"} <= codes

    sogpos = get_provider_profile("SOGPOS_SACREDION")
    assert sogpos.website_url == "https://www.sacredioncors.com/"
    assert sogpos.requires_account_credentials is True

    # Empty env -> strictly BLOCKED_EXTERNAL_ACCESS across all external providers
    for code in ("SOGPOS_SACREDION", "NIGNET_OSGOF", "CORSLOCATE_NG"):
        gate = evaluate_stage_b_provider_gate(code, env={})
        assert gate.status == StageBStatus.BLOCKED_EXTERNAL_ACCESS
        assert gate.external_connection_permitted is False
        assert len(gate.missing_prerequisites) == 6

    # Local Stage A does not require external credentials
    stage_a = evaluate_stage_b_provider_gate("NLGCP_LOCAL_STAGE_A", env={})
    assert stage_a.status == StageBStatus.STAGE_A_AVAILABLE_OFFLINE
    assert stage_a.external_connection_permitted is False


def test_stage_a_recorded_rtcm_quarantines_corrupt_and_emits_b08_events(tmp_path: Path) -> None:
    valid = _synthetic_1005_frame()
    corrupt = bytearray(valid)
    corrupt[-1] ^= 0xFF
    rtcm_file = tmp_path / "recorded_lab.rtcm3"
    rtcm_file.write_bytes(valid + bytes(corrupt) + valid)

    bus = BoundedEventBus(max_retained=100)
    # Verified station mapping -> publishes valid frames, quarantines corrupt frame
    summary, events = ingest_recorded_rtcm_file_to_event_bus(
        rtcm_file,
        event_bus=bus,
        mountpoint="EKAK_MOUNT",
        station_registry={"EKAK_MOUNT": "EKAK00NGA"},
        data_classification="SYNTHETIC_TEST_ONLY",
    )
    assert summary.station_id == "EKAK00NGA"
    assert summary.station_identity_verified is True
    assert summary.frames_parsed == 3
    assert summary.frames_crc_valid == 2
    assert summary.frames_crc_invalid_quarantined == 1
    assert summary.events_published == 2
    assert summary.operational_approved is False
    assert all(e.subject == "correction.replay.EKAK00NGA" for e in events)
    assert any(
        e.event_type == EventType.AUDIT_SECURITY
        and e.payload["reason_code"] == "RTCM_CRC24Q_QUARANTINED"
        for e in bus.recent()
    )

    # Unmapped mountpoint fails closed (0 frame events emitted by default)
    bus2 = BoundedEventBus(max_retained=100)
    summary2, events2 = ingest_recorded_rtcm_file_to_event_bus(
        rtcm_file,
        event_bus=bus2,
        mountpoint="UNMAPPED_MP",
        station_registry={},
        data_classification="SYNTHETIC_TEST_ONLY",
    )
    assert summary2.station_identity_verified is False
    assert summary2.events_published == 0
    assert events2 == []


def test_stage_a_loopback_ntrip_client_wired_to_b08_event_bus() -> None:
    frame = _synthetic_1005_frame()
    cfg = CasterConfig(
        host=LOOPBACK_HOST,
        port=0,
        client_credentials={"stagea": "stageapass"},
    )
    with LocalNtripCaster(cfg) as caster:
        caster.publish_raw_frame(frame)
        client = LocalNtripClient(
            ClientConfig(
                host=LOOPBACK_HOST,
                port=caster.port,
                mountpoint=DEFAULT_MOUNTPOINT,
                username="stagea",
                password="stageapass",
                read_timeout_s=1.0,
            )
        )
        res = client.receive_frames(max_frames=1)
        assert res.ok
        assert len(res.valid_frames) == 1

    bus = BoundedEventBus(max_retained=50)
    summary, events = ingest_rtcm_bytes_to_event_bus(
        res.valid_frames[0].raw,
        event_bus=bus,
        mountpoint=DEFAULT_MOUNTPOINT,
        station_registry={DEFAULT_MOUNTPOINT: "EKAK00NGA"},
        origin="live",
        data_classification="SYNTHETIC_TEST_ONLY",
    )
    assert summary.frames_crc_valid == 1
    assert summary.events_published == 1
    assert events[0].subject == "correction.live.EKAK00NGA"

    with pytest.raises(ValueError, match="OPERATIONAL_APPROVED"):
        ingest_rtcm_bytes_to_event_bus(
            frame,
            event_bus=bus,
            data_classification="OPERATIONAL_APPROVED",
        )
