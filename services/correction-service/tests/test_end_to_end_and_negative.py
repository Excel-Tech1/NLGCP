"""SYNTHETIC TEST DATA — NOT VALID FOR NAVIGATION OR SCIENTIFIC POSITIONING RESULTS.

End-to-end integration tests (Phase 11 -> Phase 12 Caster -> Authenticated
NTRIP Client -> Independent RTKLIB Decoder) and all required negative /
resilience tests for Phase 12 Days 4-5.
"""

from __future__ import annotations

import os
import socket
import threading
import time
from contextlib import suppress
from pathlib import Path
from typing import Any

import pytest
from nlgcp_correction_service import (
    DEFAULT_MOUNTPOINT,
    LOOPBACK_HOST,
    SCIENTIFIC_READINESS_STATUS,
)
from nlgcp_correction_service.caster import LocalNtripCaster
from nlgcp_correction_service.client import LocalNtripClient
from nlgcp_correction_service.config import CasterConfig, ClientConfig
from nlgcp_correction_service.pipeline import (
    generate_phase11_synthetic_bundle,
    run_local_end_to_end_demo,
)
from nlgcp_ntrip_ingest.backoff import ReconnectPolicy
from nlgcp_ntrip_ingest.models import FailureClass
from nlgcp_rtcm_generation.generator import CorrectionGenerator
from nlgcp_rtcm_generation.independent_decoder import (
    IndependentDecoderUnavailable,
    build_rtklib_decoder,
    decode_with_convbin,
    decode_with_rtklib_native,
    glonass_wavelength_m,
    gps_wavelength_m,
    locate_convbin,
)
from nlgcp_rtcm_generation.messages import RANGE_MS

TEST_USER = "lab_rover"
TEST_PASS = "ephemeral_lab_pw_2026"
FINE_PR_HALF_LSB_M = 0.5 * RANGE_MS / (1 << 24)
FINE_PH_HALF_LSB_M = 0.5 * RANGE_MS / (1 << 29)


def _start_raw_loopback_server(
    response_bytes: bytes,
) -> tuple[socket.socket, int, threading.Thread]:
    """Minimal raw TCP loopback server for negative wire-corruption tests."""
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((LOOPBACK_HOST, 0))
    srv.listen(4)
    port = int(srv.getsockname()[1])

    def _serve() -> None:
        with suppress(OSError):
            srv.settimeout(3.0)
            conn, _ = srv.accept()
            with conn:
                conn.settimeout(2.0)
                with suppress(OSError):
                    conn.recv(4096)
                with suppress(OSError):
                    conn.sendall(response_bytes)

    thread = threading.Thread(target=_serve, daemon=True)
    thread.start()
    return srv, port, thread


