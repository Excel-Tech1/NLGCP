"""SYNTHETIC TEST DATA — NOT VALID FOR SCIENTIFIC RESULTS."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import nlgcp_gnss_qc.engine as qc_engine
import pytest
from nlgcp_api.rinex_inventory import sha256_file
from nlgcp_gnss_qc.classify import classify_session
from nlgcp_gnss_qc.dataset import (
    CoordinateEligibility,
    DatasetError,
    NavigationProduct,
    inventory_navigation_products,
    load_session_inputs,
    navigation_for_session,
    parse_filename,
    resolve_identity,
)
from nlgcp_gnss_qc.engine import plan_dataset, select_sessions
from nlgcp_gnss_qc.models import (
    Classification,
    RinexAnalysis,
    SessionInput,
    overall_classification,
)
from nlgcp_gnss_qc.profiles import ProfileError, load_profiles
from nlgcp_gnss_qc.rinex import RinexParseError, analyse_rinex2, phase_frequencies
from nlgcp_single_base.conversion import ObservationConversion

SYNTHETIC_LABEL = "SYNTHETIC TEST DATA — NOT VALID FOR SCIENTIFIC RESULTS"


def header_line(content: str, label: str) -> str:
    return f"{content:<60}{label:<20}\n"


def epoch_line(second: int, satellites: tuple[str, ...] = ("G01", "R01")) -> str:
    minute, second_in_minute = divmod(second, 60)
    return (
        f" 24  1 26  0 {minute:2d} {float(second_in_minute):10.7f}  "
        f"0{len(satellites):3d}{''.join(satellites)}\n"
    )


def observation_line(*, lli: str = "0") -> str:
    fields = [f"{20_000_000 + index:14.3f}{lli if index in {1, 2} else '0'}5" for index in range(4)]
    return "".join(fields) + "\n"


def synthetic_rinex(
    *, marker: str = "ABFC", seconds: tuple[int, ...] = (0, 30, 60), lli: str = "0"
) -> list[str]:
    types = f"{4:6d}" + "".join(f"{value:>6}" for value in ("C1", "L1", "L2", "P2"))
    lines = [
        header_line("     2.11           OBSERVATION DATA    M", "RINEX VERSION / TYPE"),
        header_line(marker, "MARKER NAME"),
        header_line("33805M001", "MARKER NUMBER"),
        header_line("OBSERVER            OSGOF", "OBSERVER / AGENCY"),
        header_line("RX001               TEST RX             1.0", "REC # / TYPE / VERS"),
        header_line("ANT001              TEST ANTENNA        NONE", "ANT # / TYPE"),
        header_line("  6246471.0       820849.0       994268.0", "APPROX POSITION XYZ"),
        header_line("        0.1000        0.0000        0.0000", "ANTENNA: DELTA H/E/N"),
        header_line(types, "# / TYPES OF OBSERV"),
        header_line("    30.000", "INTERVAL"),
        header_line("  2024     1    26     0     0    0.0000000     GPS", "TIME OF FIRST OBS"),
        header_line("    18", "LEAP SECONDS"),
        header_line(SYNTHETIC_LABEL, "COMMENT"),
        header_line("", "END OF HEADER"),
    ]
    for second in seconds:
        lines.append(epoch_line(second))
        lines.extend([observation_line(lli=lli), observation_line(lli=lli)])
    return lines


@pytest.fixture
def analysis():  # type: ignore[no-untyped-def]
    return analyse_rinex2(synthetic_rinex(), year=2024, day_of_year=26)


@pytest.fixture
def session(tmp_path: Path) -> tuple[SessionInput, Path]:
    source = tmp_path / "ABFC0260.24D.Z"
    source.write_bytes(b"synthetic")
    return (
        SessionInput(
            station_id="ABFC00NGA",
            year=2024,
            day_of_year=26,
            relative_path="raw/nignet/2024/ABFC00NGA/026/observation/ABFC0260.24D.Z",
            source_relative_path="delivery/ABFC0260.24D.Z",
            sha256="observed",
            size_bytes=source.stat().st_size,
        ),
        source,
    )


def test_rinex_filename_parsing_and_hatanaka_recognition() -> None:
    assert parse_filename("ABFC0260.24D.Z") == ("ABFC", 2024, 26, "D")


@pytest.mark.parametrize("name", ["bad.24D.Z", "ABFC0000.24D.Z", "ABFC3670.24D.Z"])
def test_invalid_filename_rejected(name: str) -> None:
    with pytest.raises(DatasetError):
        parse_filename(name)


@pytest.mark.parametrize(
    ("station", "marker", "expected"),
    [
        ("ABFC00NGA", "ABFC", "CANONICAL_MATCH"),
        ("BKFP00NGA", "BIKE", "KNOWN_ALIAS"),
        ("FUTY00NGA", "YLAD", "KNOWN_ALIAS"),
        ("ULAG00NGA", "LGLA", "KNOWN_ALIAS"),
        ("UNEC00NGA", "ENEN", "KNOWN_ALIAS"),
        ("UNEC00NGA", "UNEC", "CANONICAL_MATCH"),
    ],
)
def test_known_station_aliases(station: str, marker: str, expected: str) -> None:
    assert resolve_identity(station, marker, marker) == expected


def test_unknown_alias_fails_closed() -> None:
    with pytest.raises(DatasetError, match="not registered"):
        resolve_identity("ABFC00NGA", "XXXX", "XXXX")


def test_header_metadata_parsed(analysis) -> None:  # type: ignore[no-untyped-def]
    header = analysis.header
    assert header.rinex_version == "2.11"
    assert header.rinex_type == "O"
    assert header.marker_name == "ABFC"
    assert header.marker_number == "33805M001"
    assert header.receiver_number == "RX001"
    assert header.receiver_type == "TEST RX"
    assert header.receiver_version == "1.0"
    assert header.antenna_number == "ANT001"
    assert header.antenna_type == "TEST ANTENNA        NONE"
    assert header.approximate_xyz_m == (6246471.0, 820849.0, 994268.0)
    assert header.antenna_delta_hen_m == (0.1, 0.0, 0.0)
    assert header.time_of_first_observation == "2024-01-26T00:00:00Z"
    assert header.leap_seconds == 18


def test_observation_types_and_dual_frequency(analysis) -> None:  # type: ignore[no-untyped-def]
    assert analysis.header.observation_types == ("C1", "L1", "L2", "P2")
    assert phase_frequencies(analysis.header.observation_types) == ("1", "2")


def test_sampling_and_epoch_count(analysis) -> None:  # type: ignore[no-untyped-def]
    assert analysis.declared_interval_seconds == 30
    assert analysis.empirical_interval_seconds == 30
    assert analysis.epochs_observed == 3
    assert analysis.epochs_expected == 2880
    assert analysis.interval_consistent is True


def test_partial_session_metrics(analysis) -> None:  # type: ignore[no-untyped-def]
    assert analysis.first_epoch == "2024-01-26T00:00:00Z"
    assert analysis.last_epoch == "2024-01-26T00:01:00Z"
    assert analysis.end_shortfall_seconds == 86310
    assert analysis.availability_percent == pytest.approx(3 / 2880 * 100)


def test_gap_detection() -> None:
    result = analyse_rinex2(synthetic_rinex(seconds=(0, 30, 90)), year=2024, day_of_year=26)
    assert result.gap_count == 1
    assert result.gaps[0].elapsed_seconds == 60
    assert result.gaps[0].missing_epochs == 1
    assert result.largest_gap_seconds == 60


def test_satellite_and_constellation_statistics(analysis) -> None:  # type: ignore[no-untyped-def]
    assert analysis.satellites_min == 2
    assert analysis.satellites_median == 2
    assert analysis.satellites_max == 2
    assert analysis.constellation_statistics["GPS"]["epochs_present"] == 3
    assert analysis.constellation_statistics["GLONASS"]["median_per_epoch"] == 1


def test_loss_of_lock_is_indicator_not_claim() -> None:
    result = analyse_rinex2(synthetic_rinex(lli="1"), year=2024, day_of_year=26)
    assert result.potential_cycle_slip_indicators == 12


def test_missing_header_terminator_rejected() -> None:
    with pytest.raises(RinexParseError, match="END OF HEADER"):
        analyse_rinex2(synthetic_rinex()[:-10], year=2024, day_of_year=26)


def test_unsupported_rinex_version_rejected() -> None:
    lines = synthetic_rinex()
    lines[0] = header_line("     3.05           OBSERVATION DATA    M", "RINEX VERSION / TYPE")
    with pytest.raises(RinexParseError, match="requires RINEX 2"):
        analyse_rinex2(lines, year=2024, day_of_year=26)


def test_profiles_are_named_versioned_and_provisional() -> None:
    profiles = load_profiles()
    assert set(profiles) == {"archive", "single_base_rtk", "network_rtk"}
    assert all(profile.version == "1.0" for profile in profiles.values())
    assert all("PROVISIONAL" in profile.status for profile in profiles.values())


def test_invalid_profile_thresholds_rejected(tmp_path: Path) -> None:
    path = tmp_path / "profiles.json"
    path.write_text(
        json.dumps(
            {
                "profile_set_version": "x",
                "status": "PROVISIONAL",
                "profiles": {
                    "bad": {
                        "expected_interval_seconds": 30,
                        "sampling_tolerance_seconds": 0,
                        "accept_completeness_fraction": 0.5,
                        "reject_below_completeness_fraction": 0.8,
                        "maximum_warn_gap_seconds": 0,
                        "require_dual_frequency_phase": False,
                        "require_navigation": False,
                        "require_verified_coordinates": False,
                        "warn_on_partial_session": True,
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ProfileError, match="reject threshold"):
        load_profiles(path)


def classify(
    session_and_path: tuple[SessionInput, Path],
    analysis: RinexAnalysis,
    profile_name: str,
    *,
    navigation: NavigationProduct | None = None,
    coordinate: CoordinateEligibility | None = None,
) -> Classification:
    item, source = session_and_path
    findings = classify_session(
        item,
        analysis,
        load_profiles()[profile_name],
        identity_status="CANONICAL_MATCH",
        source_path=source,
        observed_sha256="observed",
        navigation=navigation,
        coordinate=coordinate,
    )
    return overall_classification(findings)


def test_archive_partial_session_warns(session, analysis) -> None:  # type: ignore[no-untyped-def]
    assert classify(session, analysis, "archive") is Classification.WARN


def test_severely_partial_rtk_session_rejects(session, analysis) -> None:  # type: ignore[no-untyped-def]
    assert classify(session, analysis, "single_base_rtk") is Classification.REJECT


def test_missing_navigation_blocks_otherwise_full_session(session, analysis) -> None:  # type: ignore[no-untyped-def]
    full = replace(
        analysis,
        availability_percent=100.0,
        end_shortfall_seconds=0,
        session_duration_seconds=86400,
    )
    assert (
        classify(session, full, "single_base_rtk", coordinate=_coordinate())
        is Classification.BLOCKED
    )


def test_full_rtk_session_warns_when_product_provenance_missing(session, analysis) -> None:  # type: ignore[no-untyped-def]
    full = replace(
        analysis,
        availability_percent=100.0,
        end_shortfall_seconds=0,
        session_duration_seconds=86400,
    )
    assert (
        classify(
            session,
            full,
            "single_base_rtk",
            navigation=_navigation(),
            coordinate=_coordinate(),
        )
        is Classification.WARN
    )  # product provenance is explicitly unavailable


def test_full_rtk_session_accepts_with_provenanced_dependencies(session, analysis) -> None:  # type: ignore[no-untyped-def]
    full = replace(analysis, availability_percent=100.0, end_shortfall_seconds=0)
    navigation = replace(_navigation(), acquisition_provenance="https://example.test/nav")
    assert (
        classify(
            session,
            full,
            "single_base_rtk",
            navigation=navigation,
            coordinate=_coordinate(),
        )
        is Classification.ACCEPT
    )


def test_coordinate_on_other_day_blocks(session, analysis) -> None:  # type: ignore[no-untyped-def]
    full = replace(analysis, availability_percent=100.0, end_shortfall_seconds=0)
    coordinate = replace(_coordinate(), coordinate_epoch="2024-01-25T12:00:00Z")
    assert (
        classify(session, full, "network_rtk", navigation=_navigation(), coordinate=coordinate)
        is Classification.BLOCKED
    )


def test_reject_precedes_blocked(session, analysis) -> None:  # type: ignore[no-untyped-def]
    assert classify(session, analysis, "network_rtk") is Classification.REJECT


def test_manifest_duplicate_detection(tmp_path: Path) -> None:
    manifest = tmp_path / "manifests"
    manifest.mkdir()
    (manifest / "canonical-raw-archive-2024.json").write_text(
        json.dumps(
            {
                "records": [
                    {
                        "artifact_type": "observation",
                        "canonical_relative_path": "raw/x/EKAK2000.24D.Z",
                        "source_relative_path": "delivery/EKAK2000.24D.Z",
                        "station_id": "EKAK00NGA",
                        "year": 2024,
                        "day_of_year": 200,
                        "sha256": "abc",
                        "size_bytes": 12,
                    }
                ],
                "exact_duplicates": [
                    {
                        "canonical_relative_path": "raw/x/EKAK2000.24D.Z",
                        "excluded_source_relative_path": "delivery/EKAK2000 (1).24D.Z",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    result = load_session_inputs(tmp_path)
    assert result[0].exact_duplicate_sources == ("delivery/EKAK2000 (1).24D.Z",)


def test_navigation_inventory_and_association(tmp_path: Path) -> None:
    root = tmp_path / "external-products" / "brdc" / "2024"
    root.mkdir(parents=True)
    (root / "BRDC00IGS_R_20240260000_01D_MN.rnx.gz").write_bytes(b"synthetic nav")
    products = inventory_navigation_products(tmp_path)
    assert len(products) == 1
    assert navigation_for_session(products, 2024, 26) is products[0]
    assert navigation_for_session(products, 2024, 27) is None


def test_selection_modes() -> None:
    rows = [
        SessionInput("ABFC00NGA", 2024, 1, "a", "a", "x", 1),
        SessionInput("MGBO00NGA", 2024, 18, "b", "b", "y", 1),
    ]
    assert select_sessions(rows, station_ids={"MGBO00NGA"}) == [rows[1]]
    assert select_sessions(rows, start_doy=2, end_doy=20) == [rows[1]]


def test_dry_run_does_not_create_output(tmp_path: Path) -> None:
    manifests = tmp_path / "manifests"
    manifests.mkdir()
    payload = {
        "records": [
            {
                "artifact_type": "observation",
                "canonical_relative_path": "raw/a.24D.Z",
                "source_relative_path": "delivery/a.24D.Z",
                "station_id": "ABFC00NGA",
                "year": 2024,
                "day_of_year": 1,
                "sha256": "x",
                "size_bytes": 1,
            }
        ],
        "exact_duplicates": [],
    }
    (manifests / "canonical-raw-archive-2024.json").write_text(
        json.dumps(payload), encoding="utf-8"
    )
    sessions = load_session_inputs(tmp_path)
    plan = plan_dataset(tmp_path, sessions, [load_profiles()["archive"]], convert=True)
    assert plan["files_selected"] == 1
    assert not (tmp_path / "processed").exists()


def test_verified_conversion_is_resumable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "raw" / "ABFC0260.24D.Z"
    source.parent.mkdir()
    source.write_bytes(b"synthetic compressed bytes")
    source_hash = sha256_file(source)
    session = SessionInput(
        "ABFC00NGA",
        2024,
        26,
        "raw/ABFC0260.24D.Z",
        "delivery/x",
        source_hash,
        source.stat().st_size,
    )
    calls: list[Path] = []

    def fake_convert(source_path: Path, output_dir: Path) -> ObservationConversion:
        calls.append(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        decompressed = output_dir / "ABFC0260.24D"
        converted = output_dir / "ABFC0260.24O"
        decompressed.write_bytes(b"d")
        converted.write_bytes(b"o")
        return ObservationConversion(
            source_path=source_path,
            source_sha256=source_hash,
            decompressed_path=decompressed,
            decompressed_sha256=sha256_file(decompressed),
            converted_path=converted,
            converted_sha256=sha256_file(converted),
            crx2rnx_version="synthetic",
            uncompress_tool="synthetic",
            started_at="2024-01-26T00:00:00+00:00",
            duration_seconds=0.1,
            crx2rnx_rc=0,
        )

    monkeypatch.setattr(qc_engine, "convert_observation", fake_convert)
    first = qc_engine._convert_verified(tmp_path, session, source)
    manifest = tmp_path / "working/qc-converted/2024/ABFC00NGA/026/conversion-manifest.json"
    manifest.write_text(json.dumps(first.as_dict()), encoding="utf-8")
    second = qc_engine._convert_verified(tmp_path, session, source)
    assert len(calls) == 1
    assert second.converted_sha256 == first.converted_sha256


def _navigation() -> NavigationProduct:
    return NavigationProduct(
        product_type="broadcast_navigation",
        source=None,
        relative_path="external-products/nav.rnx.gz",
        coverage_start="2024-01-26T00:00:00Z",
        coverage_end="2024-01-27T00:00:00Z",
        sha256="navhash",
        size_bytes=1,
        acquisition_provenance=None,
    )


def _coordinate() -> CoordinateEligibility:
    return CoordinateEligibility(
        station_id="ABFC00NGA",
        scientifically_valid=True,
        reference_frame="IGS20",
        coordinate_epoch="2024-01-26T12:00:00Z",
        source_path="processed/single-base/derived-coordinates.json",
        source_sha256="coordhash",
    )
