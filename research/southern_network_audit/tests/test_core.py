"""Synthetic unit fixtures for archive and geometry primitives."""

from __future__ import annotations

import csv
import gzip
import io
import json
import tarfile
import zipfile
from pathlib import Path
from zipfile import ZipFile

import pytest
from nlgcp_southern_audit.core import (
    BUFFER_SIZE,
    classify_file,
    combinations,
    convex_hull,
    coordinate_provenance_status,
    ecef_to_enu,
    ecef_to_geodetic,
    intersect_windows,
    parse_header_time,
    parse_rinex_header,
    point_in_polygon,
    safe_extract_tar,
    safe_extract_zip,
    station_code,
)
from nlgcp_southern_audit.pipeline import _geometry, _header_from_zip, _record_hash, run_audit


def _header(version: str, kind: str = "O") -> bytes:
    def line(content: str, label: str) -> str:
        return content.ljust(60)[:60] + label.ljust(20)

    lines = [
        line(f"{version:>9}           {kind}                   GPS", "RINEX VERSION / TYPE"),
        line("TESTMARKER", "MARKER NAME"),
        line("12345", "MARKER NUMBER"),
        line("RX01                RX TYPE             1.2", "REC # / TYPE / VERS"),
        line("ANT01               ANT TYPE", "ANT # / TYPE"),
        line("  6378137.0000        0.0000        0.0000", "APPROX POSITION XYZ"),
        line("     1.000", "INTERVAL"),
        line(" 2024     1     2     3     4   5.0000000".ljust(48) + "GPS", "TIME OF FIRST OBS"),
        line(" 2024     1     2     3     4  59.0000000".ljust(48) + "GPS", "TIME OF LAST OBS"),
        line("", "END OF HEADER"),
    ]
    return ("\n".join(lines) + "\n").encode()


def test_rinex2_header_and_station_coordinate() -> None:
    parsed = parse_rinex_header(io.BytesIO(_header("     2.11")))
    assert parsed.version == "2.11"
    assert parsed.marker_name == "TESTMARKER"
    assert parsed.approx_xyz == (6378137.0, 0.0, 0.0)
    assert parsed.time_system == "GPS"
    assert station_code("ABCD0010.24O", parsed.marker_name) == "ABCD"


def test_rinex3_and_4_system_observables() -> None:
    for version in ("     3.04", "     4.00"):
        system_line = b"G    2 C1C L1C".ljust(60) + b"SYS / # / OBS TYPES".ljust(20)
        end_line = b"".ljust(60) + b"END OF HEADER".ljust(20)
        raw = _header(version).replace(end_line, system_line + b"\n" + end_line)
        parsed = parse_rinex_header(io.BytesIO(raw))
        assert parsed.version.strip() == version.strip()
        assert "G" in parsed.systems
        assert {"C1C", "L1C"}.issubset(parsed.observables)


def test_compressed_rinex_detection() -> None:
    assert classify_file("ABCD00XXX_R_20240010000_01D_30S_MO.crx.gz")[0] == "hatanaka_observation"
    assert classify_file("ABCD0010.24o.gz")[0] == "observation"


def test_time_parsing_and_scale_mismatch_are_not_mixed() -> None:
    gps, scale_gps = parse_header_time("2024 1 2 3 4 5.0000000 GPS")
    utc, scale_utc = parse_header_time("2024 1 2 3 4 5.0000000 UTC")
    assert gps is not None and utc is not None and gps == utc
    assert gps.tzinfo is None and utc.tzinfo is None
    assert intersect_windows([(gps, gps, scale_gps, "a"), (utc, utc, scale_utc, "b")]) is None
    assert intersect_windows([(gps, gps, scale_gps, "a"), (gps, gps, scale_gps, "b")]) == (
        gps,
        gps,
    )


def test_ecef_to_enu_origin_and_geodetic() -> None:
    origin = (6378137.0, 0.0, 0.0)
    assert ecef_to_geodetic(*origin) == (0.0, 0.0, 0.0)
    assert ecef_to_enu(origin, origin) == (0.0, 0.0, 0.0)


