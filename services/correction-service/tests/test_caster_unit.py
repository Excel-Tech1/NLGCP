"""SYNTHETIC TEST DATA — NOT VALID FOR NAVIGATION OR SCIENTIFIC POSITIONING RESULTS.

Unit and security boundary tests for the Phase 12 loopback-only NTRIP caster,
configuration, constant-time authentication, synthetic mountpoint registry,
RTCM frame validation gate, source push, capacity limits, and diagnostics.
"""

from __future__ import annotations

import logging
import socket
import threading
import time

import pytest
from nlgcp_correction_service import (
    DEFAULT_MOUNTPOINT,
    LOOPBACK_HOST,
    SCIENTIFIC_READINESS_STATUS,
    SYNTHETIC_MOUNTPOINT_LABEL,
)
from nlgcp_correction_service.auth import (
    CredentialStore,
    basic_auth_header,
    parse_basic_authorization,
)
from nlgcp_correction_service.caster import LocalNtripCaster
from nlgcp_correction_service.client import LocalNtripClient
from nlgcp_correction_service.config import (
    CasterConfig,
    ClientConfig,
    ConfigurationError,
)
from nlgcp_correction_service.diagnostics import StructuredEventLogger
from nlgcp_correction_service.mountpoints import (
    MountpointDefinition,
    MountpointError,
    MountpointRegistry,
)
from nlgcp_correction_service.pipeline import generate_phase11_synthetic_bundle
from nlgcp_correction_service.publisher import PublicationError
from nlgcp_correction_service.validation import (
    FrameValidationError,
    validate_rtcm_bytes,
)
from nlgcp_ntrip_ingest.backoff import ReconnectPolicy
from nlgcp_rtcm_generation.generator import CorrectionGenerator
from nlgcp_rtcm_generation.models import OutputClassification

TEST_USER = "lab_user"
TEST_PASS = "lab_ephemeral_secret_98765"
SRC_USER = "lab_source"
SRC_PASS = "lab_source_secret_54321"


# ---------------------------------------------------------------------------
# Configuration & Loopback-Only Enforcement (AC-02, AC-17)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bad_host", ["0.0.0.0", "::", "localhost", "192.168.1.10", "8.8.8.8", ""])
def test_caster_config_rejects_non_loopback_hosts(bad_host: str) -> None:
    cfg = CasterConfig(host=bad_host, port=0, client_credentials={TEST_USER: TEST_PASS})
    with pytest.raises(ConfigurationError, match="127.0.0.1"):
        cfg.validate()


@pytest.mark.parametrize("bad_host", ["0.0.0.0", "::", "localhost", "10.0.0.1"])
def test_client_config_rejects_non_loopback_hosts(bad_host: str) -> None:
    cfg = ClientConfig(host=bad_host, port=2101, username=TEST_USER, password=TEST_PASS)
    with pytest.raises(ConfigurationError, match="127.0.0.1"):
        cfg.validate()


def test_caster_config_requires_credentials_and_bounded_limits() -> None:
    with pytest.raises(ConfigurationError, match="credential"):
        CasterConfig(host=LOOPBACK_HOST, port=0, client_credentials={}).validate()
    with pytest.raises(ConfigurationError, match="max_clients"):
        CasterConfig(
            host=LOOPBACK_HOST, port=0, client_credentials={TEST_USER: TEST_PASS}, max_clients=0
        ).validate()
    with pytest.raises(ConfigurationError, match="max_attempts"):
        ClientConfig(
            host=LOOPBACK_HOST,
            port=2101,
            username=TEST_USER,
            password=TEST_PASS,
            reconnect_policy=ReconnectPolicy(base_delay_s=0.1, max_delay_s=1.0, max_attempts=50),
        ).validate()


