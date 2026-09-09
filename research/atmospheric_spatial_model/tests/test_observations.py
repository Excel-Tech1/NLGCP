"""Tests for RINEX 2 extraction and common-observation discovery (synthetic)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from nlgcp_atmospheric_model.observations import (  # noqa: E402
    common_epochs,
    common_satellite_summary,
    common_satellites,
    discover_observables,
    parse_rinex2_header,
    read_rinex2_observations,
)
from phase6_fixtures import epoch_line, obs_line, write_rinex2  # noqa: E402


def test_header_parses_obs_types(tmp_path: Path) -> None:
    path = write_rinex2(tmp_path / "T001.24O")
    header = parse_rinex2_header(path)
    assert header.obs_types == ("L1", "L2", "C1", "P1")
    assert header.interval_s == pytest.approx(30.0)
    assert header.approx_xyz_m is not None


def test_epochs_and_values_parse(tmp_path: Path) -> None:
    path = write_rinex2(tmp_path / "T002.24O", epochs=3)
    dataset = read_rinex2_observations(path, "T002")
    assert len(dataset.epochs) == 3
    first = dataset.data[dataset.epochs[0]]["G01"]
    assert first.values["L1"] == pytest.approx(1_000_000.0)
    assert first.values["L2"] == pytest.approx(800_000.0)


def test_stride_decimation_is_deterministic(tmp_path: Path) -> None:
    path = write_rinex2(tmp_path / "T003.24O", epochs=6)
    full = read_rinex2_observations(path, "T003", stride=1)
    part = read_rinex2_observations(path, "T003", stride=2)
    assert len(full.epochs) == 6
    assert len(part.epochs) == 3
    assert part.epochs == full.epochs[::2]


def test_epoch_flag_excluded_with_reason(tmp_path: Path) -> None:
    path = tmp_path / "T004.24O"
    write_rinex2(path, epochs=2)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(epoch_line(minute=2, flag=5, sats=["G01"]) + "\n")
        handle.write(obs_line([1.0, 2.0, 3.0, 4.0]) + "\n")
    dataset = read_rinex2_observations(path, "T004")
    assert len(dataset.epochs) == 2
    assert dataset.skip_reasons.get("epoch flag 5 excluded") == 1


def test_malformed_epoch_line_counted(tmp_path: Path) -> None:
    path = write_rinex2(tmp_path / "T005.24O", epochs=1)
    with path.open("a", encoding="utf-8") as handle:
        handle.write("not an epoch line\n")
    dataset = read_rinex2_observations(path, "T005")
    assert dataset.skip_reasons.get("malformed epoch line") == 1


def test_more_than_twelve_satellites(tmp_path: Path) -> None:
    sats = [f"G{i:02d}" for i in range(1, 15)]
    path = write_rinex2(tmp_path / "T006.24O", epochs=1, sats=sats)
    dataset = read_rinex2_observations(path, "T006")
    assert len(dataset.data[dataset.epochs[0]]) == 14


def test_common_epochs_require_all_stations(tmp_path: Path) -> None:
    a = read_rinex2_observations(write_rinex2(tmp_path / "A.24O", epochs=3), "A")
    b = read_rinex2_observations(write_rinex2(tmp_path / "B.24O", epochs=3, gap_at=1), "B")
    common = common_epochs({"A": a, "B": b})
    assert len(common) == 2


def test_common_satellites_require_l1_l2(tmp_path: Path) -> None:
    a = read_rinex2_observations(write_rinex2(tmp_path / "A2.24O", epochs=1), "A2")
    b = read_rinex2_observations(
        write_rinex2(tmp_path / "B2.24O", epochs=1, codes=["L1", "C1"]), "B2"
    )
    epoch = a.epochs[0]
    assert common_satellites({"A2": a, "B2": b}, epoch) == {}
    discovery = discover_observables({"A2": a, "B2": b})
    assert discovery["gps_l1_l2_compatible"] is False


def test_glonass_excluded_from_gf_common(tmp_path: Path) -> None:
    a = read_rinex2_observations(
        write_rinex2(tmp_path / "A3.24O", epochs=1, sats=["G01", "R07"]), "A3"
    )
    b = read_rinex2_observations(
        write_rinex2(tmp_path / "B3.24O", epochs=1, sats=["G01", "R07"]), "B3"
    )
    common = common_satellites({"A3": a, "B3": b}, a.epochs[0])
    assert set(common) == {"G01"}


def test_summary_statistics(tmp_path: Path) -> None:
    a = read_rinex2_observations(write_rinex2(tmp_path / "A4.24O", epochs=4), "A4")
    b = read_rinex2_observations(write_rinex2(tmp_path / "B4.24O", epochs=4), "B4")
    summary = common_satellite_summary({"A4": a, "B4": b}, common_epochs({"A4": a, "B4": b}))
    assert summary["epoch_count"] == 4
    assert summary["median_gps_l1l2_common"] == 2.0
    assert summary["minimum_gps_l1l2_common"] == 2
    assert summary["usable_epoch_fraction"] == pytest.approx(1.0)


def test_missing_file_header_only_graceful(tmp_path: Path) -> None:
    empty = tmp_path / "E.24O"
    empty.write_text("garbage\n", encoding="utf-8")
    header = parse_rinex2_header(empty)
    assert header.obs_types == ()
    dataset = read_rinex2_observations(empty, "E")
    assert dataset.epochs == []
    assert "no observation types in header" in dataset.skip_reasons


def _field(value: float | None) -> str:
    if value is None:
        return " " * 16
    return f"{value:14.3f}  "


def test_multiline_blocks_with_blank_lines_stay_aligned(tmp_path: Path) -> None:
    """Real RINEX 2 files (>5 obs types, SBAS sats with only C1) contain
    blank lines *inside* satellite observation blocks. Those lines are
    structural: skipping them desynchronises every later record
    (observed on the real DOY 026 archive: L1/L2 columns misassigned).
    """
    codes = ["C1", "L1", "L2", "P2", "P1", "C2", "C5", "L5", "C6", "L6", "C7", "L7", "C8", "L8"]
    first = f"{len(codes):6d}" + "".join(f"{c:>6s}" for c in codes[:9])
    second = "      " + "".join(f"{c:>6s}" for c in codes[9:])
    header_lines = [
        "     2.11           OBSERVATION DATA    M (MIXED)",
        first.ljust(60) + "# / TYPES OF OBSERV",
        second.ljust(60) + "# / TYPES OF OBSERV",
        "    30.0000".ljust(60) + "INTERVAL",
        ("  2024     1    26     0     0    0.0000000".ljust(48) + "GPS").ljust(60)
        + "TIME OF FIRST OBS",
        "                                                            END OF HEADER",
    ]
    gps_values: list[float | None] = [
        22000000.0,
        115000000.0,
        89600000.0,
        22000001.0,
        22000002.0,
        22000003.0,
        22000004.0,
        22000005.0,
        22000006.0,
        22000007.0,
        22000008.0,
        22000009.0,
        22000010.0,
        22000011.0,
    ]

    def sat_block(values: list[float | None]) -> list[str]:
        fields = "".join(_field(v) for v in values)
        return [fields[k : k + 80] for k in range(0, len(fields), 80)]

    body: list[str] = []
    for minute in (0, 1):
        body.append(epoch_line(minute=minute, second=0.0, sats=["G01", "S48"]))
        body.extend(sat_block(gps_values))
        body.extend(sat_block([30000000.0] + [None] * 13))
    path = tmp_path / "M.24O"
    path.write_text("\n".join(header_lines + body) + "\n", encoding="utf-8")

    header = parse_rinex2_header(path)
    assert len(header.obs_types) == 14
    dataset = read_rinex2_observations(path, "M")
    assert len(dataset.epochs) == 2
    for epoch in dataset.epochs:
        sats = dataset.data[epoch]
        assert set(sats) == {"G01", "S48"}
        gps = sats["G01"]
        assert gps.values["L1"] == pytest.approx(115000000.0)
        assert gps.values["L2"] == pytest.approx(89600000.0)
        l1 = gps.values["L1"]
        l2 = gps.values["L2"]
        assert l1 is not None and l2 is not None
        assert l1 / l2 == pytest.approx(1.2833, rel=1e-3)
        sbas = sats["S48"]
        assert sbas.values["C1"] == pytest.approx(30000000.0)
        assert sbas.values["L1"] is None
        assert sbas.values["L2"] is None
