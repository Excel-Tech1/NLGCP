"""SYNTHETIC TEST DATA — NOT VALID FOR SCIENTIFIC RESULTS.

Milestone B-08 runtime integration, event bus, Phase 8 -> Phase 11 bridge,
and Day 7 security hardening (SEC-03, SEC-04, SEC-07, SEC-09, SEC-11) tests.
"""

from __future__ import annotations

import base64
import socket
import threading
import time

import pytest
from nlgcp_correction_service import DEFAULT_MOUNTPOINT, LOOPBACK_HOST
from nlgcp_correction_service.caster import LocalNtripCaster
from nlgcp_correction_service.config import CasterConfig, ClientConfig
from nlgcp_correction_service.decision_bridge import (
    BridgeInputContext,
    DecisionBridgeError,
    decision_to_generation_request,
    execute_decision_to_rtcm,
)
from nlgcp_correction_service.events import (
    BoundedEventBus,
    EventContractError,
    EventEnvelope,
    NatsJetStreamConfig,
    build_decision_event,
    build_ingested_frame_event,
    build_rtcm_generated_event,
    build_security_audit_event,
    probe_nats_endpoint,
    validate_subject,
)
from nlgcp_hybrid_decision.models import (
    CorrectionDecision,
    CorrectionMode,
    DecisionStatus,
    IntegrityStatus,
    SpatialModelStatus,
    VRSStatus,
)
from nlgcp_hybrid_decision.models import ReasonCode as Phase8ReasonCode
from nlgcp_rtcm_generation import ENCODER_VERSION_1005
from nlgcp_rtcm_generation.models import (
    CoordinateProvenance,
    GenerationMode,
    GenerationStatus,
    OutputClassification,
    ReasonCode,
    VerificationState,
)


def _sample_phase8_decision(mode: CorrectionMode, status: DecisionStatus) -> CorrectionDecision:
    return CorrectionDecision(
        decision_id="dec-b08-001",
        request_id="req-b08-001",
        timestamp="2026-11-27T00:00:00Z",
        mode=mode,
        status=status,
        reason_code=(
            Phase8ReasonCode.SINGLE_BASE_SELECTED
            if mode == CorrectionMode.SINGLE_BASE
            else Phase8ReasonCode.VRS_MODEL_NOT_VALIDATED
        ),
        reason_text="synthetic B-08 bridge test decision",
        selected_reference="EKAK00NGA" if mode == CorrectionMode.SINGLE_BASE else None,
        selected_vrs_experiment="vrs-exp-001" if mode == CorrectionMode.VRS else None,
        spatial_model_status=SpatialModelStatus.PROVISIONAL,
        vrs_status=VRSStatus.BLOCKED,
        integrity_status=IntegrityStatus.PASS,
        decision_fingerprint="a" * 64,
    )


def _synthetic_coord() -> CoordinateProvenance:
    return CoordinateProvenance(
        station_id="SYNA00SYN",
        ecef_xyz_m=(111111.1111, -222222.2222, 3333333.3333),
        reference_frame="SYNTHETIC_FRAME",
        coordinate_epoch="2026-01-01T00:00:00Z",
        source="SYNTHETIC TEST DATA",
        fingerprint="synth-coord-fp",
        verification_state=VerificationState.SYNTHETIC_TEST_ONLY,
    )


def test_events_contracts_subject_validation_and_bounded_bus() -> None:
    assert validate_subject("correction.live.EKAK00NGA") == "correction.live.EKAK00NGA"
    with pytest.raises(EventContractError):
        validate_subject("arbitrary.topic.bad")
    with pytest.raises(EventContractError):
        validate_subject("correction.live.bad token")

    bus = BoundedEventBus(max_retained=2)
    received: list[EventEnvelope] = []
    bus.subscribe("correction.", received.append)

    e1 = build_ingested_frame_event(
        event_id="ev-1",
        station_id="EKAK00NGA",
        origin="replay",
        message_number=1005,
        frame_sha256="0" * 64,
        frame_length=25,
        crc_status="PASS",
        provider="synthetic-lab",
        data_classification="SYNTHETIC_TEST_ONLY",
    )
    e2 = build_decision_event(
        event_id="ev-2",
        station_id="EKAK00NGA",
        decision_id="dec-1",
        decision_fingerprint="1" * 64,
        mode="SINGLE_BASE",
        status="OK",
        reason_code="SINGLE_BASE_SELECTED",
        data_classification="SYNTHETIC_TEST_ONLY",
    )
    e3 = build_rtcm_generated_event(
        event_id="ev-3",
        mountpoint="NLGCP_TEST",
        request_id="req-1",
        decision_id="dec-1",
        message_families=("REFERENCE_STATION_1005",),
        frame_count=1,
        stream_sha256="2" * 64,
        data_classification="SYNTHETIC_TEST_ONLY",
    )
    for ev in (e1, e2, e3):
        bus.publish(ev)

    assert len(received) == 3
    stats = bus.stats()
    assert stats["published_total"] == 3
    assert stats["retained"] == 2
    assert stats["evicted_total"] == 1

    sec_ev = build_security_audit_event(
        event_id="sec-1",
        service="caster",
        severity="WARNING",
        reason_code="AUTH_FAILED",
        message="failed password=SUPER_SECRET_TOKEN",
        secrets=("SUPER_SECRET_TOKEN",),
    )
    assert "SUPER_SECRET_TOKEN" not in sec_ev.to_json_bytes().decode("utf-8")