def test_caster_config_from_env_and_missing_secret_fails_closed() -> None:
    with pytest.raises(ConfigurationError):
        CasterConfig.from_env({})
    with pytest.raises(ConfigurationError, match="127.0.0.1"):
        CasterConfig.from_env(
            {
                "NLGCP_CASTER_HOST": "0.0.0.0",
                "NLGCP_CASTER_PORT": "2101",
                "NLGCP_CASTER_CLIENT_USER": TEST_USER,
                "NLGCP_CASTER_CLIENT_PASSWORD": TEST_PASS,
            }
        )
    cfg = CasterConfig.from_env(
        {
            "NLGCP_CASTER_HOST": "127.0.0.1",
            "NLGCP_CASTER_PORT": "0",
            "NLGCP_CASTER_MOUNTPOINT": DEFAULT_MOUNTPOINT,
            "NLGCP_CASTER_CLIENT_USER": TEST_USER,
            "NLGCP_CASTER_CLIENT_PASSWORD": TEST_PASS,
            "NLGCP_CASTER_SOURCE_USER": SRC_USER,
            "NLGCP_CASTER_SOURCE_PASSWORD": SRC_PASS,
        }
    )
    assert cfg.host == LOOPBACK_HOST
    assert cfg.mountpoint == DEFAULT_MOUNTPOINT
    assert cfg.client_credentials == {TEST_USER: TEST_PASS}
    assert cfg.source_credentials == {SRC_USER: SRC_PASS}


# ---------------------------------------------------------------------------
# Authentication & Credential Redaction (AC-04, AC-05)
# ---------------------------------------------------------------------------


def test_credential_store_constant_time_verification_and_redaction() -> None:
    store = CredentialStore({TEST_USER: TEST_PASS})
    assert parse_basic_authorization(None) is None
    assert parse_basic_authorization("Bearer abc") is None
    assert parse_basic_authorization("Basic !!!not-base64!!!") is None

    ok_hdr = basic_auth_header(TEST_USER, TEST_PASS)
    assert store.verify_basic(ok_hdr).authenticated is True
    assert store.verify_basic(ok_hdr).username == TEST_USER

    bad_user = basic_auth_header("wrong_user", TEST_PASS)
    assert store.verify_basic(bad_user).authenticated is False

    bad_pass = basic_auth_header(TEST_USER, "wrong_pass")
    assert store.verify_basic(bad_pass).authenticated is False

    logger = StructuredEventLogger("nlgcp.test.redact", secrets=store.secrets_tuple())
    emitted = logger.emit(
        logging.INFO,
        "auth_check",
        password=TEST_PASS,
        authorization=ok_hdr,
        detail=f"attempt using {TEST_PASS}",
    )
    assert TEST_PASS not in emitted
    assert ok_hdr not in emitted
    assert "***REDACTED***" in emitted


# ---------------------------------------------------------------------------
# Synthetic Mountpoint Registry & Source Table (AC-03)
# ---------------------------------------------------------------------------


def test_mountpoint_registry_enforces_synthetic_only_policy() -> None:
    with pytest.raises(MountpointError, match="non-synthetic"):
        MountpointDefinition(name="OP_REAL", synthetic_only=False).validate()
    with pytest.raises(MountpointError, match="SYNTHETIC"):
        MountpointDefinition(name="NLGCP_TEST", label="production service").validate()

    mp = MountpointDefinition(name=DEFAULT_MOUNTPOINT)
    assert mp.accepts_classification(OutputClassification.SYNTHETIC_TEST_ONLY) is True
    assert mp.accepts_classification(OutputClassification.OPERATIONAL_APPROVED) is False
    assert mp.accepts_classification(OutputClassification.RESEARCH_VALIDATION) is False

    registry = MountpointRegistry((mp,))
    table = registry.render_sourcetable(port=2101)
    assert f"STR;{DEFAULT_MOUNTPOINT};" in table
    assert "SYNTHETIC TEST DATA" in table
    assert "ENDSOURCETABLE" in table
    assert "127.0.0.1" in table


# ---------------------------------------------------------------------------
# RTCM Frame Validation Boundary (AC-07, AC-15)
# ---------------------------------------------------------------------------