# ---------------------------------------------------------------------------
# End-to-End Integration: Phase 11 -> Phase 12 -> Client -> RTKLIB (AC-07..12)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("ntrip_version", ["2.0", "1.0"])
def test_end_to_end_phase11_to_phase12_client_and_convbin(ntrip_version: str) -> None:
    report = run_local_end_to_end_demo(ntrip_version=ntrip_version)
    assert report.ok is True
    assert report.mountpoint == DEFAULT_MOUNTPOINT
    assert report.sent_message_numbers == (1005, 1074, 1084)
    assert report.received_message_numbers == (1005, 1074, 1084)
    assert report.byte_exact_match is True
    assert report.client_result.invalid_frames == ()
    assert report.scientific_readiness == SCIENTIFIC_READINESS_STATUS
    assert report.caster_diagnostics["health"]["SCIENTIFIC_READINESS"] == (
        SCIENTIFIC_READINESS_STATUS
    )
    assert report.client_result.diagnostics["health"]["SCIENTIFIC_READINESS"] == (
        SCIENTIFIC_READINESS_STATUS
    )

    # Independent RTKLIB convbin verification on the client-received RTCM bytes.
    try:
        convbin_bin = locate_convbin()
    except IndependentDecoderUnavailable:
        pytest.skip("RTKLIB convbin binary is not installed")

    recv = [f.raw for f in report.client_result.valid_frames]
    dec_1005_1074 = decode_with_convbin(recv[0] + recv[1], binary=convbin_bin)
    assert dec_1005_1074.station_id == 1234
    assert dec_1005_1074.approx_position_xyz == pytest.approx(
        (111111.1111, -222222.2222, 3333333.3333), abs=1e-4
    )
    assert dec_1005_1074.sys_obs_types["G"] == ("C1C", "L1C", "S1C", "C2P", "L2P", "S2P")
    sats_g = dec_1005_1074.epochs[0].satellites
    assert abs(sats_g["G01"]["C1C"].value - 20_000_000.0) <= FINE_PR_HALF_LSB_M + 1e-3
    assert (
        abs(sats_g["G01"]["L1C"].value * gps_wavelength_m(1) - 20_000_050.0)
        <= FINE_PH_HALF_LSB_M + 1e-3
    )
    assert sats_g["G02"]["L1C"].lli == 3
    assert abs(sats_g["G03"]["C2P"].value - 22_000_000.0) <= FINE_PR_HALF_LSB_M + 1e-3

    dec_1084 = decode_with_convbin(recv[2], binary=convbin_bin)
    assert dec_1084.station_id == 3210
    assert dec_1084.sys_obs_types["R"] == ("C1C", "S1C", "C2C", "S2C")
    sats_r = dec_1084.epochs[0].satellites
    assert abs(sats_r["R01"]["C1C"].value - 19_100_000.0) <= FINE_PR_HALF_LSB_M + 1e-3
    assert abs(sats_r["R02"]["C2C"].value - 20_500_006.0) <= FINE_PR_HALF_LSB_M + 1e-3


def test_end_to_end_native_rtklib_input_rtcm3_semantic_verification() -> None:
    source = os.environ.get("RTKLIB_SOURCE")
    if not source:
        pytest.skip("external pinned RTKLIB_SOURCE is required for native input_rtcm3 checks")
    repo = Path(__file__).resolve().parents[3]
    exe, _prov = build_rtklib_decoder(repo, Path(source))

    report = run_local_end_to_end_demo(
        ntrip_version="2.0", rtklib_source=Path(source), repo_root=repo
    )
    assert report.ok is True
    assert report.rtklib_validation["native_input_rtcm3_performed"] is True

    recv = [f.raw for f in report.client_result.valid_frames]
    d1005 = decode_with_rtklib_native(exe, recv[0])["events"][0]
    assert d1005["ret"] == 5
    assert d1005["staid"] == 1234
    assert d1005["pos_ecef"] == pytest.approx(
        [111111.1111, -222222.2222, 3333333.3333], abs=1e-4
    )

    d1074 = decode_with_rtklib_native(exe, recv[1])["events"][0]
    assert d1074["ret"] == 1
    assert d1074["msmtype_gps"] == "L1C,L2P"
    assert d1074["gps_tow_s"] == pytest.approx(345600.123, abs=1e-6)

    fcns = {1: 1, 2: -4}
    d1084 = decode_with_rtklib_native(exe, recv[2], glo_fcns=fcns)["events"][0]
    assert d1084["ret"] == 1
    assert d1084["msmtype_glo"] == "L1C,L2C"
    for obs in d1084["obs"]:
        wl = glonass_wavelength_m(obs["freq"], fcns[obs["prn"]])
        assert obs["L_cyc"] * wl > 19_000_000.0


def test_client_reconstructs_frames_over_single_byte_tcp_chunks() -> None:
    bundle = generate_phase11_synthetic_bundle()
    generator = CorrectionGenerator()
    cfg = CasterConfig(
        host=LOOPBACK_HOST,
        port=0,
        mountpoint=DEFAULT_MOUNTPOINT,
        client_credentials={TEST_USER: TEST_PASS},
    )
    with LocalNtripCaster(cfg) as caster:
        for res in bundle:
            caster.publish_phase11_result(res, artifact=generator.handoff(res))
        client = LocalNtripClient(
            ClientConfig(
                host=LOOPBACK_HOST,
                port=caster.port,
                mountpoint=DEFAULT_MOUNTPOINT,
                username=TEST_USER,
                password=TEST_PASS,
                read_chunk_bytes=1,  # worst-case 1-byte TCP framing split
            )
        )
        recv_res = client.receive_frames(max_frames=3, allow_reconnect=False)
        assert recv_res.ok is True
        assert [f.raw for f in recv_res.valid_frames] == [
            r.frames[0].raw_bytes for r in bundle
        ]