def test_nats_jetstream_config_and_honest_unavailable_probe() -> None:
    cfg = NatsJetStreamConfig(host=LOOPBACK_HOST, port=1)
    cfg.validate()
    probe = probe_nats_endpoint(cfg)
    assert probe["reachable"] is False
    assert probe["status"] == "UNAVAILABLE"

    with pytest.raises(EventContractError):
        NatsJetStreamConfig(host="0.0.0.0").validate()


def test_phase8_to_phase11_bridge_fail_closed_and_synthetic_1005() -> None:
    # 1. Operational classification unconditionally forbidden
    dec_sb = _sample_phase8_decision(CorrectionMode.SINGLE_BASE, DecisionStatus.OK)
    with pytest.raises(DecisionBridgeError):
        decision_to_generation_request(
            dec_sb,
            BridgeInputContext(
                gnss_epoch="2026-01-01T00:00:00Z",
                coordinate=_synthetic_coord(),
                output_message_family="REFERENCE_STATION_1005",
                encoder_version=ENCODER_VERSION_1005,
                classification=OutputClassification.OPERATIONAL_APPROVED,
            ),
        )

    # 2. VRS decision stays strictly BLOCKED at Phase 11 admission
    dec_vrs = _sample_phase8_decision(CorrectionMode.VRS, DecisionStatus.OK)
    req_vrs, res_vrs = execute_decision_to_rtcm(
        dec_vrs,
        BridgeInputContext(
            gnss_epoch="2026-01-01T00:00:00Z",
            coordinate=_synthetic_coord(),
            output_message_family="REFERENCE_STATION_1005",
            encoder_version=ENCODER_VERSION_1005,
            input_source_fingerprint="src-fp",
            input_source_admitted=True,
            station_identity_verified=True,
            coordinate_verified=True,
            correction_model_fingerprint="mod-fp",
            correction_model_approved=True,
            classification=OutputClassification.SYNTHETIC_TEST_ONLY,
            synthetic_fixture=True,
        ),
    )
    assert req_vrs.mode == GenerationMode.VRS
    assert res_vrs.status == GenerationStatus.BLOCKED
    assert ReasonCode.VRS_OPERATIONAL_NOT_APPROVED in res_vrs.reason_codes

    # 3. Authentic single-base without admitted live input stays BLOCKED honestly
    _, res_auth_blocked = execute_decision_to_rtcm(
        dec_sb,
        BridgeInputContext(
            gnss_epoch="2026-01-01T00:00:00Z",
            coordinate=CoordinateProvenance(
                station_id="EKAK00NGA",
                ecef_xyz_m=(6296841.3252, 875621.0042, 512343.1243),
                reference_frame="IGS20",
                coordinate_epoch="2024-01-26",
                source="PRIDE",
                fingerprint="ekak-fp",
                verification_state=VerificationState.VERIFIED,
            ),
            output_message_family="REFERENCE_STATION_1005",
            encoder_version=ENCODER_VERSION_1005,
            input_source_admitted=False,
            classification=OutputClassification.RESEARCH_VALIDATION,
            synthetic_fixture=False,
        ),
    )
    assert res_auth_blocked.status == GenerationStatus.BLOCKED
    assert ReasonCode.AUTHENTIC_INPUT_SOURCE_UNAVAILABLE in res_auth_blocked.reason_codes

    # 4. Synthetic single-base fixture encodes RTCM 1005 cleanly end-to-end
    _, res_syn = execute_decision_to_rtcm(
        dec_sb,
        BridgeInputContext(
            gnss_epoch="2026-01-01T00:00:00Z",
            coordinate=_synthetic_coord(),
            output_message_family="REFERENCE_STATION_1005",
            encoder_version=ENCODER_VERSION_1005,
            input_source_fingerprint="synth-src-fp",
            input_source_admitted=True,
            station_identity_verified=True,
            coordinate_verified=True,
            correction_model_fingerprint="synth-mod-fp",
            correction_model_approved=True,
            classification=OutputClassification.SYNTHETIC_TEST_ONLY,
            synthetic_fixture=True,
        ),
        fields={
            "station_id": 1234,
            "itrf_realization_year": 0,
            "gps_indicator": True,
            "glonass_indicator": False,
            "galileo_indicator": False,
            "reference_station_indicator": False,
            "ecef_x_m": 111111.1111,
            "ecef_y_m": -222222.2222,
            "ecef_z_m": 3333333.3333,
            "oscillator_indicator": True,
            "quarter_cycle_indicator": 0,
        },
    )
    assert res_syn.status == GenerationStatus.ENCODED
    assert len(res_syn.frames) == 1
    assert res_syn.frames[0].message_number == 1005