def test_coordinate_provenance_fails_closed() -> None:
    xyz = (6378137.0, 0.0, 0.0)
    assert coordinate_provenance_status(None) == "MISSING"
    assert coordinate_provenance_status(xyz) == "PROVISIONAL"
    assert coordinate_provenance_status(xyz, "SINEX", "IGS20", "2024.0") == "VERIFIED"


def test_convex_hull_containment_and_combinations() -> None:
    hull = convex_hull([(0, 0), (2, 0), (2, 2), (0, 2), (1, 1), (0, 0)])
    assert len(hull) == 4
    assert point_in_polygon((1, 1), hull) == "INSIDE"
    assert point_in_polygon((3, 1), hull) == "OUTSIDE"
    assert point_in_polygon((0, 1), hull) == "BOUNDARY"
    assert len(list(combinations(["A", "B", "C", "D"], (3, 4)))) == 5
    assert point_in_polygon((1, 0), convex_hull([(0, 0), (1, 0), (2, 0)])) == "DEGENERATE"


def test_geometry_ranking_and_held_out_containment() -> None:
    # SYNTHETIC TEST DATA — NOT VALID FOR SCIENTIFIC RESULTS.
    stations = {
        "A": {
            "xyz": (6378137.0, -1000.0, -1000.0),
            "coordinate_status": "PROVISIONAL",
            "common_days": 2,
            "navigation_match": 0,
        },
        "B": {
            "xyz": (6378137.0, 1000.0, -1000.0),
            "coordinate_status": "PROVISIONAL",
            "common_days": 2,
            "navigation_match": 0,
        },
        "C": {
            "xyz": (6378137.0, 1000.0, 1000.0),
            "coordinate_status": "PROVISIONAL",
            "common_days": 2,
            "navigation_match": 0,
        },
        "D": {
            "xyz": (6378137.0, -1000.0, 1000.0),
            "coordinate_status": "PROVISIONAL",
            "common_days": 2,
            "navigation_match": 0,
        },
        "T": {
            "xyz": (6378137.0, 0.0, 0.0),
            "coordinate_status": "PROVISIONAL",
            "common_days": 2,
            "navigation_match": 0,
        },
    }
    _, held, rankings, _ = _geometry(stations, (4,))
    square = next(
        row
        for row in held
        if row["reference_stations"] == "A+B+C+D" and row["target_station"] == "T"
    )
    rank = next(
        row
        for row in rankings
        if row["reference_stations"] == "A+B+C+D" and row["target_station"] == "T"
    )
    assert square["containment"] == "INSIDE"
    assert rank["state"] == "GEOMETRY_PROVISIONAL"
    assert rank["rank_basis"].startswith("Lexicographic")


def test_zip_safe_extraction_rejects_traversal_and_preserves_existing(tmp_path: Path) -> None:
    archive = tmp_path / "bad.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("../escape.txt", "bad")
    dest = tmp_path / "out"
    with pytest.raises(ValueError, match="unsafe archive"):
        safe_extract_zip(archive, dest)
    safe_archive = tmp_path / "good.zip"
    with zipfile.ZipFile(safe_archive, "w") as zf:
        zf.writestr("safe/file.txt", "ok")
    dest.mkdir()
    (dest / "safe").mkdir()
    (dest / "safe/file.txt").write_text("keep")
    with pytest.raises(FileExistsError):
        safe_extract_zip(safe_archive, dest)
    assert (dest / "safe/file.txt").read_text() == "keep"


def test_zip_safe_extraction_rejects_symlink(tmp_path: Path) -> None:
    archive = tmp_path / "link.zip"
    info = zipfile.ZipInfo("link")
    info.create_system = 3
    info.external_attr = 0o120777 << 16
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr(info, "../../outside")
    with pytest.raises(ValueError, match="unsafe archive"):
        safe_extract_zip(archive, tmp_path / "out")


def test_tar_safe_extraction_rejects_symlink(tmp_path: Path) -> None:
    archive = tmp_path / "link.tar"
    with tarfile.open(archive, "w") as tf:
        member = tarfile.TarInfo("link")
        member.type = tarfile.SYMTYPE
        member.linkname = "../../outside"
        tf.addfile(member)
    with pytest.raises(ValueError, match="unsafe archive"):
        safe_extract_tar(archive, tmp_path / "out")


