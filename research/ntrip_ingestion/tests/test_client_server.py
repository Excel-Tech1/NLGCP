"""Live-client integration tests against the deterministic test server.

SYNTHETIC TEST DATA — NOT VALID FOR SCIENTIFIC RESULTS.
No internet, no NATS, no credentials required.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from nlgcp_ntrip_ingest.bridge import (
    admit_capture_for_phase9,
    capture_source_for_phase9,
    live_to_phase9,
)
from nlgcp_ntrip_ingest.capture import CaptureWriter, sanitize_identifier
from nlgcp_ntrip_ingest.client import NtripClient
from nlgcp_ntrip_ingest.models import (
    ConnectionState,
    FailureClass,
    LiveFrame,
    config_from_env,
)
from nlgcp_ntrip_ingest.reporting import sha256_file, summarize_capture, validate_capture
from nlgcp_ntrip_ingest.subjects import envelope, live_subject, ordering_key
from phase10_fixtures import (
    SYNTHETIC_MESSAGES,
    base_config,
    single_pass_bytes,
    start_server,
    synthetic_stream,
)


def _client_for(server_host: str, server_port: int, **overrides: object) -> NtripClient:
    config = base_config(host=server_host, port=server_port, **overrides)
    return NtripClient(config, provider="test-provider",
                       station_registry={"TEST00SYN": "EKAK00NGA"},
                       authorization_basis="test-authorization")


def test_probe_valid_stream() -> None:
    server = start_server("valid")
    try:
        client = _client_for("127.0.0.1", server.port)
        result = client.probe_stream(duration_s=5.0, max_bytes=1 << 20)
    finally:
        server.stop()
    assert result.ok
    assert result.frames_received == len(SYNTHETIC_MESSAGES)
    assert result.frames_crc_valid == len(SYNTHETIC_MESSAGES)
    assert result.frames_crc_invalid == 0
    assert result.message_types == {"1005": 2, "1077": 2, "1087": 2, "1230": 1, "1006": 1}
    assert ConnectionState.STREAMING.value in client.transitions
    assert client.transitions[-1] == ConnectionState.STOPPED.value


def test_probe_v1_icy_tolerance() -> None:
    server = start_server("v1")
    try:
        result = _client_for("127.0.0.1", server.port).probe_stream()
    finally:
        server.stop()
    assert result.ok and result.frames_received == len(SYNTHETIC_MESSAGES)


def test_probe_split_delivery_reassembles() -> None:
    server = start_server("split", split_size=1)
    try:
        result = _client_for("127.0.0.1", server.port).probe_stream()
    finally:
        server.stop()
    assert result.ok and result.frames_received == len(SYNTHETIC_MESSAGES)


def test_probe_401_terminal_no_reconnect() -> None:
    server = start_server("auth", username="user", password="pw")
    try:
        client = _client_for("127.0.0.1", server.port)
        result = client.probe_stream()
    finally:
        server.stop()
    assert not result.ok and result.failure == FailureClass.AUTH_FAILURE
    assert client.transitions[-1] == ConnectionState.BLOCKED.value
    assert ConnectionState.RECONNECTING.value not in client.transitions


def test_probe_auth_success_with_credentials() -> None:
    server = start_server("auth", username="user", password="pw")
    try:
        client = _client_for("127.0.0.1", server.port, username="user", password="pw")
        result = client.probe_stream()
    finally:
        server.stop()
    assert result.ok and result.frames_received == len(SYNTHETIC_MESSAGES)


def test_probe_404_terminal() -> None:
    server = start_server("notfound")
    try:
        result = _client_for("127.0.0.1", server.port).probe_stream()
    finally:
        server.stop()
    assert not result.ok and result.failure == FailureClass.MOUNTPOINT_NOT_FOUND


def test_probe_wrong_mountpoint_404() -> None:
    server = start_server("valid", mountpoint="OTHER")
    try:
        result = _client_for("127.0.0.1", server.port).probe_stream()
    finally:
        server.stop()
    assert not result.ok and result.failure == FailureClass.MOUNTPOINT_NOT_FOUND


def test_probe_html_rejected() -> None:
    server = start_server("html")
    try:
        result = _client_for("127.0.0.1", server.port).probe_stream()
    finally:
        server.stop()
    assert not result.ok and result.failure == FailureClass.WRONG_CONTENT


def test_probe_sourcetable_instead_of_stream_rejected() -> None:
    server = start_server("sourcetable-instead")
    try:
        result = _client_for("127.0.0.1", server.port).probe_stream()
    finally:
        server.stop()
    assert not result.ok and result.failure == FailureClass.WRONG_CONTENT


def test_probe_empty_response_rejected() -> None:
    server = start_server("empty")
    try:
        result = _client_for("127.0.0.1", server.port).probe_stream()
    finally:
        server.stop()
    assert not result.ok
    assert result.failure in (FailureClass.EMPTY_RESPONSE, FailureClass.CONNECTION_LOST)


def test_probe_dial_failure_is_connection_lost() -> None:
    client = _client_for("127.0.0.1", 1)  # closed port
    result = client.probe_stream()
    assert not result.ok and result.failure == FailureClass.CONNECTION_LOST


def test_probe_invalid_config_blocked() -> None:
    config = base_config(host="", mountpoint="")
    result = NtripClient(config).probe_stream()
    assert not result.ok and result.failure == FailureClass.CONFIG_INVALID


def test_fetch_sourcetable_bounded() -> None:
    server = start_server("sourcetable")
    try:
        client = _client_for("127.0.0.1", server.port)
        table, provenance = client.fetch_sourcetable()
    finally:
        server.stop()
    assert len(table.streams) == 2
    assert provenance["streams"] == 2
    assert len(provenance["sha256"]) == 64


def test_capture_valid_produces_immutable_bundle(tmp_path: Path) -> None:
    server = start_server("valid")
    try:
        client = _client_for("127.0.0.1", server.port)
        result = client.capture_stream(tmp_path, capture_id="cap-valid",
                                       duration_s=10.0, max_bytes=single_pass_bytes())
    finally:
        server.stop()
    assert result.status == "COMPLETE"
    capture_dir = Path(result.capture_dir)
    for name in ("stream.rtcm3", "arrival-index.csv", "source-table.txt",
                 "capture.json", "SHA256SUMS.txt"):
        assert (capture_dir / name).is_file()
    assert result.metadata["valid_frames"] == len(SYNTHETIC_MESSAGES)
    assert result.metadata["invalid_frames"] == 0
    assert result.metrics["frames_dropped"] == 0
    assert result.frames_forwarded == len(SYNTHETIC_MESSAGES)
    assert "password" not in json.dumps(result.metadata).lower()
    report = validate_capture(capture_dir)
    assert report["status"] == "VALID", report["findings"]
    assert report["index_rows"] == len(SYNTHETIC_MESSAGES)


def test_capture_lossless_with_capacity_one(tmp_path: Path) -> None:
    server = start_server("valid")
    try:
        client = _client_for("127.0.0.1", server.port, buffer_capacity=1)
        result = client.capture_stream(tmp_path, capture_id="cap-tight",
                                       duration_s=10.0, max_bytes=single_pass_bytes())
    finally:
        server.stop()
    assert result.status == "COMPLETE"
    assert result.frames_forwarded == len(SYNTHETIC_MESSAGES)
    assert result.metrics["frames_dropped"] == 0
    assert result.metrics["buffer_high_water_mark"] == 1


def test_capture_quarantines_crc_failures(tmp_path: Path) -> None:
    from nlgcp_ntrip_ingest.testserver import NtripTestServer
    from nlgcp_rtcm_replay import fixtures as replay_fixtures
    from nlgcp_rtcm_replay.framing import encode_frame

    parts = [encode_frame(m, replay_fixtures.payload_for(m)) for m in SYNTHETIC_MESSAGES]
    bad = bytearray(parts[3])
    bad[5] ^= 0x01
    corrupted = b"".join([*parts[:3], bytes(bad), *parts[4:]])
    server = NtripTestServer("corrupt", stream_bytes=corrupted)
    server.start()
    try:
        client = _client_for("127.0.0.1", server.port)
        result = client.capture_stream(tmp_path, capture_id="cap-corrupt",
                                       duration_s=10.0, max_bytes=single_pass_bytes())
    finally:
        server.stop()
    assert result.metadata["valid_frames"] == len(SYNTHETIC_MESSAGES) - 1
    assert result.metadata["invalid_frames"] == 1
    assert result.frames_forwarded == len(SYNTHETIC_MESSAGES) - 1
    assert "1005" in result.metrics["message_type_counts"]


def test_capture_disconnect_reconnects_with_new_connection(tmp_path: Path) -> None:
    server = start_server("disconnect")
    try:
        client = _client_for("127.0.0.1", server.port)
        result = client.capture_stream(tmp_path, capture_id="cap-dc",
                                       duration_s=5.0, max_bytes=1 << 20)
    finally:
        server.stop()
    assert ConnectionState.RECONNECTING.value in client.transitions
    assert result.metrics["reconnects"] >= 1
    assert result.status in ("PARTIAL", "FAILED", "COMPLETE")


def test_capture_terminal_auth_does_not_reconnect(tmp_path: Path) -> None:
    server = start_server("auth", username="user", password="pw")
    try:
        client = _client_for("127.0.0.1", server.port)
        result = client.capture_stream(tmp_path, capture_id="cap-auth",
                                       duration_s=5.0, max_bytes=1 << 20)
    finally:
        server.stop()
    assert result.status in ("PARTIAL", "FAILED")
    assert result.metrics["reconnects"] == 0
    assert client.transitions[-1] in (ConnectionState.BLOCKED.value, ConnectionState.STOPPED.value)


def test_capture_partial_frame_preserved(tmp_path: Path) -> None:
    server = start_server("partial")
    try:
        client = _client_for("127.0.0.1", server.port)
        result = client.capture_stream(tmp_path, capture_id="cap-partial",
                                       duration_s=5.0, max_bytes=1 << 20)
    finally:
        server.stop()
    # Partial bytes carry no complete frame; evidence is retained, status honest.
    assert result.status in ("PARTIAL", "FAILED", "COMPLETE")
    assert Path(result.capture_dir, "stream.rtcm3").is_file()


def test_capture_timeout_bounded(tmp_path: Path) -> None:
    server = start_server("stall", stall_silence_s=30.0)
    try:
        client = _client_for("127.0.0.1", server.port, read_timeout_s=0.3,
                             idle_timeout_s=5.0)
        result = client.capture_stream(tmp_path, capture_id="cap-stall",
                                       duration_s=2.0, max_bytes=1 << 20)
    finally:
        server.stop()
    assert result.status in ("PARTIAL", "FAILED", "COMPLETE")
    assert result.metrics["reconnects"] >= 1


def test_station_identity_unverified_still_captures_labelled(tmp_path: Path) -> None:
    server = start_server("valid")
    try:
        config = base_config(host="127.0.0.1", port=server.port)
        client = NtripClient(config, provider="test-provider", station_registry={},
                             authorization_basis="test-authorization")
        result = client.capture_stream(tmp_path, capture_id="cap-unverified",
                                       duration_s=10.0, max_bytes=single_pass_bytes())
    finally:
        server.stop()
    assert result.metadata["station_mapping"] == "STATION_IDENTITY_UNVERIFIED"
    assert result.admission["admission_status"] in ("WARN", "ACCEPT")


def test_capture_never_stores_password(tmp_path: Path) -> None:
    server = start_server("valid")
    try:
        client = _client_for("127.0.0.1", server.port, username="user", password="s3cret")
        result = client.capture_stream(tmp_path, capture_id="cap-cred",
                                       duration_s=10.0, max_bytes=single_pass_bytes())
    finally:
        server.stop()
    blob = "".join((Path(result.capture_dir) / name).read_text(errors="replace")
                   for name in ("capture.json", "arrival-index.csv", "source-table.txt"))
    assert "s3cret" not in blob


def test_path_traversal_sanitized(tmp_path: Path) -> None:
    writer = CaptureWriter.create(
        tmp_path, provider="../../etc", mountpoint="/x", station_id="..",
        capture_id="cap", caster_host="h", caster_port=2101, tls_mode="plain",
        authorization_provenance="test", software_commit="abc",
        source_table_sha256="0" * 64, source_table_text="ENDSOURCETABLE\n",
    )
    resolved = writer.capture_dir.resolve()
    assert str(resolved).startswith(str(tmp_path.resolve()))
    assert ".." not in writer.capture_dir.parts
    writer.close("FAILED")
    assert sanitize_identifier("../../etc") == "etc"
    assert sanitize_identifier("") == "unknown"


def test_dry_run_claims_no_connectivity() -> None:
    config = base_config(host="caster.example.invalid")
    report = NtripClient(config).dry_run()
    assert report["dry_run"] is True
    assert report["connectivity_claimed"] is False


def test_config_from_env_convention() -> None:
    env = {"NLGCP_NTRIP_HOST": "caster.example.invalid",
           "NLGCP_NTRIP_PORT": "2102",
           "NLGCP_NTRIP_MOUNTPOINT": "TEST00SYN",
           "NLGCP_NTRIP_USERNAME": "user",
           "NLGCP_NTRIP_PASSWORD": "pw",
           "NLGCP_NTRIP_TLS": "true",
           "NLGCP_NTRIP_USER_AGENT": "TestAgent/1.0"}
    config = config_from_env(env)
    assert (config.host, config.port) == ("caster.example.invalid", 2102)
    assert config.use_tls and config.user_agent == "TestAgent/1.0"
    assert config.validate() == []
    assert "pw" not in json.dumps(config.as_dict_redacted())


def test_config_validation_fail_closed() -> None:
    config = base_config(host="", mountpoint="")
    problems = config.validate()
    assert any("host" in p for p in problems)


def test_live_subjects_and_ordering() -> None:
    frame = LiveFrame(sequence=3, source_type="LIVE_NTRIP", provider="p",
                      station_id="EKAK00NGA", mountpoint="TEST00SYN",
                      message_number=1077, raw_bytes=b"\xd3\x00",
                      crc_status="PASS", arrival_timestamp="2026-01-01T00:00:00+00:00",
                      gnss_epoch=None, connection_id="conn-1",
                      provenance={"capture_id": "cap-1"})
    assert live_subject("EKAK00NGA") == "correction.live.EKAK00NGA"
    assert ordering_key(frame) == ("conn-1", "cap-1", 3)
    assert envelope(frame)["subject"] == "correction.live.EKAK00NGA"
    with pytest.raises(ValueError):
        live_subject("../../evil")


def test_bridge_converts_to_phase9_contract() -> None:
    frame = LiveFrame(sequence=0, source_type="LIVE_NTRIP", provider="test",
                      station_id="EKAK00NGA", mountpoint="TEST00SYN",
                      message_number=1005, raw_bytes=b"\xd3\x00\x01",
                      crc_status="PASS", arrival_timestamp="2026-01-01T00:00:00+00:00",
                      gnss_epoch=None, connection_id="conn-1",
                      provenance={"capture_id": "cap-1"})
    converted = live_to_phase9(frame, replay_timestamp="2026-01-01T00:00:01+00:00")
    assert converted.sequence == 0
    assert converted.station_id == "EKAK00NGA"
    assert converted.source_timestamp == "2026-01-01T00:00:00+00:00"
    assert converted.provenance["origin"] == "LIVE_NTRIP"
    assert converted.provenance["connection_id"] == "conn-1"


def test_phase9_admits_phase10_capture_format(tmp_path: Path) -> None:
    stream, _ = synthetic_stream()
    path = tmp_path / "stream.rtcm3"
    path.write_bytes(stream)
    digest = sha256_file(path)
    source = capture_source_for_phase9(
        source_id="phase10-pilot", source_path=str(path), station_id="EKAK00NGA",
        mountpoint="TEST00SYN", byte_size=len(stream), sha256=digest,
        capture_method="nlgcp-ntrip-ingest 0.1.0 capture",
        capture_provenance="test-authorization",
    )
    result = admit_capture_for_phase9(source)
    assert result.verdict.value in ("ACCEPT", "WARN")
    assert result.frames_valid == len(SYNTHETIC_MESSAGES)


def test_summarize_capture_round_trip(tmp_path: Path) -> None:
    server = start_server("valid")
    try:
        client = _client_for("127.0.0.1", server.port)
        result = client.capture_stream(tmp_path, capture_id="cap-sum",
                                       duration_s=10.0, max_bytes=single_pass_bytes())
    finally:
        server.stop()
    summary = summarize_capture(Path(result.capture_dir))
    assert summary["status"] == "VALID"
    assert summary["valid_frames"] == len(SYNTHETIC_MESSAGES)
    assert summary["station_mapping"] == "EKAK00NGA"
    assert len(summary["stream_sha256"]) == 64