def test_sec09_credentials_omitted_from_config_repr() -> None:
    secret_a = "VerySecretClientPass99"
    secret_b = "VerySecretSourcePass88"
    caster_cfg = CasterConfig(
        client_credentials={"user": secret_a},
        source_credentials={"src": secret_b},
    )
    client_cfg = ClientConfig(username="user", password=secret_a)
    assert secret_a not in repr(caster_cfg)
    assert secret_b not in repr(caster_cfg)
    assert secret_a not in repr(client_cfg)


def test_sec04_sec07_sec11_caster_hardening() -> None:
    cfg = CasterConfig(
        host=LOOPBACK_HOST,
        port=0,
        client_credentials={"labuser": "labpass"},
        source_credentials={"srcuser": "srcpass"},
        socket_timeout_s=0.35,
        max_sources=2,
        max_pre_auth_connections=8,
    )
    with LocalNtripCaster(cfg) as caster:
        # SEC-11: 405 records connection error + redacted fault event
        with socket.create_connection((caster.host, caster.port), timeout=2.0) as s:
            s.sendall(b"DELETE /NLGCP_TEST HTTP/1.1\r\nHost: 127.0.0.1\r\n\r\n")
            resp = s.recv(1024).decode("ascii", errors="replace")
            assert resp.startswith("HTTP/1.1 405")
        faults = caster.diagnostics.recent_faults_snapshot()
        assert any(f["event_type"] == "method_not_allowed" for f in faults)

        # SEC-07: Slowloris drip exceeding cumulative header deadline returns 400 promptly
        t0 = time.monotonic()
        with socket.create_connection((caster.host, caster.port), timeout=2.0) as s:
            s.sendall(b"GET / HTTP/1.1\r\nX-Slow: ")
            time.sleep(0.15)
            s.sendall(b"a")
            time.sleep(0.30)
            resp_slow = s.recv(1024).decode("ascii", errors="replace")
            assert resp_slow.startswith("HTTP/1.1 400")
        assert time.monotonic() - t0 < 2.0

        # SEC-04: Exclusive source lease rejects second concurrent publisher on same mountpoint
        auth_b64 = base64.b64encode(b"srcuser:srcpass").decode("ascii")
        src1 = socket.create_connection((caster.host, caster.port), timeout=2.0)
        try:
            src1.sendall(
                (
                    f"POST /{DEFAULT_MOUNTPOINT} HTTP/1.1\r\n"
                    f"Ntrip-Version: Ntrip/2.0\r\n"
                    f"Authorization: Basic {auth_b64}\r\n\r\n"
                ).encode("ascii")
            )
            r1 = src1.recv(1024).decode("ascii", errors="replace")
            assert "200 OK" in r1

            # Concurrent second source on the exact same mountpoint must get 503
            second_resp: list[str] = []

            def _try_second() -> None:
                with socket.create_connection((caster.host, caster.port), timeout=2.0) as src2:
                    src2.sendall(
                        (
                            f"POST /{DEFAULT_MOUNTPOINT} HTTP/1.1\r\n"
                            f"Ntrip-Version: Ntrip/2.0\r\n"
                            f"Authorization: Basic {auth_b64}\r\n\r\n"
                        ).encode("ascii")
                    )
                    second_resp.append(src2.recv(1024).decode("ascii", errors="replace"))

            t = threading.Thread(target=_try_second)
            t.start()
            t.join(timeout=3.0)
            assert second_resp and "503 Service Unavailable" in second_resp[0]
        finally:
            src1.close()