def test_compressed_observation_header_and_epoch_scan(tmp_path: Path) -> None:
    # SYNTHETIC TEST DATA — NOT VALID FOR SCIENTIFIC RESULTS.
    header = _header("     2.11").replace(
        ("".ljust(60) + "TIME OF LAST OBS".ljust(20) + "\n").encode(), b""
    )
    epochs = b" 24  1  2  3  4  5.0000000  0  1G01\n 24  1  2  3  4 35.0000000  0  1G01\n"
    archive = tmp_path / "compressed.zip"
    with ZipFile(archive, "w") as zf:
        zf.writestr("ABCD0020.24O.gz", gzip.compress(header + epochs))
        zf.writestr("EFGH0020.24O", header + epochs)
    with ZipFile(archive) as zf:
        compressed = zf.getinfo("ABCD0020.24O.gz")
        parsed = _header_from_zip(zf, compressed)
        assert parsed is not None and parsed.time_system == "GPS"
        _, _, status, first, last, count = _record_hash(
            zf, zf.getinfo("EFGH0020.24O"), scan_rinex2=True
        )
    assert status == "OK"
    assert first is not None and last is not None
    assert (last - first).total_seconds() == 30
    assert count == 2


def test_epoch_scanner_never_treats_partial_line_as_epoch(tmp_path: Path) -> None:
    # SYNTHETIC TEST DATA — NOT VALID FOR SCIENTIFIC RESULTS.
    fake = b" 01  1 27  7 38 30.0000000  0  1G01"
    filler = b"X" * (BUFFER_SIZE - 128 - len(fake))
    first_chunk = filler + fake + b"X" * (128 - len(fake))
    real = b"\n 11  1 27  7 38 30.0000000  0  1G01\n"
    archive = tmp_path / "boundary.zip"
    with ZipFile(archive, "w") as zf:
        zf.writestr("boundary.11O", first_chunk + real)
    with ZipFile(archive) as zf:
        result = _record_hash(zf, zf.getinfo("boundary.11O"), scan_rinex2=True)
    assert result[-1] == 1
    assert result[3] == result[4]
    assert result[3] is not None and result[3].year == 2011


def test_missing_metadata_is_explicit() -> None:
    parsed = parse_rinex_header(io.BytesIO(b"no rinex header\n"))
    assert parsed.parse_status == "incomplete_header"
    assert set(parsed.missing_fields) == {"version", "marker_name", "approx_xyz"}


def test_inventory_duplicate_detection_and_raw_preservation(tmp_path: Path) -> None:
    # SYNTHETIC TEST DATA — NOT VALID FOR SCIENTIFIC RESULTS.
    archive = tmp_path / "small.zip"
    first = _header("     2.11")
    second = first.replace(b"     1.000", b"     2.000")
    later_day = first.replace(b"2024     1     2", b"2024     1     4")
    with ZipFile(archive, "w") as zf:
        zf.writestr("one/ABCD0020.24O", first)
        zf.writestr("two/ABCD0020.24O", second)
        zf.writestr("other/EFGH0040.24O", later_day)
    output = tmp_path / "derived"
    result = run_audit(archive, output)
    assert result["raw_data_extracted"] is False
    duplicates = (output / "duplicate_analysis.csv").read_text()
    inventory = json.loads((output / "file_inventory.json").read_text())
    with (output / "station_day_availability.csv").open(newline="") as stream:
        availability = list(csv.DictReader(stream))
    assert "DUPLICATE_STATION_DAY_SESSION" in duplicates
    assert "CONFLICTING_BASENAME" in duplicates
    assert all(row["sha256"] for row in inventory)
    observed = next(
        row for row in availability if row["station_code"] == "ABCD" and row["date"] == "2024-01-02"
    )
    missing = next(
        row for row in availability if row["station_code"] == "ABCD" and row["date"] == "2024-01-03"
    )
    assert observed["availability"] == "OBSERVED_WINDOW_SCANNED"
    assert missing["availability"] == "MISSING"
    assert not (tmp_path / "one").exists()
