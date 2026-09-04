from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from nlgcp_api.phase2_dataset import (
    ArchiveRecord,
    Phase2DatasetError,
    analyse_rinex_lines,
    build_canonical_archive,
    build_station_registry,
    calculate_baselines,
    calculate_pairwise_overlap,
    parse_rinex2_epoch,
)

SYNTHETIC_NOTICE = "SYNTHETIC TEST DATA — NOT VALID FOR SCIENTIFIC RESULTS"


def test_builds_verified_archive_and_excludes_exact_duplicate(tmp_path: Path) -> None:
    delivery = tmp_path / "00-deliveries" / "osgof-2024" / "batch-001"
    january = delivery / "ABCD00NGA Test - Nigeria" / "JANUARY"
    january.mkdir(parents=True)
    content = SYNTHETIC_NOTICE.encode()
    (january / "ABCD0010.24D.Z").write_bytes(content)
    (january / "ABCD0010 (1).24D.Z").write_bytes(content)

    result = build_canonical_archive(delivery, tmp_path)

    assert len(result.records) == 1
    assert len(result.exact_duplicates) == 1
    target = tmp_path / result.records[0].canonical_relative_path
    assert target.read_bytes() == content
    assert target.stat().st_mode & 0o222 == 0


def test_fails_closed_on_conflicting_canonical_path(tmp_path: Path) -> None:
    delivery = tmp_path / "00-deliveries" / "osgof-2024" / "batch-001"
    january = delivery / "ABCD00NGA Test - Nigeria" / "JANUARY"
    january.mkdir(parents=True)
    (january / "ABCD0010.24D.Z").write_bytes(SYNTHETIC_NOTICE.encode())
    (january / "ABCD0010 (1).24D.Z").write_bytes(b"different synthetic data")

    with pytest.raises(Phase2DatasetError, match="different content"):
        build_canonical_archive(delivery, tmp_path)


def test_extracts_header_and_detects_exact_session_gap() -> None:
    record = _record("ABCD00NGA", 1, "ABCD0010.24D.Z")
    lines = [
        _line("     2.11           OBSERVATION DATA    M", "RINEX VERSION / TYPE"),
        _line("ABCD", "MARKER NAME"),
        _line("00001M001", "MARKER NUMBER"),
        _line("observer            agency", "OBSERVER / AGENCY"),
        _line("serial              receiver            firmware", "REC # / TYPE / VERS"),
        _line("antenna             type", "ANT # / TYPE"),
        _line("        1.0000        2.0000        3.0000", "APPROX POSITION XYZ"),
        _line("    30.0000", "INTERVAL"),
        _line("", "END OF HEADER"),
        " 24  1  1  0  0  0.0000000  0  1",
        " 24  1  1  0  0 30.0000000  0  1",
        " 24  1  1  0  1 30.0000000  0  1",
        f"# {SYNTHETIC_NOTICE}",
    ]

    session, gaps = analyse_rinex_lines(lines, record)

    assert session.header.marker_name == "ABCD"
    assert session.header.approximate_position_xyz_m == (1.0, 2.0, 3.0)
    assert session.epoch_count == 3
    assert session.completeness == "incomplete"
    assert len(gaps) == 1
    assert gaps[0].estimated_missing_epochs == 1


def test_rinex2_epoch_parser_rejects_numeric_observation_row() -> None:
    observation = " 121801828.596 7                  23178079.719"

    assert parse_rinex2_epoch(observation) is None


def test_builds_registry_approximate_baselines_and_temporal_overlap() -> None:
    first, _ = analyse_rinex_lines(
        _complete_half_day_lines("AAAA", (0.0, 0.0, 0.0)),
        _record("AAAA00NGA", 1, "AAAA0010.24D.Z"),
    )
    second, _ = analyse_rinex_lines(
        _complete_half_day_lines("BBBB", (3000.0, 4000.0, 0.0)),
        _record("BBBB00NGA", 1, "BBBB0010.24D.Z"),
    )

    registry = build_station_registry([first, second], {"AAAA00NGA": "Alpha", "BBBB00NGA": "Beta"})
    baselines = calculate_baselines(registry)
    overlap = calculate_pairwise_overlap([first, second])

    assert first.completeness == "complete"
    assert len(registry) == 2
    assert registry[0]["coordinate_reference_frame"] is None
    assert baselines[0]["ecef_chord_distance_km"] == 5.0
    assert overlap[0]["common_session_days"] == 1
    assert overlap[0]["total_overlap_hours"] == 24.0


def _record(station: str, day_of_year: int, filename: str) -> ArchiveRecord:
    return ArchiveRecord(
        source_relative_path=f"source/{filename}",
        canonical_relative_path=(
            f"raw/nignet/2024/{station}/{day_of_year:03d}/observation/{filename}"
        ),
        station_id=station,
        year=2024,
        day_of_year=day_of_year,
        artifact_type="observation",
        size_bytes=1,
        sha256="a" * 64,
    )


def _complete_half_day_lines(marker: str, xyz: tuple[float, float, float]) -> list[str]:
    return [
        _line("     2.11           OBSERVATION DATA    M", "RINEX VERSION / TYPE"),
        _line(marker, "MARKER NAME"),
        _line(f"{xyz[0]:14.4f}{xyz[1]:14.4f}{xyz[2]:14.4f}", "APPROX POSITION XYZ"),
        _line(" 43200.0000", "INTERVAL"),
        _line("", "END OF HEADER"),
        " 24  1  1  0  0  0.0000000  0  1",
        " 24  1  1 12  0  0.0000000  0  1",
        f"# {SYNTHETIC_NOTICE}",
    ]


def _line(content: str, label: str) -> str:
    return f"{content[:60]:<60}{label}\n"


def test_fixture_epoch_is_utc() -> None:
    assert datetime(2024, 1, 1, tzinfo=UTC).utcoffset() is not None