def test_frame_validation_accepts_valid_and_rejects_corrupt_or_operational() -> None:
    bundle = generate_phase11_synthetic_bundle()
    valid_raw = bundle[0].frames[0].raw_bytes

    validated = validate_rtcm_bytes(valid_raw)
    assert validated.message_number == 1005
    assert validated.classification == OutputClassification.SYNTHETIC_TEST_ONLY

    with pytest.raises(FrameValidationError, match="OPERATIONAL_APPROVED"):
        validate_rtcm_bytes(valid_raw, classification=OutputClassification.OPERATIONAL_APPROVED)

    with pytest.raises(FrameValidationError, match="preamble"):
        bad_pre = bytearray(valid_raw)
        bad_pre[0] = 0xD2
        validate_rtcm_bytes(bytes(bad_pre))

    with pytest.raises(FrameValidationError, match="CRC-24Q"):
        bad_crc = bytearray(valid_raw)
        bad_crc[-1] ^= 0x01
        validate_rtcm_bytes(bytes(bad_crc))

    with pytest.raises(FrameValidationError, match="length mismatch"):
        validate_rtcm_bytes(valid_raw[:-1])

    with pytest.raises(FrameValidationError, match="truncated"):
        validate_rtcm_bytes(b"\xd3\x00\x01")


# ---------------------------------------------------------------------------
# Caster Lifecycle, Source Table, Source Push, Multi-Client, Diagnostics
# ---------------------------------------------------------------------------


def test_caster_starts_on_loopback_serves_v2_and_v1_sourcetable_and_stops_cleanly() -> None:
    cfg = CasterConfig(
        host=LOOPBACK_HOST,
        port=0,
        mountpoint=DEFAULT_MOUNTPOINT,
        client_credentials={TEST_USER: TEST_PASS},
    )
    caster = LocalNtripCaster(cfg)
    host, port = caster.start()
    try:
        assert host == "127.0.0.1"
        assert port > 0
        assert caster.is_running is True

        v2_client = LocalNtripClient(
            ClientConfig(
                host=LOOPBACK_HOST,
                port=port,
                mountpoint=DEFAULT_MOUNTPOINT,
                username=TEST_USER,
                password=TEST_PASS,
                ntrip_version="2.0",
            )
        )
        code2, body2 = v2_client.fetch_sourcetable()
        assert code2 == 200
        assert f"STR;{DEFAULT_MOUNTPOINT};" in body2
        assert SYNTHETIC_MOUNTPOINT_LABEL.replace(";", ",") in body2
        assert "ENDSOURCETABLE" in body2

        v1_client = LocalNtripClient(
            ClientConfig(
                host=LOOPBACK_HOST,
                port=port,
                mountpoint=DEFAULT_MOUNTPOINT,
                username=TEST_USER,
                password=TEST_PASS,
                ntrip_version="1.0",
            )
        )
        code1, body1 = v1_client.fetch_sourcetable()
        assert code1 == 200
        assert f"STR;{DEFAULT_MOUNTPOINT};" in body1
    finally:
        caster.stop()

    assert caster.is_running is False
    snap = caster.status_snapshot()
    assert snap["caster_status"] == "STOPPED"
    assert snap["health"]["SERVICE_HEALTH"] == "STOPPED"
    assert snap["health"]["SCIENTIFIC_READINESS"] == SCIENTIFIC_READINESS_STATUS
    assert TEST_PASS not in str(snap)