# ---------------------------------------------------------------------------
# Negative & Resilience Tests (Section 5.4: all 12 required scenarios)
# ---------------------------------------------------------------------------


def test_negative_invalid_username_and_invalid_password() -> None:
    cfg = CasterConfig(
        host=LOOPBACK_HOST,
        port=0,
        mountpoint=DEFAULT_MOUNTPOINT,
        client_credentials={TEST_USER: TEST_PASS},
    )
    with LocalNtripCaster(cfg) as caster:
        for bad_user, bad_pass in (("wrong_user", TEST_PASS), (TEST_USER, "wrong_pass")):
            client = LocalNtripClient(
                ClientConfig(
                    host=LOOPBACK_HOST,
                    port=caster.port,
                    mountpoint=DEFAULT_MOUNTPOINT,
                    username=bad_user,
                    password=bad_pass,
                )
            )
            res = client.receive_frames(max_frames=1, allow_reconnect=True)
            assert res.ok is False
            assert res.status_code == 401
            assert res.failure == FailureClass.AUTH_FAILURE
            # Terminal auth failure must NEVER trigger reconnect loops.
            assert res.reconnection_attempts == 0
            assert bad_pass not in str(res.diagnostics)

        snap = caster.status_snapshot()
        assert snap["failed_auth_attempts"] == 2
        assert snap["authenticated_clients_total"] == 0


def test_negative_unknown_mountpoint_rejected_without_retry() -> None:
    cfg = CasterConfig(
        host=LOOPBACK_HOST,
        port=0,
        mountpoint=DEFAULT_MOUNTPOINT,
        client_credentials={TEST_USER: TEST_PASS},
    )
    with LocalNtripCaster(cfg) as caster:
        client = LocalNtripClient(
            ClientConfig(
                host=LOOPBACK_HOST,
                port=caster.port,
                mountpoint="UNKNOWN_MOUNT",
                username=TEST_USER,
                password=TEST_PASS,
            )
        )
        res = client.receive_frames(max_frames=1, allow_reconnect=True)
        assert res.ok is False
        assert res.status_code == 404
        assert res.failure == FailureClass.MOUNTPOINT_NOT_FOUND
        assert res.reconnection_attempts == 0


def test_negative_caster_unavailable_respects_bounded_retries() -> None:
    # Reserve and immediately close an ephemeral loopback port so connect fails fast.
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    probe.bind((LOOPBACK_HOST, 0))
    closed_port = int(probe.getsockname()[1])
    probe.close()

    sleeps: list[float] = []
    client = LocalNtripClient(
        ClientConfig(
            host=LOOPBACK_HOST,
            port=closed_port,
            mountpoint=DEFAULT_MOUNTPOINT,
            username=TEST_USER,
            password=TEST_PASS,
            connect_timeout_s=0.5,
            reconnect_policy=ReconnectPolicy(
                base_delay_s=0.1, max_delay_s=0.3, max_attempts=3
            ),
        ),
        sleep_fn=sleeps.append,
    )
    res = client.receive_frames(max_frames=1, allow_reconnect=True)
    assert res.ok is False
    assert res.failure == FailureClass.CONNECTION_LOST
    assert res.reconnection_attempts == 3
    # Verify exponential backoff capped at max_delay_s (0.1, 0.2, 0.3).
    assert sleeps == [pytest.approx(0.1), pytest.approx(0.2), pytest.approx(0.3)]


