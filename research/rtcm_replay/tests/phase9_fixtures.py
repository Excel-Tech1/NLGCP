"""Shared synthetic helpers for Phase 9 tests.

SYNTHETIC TEST DATA — NOT VALID FOR SCIENTIFIC RESULTS.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from nlgcp_rtcm_replay import fixtures
from nlgcp_rtcm_replay.models import ReplayConfig, RTCMSource, SourceType


def write_source_file(tmp_path: Path, name: str, data: bytes) -> Path:
    path = tmp_path / name
    path.write_bytes(data)
    return path


def synthetic_source(
    path: Path,
    *,
    source_id: str = "syn-valid-001",
    station_id: str = "SYN00TST",
    timestamp_source: str = "capture",
) -> RTCMSource:
    data = path.read_bytes()
    return RTCMSource(
        source_id=source_id,
        source_type=SourceType.SYNTHETIC_TEST_FIXTURE,
        source_path=str(path),
        station_id=station_id,
        mountpoint="SYNTHETIC",
        start_time="2026-01-01T00:00:00Z",
        end_time="2026-01-01T00:00:08Z",
        byte_size=len(data),
        sha256=hashlib.sha256(data).hexdigest(),
        capture_method="synthetic-fixture-builder",
        capture_provenance="SYNTHETIC TEST DATA — NOT VALID FOR SCIENTIFIC RESULTS",
        rtcm_version="3.x",
        message_types=("1005", "1077"),
        timestamp_source=timestamp_source,
        verified=True,
    )


def make_valid_source(tmp_path: Path, **kwargs: object) -> tuple[Path, RTCMSource, list[int]]:
    stream, sequence = fixtures.valid_fixture_stream()
    path = write_source_file(tmp_path, "valid.rtcm3", stream)
    source = synthetic_source(path, **kwargs)  # type: ignore[arg-type]
    return path, source, sequence


def default_config(speed: float = 0.0, buffer_capacity: int = 16) -> ReplayConfig:
    return ReplayConfig(speed=speed, buffer_capacity=buffer_capacity)


def source_dict(source: RTCMSource) -> dict[str, Any]:
    return dict(json.loads(json.dumps(source.as_dict())))
