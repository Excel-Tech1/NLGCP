from __future__ import annotations

import gzip
import json
from hashlib import sha256
from pathlib import Path

from nlgcp_api.rinex_inventory import (
    discover_rinex_inventory,
    inventory_file,
    write_inventory,
)

SYNTHETIC_NOTICE = "SYNTHETIC TEST DATA - NOT VALID FOR SCIENTIFIC RESULTS"


def test_inventories_rinex3_observation_file(tmp_path: Path) -> None:
    rinex_path = tmp_path / "raw" / "ABCD00NGA_R_20260010000_01D_30S_MO.rnx"
    rinex_path.parent.mkdir()
    rinex_path.write_text(
        "\n".join(
            [
                _rinex_line("     3.04           OBSERVATION DATA    M", "RINEX VERSION / TYPE"),
                _rinex_line("ABCD", "MARKER NAME"),
                _rinex_line(
                    "  2026     1     1     0     0    0.0000000     GPS",
                    "TIME OF FIRST OBS",
                ),
                _rinex_line(
                    "  2026     1     1     0     1    0.0000000     GPS",
                    "TIME OF LAST OBS",
                ),
                _rinex_line("", "END OF HEADER"),
                "> 2026 01 01 00 00  0.0000000  0  1",
                "> 2026 01 01 00 00 30.0000000  0  1",
                f"# {SYNTHETIC_NOTICE}",
            ]
        )
        + "\n",
        encoding="ascii",
    )

    record = inventory_file(rinex_path, tmp_path)

    assert record.relative_vault_path == (
        "raw/ABCD00NGA_R_20260010000_01D_30S_MO.rnx"
    )
    assert record.station_marker == "ABCD"
    assert record.rinex_version == "3.04"
    assert record.file_type == "observation"
    assert record.compression is None
    assert record.observation_date == "2026-01-01"
    assert record.first_epoch == "2026-01-01T00:00:00Z"
    assert record.last_epoch == "2026-01-01T00:01:00Z"
    assert record.approximate_sampling_interval_seconds == 30.0
    assert record.sha256 == sha256(rinex_path.read_bytes()).hexdigest()
    assert record.parser_status == "parsed"
    assert record.errors == []


def test_discovers_gzip_rinex2_navigation_file(tmp_path: Path) -> None:
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    nav_path = raw_dir / "abcd0010.26n.gz"
    content = "\n".join(
        [
            _rinex_line("     2.11           NAVIGATION DATA     G", "RINEX VERSION / TYPE"),
            _rinex_line("", "END OF HEADER"),
            f"# {SYNTHETIC_NOTICE}",
        ]
    )
    with gzip.open(nav_path, "wt", encoding="ascii") as nav_file:
        nav_file.write(content)

    records = discover_rinex_inventory(tmp_path)

    assert len(records) == 1
    assert records[0].filename == "abcd0010.26n.gz"
    assert records[0].station_marker == "ABCD"
    assert records[0].file_type == "navigation"
    assert records[0].compression == "gzip"
    assert records[0].parser_status == "parsed"


def test_reports_unsupported_compression_without_modifying_file(tmp_path: Path) -> None:
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    compressed_path = raw_dir / "abcd0010.26o.Z"
    compressed_path.write_bytes(b"not actually parsed\n")

    record = inventory_file(compressed_path, tmp_path)

    assert record.parser_status == "not_parsed"
    assert record.compression == "unix-compress"
    assert record.warnings == [
        "compression unix-compress is discovered but not parsed"
    ]
    assert compressed_path.read_bytes() == b"not actually parsed\n"


def test_write_inventory_is_deterministic_json(tmp_path: Path) -> None:
    rinex_path = tmp_path / "raw" / "ABCD00NGA_R_20260010000_01D_30S_MO.rnx"
    output_path = tmp_path / "manifests" / "rinex-inventory.json"
    rinex_path.parent.mkdir()
    rinex_path.write_text(
        "\n".join(
            [
                _rinex_line("     3.04           OBSERVATION DATA    M", "RINEX VERSION / TYPE"),
                _rinex_line("", "END OF HEADER"),
                f"# {SYNTHETIC_NOTICE}",
            ]
        )
        + "\n",
        encoding="ascii",
    )
    records = discover_rinex_inventory(tmp_path)

    write_inventory(records, output_path)
    first = output_path.read_text(encoding="utf-8")
    write_inventory(records, output_path)
    second = output_path.read_text(encoding="utf-8")

    assert first == second
    assert json.loads(first)[0]["relative_vault_path"] == (
        "raw/ABCD00NGA_R_20260010000_01D_30S_MO.rnx"
    )


def _rinex_line(content: str, label: str) -> str:
    return f"{content[:60]:<60}{label}"