def test_negative_client_disconnect_and_caster_shutdown() -> None:
    cfg = CasterConfig(
        host=LOOPBACK_HOST,
        port=0,
        mountpoint=DEFAULT_MOUNTPOINT,
        client_credentials={TEST_USER: TEST_PASS},
    )
    caster = LocalNtripCaster(cfg)
    caster.start()
    try:
        # 1. Abrupt client disconnect mid-stream: caster cleans up active_clients.
        with socket.create_connection((LOOPBACK_HOST, caster.port), timeout=2.0) as s:
            from nlgcp_correction_service.auth import basic_auth_header

            req = (
                f"GET /{DEFAULT_MOUNTPOINT} HTTP/1.1\r\n"
                f"Host: 127.0.0.1:{caster.port}\r\n"
                "Ntrip-Version: Ntrip/2.0\r\n"
                f"Authorization: {basic_auth_header(TEST_USER, TEST_PASS)}\r\n\r\n"
            ).encode("ascii")
            s.sendall(req)
            head = s.recv(1024)
            assert head.startswith(b"HTTP/1.1 200 OK")
        # Push a frame so the caster writer detects the closed peer socket cleanly.
        caster.publish_raw_frame(generate_phase11_synthetic_bundle()[0].frames[0].raw_bytes)
        time.sleep(0.15)
        assert caster.status_snapshot()["active_clients"] == 0

        # 2. Caster shutdown while client is waiting -> client exits cleanly.
        caster.broker.clear_backlog(DEFAULT_MOUNTPOINT)
        client = LocalNtripClient(
            ClientConfig(
                host=LOOPBACK_HOST,
                port=caster.port,
                mountpoint=DEFAULT_MOUNTPOINT,
                username=TEST_USER,
                password=TEST_PASS,
                read_timeout_s=2.0,
                reconnect_policy=ReconnectPolicy(
                    base_delay_s=0.05, max_delay_s=0.1, max_attempts=1
                ),
            )
        )
        holder: dict[str, Any] = {}

        def _recv() -> None:
            holder["result"] = client.receive_frames(max_frames=1, allow_reconnect=False)

        t = threading.Thread(target=_recv)
        t.start()
        time.sleep(0.1)
        caster.stop()
        t.join(timeout=5.0)
        assert not t.is_alive()
        assert holder["result"].ok is False
    finally:
        caster.stop()


def test_negative_reconnection_after_interruption() -> None:
    bundle = generate_phase11_synthetic_bundle()
    raw_1005 = bundle[0].frames[0].raw_bytes
    raw_1074 = bundle[1].frames[0].raw_bytes
    cfg = CasterConfig(
        host=LOOPBACK_HOST,
        port=0,
        mountpoint=DEFAULT_MOUNTPOINT,
        client_credentials={TEST_USER: TEST_PASS},
    )
    with LocalNtripCaster(cfg) as caster:
        caster.publish_raw_frame(raw_1005)

        def _interrupt_then_publish() -> None:
            # Wait until client receives frame 1, then drop connection and replace backlog.
            deadline = time.monotonic() + 3.0
            while time.monotonic() < deadline:
                if caster.status_snapshot()["rtcm_frames_transmitted"] >= 1:
                    break
                time.sleep(0.02)
            caster.broker.clear_backlog(DEFAULT_MOUNTPOINT)
            caster.disconnect_clients(DEFAULT_MOUNTPOINT)
            time.sleep(0.05)
            caster.publish_raw_frame(raw_1074)

        controller = threading.Thread(target=_interrupt_then_publish, daemon=True)
        controller.start()

        client = LocalNtripClient(
            ClientConfig(
                host=LOOPBACK_HOST,
                port=caster.port,
                mountpoint=DEFAULT_MOUNTPOINT,
                username=TEST_USER,
                password=TEST_PASS,
                read_timeout_s=1.0,
                reconnect_policy=ReconnectPolicy(
                    base_delay_s=0.05, max_delay_s=0.2, max_attempts=3
                ),
            )
        )
        res = client.receive_frames(max_frames=2, allow_reconnect=True)
        controller.join(timeout=3.0)
        assert res.ok is True
        assert res.reconnection_attempts >= 1
        assert [f.message_number for f in res.valid_frames] == [1005, 1074]