def test_caster_source_push_v2_and_v1_validates_frames_and_rejects_bad_auth() -> None:
    bundle = generate_phase11_synthetic_bundle()
    raw_1005 = bundle[0].frames[0].raw_bytes
    corrupt_1005 = bytearray(raw_1005)
    corrupt_1005[-1] ^= 0xFF

    cfg = CasterConfig(
        host=LOOPBACK_HOST,
        port=0,
        mountpoint=DEFAULT_MOUNTPOINT,
        client_credentials={TEST_USER: TEST_PASS},
        source_credentials={SRC_USER: SRC_PASS},
    )
    with LocalNtripCaster(cfg) as caster:
        # Bad v2 source auth -> 401
        with socket.create_connection((LOOPBACK_HOST, caster.port), timeout=2.0) as s:
            req = (
                f"POST /{DEFAULT_MOUNTPOINT} HTTP/1.1\r\n"
                f"Host: 127.0.0.1:{caster.port}\r\n"
                "Ntrip-Version: Ntrip/2.0\r\n"
                f"Authorization: {basic_auth_header(SRC_USER, 'wrong')}\r\n\r\n"
            ).encode("ascii")
            s.sendall(req)
            resp = s.recv(1024).decode("ascii", errors="replace")
            assert resp.startswith("HTTP/1.1 401 Unauthorized")

        # Bad v1 SOURCE password -> ERROR - Bad Password
        with socket.create_connection((LOOPBACK_HOST, caster.port), timeout=2.0) as s:
            s.sendall(f"SOURCE wrongpw /{DEFAULT_MOUNTPOINT}\r\n\r\n".encode("ascii"))
            resp = s.recv(1024).decode("ascii", errors="replace")
            assert "ERROR - Bad Password" in resp

        # Valid v2 source push: send 1 corrupt frame + 1 valid frame -> only valid published!
        with socket.create_connection((LOOPBACK_HOST, caster.port), timeout=2.0) as s:
            req = (
                f"POST /{DEFAULT_MOUNTPOINT} HTTP/1.1\r\n"
                f"Host: 127.0.0.1:{caster.port}\r\n"
                "Ntrip-Version: Ntrip/2.0\r\n"
                f"Authorization: {basic_auth_header(SRC_USER, SRC_PASS)}\r\n\r\n"
            ).encode("ascii")
            s.sendall(req)
            resp = s.recv(1024).decode("ascii", errors="replace")
            assert resp.startswith("HTTP/1.1 200 OK")
            s.sendall(bytes(corrupt_1005) + raw_1005)
            time.sleep(0.1)

        snap = caster.status_snapshot()
        assert snap["crc_failures"] == 1
        assert snap["rtcm_frames_received"] == 1
        assert snap["message_types_observed"] == {1005: 1}


def test_caster_multiple_concurrent_clients_and_capacity_limit() -> None:
    bundle = generate_phase11_synthetic_bundle()
    generator = CorrectionGenerator()
    cfg = CasterConfig(
        host=LOOPBACK_HOST,
        port=0,
        mountpoint=DEFAULT_MOUNTPOINT,
        client_credentials={TEST_USER: TEST_PASS},
        max_clients=2,
    )
    with LocalNtripCaster(cfg) as caster:
        for res in bundle:
            caster.publish_phase11_result(res, artifact=generator.handoff(res))

        # Verify broker rejects corrupt raw frames directly too
        with pytest.raises(PublicationError, match="CRC-24Q"):
            bad = bytearray(bundle[0].frames[0].raw_bytes)
            bad[-1] ^= 0x01
            caster.publish_raw_frame(bytes(bad))

        results: list[tuple[int, ...]] = []
        lock = threading.Lock()

        def _run_client() -> None:
            client = LocalNtripClient(
                ClientConfig(
                    host=LOOPBACK_HOST,
                    port=caster.port,
                    mountpoint=DEFAULT_MOUNTPOINT,
                    username=TEST_USER,
                    password=TEST_PASS,
                )
            )
            r = client.receive_frames(max_frames=3, allow_reconnect=False)
            assert r.ok
            with lock:
                results.append(tuple(f.message_number or 0 for f in r.valid_frames))

        t1 = threading.Thread(target=_run_client)
        t2 = threading.Thread(target=_run_client)
        t1.start()
        t2.start()
        t1.join(timeout=5.0)
        t2.join(timeout=5.0)
        assert results == [(1005, 1074, 1084), (1005, 1074, 1084)]
        snap = caster.status_snapshot()
        assert snap["authenticated_clients_total"] == 2
        assert snap["rtcm_frames_transmitted"] == 6
        assert snap["bytes_transmitted"] > 0
        assert snap["health"]["SCIENTIFIC_READINESS"] == SCIENTIFIC_READINESS_STATUS
