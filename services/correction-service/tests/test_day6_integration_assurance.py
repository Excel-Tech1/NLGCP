"""SYNTHETIC TEST DATA — NOT VALID FOR NAVIGATION OR SCIENTIFIC POSITIONING RESULTS.

Day 6 integration assurance suite spanning Phase 9 (RTCM framing/CRC-24Q),
Phase 10 (NTRIP handshake/streaming framer/backoff/redaction), Phase 11
(RTCM 1005/1074/1084 generation, admission gates, handoff artifacts), and
Phase 12 (loopback-only local NTRIP caster, broker, client, diagnostics).
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import logging
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

import pytest
from nlgcp_correction_service import (
    DEFAULT_MOUNTPOINT,
    LOOPBACK_HOST,
    SCIENTIFIC_READINESS_STATUS,
    SYNTHETIC_MOUNTPOINT_LABEL,
)
from nlgcp_correction_service.auth import basic_auth_header
from nlgcp_correction_service.caster import LocalNtripCaster
from nlgcp_correction_service.client import LocalNtripClient
from nlgcp_correction_service.config import CasterConfig, ClientConfig, ConfigurationError
from nlgcp_correction_service.mountpoints import MountpointDefinition, MountpointRegistry
from nlgcp_correction_service.pipeline import (
    LAB_SYNTHETIC_1005_FIELDS,
    _synthetic_phase11_request,
    generate_phase11_synthetic_bundle,
    run_local_end_to_end_demo,
)
from nlgcp_correction_service.publisher import PublicationError
from nlgcp_correction_service.validation import FrameValidationError, validate_generated_frame
from nlgcp_ntrip_ingest.backoff import ReconnectPolicy
from nlgcp_ntrip_ingest.models import FailureClass
from nlgcp_rtcm_generation import ENCODER_VERSION_1005
from nlgcp_rtcm_generation.generator import CorrectionGenerator
from nlgcp_rtcm_generation.handoff import CorrectionStreamArtifact
from nlgcp_rtcm_generation.independent_decoder import (
    IndependentDecoderUnavailable,
    decode_with_convbin,
    locate_convbin,
)
from nlgcp_rtcm_generation.models import (
    GenerationMode,
    GenerationStatus,
    OutputClassification,
    ReasonCode,
)
from nlgcp_rtcm_generation.registry import (
    MessageFamily,
    MessageFamilyRegistry,
    MessageFamilyStatus,
)

DAY6_USER = "day6_rover"
DAY6_PASS = "day6_ephemeral_secret_XYZ_9012"
DAY6_SRC_USER = "day6_src"
DAY6_SRC_PASS = "day6_source_secret_ABC_3456"


def _make_caster(
    *,
    max_clients: int = 16,
    max_queue_frames: int = 256,
    mountpoints: tuple[MountpointDefinition, ...] | None = None,
) -> LocalNtripCaster:
    cfg = CasterConfig(
        host=LOOPBACK_HOST,
        port=0,
        mountpoint=DEFAULT_MOUNTPOINT,
        client_credentials={DAY6_USER: DAY6_PASS},
        source_credentials={DAY6_SRC_USER: DAY6_SRC_PASS},
        max_clients=max_clients,
        max_queue_frames=max_queue_frames,
    )
    registry = MountpointRegistry(mountpoints) if mountpoints is not None else None
    return LocalNtripCaster(cfg, registry=registry)


# ---------------------------------------------------------------------------
# Verification A: Pipeline Integrity (AC-02, AC-03, AC-04, AC-05)
# ---------------------------------------------------------------------------


def test_multi_client_concurrent_byte_exact_and_mountpoint_isolation() -> None:
    bundle = generate_phase11_synthetic_bundle()
    generator = CorrectionGenerator()
    expected_raw = [r.frames[0].raw_bytes for r in bundle]
    expected_hashes = [hashlib.sha256(b).hexdigest() for b in expected_raw]

    mountpoints = (
        MountpointDefinition(name=DEFAULT_MOUNTPOINT),
        MountpointDefinition(name="NLGCP_TEST_ALT"),
    )
    with _make_caster(max_clients=8, mountpoints=mountpoints) as caster:
        for res in bundle:
            caster.publish_phase11_result(
                res, mountpoint=DEFAULT_MOUNTPOINT, artifact=generator.handoff(res)
            )
        # Publish only 1005 to the alternate synthetic mountpoint to verify isolation.
        caster.publish_phase11_result(
            bundle[0], mountpoint="NLGCP_TEST_ALT", artifact=generator.handoff(bundle[0])
        )

        received_by_client: dict[int, list[bytes]] = {}
        errors: list[str] = []
        lock = threading.Lock()

        def _worker(idx: int, mount: str, count: int) -> None:
            client = LocalNtripClient(
                ClientConfig(
                    host=LOOPBACK_HOST,
                    port=caster.port,
                    mountpoint=mount,
                    username=DAY6_USER,
                    password=DAY6_PASS,
                    read_chunk_bytes=17,
                )
            )
            res = client.receive_frames(max_frames=count, allow_reconnect=False)
            with lock:
                if not res.ok or res.invalid_frames:
                    errors.append(f"client {idx} failed: {res.reason}")
                received_by_client[idx] = [f.raw for f in res.valid_frames]

        threads = [
            threading.Thread(target=_worker, args=(i, DEFAULT_MOUNTPOINT, 3))
            for i in range(4)
        ]
        threads.append(threading.Thread(target=_worker, args=(99, "NLGCP_TEST_ALT", 1)))
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5.0)
            assert not t.is_alive()

        assert errors == []
        for idx in range(4):
            assert received_by_client[idx] == expected_raw
            assert [hashlib.sha256(b).hexdigest() for b in received_by_client[idx]] == (
                expected_hashes
            )
        assert received_by_client[99] == [expected_raw[0]]


@pytest.mark.parametrize("chunk_bytes", [1, 3, 7, 13])
def test_irregular_tcp_fragmentation_preserves_crc_and_bytes(chunk_bytes: int) -> None:
    bundle = generate_phase11_synthetic_bundle()
    generator = CorrectionGenerator()
    expected = [r.frames[0].raw_bytes for r in bundle]

    with _make_caster() as caster:
        for res in bundle:
            caster.publish_phase11_result(res, artifact=generator.handoff(res))

        client = LocalNtripClient(
            ClientConfig(
                host=LOOPBACK_HOST,
                port=caster.port,
                mountpoint=DEFAULT_MOUNTPOINT,
                username=DAY6_USER,
                password=DAY6_PASS,
                read_chunk_bytes=chunk_bytes,
            )
        )
        recv = client.receive_frames(max_frames=3, allow_reconnect=False)
        assert recv.ok is True
        assert recv.invalid_frames == ()
        assert recv.diagnostics["crc_failures"] == 0
        assert [f.raw for f in recv.valid_frames] == expected
        assert [f.message_number for f in recv.valid_frames] == [1005, 1074, 1084]


def test_interruption_recovery_preserves_subsequent_frames_and_rtklib_decode() -> None:
    bundle = generate_phase11_synthetic_bundle()
    generator = CorrectionGenerator()

    with _make_caster() as caster:
        caster.publish_phase11_result(bundle[0], artifact=generator.handoff(bundle[0]))

        def _drop_then_publish_rest() -> None:
            deadline = time.monotonic() + 3.0
            while time.monotonic() < deadline:
                if caster.status_snapshot()["rtcm_frames_transmitted"] >= 1:
                    break
                time.sleep(0.01)
            caster.broker.clear_backlog(DEFAULT_MOUNTPOINT)
            caster.disconnect_clients(DEFAULT_MOUNTPOINT)
            time.sleep(0.05)
            for res in bundle[1:]:
                caster.publish_phase11_result(res, artifact=generator.handoff(res))

        ctrl = threading.Thread(target=_drop_then_publish_rest, daemon=True)
        ctrl.start()

        client = LocalNtripClient(
            ClientConfig(
                host=LOOPBACK_HOST,
                port=caster.port,
                mountpoint=DEFAULT_MOUNTPOINT,
                username=DAY6_USER,
                password=DAY6_PASS,
                read_timeout_s=1.0,
                reconnect_policy=ReconnectPolicy(
                    base_delay_s=0.05, max_delay_s=0.15, max_attempts=4
                ),
            )
        )
        recv = client.receive_frames(max_frames=3, allow_reconnect=True)
        ctrl.join(timeout=3.0)

        assert recv.ok is True
        assert recv.reconnection_attempts >= 1
        assert recv.invalid_frames == ()
        assert [f.raw for f in recv.valid_frames] == [r.frames[0].raw_bytes for r in bundle]

    try:
        convbin = locate_convbin()
    except IndependentDecoderUnavailable:
        pytest.skip("RTKLIB convbin binary is not installed")

    raws = [f.raw for f in recv.valid_frames]
    dec_g = decode_with_convbin(raws[0] + raws[1], binary=convbin)
    dec_r = decode_with_convbin(raws[2], binary=convbin)
    assert dec_g.station_id == 1234
    assert dec_g.approx_position_xyz == pytest.approx(
        (111111.1111, -222222.2222, 3333333.3333), abs=1e-4
    )
    assert dec_g.sys_obs_types["G"] == ("C1C", "L1C", "S1C", "C2P", "L2P", "S2P")
    assert dec_r.station_id == 3210
    assert dec_r.sys_obs_types["R"] == ("C1C", "S1C", "C2C", "S2C")


# ---------------------------------------------------------------------------
# Verification B: Admission Control (AC-06, AC-07, AC-08, AC-09)
# ---------------------------------------------------------------------------


def test_admission_valid_synthetic_result_publishes_to_nlgcp_test() -> None:
    bundle = generate_phase11_synthetic_bundle()
    generator = CorrectionGenerator()
    with _make_caster() as caster:
        published = caster.publish_phase11_result(
            bundle[0], mountpoint=DEFAULT_MOUNTPOINT, artifact=generator.handoff(bundle[0])
        )
        assert len(published) == 1
        assert published[0].message_number == 1005
        assert published[0].raw_bytes == bundle[0].frames[0].raw_bytes
        snap = caster.status_snapshot()
        assert snap["rtcm_frames_received"] == 1
        assert snap["rejected_frames"] == 0


def test_admission_rejects_rejected_blocked_and_reason_coded_results() -> None:
    generator = CorrectionGenerator()
    valid_res = generate_phase11_synthetic_bundle()[0]
    valid_art = generator.handoff(valid_res)

    # 1. NO_CORRECTION result from Phase 11
    no_corr_req = dataclasses.replace(
        _synthetic_phase11_request(
            request_id="d6-nocorr",
            family="REFERENCE_STATION_1005",
            encoder_version=ENCODER_VERSION_1005,
        ),
        mode=GenerationMode.NO_CORRECTION,
    )
    no_corr_res = generator.generate(no_corr_req, fields=dict(LAB_SYNTHETIC_1005_FIELDS))
    assert no_corr_res.status == GenerationStatus.NO_CORRECTION

    # 2. BLOCKED result from Phase 11 (unverified coordinate)
    blocked_req = dataclasses.replace(
        _synthetic_phase11_request(
            request_id="d6-blocked",
            family="REFERENCE_STATION_1005",
            encoder_version=ENCODER_VERSION_1005,
        ),
        coordinate_verified=False,
    )
    blocked_res = generator.generate(blocked_req, fields=dict(LAB_SYNTHETIC_1005_FIELDS))
    assert blocked_res.status == GenerationStatus.BLOCKED

    # 3. Crafted ACCEPTED result without encoded frames
    accepted_empty = dataclasses.replace(valid_res, status=GenerationStatus.ACCEPTED, frames=())

    # 4. Crafted ENCODED result carrying non-empty reason_codes
    reason_coded = dataclasses.replace(
        valid_res, reason_codes=(ReasonCode.CORRECTION_MODEL_NOT_APPROVED,)
    )

    with _make_caster() as caster:
        for bad_res, art in (
            (no_corr_res, generator.handoff(no_corr_res)),
            (blocked_res, generator.handoff(blocked_res)),
            (accepted_empty, valid_art),
            (reason_coded, valid_art),
        ):
            with pytest.raises(PublicationError):
                caster.publish_phase11_result(bad_res, artifact=art)
        snap = caster.status_snapshot()
        assert snap["rtcm_frames_received"] == 0
        assert snap["rejected_frames"] == 4


def test_admission_rejects_missing_or_invalid_stream_artifact() -> None:
    generator = CorrectionGenerator()
    valid_res = generate_phase11_synthetic_bundle()[0]
    valid_art = generator.handoff(valid_res)

    bad_artifacts: list[CorrectionStreamArtifact | None] = [
        None,
        dataclasses.replace(valid_art, schema_version=""),
        dataclasses.replace(valid_art, stream_id=""),
        dataclasses.replace(valid_art, provenance_fingerprint=""),
        dataclasses.replace(valid_art, provenance_fingerprint="tampered-fingerprint"),
        dataclasses.replace(valid_art, decision_id="different-decision"),
        dataclasses.replace(valid_art, mode=str(GenerationMode.VRS)),
        dataclasses.replace(valid_art, mode=str(GenerationMode.NO_CORRECTION)),
        dataclasses.replace(valid_art, generation_status=str(GenerationStatus.BLOCKED)),
        dataclasses.replace(
            valid_art, classification=str(OutputClassification.RESEARCH_VALIDATION)
        ),
        dataclasses.replace(
            valid_art, classification=str(OutputClassification.OPERATIONAL_APPROVED)
        ),
        dataclasses.replace(valid_art, message_families=("MSM4_GPS_1074",)),
        dataclasses.replace(valid_art, message_families=()),
    ]

    with _make_caster() as caster:
        for bad_art in bad_artifacts:
            with pytest.raises(PublicationError):
                caster.publish_phase11_result(valid_res, artifact=bad_art)
        snap = caster.status_snapshot()
        assert snap["rtcm_frames_received"] == 0
        assert snap["rejected_frames"] == len(bad_artifacts)


def test_admission_rejects_invalid_rtcm_frame_message_number_and_crc() -> None:
    generator = CorrectionGenerator()
    valid_res = generate_phase11_synthetic_bundle()[0]
    valid_art = generator.handoff(valid_res)
    good_frame = valid_res.frames[0]

    # 1. Invalid preamble (hash updated so preamble gate is exercised)
    bad_pre_bytes = b"\xd2" + good_frame.raw_bytes[1:]
    bad_pre_frame = dataclasses.replace(
        good_frame,
        raw_bytes=bad_pre_bytes,
        frame_sha256=hashlib.sha256(bad_pre_bytes).hexdigest(),
    )

    # 2. Invalid reserved header bits
    bad_rsv_bytes = bytes([good_frame.raw_bytes[0], good_frame.raw_bytes[1] | 0x80]) + (
        good_frame.raw_bytes[2:]
    )
    bad_rsv_frame = dataclasses.replace(
        good_frame,
        raw_bytes=bad_rsv_bytes,
        frame_sha256=hashlib.sha256(bad_rsv_bytes).hexdigest(),
    )

    # 3. Truncated frame
    trunc_bytes = good_frame.raw_bytes[:-2]
    trunc_frame = dataclasses.replace(
        good_frame,
        raw_bytes=trunc_bytes,
        frame_sha256=hashlib.sha256(trunc_bytes).hexdigest(),
    )

    # 4. SHA-256 metadata mismatch
    sha_mismatch_frame = dataclasses.replace(good_frame, frame_sha256="0" * 64)

    # 5. Incorrect message number (payload is 1005, metadata says 1074)
    wrong_num_frame = dataclasses.replace(good_frame, message_number=1074)

    # 6. Family/message mismatch (payload is 1074, metadata claims REFERENCE_STATION_1005)
    frame_1074 = generate_phase11_synthetic_bundle()[1].frames[0]
    payload_mismatch_frame = dataclasses.replace(
        good_frame,
        raw_bytes=frame_1074.raw_bytes,
        frame_sha256=frame_1074.frame_sha256,
    )

    # 7. Invalid CRC-24Q
    bad_crc_bytes = bytearray(good_frame.raw_bytes)
    bad_crc_bytes[-1] ^= 0x01
    bad_crc_frame = dataclasses.replace(
        good_frame,
        raw_bytes=bytes(bad_crc_bytes),
        frame_sha256=hashlib.sha256(bytes(bad_crc_bytes)).hexdigest(),
    )

    with _make_caster() as caster:
        for bad_frame in (
            bad_pre_frame,
            bad_rsv_frame,
            trunc_frame,
            sha_mismatch_frame,
            wrong_num_frame,
            payload_mismatch_frame,
        ):
            crafted = dataclasses.replace(valid_res, frames=(bad_frame,))
            with pytest.raises(PublicationError):
                caster.publish_phase11_result(crafted, artifact=valid_art)

        crc_res = dataclasses.replace(valid_res, frames=(bad_crc_frame,))
        with pytest.raises(PublicationError, match="CRC-24Q"):
            caster.publish_phase11_result(crc_res, artifact=valid_art)

        snap = caster.status_snapshot()
        assert snap["rtcm_frames_received"] == 0
        assert snap["crc_failures"] == 1
        assert snap["rejected_frames"] == 7


def test_admission_rejects_non_synthetic_operational_approved_and_vrs() -> None:
    generator = CorrectionGenerator()
    valid_res = generate_phase11_synthetic_bundle()[0]
    valid_art = generator.handoff(valid_res)

    # 1. Phase 11 request with OPERATIONAL_APPROVED is blocked by Phase 11
    op_req = dataclasses.replace(
        _synthetic_phase11_request(
            request_id="d6-op",
            family="REFERENCE_STATION_1005",
            encoder_version=ENCODER_VERSION_1005,
        ),
        classification=OutputClassification.OPERATIONAL_APPROVED,
        synthetic_fixture=False,
    )
    op_phase11_res = generator.generate(op_req, fields=dict(LAB_SYNTHETIC_1005_FIELDS))
    assert op_phase11_res.status == GenerationStatus.BLOCKED
    assert ReasonCode.OPERATIONAL_CLASSIFICATION_FORBIDDEN in op_phase11_res.reason_codes

    # 2. Phase 11 VRS request is blocked by Phase 11
    vrs_req = dataclasses.replace(
        _synthetic_phase11_request(
            request_id="d6-vrs",
            family="REFERENCE_STATION_1005",
            encoder_version=ENCODER_VERSION_1005,
        ),
        mode=GenerationMode.VRS,
        virtual_station_id="VRS001",
    )
    vrs_phase11_res = generator.generate(vrs_req, fields=dict(LAB_SYNTHETIC_1005_FIELDS))
    assert vrs_phase11_res.status == GenerationStatus.BLOCKED
    assert ReasonCode.VRS_OPERATIONAL_NOT_APPROVED in vrs_phase11_res.reason_codes

    # 3. Crafted results bypassing Phase 11 must still fail closed at Phase 12
    with _make_caster() as caster:
        for bad_cls in (
            OutputClassification.DIAGNOSTIC_ONLY,
            OutputClassification.RESEARCH_VALIDATION,
            OutputClassification.OPERATIONAL_APPROVED,
        ):
            crafted_res = dataclasses.replace(
                valid_res,
                classification=bad_cls,
                frames=(dataclasses.replace(valid_res.frames[0], classification=bad_cls),),
            )
            crafted_art = dataclasses.replace(valid_art, classification=str(bad_cls))
            with pytest.raises(PublicationError):
                caster.publish_phase11_result(crafted_res, artifact=crafted_art)
            with pytest.raises(PublicationError):
                caster.publish_raw_frame(valid_res.frames[0].raw_bytes, classification=bad_cls)

        # Crafted VRS result even with ENCODED status and synthetic classification
        crafted_vrs = dataclasses.replace(
            valid_res, mode=GenerationMode.VRS, virtual_station_id="VRS001"
        )
        crafted_vrs_art = dataclasses.replace(
            valid_art, mode=str(GenerationMode.VRS), virtual_station_id="VRS001"
        )
        with pytest.raises(PublicationError, match="VRS"):
            caster.publish_phase11_result(crafted_vrs, artifact=crafted_vrs_art)

        # Phase 11 blocked VRS and OPERATIONAL_APPROVED results also fail closed
        with pytest.raises(PublicationError):
            caster.publish_phase11_result(
                op_phase11_res, artifact=generator.handoff(op_phase11_res)
            )
        with pytest.raises(PublicationError):
            caster.publish_phase11_result(
                vrs_phase11_res, artifact=generator.handoff(vrs_phase11_res)
            )

        assert caster.status_snapshot()["rtcm_frames_received"] == 0


@pytest.mark.parametrize(
    "bad_status",
    [
        MessageFamilyStatus.DECLARED,
        MessageFamilyStatus.SCAFFOLDED,
        MessageFamilyStatus.BLOCKED,
        MessageFamilyStatus.REAL_INPUT_VALIDATED,
        MessageFamilyStatus.OPERATIONALLY_APPROVED,
    ],
)
def test_admission_rejects_unsupported_registry_statuses(
    bad_status: MessageFamilyStatus,
) -> None:
    generator = CorrectionGenerator()
    valid_res = generate_phase11_synthetic_bundle()[0]
    valid_art = generator.handoff(valid_res)

    custom_registry = MessageFamilyRegistry(
        (
            MessageFamily(
                "REFERENCE_STATION_1005",
                (1005,),
                "test override",
                bad_status,
                "test",
                encoder_key="rtcm1005",
            ),
        )
    )
    with pytest.raises(FrameValidationError, match="SYNTHETICALLY_VALIDATED"):
        validate_generated_frame(valid_res.frames[0], registry=custom_registry)

    with _make_caster() as caster:
        with pytest.raises(PublicationError, match="SYNTHETICALLY_VALIDATED"):
            caster.publish_phase11_result(
                valid_res, artifact=valid_art, registry=custom_registry
            )
        assert caster.status_snapshot()["rtcm_frames_received"] == 0


def test_admission_rejects_unknown_family_unregistered_mountpoint_and_partial_batch() -> None:
    generator = CorrectionGenerator()
    bundle = generate_phase11_synthetic_bundle()
    valid_res = bundle[0]
    valid_art = generator.handoff(valid_res)

    # Unknown message family
    unknown_frame = dataclasses.replace(valid_res.frames[0], message_family="UNKNOWN_9999")
    with pytest.raises(FrameValidationError, match="unsupported Phase 11 message family"):
        validate_generated_frame(unknown_frame)

    with _make_caster() as caster:
        # Unregistered mountpoint
        with pytest.raises(PublicationError, match="unknown mountpoint"):
            caster.publish_phase11_result(
                valid_res, mountpoint="UNREGISTERED_MP", artifact=valid_art
            )

        # Atomic multi-frame rejection: valid frame 1 + CRC-corrupted frame 2 -> 0 published
        frame2 = bundle[1].frames[0]
        corrupt2_bytes = bytearray(frame2.raw_bytes)
        corrupt2_bytes[-1] ^= 0xFF
        corrupt2_frame = dataclasses.replace(
            frame2,
            raw_bytes=bytes(corrupt2_bytes),
            frame_sha256=hashlib.sha256(bytes(corrupt2_bytes)).hexdigest(),
        )
        batch_res = dataclasses.replace(
            valid_res, frames=(valid_res.frames[0], corrupt2_frame)
        )
        batch_art = dataclasses.replace(
            valid_art,
            message_families=("REFERENCE_STATION_1005", "MSM4_GPS_1074"),
        )
        with pytest.raises(PublicationError, match="CRC-24Q"):
            caster.publish_phase11_result(batch_res, artifact=batch_art)

        snap = caster.status_snapshot()
        assert snap["rtcm_frames_received"] == 0
        assert snap["crc_failures"] == 1


# ---------------------------------------------------------------------------
# Verification C: Fault Propagation & Resource Bounds (AC-10..AC-13)
# ---------------------------------------------------------------------------


def test_fault_rtcm_generator_failure_propagates_fail_closed() -> None:
    generator = CorrectionGenerator()
    req = _synthetic_phase11_request(
        request_id="d6-bad-fields",
        family="REFERENCE_STATION_1005",
        encoder_version=ENCODER_VERSION_1005,
    )
    # Missing required ECEF fields -> Phase 11 returns BLOCKED with MISSING_REQUIRED_FIELD
    bad_fields_res = generator.generate(req, fields={"station_id": 1234})
    assert bad_fields_res.status == GenerationStatus.BLOCKED
    assert ReasonCode.MISSING_REQUIRED_FIELD in bad_fields_res.reason_codes

    # Out-of-range coordinate -> Phase 11 returns BLOCKED with OUT_OF_RANGE_FIELD
    oor_fields = dict(LAB_SYNTHETIC_1005_FIELDS)
    oor_fields["ecef_x_m"] = 999_999_999.0
    oor_res = generator.generate(req, fields=oor_fields)
    assert oor_res.status == GenerationStatus.BLOCKED
    assert ReasonCode.OUT_OF_RANGE_FIELD in oor_res.reason_codes

    with _make_caster() as caster:
        for res in (bad_fields_res, oor_res):
            with pytest.raises(PublicationError):
                caster.publish_phase11_result(res, artifact=generator.handoff(res))
        snap = caster.status_snapshot()
        assert snap["rtcm_frames_received"] == 0
        assert snap["rejected_frames"] == 2


def test_fault_publisher_queue_saturation_is_bounded_and_isolated() -> None:
    bundle = generate_phase11_synthetic_bundle()
    generator = CorrectionGenerator()

    with _make_caster(max_queue_frames=2) as caster:
        slow_sub = caster.broker.subscribe(
            "slow-client", DEFAULT_MOUNTPOINT, DAY6_USER, replay_backlog=False
        )
        fast_sub = caster.broker.subscribe(
            "fast-client", DEFAULT_MOUNTPOINT, DAY6_USER, replay_backlog=False
        )
        try:
            # Publish 3 frames while slow_sub never drains (queue capacity = 2).
            fast_received: list[int] = []
            for res in bundle:
                caster.publish_phase11_result(res, artifact=generator.handoff(res))
                item = fast_sub.queue.get_nowait()
                assert item is not None
                fast_received.append(item.message_number)

            # Fast consumer received all 3 frames in FIFO order without blocking.
            assert fast_received == [1005, 1074, 1084]
            # Slow consumer retained first 2 frames bounded; 3rd counted as overflow.
            assert slow_sub.queue.qsize() == 2
            first = slow_sub.queue.get_nowait()
            second = slow_sub.queue.get_nowait()
            assert first is not None and first.message_number == 1005
            assert second is not None and second.message_number == 1074
            assert caster.status_snapshot()["queue_overflow_drops"] >= 1
        finally:
            caster.broker.unsubscribe(slow_sub)
            caster.broker.unsubscribe(fast_sub)


def test_fault_max_client_capacity_enforced_with_503_and_recovers() -> None:
    with _make_caster(max_clients=2) as caster:
        auth_hdr = basic_auth_header(DAY6_USER, DAY6_PASS)
        req = (
            f"GET /{DEFAULT_MOUNTPOINT} HTTP/1.1\r\n"
            f"Host: 127.0.0.1:{caster.port}\r\n"
            "Ntrip-Version: Ntrip/2.0\r\n"
            f"Authorization: {auth_hdr}\r\n\r\n"
        ).encode("ascii")

        s1 = socket.create_connection((LOOPBACK_HOST, caster.port), timeout=2.0)
        s2 = socket.create_connection((LOOPBACK_HOST, caster.port), timeout=2.0)
        try:
            s1.sendall(req)
            s2.sendall(req)
            assert s1.recv(1024).startswith(b"HTTP/1.1 200 OK")
            assert s2.recv(1024).startswith(b"HTTP/1.1 200 OK")
            assert caster.status_snapshot()["active_clients"] == 2

            # 3rd client must receive 503 Service Unavailable and not exceed capacity.
            with socket.create_connection((LOOPBACK_HOST, caster.port), timeout=2.0) as s3:
                s3.settimeout(2.0)
                s3.sendall(req)
                resp3 = s3.recv(1024).decode("ascii", errors="replace")
                assert resp3.startswith("HTTP/1.1 503 Service Unavailable")
            snap = caster.status_snapshot()
            assert snap["active_clients"] == 2
            assert snap["connection_errors"] >= 1
        finally:
            s1.close()

        # Wait for caster to observe s1 closed and free one slot.
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline:
            if caster.status_snapshot()["active_clients"] == 1:
                break
            time.sleep(0.02)
        assert caster.status_snapshot()["active_clients"] == 1

        # New client can now connect into the freed slot.
        with socket.create_connection((LOOPBACK_HOST, caster.port), timeout=2.0) as s4:
            s4.settimeout(2.0)
            s4.sendall(req)
            assert s4.recv(1024).startswith(b"HTTP/1.1 200 OK")
        s2.close()


def test_fault_unsupported_method_malformed_source_and_v1_corrupt_source_push() -> None:
    bundle = generate_phase11_synthetic_bundle()
    raw_1005 = bundle[0].frames[0].raw_bytes
    corrupt = bytearray(raw_1005)
    corrupt[-1] ^= 0x55
    truncated = raw_1005[:-4]

    with _make_caster() as caster:
        # Unsupported HTTP method -> 405
        with socket.create_connection((LOOPBACK_HOST, caster.port), timeout=2.0) as s:
            s.sendall(b"DELETE /NLGCP_TEST HTTP/1.1\r\nHost: 127.0.0.1\r\n\r\n")
            resp = s.recv(1024).decode("ascii", errors="replace")
            assert resp.startswith("HTTP/1.1 405 Method Not Allowed")

        # Malformed SOURCE line -> 400
        with socket.create_connection((LOOPBACK_HOST, caster.port), timeout=2.0) as s:
            s.sendall(b"SOURCE onlyonearg\r\n\r\n")
            resp = s.recv(1024).decode("ascii", errors="replace")
            assert resp.startswith("HTTP/1.1 400 Bad Request")

        # Valid v1 SOURCE push containing corrupt frame + valid frame + trailing truncation
        with socket.create_connection((LOOPBACK_HOST, caster.port), timeout=2.0) as s:
            s.sendall(f"SOURCE {DAY6_SRC_PASS} /{DEFAULT_MOUNTPOINT}\r\n\r\n".encode("ascii"))
            resp = s.recv(1024).decode("ascii", errors="replace")
            assert resp.startswith("ICY 200 OK")
            s.sendall(bytes(corrupt) + raw_1005 + truncated)
            time.sleep(0.1)

        snap = caster.status_snapshot()
        assert snap["crc_failures"] == 1
        assert snap["rtcm_frames_received"] == 1
        assert snap["message_types_observed"] == {1005: 1}


def test_fault_prolonged_inactivity_timeout_and_reconnection_exhaustion() -> None:
    sleeps: list[float] = []
    with _make_caster() as caster:
        client = LocalNtripClient(
            ClientConfig(
                host=LOOPBACK_HOST,
                port=caster.port,
                mountpoint=DEFAULT_MOUNTPOINT,
                username=DAY6_USER,
                password=DAY6_PASS,
                read_timeout_s=0.15,
                reconnect_policy=ReconnectPolicy(
                    base_delay_s=0.05, max_delay_s=0.1, max_attempts=2
                ),
            ),
            sleep_fn=sleeps.append,
        )
        res = client.receive_frames(max_frames=1, allow_reconnect=True)
        assert res.ok is False
        assert res.failure == FailureClass.TIMEOUT
        assert res.reconnection_attempts == 2
        assert sleeps == [pytest.approx(0.05), pytest.approx(0.1)]
        assert res.diagnostics["connection_state"] == "DISCONNECTED"
        assert res.diagnostics["health"]["STREAM_HEALTH"] == "EMPTY"
        assert res.diagnostics["health"]["RTCM_FRAME_HEALTH"] == "NO_FRAMES"
        assert res.diagnostics["connection_errors"] >= 3


def test_fault_credentials_never_leak_in_logs_or_diagnostics(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG, logger="nlgcp.correction_service")
    b64_client = basic_auth_header(DAY6_USER, DAY6_PASS).split()[1]
    b64_source = basic_auth_header(DAY6_SRC_USER, DAY6_SRC_PASS).split()[1]

    with _make_caster() as caster:
        # Trigger auth failure, unknown mountpoint, valid stream, and reconnect log paths
        bad_client = LocalNtripClient(
            ClientConfig(
                host=LOOPBACK_HOST,
                port=caster.port,
                mountpoint=DEFAULT_MOUNTPOINT,
                username=DAY6_USER,
                password=DAY6_PASS + "_wrong",
            )
        )
        r_bad = bad_client.receive_frames(max_frames=1, allow_reconnect=False)
        assert r_bad.status_code == 401

        unk_client = LocalNtripClient(
            ClientConfig(
                host=LOOPBACK_HOST,
                port=caster.port,
                mountpoint="NO_SUCH_MP",
                username=DAY6_USER,
                password=DAY6_PASS,
            )
        )
        r_unk = unk_client.receive_frames(max_frames=1, allow_reconnect=False)
        assert r_unk.status_code == 404

        good_client = LocalNtripClient(
            ClientConfig(
                host=LOOPBACK_HOST,
                port=caster.port,
                mountpoint=DEFAULT_MOUNTPOINT,
                username=DAY6_USER,
                password=DAY6_PASS,
                read_timeout_s=0.1,
                reconnect_policy=ReconnectPolicy(
                    base_delay_s=0.01, max_delay_s=0.02, max_attempts=1
                ),
            )
        )
        r_good = good_client.receive_frames(max_frames=1, allow_reconnect=True)
        caster_snap = caster.status_snapshot()

    combined_text = "\n".join(
        [
            caplog.text,
            json.dumps(caster_snap, default=str),
            json.dumps(r_bad.diagnostics, default=str),
            json.dumps(r_unk.diagnostics, default=str),
            json.dumps(r_good.diagnostics, default=str),
        ]
    )
    for secret in (DAY6_PASS, DAY6_SRC_PASS, b64_client, b64_source):
        assert secret not in combined_text


# ---------------------------------------------------------------------------
# Verification D: Separated Diagnostics (AC-14)
# ---------------------------------------------------------------------------


def test_diagnostics_five_categories_remain_distinct_across_states() -> None:
    bundle = generate_phase11_synthetic_bundle()
    generator = CorrectionGenerator()

    caster = _make_caster()
    # 0. Before start
    pre = caster.status_snapshot()["health"]
    assert set(pre.keys()) == {
        "SERVICE_HEALTH",
        "CONNECTION_HEALTH",
        "STREAM_HEALTH",
        "RTCM_FRAME_HEALTH",
        "SCIENTIFIC_READINESS",
    }
    assert pre["SERVICE_HEALTH"] == "STOPPED"
    assert pre["SCIENTIFIC_READINESS"] == SCIENTIFIC_READINESS_STATUS

    caster.start()
    try:
        # 1. Running caster, zero clients, zero frames:
        #    caster availability != stream availability.
        idle = caster.status_snapshot()["health"]
        assert idle["SERVICE_HEALTH"] == "HEALTHY"
        assert idle["CONNECTION_HEALTH"] == "IDLE"
        assert idle["STREAM_HEALTH"] == "IDLE"
        assert idle["RTCM_FRAME_HEALTH"] == "NO_FRAMES"
        assert idle["SCIENTIFIC_READINESS"] == SCIENTIFIC_READINESS_STATUS

        # 2. Client connected to empty mountpoint:
        #    connected client != receiving valid RTCM.
        auth_hdr = basic_auth_header(DAY6_USER, DAY6_PASS)
        with socket.create_connection((LOOPBACK_HOST, caster.port), timeout=2.0) as s:
            s.sendall(
                (
                    f"GET /{DEFAULT_MOUNTPOINT} HTTP/1.1\r\n"
                    f"Host: 127.0.0.1:{caster.port}\r\n"
                    "Ntrip-Version: Ntrip/2.0\r\n"
                    f"Authorization: {auth_hdr}\r\n\r\n"
                ).encode("ascii")
            )
            assert s.recv(1024).startswith(b"HTTP/1.1 200 OK")
            connected_no_frames = caster.status_snapshot()["health"]
            assert connected_no_frames["SERVICE_HEALTH"] == "HEALTHY"
            assert connected_no_frames["CONNECTION_HEALTH"] == "ACTIVE_CLIENTS"
            assert connected_no_frames["STREAM_HEALTH"] == "IDLE"
            assert connected_no_frames["RTCM_FRAME_HEALTH"] == "NO_FRAMES"
            assert connected_no_frames["SCIENTIFIC_READINESS"] == SCIENTIFIC_READINESS_STATUS

        # 3. Frames published without active client -> PUBLISHED_WAITING_CLIENTS
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline and caster.status_snapshot()["active_clients"] > 0:
            time.sleep(0.02)
        caster.publish_phase11_result(bundle[0], artifact=generator.handoff(bundle[0]))
        published = caster.status_snapshot()["health"]
        assert published["STREAM_HEALTH"] == "PUBLISHED_WAITING_CLIENTS"
        assert published["RTCM_FRAME_HEALTH"] == "VALID_TRANSPORT_FRAMES"
        assert published["SCIENTIFIC_READINESS"] == SCIENTIFIC_READINESS_STATUS

        # 4. Client receives valid CRC frame -> transport valid, science STILL NOT READY
        client = LocalNtripClient(
            ClientConfig(
                host=LOOPBACK_HOST,
                port=caster.port,
                mountpoint=DEFAULT_MOUNTPOINT,
                username=DAY6_USER,
                password=DAY6_PASS,
            )
        )
        recv = client.receive_frames(max_frames=1, allow_reconnect=False)
        assert recv.ok is True
        c_health = recv.diagnostics["health"]
        assert c_health["STREAM_HEALTH"] == "FRAMES_RECEIVED"
        assert c_health["RTCM_FRAME_HEALTH"] == "VALID_TRANSPORT_FRAMES"
        assert c_health["SCIENTIFIC_READINESS"] == SCIENTIFIC_READINESS_STATUS
        deadline = time.monotonic() + 2.0
        while (
            time.monotonic() < deadline
            and caster.status_snapshot()["rtcm_frames_transmitted"] < 1
        ):
            time.sleep(0.01)
        assert caster.status_snapshot()["health"]["STREAM_HEALTH"] == "STREAMING"

        # 5. CRC failure flips RTCM_FRAME_HEALTH without masking SERVICE_HEALTH
        bad = bytearray(bundle[0].frames[0].raw_bytes)
        bad[-1] ^= 0x01
        with pytest.raises(PublicationError, match="CRC-24Q"):
            caster.publish_raw_frame(bytes(bad))
        degraded = caster.status_snapshot()["health"]
        assert degraded["SERVICE_HEALTH"] == "HEALTHY"
        assert degraded["RTCM_FRAME_HEALTH"] == "CRC_FAILURES_OBSERVED"
        assert degraded["SCIENTIFIC_READINESS"] == SCIENTIFIC_READINESS_STATUS
    finally:
        caster.stop()

    assert caster.status_snapshot()["health"]["SERVICE_HEALTH"] == "STOPPED"


# ---------------------------------------------------------------------------
# Verification E: 10-Step Lifecycle & Resource Safety (AC-15, AC-16)
# ---------------------------------------------------------------------------


def test_full_ten_step_lifecycle_loopback_and_resource_cleanup() -> None:
    # Step 1 & 2: Load config from env and verify loopback-only enforcement
    for forbidden_host in ("0.0.0.0", "::", "192.168.0.10", "localhost"):
        with pytest.raises(ConfigurationError, match="127.0.0.1"):
            CasterConfig.from_env(
                {
                    "NLGCP_CASTER_HOST": forbidden_host,
                    "NLGCP_CASTER_PORT": "0",
                    "NLGCP_CASTER_CLIENT_USER": DAY6_USER,
                    "NLGCP_CASTER_CLIENT_PASSWORD": DAY6_PASS,
                }
            )

    cfg = CasterConfig.from_env(
        {
            "NLGCP_CASTER_HOST": "127.0.0.1",
            "NLGCP_CASTER_PORT": "0",
            "NLGCP_CASTER_MOUNTPOINT": DEFAULT_MOUNTPOINT,
            "NLGCP_CASTER_CLIENT_USER": DAY6_USER,
            "NLGCP_CASTER_CLIENT_PASSWORD": DAY6_PASS,
        }
    )

    # Step 3 & 4: Start caster, verify OS bind address is strictly 127.0.0.1 and mountpoint exists
    caster = LocalNtripCaster(cfg)
    host, port = caster.start()
    try:
        assert host == "127.0.0.1"
        assert port > 0
        assert caster._listen_sock is not None
        assert caster._listen_sock.getsockname() == ("127.0.0.1", port)
        assert caster.registry.get(DEFAULT_MOUNTPOINT) is not None

        # Step 5, 6, 7: Connect authenticated client, publish 1005/1074/1084, receive & validate
        bundle = generate_phase11_synthetic_bundle()
        generator = CorrectionGenerator()
        for res in bundle:
            caster.publish_phase11_result(res, artifact=generator.handoff(res))

        client = LocalNtripClient(
            ClientConfig(
                host=LOOPBACK_HOST,
                port=port,
                mountpoint=DEFAULT_MOUNTPOINT,
                username=DAY6_USER,
                password=DAY6_PASS,
            )
        )
        code, table = client.fetch_sourcetable()
        assert code == 200
        assert f"STR;{DEFAULT_MOUNTPOINT};" in table

        recv = client.receive_frames(max_frames=3, allow_reconnect=False)
        assert recv.ok is True
        assert [f.raw for f in recv.valid_frames] == [r.frames[0].raw_bytes for r in bundle]

        # Step 8: Client disconnected -> active_clients returns to 0
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline and caster.status_snapshot()["active_clients"] > 0:
            time.sleep(0.02)
        assert caster.status_snapshot()["active_clients"] == 0
    finally:
        # Step 9: Shut down caster
        caster.stop()

    # Step 10: Verify sockets, threads, and broker subscriptions are released cleanly
    assert caster.is_running is False
    assert caster._listen_sock is None
    assert caster._accept_thread is None
    assert len(caster._active_sockets) == 0
    assert len(caster._worker_threads) == 0
    assert all(len(subs) == 0 for subs in caster.broker._subscribers.values())
    assert not any(
        t.name.startswith("nlgcp-caster-") and t.is_alive() for t in threading.enumerate()
    )
    with pytest.raises(OSError):
        socket.create_connection((LOOPBACK_HOST, port), timeout=0.5)


# ---------------------------------------------------------------------------
# Reproducible End-to-End Demo Verification (AC-17)
# ---------------------------------------------------------------------------


def test_reproducible_demo_stages_and_cli_human_and_json_output() -> None:
    report = run_local_end_to_end_demo(ntrip_version="2.0")
    assert report.ok is True
    for stage_name in (
        "caster_startup",
        "mountpoint_availability",
        "authentication",
        "rtcm_publication",
        "client_reception",
        "byte_exact_comparison",
        "crc_validation",
        "message_type_identification",
        "clean_shutdown",
    ):
        assert report.stages[stage_name]["ok"] is True, f"stage {stage_name} failed"

    repo_root = Path(__file__).resolve().parents[3]
    script_path = repo_root / "scripts" / "run_phase12_lab_demo.py"
    proc = subprocess.run(
        [sys.executable, str(script_path), "--format", "both"],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert proc.returncode == 0, proc.stderr
    assert SYNTHETIC_MOUNTPOINT_LABEL in proc.stderr
    assert "Clean Shutdown:        PASS" in proc.stderr
    parsed: dict[str, Any] = json.loads(proc.stdout)
    assert parsed["ok"] is True
    assert parsed["data_notice"] == SYNTHETIC_MOUNTPOINT_LABEL
    assert parsed["byte_exact_match"] is True
    assert parsed["operational_readiness"] == "NOT_APPROVED"
    assert parsed["stages"]["clean_shutdown"]["ok"] is True