def test_negative_truncated_corrupted_crc_bad_preamble_and_empty_stream() -> None:
    raw_1005 = generate_phase11_synthetic_bundle()[0].frames[0].raw_bytes
    ok_head = b"HTTP/1.1 200 OK\r\nNtrip-Version: Ntrip/2.0\r\nContent-Type: gnss/data\r\n\r\n"

    # 1. Truncated RTCM frame
    srv, port, th = _start_raw_loopback_server(ok_head + raw_1005[:-5])
    try:
        res = LocalNtripClient(
            ClientConfig(host=LOOPBACK_HOST, port=port, username=TEST_USER, password=TEST_PASS)
        ).receive_frames(max_frames=1, allow_reconnect=False)
        assert res.ok is False
        assert res.valid_frames == ()
        assert res.diagnostics["truncated_trailing_bytes"] == len(raw_1005) - 5
        assert any("TRUNCATED_TRAILING_BYTES" in f for f in res.findings)
    finally:
        srv.close()
        th.join(timeout=2.0)

    # 2. Corrupted CRC
    bad_crc = bytearray(raw_1005)
    bad_crc[-1] ^= 0x01
    srv, port, th = _start_raw_loopback_server(ok_head + bytes(bad_crc))
    try:
        res = LocalNtripClient(
            ClientConfig(host=LOOPBACK_HOST, port=port, username=TEST_USER, password=TEST_PASS)
        ).receive_frames(max_frames=1, allow_reconnect=False)
        assert res.ok is False
        assert res.valid_frames == ()
        assert len(res.invalid_frames) == 1
        assert res.diagnostics["crc_failures"] == 1
    finally:
        srv.close()
        th.join(timeout=2.0)

    # 3. Invalid RTCM preamble / stray junk bytes before valid frame
    srv, port, th = _start_raw_loopback_server(ok_head + b"\x00\xFF\xD2junk" + raw_1005)
    try:
        res = LocalNtripClient(
            ClientConfig(host=LOOPBACK_HOST, port=port, username=TEST_USER, password=TEST_PASS)
        ).receive_frames(max_frames=1, allow_reconnect=False)
        assert res.ok is True
        assert len(res.valid_frames) == 1
        assert res.valid_frames[0].message_number == 1005
        assert res.diagnostics["stray_bytes"] == 7
        assert any("STRAY_BYTES" in f for f in res.findings)
    finally:
        srv.close()
        th.join(timeout=2.0)

    # 4. Empty stream (200 OK followed by EOF)
    srv, port, th = _start_raw_loopback_server(ok_head)
    try:
        res = LocalNtripClient(
            ClientConfig(host=LOOPBACK_HOST, port=port, username=TEST_USER, password=TEST_PASS)
        ).receive_frames(max_frames=1, allow_reconnect=False)
        assert res.ok is False
        assert res.valid_frames == ()
        assert res.diagnostics["health"]["STREAM_HEALTH"] == "EMPTY"
    finally:
        srv.close()
        th.join(timeout=2.0)


def test_negative_malformed_client_requests_return_400() -> None:
    cfg = CasterConfig(
        host=LOOPBACK_HOST,
        port=0,
        mountpoint=DEFAULT_MOUNTPOINT,
        client_credentials={TEST_USER: TEST_PASS},
        max_request_bytes=1024,
    )
    with LocalNtripCaster(cfg) as caster:
        for bad_req in (
            b"GARBAGE\r\n\r\n",
            b"GET /NLGCP_TEST NOTHTTP\r\n\r\n",
            b"GET /NLGCP_TEST HTTP/1.1\r\nX-Junk: " + (b"A" * 2048) + b"\r\n\r\n",
        ):
            with socket.create_connection((LOOPBACK_HOST, caster.port), timeout=2.0) as s:
                s.settimeout(2.0)
                with suppress(OSError):
                    s.sendall(bad_req)
                resp = s.recv(1024).decode("ascii", errors="replace")
                assert resp.startswith("HTTP/1.1 400 Bad Request")
