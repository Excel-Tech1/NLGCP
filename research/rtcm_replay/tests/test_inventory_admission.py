"""Tests for inventory, hashing, and source admission.

SYNTHETIC TEST DATA — NOT VALID FOR SCIENTIFIC RESULTS.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from nlgcp_rtcm_replay import PARSER_VERSION, fixtures
from nlgcp_rtcm_replay.admission import admit_source, sha256_file, source_fingerprint
from nlgcp_rtcm_replay.framing import parse_stream
from nlgcp_rtcm_replay.inventory import build_inventory
from nlgcp_rtcm_replay.models import (
    AdmissionVerdict,
    RTCMSource,
    SourceType,
    source_from_dict,
)
from phase9_fixtures import make_valid_source, synthetic_source, write_source_file


def test_inventory_counts_observed_types_only(tmp_path: Path) -> None:
    stream, sequence = fixtures.valid_fixture_stream()
    result = parse_stream(stream)
    inventory = build_inventory(result, parser_version=PARSER_VERSION)
    assert inventory.frames_valid == 8
    assert inventory.frames_invalid == 0
    assert inventory.crc_failures == 0
    assert sum(inventory.message_type_counts.values()) == 8
    assert inventory.message_type_counts["1005"] == 2
    assert "1001" not in inventory.message_type_counts  # never claimed
    assert inventory.inventory_fingerprint


def test_inventory_quarantines_crc_failures(tmp_path: Path) -> None:
    stream, _ = fixtures.corrupt_fixture_stream()
    result = parse_stream(stream)
    inventory = build_inventory(result, parser_version=PARSER_VERSION)
    assert inventory.frames_valid == 7
    assert inventory.frames_invalid == 1
    assert inventory.crc_failures == 1


def test_source_hashing_matches_sha256sum(tmp_path: Path) -> None:
    stream, _ = fixtures.valid_fixture_stream()
    path = write_source_file(tmp_path, "a.rtcm3", stream)
    assert sha256_file(path) == hashlib.sha256(stream).hexdigest()


def test_admission_accepts_valid_synthetic(tmp_path: Path) -> None:
    _, source, _ = make_valid_source(tmp_path)
    result = admit_source(source)
    assert result.verdict == AdmissionVerdict.ACCEPT
    assert result.frames_valid == 8
    assert result.source_fingerprint


def test_admission_labels_synthetic(tmp_path: Path) -> None:
    _, source, _ = make_valid_source(tmp_path)
    result = admit_source(source)
    assert any("SYNTHETIC" in f for f in result.findings)


def test_admission_missing_file_blocked(tmp_path: Path) -> None:
    _, source, _ = make_valid_source(tmp_path)
    missing = dict(source.as_dict())
    missing["source_path"] = str(tmp_path / "absent.rtcm3")
    result = admit_source(source_from_dict(missing))
    assert result.verdict == AdmissionVerdict.BLOCKED


def test_admission_hash_mismatch_rejected(tmp_path: Path) -> None:
    _, source, _ = make_valid_source(tmp_path)
    tampered = dict(source.as_dict())
    tampered["sha256"] = "0" * 64
    result = admit_source(source_from_dict(tampered))
    assert result.verdict == AdmissionVerdict.REJECT
    assert any("hash mismatch" in f for f in result.findings)


def test_admission_unknown_type_rejected(tmp_path: Path) -> None:
    stream, _ = fixtures.valid_fixture_stream()
    path = write_source_file(tmp_path, "u.rtcm3", stream)
    source = RTCMSource(
        source_id="unknown-001",
        source_type=SourceType.UNKNOWN,
        source_path=str(path),
        station_id="SYN00TST",
        mountpoint="SYNTHETIC",
        start_time="",
        end_time="",
        byte_size=len(stream),
        sha256=hashlib.sha256(stream).hexdigest(),
        capture_method="",
        capture_provenance="",
        rtcm_version="3.x",
        message_types=(),
        timestamp_source="",
        verified=False,
    )
    result = admit_source(source)
    assert result.verdict == AdmissionVerdict.REJECT


def test_admission_synthetic_wrong_station_rejected(tmp_path: Path) -> None:
    stream, _ = fixtures.valid_fixture_stream()
    path = write_source_file(tmp_path, "s.rtcm3", stream)
    source = synthetic_source(path, station_id="EKAK00NGA")
    result = admit_source(source)
    assert result.verdict == AdmissionVerdict.REJECT
    assert any("SYN/TEST" in f for f in result.findings)


def test_admission_real_without_provenance_rejected(tmp_path: Path) -> None:
    stream, _ = fixtures.valid_fixture_stream()
    path = write_source_file(tmp_path, "r.rtcm3", stream)
    source = RTCMSource(
        source_id="real-noprov",
        source_type=SourceType.RECORDED_RTCM,
        source_path=str(path),
        station_id="EKAK00NGA",
        mountpoint="EKAK00NGA",
        start_time="",
        end_time="",
        byte_size=len(stream),
        sha256=hashlib.sha256(stream).hexdigest(),
        capture_method="",
        capture_provenance="",
        rtcm_version="3.x",
        message_types=(),
        timestamp_source="capture",
        verified=False,
    )
    result = admit_source(source)
    assert result.verdict == AdmissionVerdict.REJECT


def test_admission_unknown_station_rejected(tmp_path: Path) -> None:
    stream, _ = fixtures.valid_fixture_stream()
    path = write_source_file(tmp_path, "r2.rtcm3", stream)
    source = RTCMSource(
        source_id="real-badstation",
        source_type=SourceType.RECORDED_RTCM,
        source_path=str(path),
        station_id="NOWHERE00XXX",
        mountpoint="NOWHERE00XXX",
        start_time="",
        end_time="",
        byte_size=len(stream),
        sha256=hashlib.sha256(stream).hexdigest(),
        capture_method="caster-capture",
        capture_provenance="field capture log 2024-026",
        rtcm_version="3.x",
        message_types=(),
        timestamp_source="capture",
        verified=True,
    )
    result = admit_source(source)
    assert result.verdict == AdmissionVerdict.REJECT


def test_admission_no_valid_frames_rejected(tmp_path: Path) -> None:
    path = write_source_file(tmp_path, "junk.bin", b"\x00\x01\x02NOT-RTCM")
    source = synthetic_source(path)
    result = admit_source(source)
    assert result.verdict == AdmissionVerdict.REJECT


def test_admission_corrupt_warns_not_accepts(tmp_path: Path) -> None:
    stream, _ = fixtures.corrupt_fixture_stream()
    path = write_source_file(tmp_path, "c.rtcm3", stream)
    source = synthetic_source(path, source_id="syn-corrupt")
    result = admit_source(source)
    assert result.verdict == AdmissionVerdict.WARN
    assert any("quarantined" in f for f in result.findings)


def test_admission_oversize_source_blocked(tmp_path: Path) -> None:
    _, source, _ = make_valid_source(tmp_path)
    result = admit_source(source, max_source_bytes=10)
    assert result.verdict == AdmissionVerdict.BLOCKED


def test_admission_malformed_metadata_blocked() -> None:
    try:
        source_from_dict({"source_id": "x"})
    except Exception as exc:  # noqa: BLE001 - fail-closed assertion below
        assert "BLOCKED" in str(exc)
    else:
        raise AssertionError("malformed source must fail closed")


def test_source_fingerprint_stable(tmp_path: Path) -> None:
    _, source, _ = make_valid_source(tmp_path)
    assert source_fingerprint(source, source.sha256) == source_fingerprint(
        source, source.sha256
    )
