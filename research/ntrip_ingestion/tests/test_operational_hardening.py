"""SYNTHETIC TEST DATA — NOT VALID FOR SCIENTIFIC RESULTS."""

from __future__ import annotations

from pathlib import Path

from nlgcp_ntrip_ingest.capture import (
    CaptureRotationPolicy,
    find_incomplete_captures,
    recover_incomplete_capture,
)
from nlgcp_ntrip_ingest.client import NtripClient
from nlgcp_ntrip_ingest.models import ConnectionState, LiveFrame, NtripConfig
from nlgcp_ntrip_ingest.publisher import BoundedPublisher
from nlgcp_ntrip_ingest.status import readiness, service_status


def test_liveness_and_disabled_readiness_are_distinct_from_streaming() -> None:
    result = service_status(NtripConfig(), stream_state=ConnectionState.DISCONNECTED)
    assert result.liveness.status == "ALIVE"
    assert result.readiness.status == "READY"
    assert not result.readiness.configured_stream
    assert result.readiness.scientific_validity == "NOT_ASSESSED"


def test_invalid_config_is_not_ready_before_network_activity(tmp_path: Path) -> None:
    config = NtripConfig(host="caster", mountpoint="", port=0)
    result = readiness(config, required_directories=(tmp_path,))
    assert result.status == "NOT_READY"
    assert "mountpoint must be non-empty" in result.reason_codes


def test_shutdown_request_transitions_without_dialling() -> None:
    client = NtripClient(NtripConfig())
    client.request_shutdown()
    assert client.state == ConnectionState.STOPPED
    assert client.transitions[-1] == ConnectionState.STOPPED.value


def test_secret_snapshot_redacts_username_password_and_nats_url() -> None:
    config = NtripConfig(
        host="caster.example.invalid",
        mountpoint="TEST00SYN",
        username="user",
        password="secret",
        nats_url="nats://user:secret@nats.example.invalid:4222",
    )
    snapshot = config.as_dict_redacted()
    assert snapshot["username"] == "***REDACTED***"
    assert snapshot["password"] == "***REDACTED***"
    assert "secret" not in str(snapshot)


def test_rotation_is_checked_before_a_frame_is_split() -> None:
    policy = CaptureRotationPolicy(max_bytes=10, max_frames=2)
    assert not policy.requires_rotation(
        current_bytes=0, current_frames=0, elapsed_seconds=0, next_frame_bytes=10
    )
    assert policy.requires_rotation(
        current_bytes=10, current_frames=1, elapsed_seconds=0, next_frame_bytes=1
    )
    assert policy.requires_rotation(
        current_bytes=0, current_frames=2, elapsed_seconds=0, next_frame_bytes=1
    )


def test_interrupted_capture_is_recovered_without_rewriting_raw_bytes(tmp_path: Path) -> None:
    directory = tmp_path / "provider" / "station" / "date" / "capture"
    directory.mkdir(parents=True)
    stream = directory / "stream.rtcm3"
    stream.write_bytes(b"partial bytes")
    assert find_incomplete_captures(tmp_path) == (directory,)
    before = stream.read_bytes()
    metadata = recover_incomplete_capture(directory)
    assert stream.read_bytes() == before
    assert metadata["capture_status"] == "PARTIAL"
    assert metadata["interruption_reason"] == "PROCESS_INTERRUPTED"
    assert find_incomplete_captures(tmp_path) == ()
    assert recover_incomplete_capture(directory)["capture_status"] == "PARTIAL"


def test_bounded_publisher_preserves_subject_and_counts_overflow() -> None:
    publisher = BoundedPublisher(capacity=1)
    frame = LiveFrame(
        sequence=0,
        source_type="LIVE_NTRIP",
        provider="synthetic-provider",
        station_id="SYNA00SYN",
        mountpoint="SYNTHETIC",
        message_number=4095,
        raw_bytes=b"synthetic",
        crc_status="PASS",
        arrival_timestamp="2026-01-01T00:00:00Z",
        gnss_epoch=None,
        connection_id="conn-1",
        provenance={"capture_id": "synthetic-capture"},
    )
    assert publisher.publish(frame)
    assert not publisher.publish(frame)
    envelope = publisher.take()
    assert envelope is not None
    assert envelope["subject"] == "correction.live.SYNA00SYN"
    assert publisher.metrics.dropped == 1
    publisher.close()
    assert not publisher.publish(frame)
    assert publisher.metrics.failed == 1
