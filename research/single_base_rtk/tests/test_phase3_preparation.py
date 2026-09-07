"""Tests for Phase 3 preparation logic.

These tests exercise RINEX parsing, station identity, session QC, navigation
association, baseline classification, experiment generation, conversion
provenance, and coordinate-derivation parsing.  They use synthetic fixtures
only; none of them supports scientific accuracy claims.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from nlgcp_single_base.baselines import (
    baseline_matrix,
    classify_baseline,
    compute_baseline,
)
from nlgcp_single_base.conversion import uncompress_tool_path
from nlgcp_single_base.coordinates import EcefCoordinate, GeodeticCoordinate, geodetic_to_ecef
from nlgcp_single_base.coordinates_derive import PrideSolution, parse_pride_pos
from nlgcp_single_base.experiments import (
    StationExperimentInput,
    experiment_id,
    generate_experiments,
    select_spanning_pairs,
)
from nlgcp_single_base.gate import assemble_phase2_audit
from nlgcp_single_base.models import (
    NavigationInput,
    Phase2Gate,
    ProcessingMode,
    StationCoordinate,
)
from nlgcp_single_base.nav import brdc_filename, parse_brdc_epoch, verify_navigation_product
from nlgcp_single_base.rinrex import parse_rinex_filename, read_rinex2_header
from nlgcp_single_base.sessions import (
    OverlapWindow,
    SessionCoverageError,
    common_overlap_window,
    load_session_qc,
)
from nlgcp_single_base.stations import (
    StationIdentityError,
    canonical_station_id_for_marker,
    markers_for_canonical_station,
    station_id_from_observation_filename,
)

SYNTHETIC_LABEL = "SYNTHETIC TEST DATA - NOT VALID FOR SCIENTIFIC RESULTS"


def test_brdc_filename_and_epoch() -> None:
    assert brdc_filename(2024, 26) == "BRDC00IGS_R_20240260000_01D_MN.rnx.gz"
    path = Path("/d/BRDC00IGS_R_20240260000_01D_MN.rnx.gz")
    assert parse_brdc_epoch(path) == (2024, 26)


def test_verify_navigation_product_epoch_check(tmp_path: Path) -> None:
    nav = tmp_path / "BRDC00IGS_R_20240260000_01D_MN.rnx.gz"
    nav.write_bytes(b"x")
    product = verify_navigation_product(nav, 2024, 26)
    assert product.year == 2024
    assert product.day_of_year == 26
    assert product.product_type == "igs_broadcast_navigation_mixed"
    with pytest.raises(ValueError, match="epoch mismatch"):
        verify_navigation_product(nav, 2024, 27)


def test_parse_rinex_filename() -> None:
    parsed = parse_rinex_filename("ABFC0260.24D.Z")
    assert parsed.marker == "ABFC"
    assert parsed.doy == 26
    assert parsed.year_2digit == 24
    assert parsed.file_type == "D"
    assert parsed.compress_flag == "Z"

    obs = parse_rinex_filename("ENEN0470.24O")
    assert obs.file_type == "O"
    assert obs.marker == "ENEN"

    with pytest.raises(ValueError):
        parse_rinex_filename("not_a_rinex")


def test_station_identity_from_filename() -> None:
    assert station_id_from_observation_filename("BIKE0260.24D.Z") == "BKFP00NGA"
    assert station_id_from_observation_filename("YLAD0180.24D.Z") == "FUTY00NGA"
    assert canonical_station_id_for_marker("LGLA") == "ULAG00NGA"
    assert canonical_station_id_for_marker("ENEN") == "UNEC00NGA"
    assert canonical_station_id_for_marker("UNEC") == "UNEC00NGA"
    assert canonical_station_id_for_marker("ABFC") == "ABFC00NGA"
    with pytest.raises(StationIdentityError):
        canonical_station_id_for_marker("ZZZZ")
    with pytest.raises(StationIdentityError):
        station_id_from_observation_filename("ZZZZ0010.24D.Z")
    assert markers_for_canonical_station("UNEC00NGA") == ("ENEN", "UNEC")


def test_read_rinex2_header(tmp_path: Path) -> None:
    header_text = (
        "     2.11           OBSERVATION DATA    M (MIXED)           RINEX VERSION / TYPE\r\n"
        "ABFC                                                        MARKER NAME\r\n"
        "33805M001                                                   MARKER NUMBER\r\n"
        " 6246471.2622  820848.7319  994267.9084                     APPROX POSITION XYZ\r\n"
        "                                                            END OF HEADER\r\n"
    )
    path = tmp_path / "test.24O"
    path.write_text(header_text, encoding="utf-8")
    header = read_rinex2_header(path)
    assert header.marker_name == "ABFC"
    assert header.marker_number == "33805M001"
    assert header.approx_position_xyz is not None
    assert header.approx_position_xyz[0] == pytest.approx(6246471.2622)


def test_classify_baseline() -> None:
    assert classify_baseline(10.0) == "short"
    assert classify_baseline(50.0) == "medium"
    assert classify_baseline(150.0) == "long"
    assert classify_baseline(500.0) == "very_long"


def test_compute_baseline_and_matrix() -> None:
    a = EcefCoordinate(0, 0, 0)
    b = EcefCoordinate(1000, 0, 0)
    bl = compute_baseline("A", a, "B", b)
    assert bl.distance_km == pytest.approx(1.0)
    assert bl.distance_class == "short"

    matrix = baseline_matrix({"A": a, "B": b, "C": EcefCoordinate(0, 1000, 0)})
    assert len(matrix) == 3


def test_session_qc_and_overlap(tmp_path: Path) -> None:
    qc = tmp_path / "sessions.csv"
    qc.write_text(
        "canonical_relative_path,sha256,station_id,year,day_of_year,filename_date,"
        "parser_status,converter_exit_code,converter_message,marker_name,marker_number,"
        "first_epoch,last_epoch,sampling_interval_seconds,epoch_count,duplicate_epoch_count,"
        "backward_epoch_count,internal_gap_count,estimated_missing_internal_epochs,"
        "expected_daily_epochs,observed_epoch_fraction,start_offset_seconds,"
        "end_shortfall_seconds,completeness,warnings\n"
        "raw/x/ABFC00NGA/026/observation/ABFC0260.24D.Z,abc,ABFC00NGA,2024,26,2024-01-26,"
        "parsed,0,,ABFC,33805M001,2024-01-26T00:00:00Z,2024-01-26T23:59:30Z,30.0,2880,0,0,0,0,"
        "2880,1.0,0.0,0.0,complete,\n"
        "raw/x/EKAK00NGA/026/observation/EKAK0260.24D.Z,def,EKAK00NGA,2024,26,2024-01-26,"
        "parsed,0,,EKAK,123456F002,2024-01-26T00:00:00Z,2024-01-26T23:59:30Z,30.0,2880,0,0,0,0,"
        "2880,1.0,0.0,0.0,complete,\n",
        encoding="utf-8",
    )
    sessions = load_session_qc(qc)
    window = common_overlap_window(sessions, 26, ["ABFC00NGA", "EKAK00NGA"])
    assert window.iso_start() == "2024-01-26T00:00:00Z"
    assert window.iso_end() == "2024-01-26T23:59:30Z"


def test_session_overlap_fails_closed_on_gaps(tmp_path: Path) -> None:
    qc = tmp_path / "sessions.csv"
    qc.write_text(
        "canonical_relative_path,sha256,station_id,year,day_of_year,filename_date,"
        "parser_status,converter_exit_code,converter_message,marker_name,marker_number,"
        "first_epoch,last_epoch,sampling_interval_seconds,epoch_count,duplicate_epoch_count,"
        "backward_epoch_count,internal_gap_count,estimated_missing_internal_epochs,"
        "expected_daily_epochs,observed_epoch_fraction,start_offset_seconds,"
        "end_shortfall_seconds,completeness,warnings\n"
        "raw/x/ABFC00NGA/026/observation/ABFC0260.24D.Z,abc,ABFC00NGA,2024,26,2024-01-26,"
        "parsed,0,,ABFC,33805M001,2024-01-26T00:00:00Z,2024-01-26T23:59:30Z,30.0,2880,0,0,280,344,"
        "2880,0.88,0.0,0.0,incomplete,has-gaps\n",
        encoding="utf-8",
    )
    sessions = load_session_qc(qc)
    with pytest.raises(SessionCoverageError, match="internal gaps"):
        common_overlap_window(sessions, 26, ["ABFC00NGA"])


def test_experiment_id_format() -> None:
    assert (
        experiment_id(2024, 26, "ABFC00NGA", "EKAK00NGA", ProcessingMode.STATIC)
        == "sb-2024d026-abfc-ekak-static"
    )


def test_select_spanning_pairs() -> None:
    stations = {
        "A": EcefCoordinate(0, 0, 0),
        "B": EcefCoordinate(2_000_000, 0, 0),
        "C": EcefCoordinate(4_000_000, 0, 0),
    }
    baselines = baseline_matrix(stations)
    pairs = select_spanning_pairs(baselines, list(stations), base_station_id="A")
    assert pairs, "expected at least one selected pair"
    assert all(isinstance(p, tuple) and len(p) == 2 for p in pairs)


def test_generate_experiments(tmp_path: Path) -> None:
    def coord(name: str) -> StationCoordinate:
        geo = GeodeticCoordinate(9.0, 7.0 if name == "a" else 8.0, 100.0)
        return StationCoordinate(
            reference_frame="IGS20",
            coordinate_epoch="2024-01-26T00:00:00Z",
            ecef=geodetic_to_ecef(geo),
            geodetic=geo,
            provenance="fixture",
        )

    obs_a = tmp_path / "ABFC0260.24O"
    obs_b = tmp_path / "EKAK0260.24O"
    obs_a.write_text("A", encoding="utf-8")
    obs_b.write_text("B", encoding="utf-8")
    nav = tmp_path / "BRDC00IGS_R_20240260000_01D_MN.rnx.gz"
    nav.write_bytes(b"nav")

    stations = {
        "ABFC00NGA": _inp("ABFC00NGA", coord("a"), obs_a),
        "EKAK00NGA": _inp("EKAK00NGA", coord("b"), obs_b),
    }
    window = _window()
    nav_product = NavigationInput(nav, product_type="igs_broadcast_navigation_mixed")
    gate = Phase2Gate(
        base_station_verified=True,
        rover_station_verified=True,
        coordinates_verified=True,
        reference_frame_verified=True,
        coordinate_epoch_verified=True,
        equipment_interval_verified=True,
        real_observations_present=True,
        navigation_present=True,
        overlapping_interval_verified=True,
        sampling_interval_verified=True,
        file_provenance_verified=True,
        hashes_verified=True,
        phase2_audit_approved=True,
    )
    defs = generate_experiments(
        year=2024,
        doy=26,
        stations=stations,
        nav=nav_product,
        window=window,
        pairs=[("ABFC00NGA", "EKAK00NGA")],
        phase2_gate=gate,
        research_question="synthetic",
    )
    assert len(defs) == 1
    assert defs[0].experiment_id.startswith("sb-2024d026-abfc-ekak")


def test_convert_observation_uncompress_available() -> None:
    assert str(uncompress_tool_path()).endswith("uncompress")


def test_parse_pride_pos(tmp_path: Path) -> None:
    pos_text = (
        "abfc                                                        STATION\n"
        "Static      10.000000 10.000000 10.000000                   POS MODE/PRIORI (meter)\n"
        "WUM0MGXRAP_20240260000_01D_05M_ORB.SP3                      SAT ORBIT\n"
        "IGS20_2290                                                  TABLE ANTEX\n"
        "*Name         Mjd               X               Y               Z   ...\n"
        " abfc  60335.4998   6246471.17131    820849.02064    994268.16646      ...\n"
    )
    path = tmp_path / "pos_2024026_abfc"
    path.write_text(pos_text, encoding="utf-8")
    sol = parse_pride_pos(path)
    assert isinstance(sol, PrideSolution)
    assert sol.ecef.x_m == pytest.approx(6246471.17131)
    assert sol.reference_frame == "IGS20"
    assert sol.mjd == pytest.approx(60335.4998)


def test_assemble_phase2_audit(tmp_path: Path) -> None:
    files = {}
    for name in (
        "station_registry.csv",
        "header-registry.csv",
        "canonical-raw-archive-2024.json",
        "anomalies.csv",
        "sessions.csv",
        "conversion.json",
        "BRDC00IGS_R_20240260000_01D_MN.rnx.gz",
        "derived-coordinates.json",
    ):
        p = tmp_path / name
        p.write_text("{}", encoding="utf-8")
        files[name] = p

    audit = assemble_phase2_audit(
        station_registry=files["station_registry.csv"],
        header_registry=files["header-registry.csv"],
        canonical_manifest=files["canonical-raw-archive-2024.json"],
        anomalies=files["anomalies.csv"],
        session_qc=files["sessions.csv"],
        conversion_manifest=files["conversion.json"],
        navigation_product=files["BRDC00IGS_R_20240260000_01D_MN.rnx.gz"],
        derived_coordinates=files["derived-coordinates.json"],
        audit_reviewed=True,
    )
    assert audit.gate.missing_items() == []
    audit.gate.assert_open()

    audit_unapproved = assemble_phase2_audit(
        station_registry=files["station_registry.csv"],
        header_registry=files["header-registry.csv"],
        canonical_manifest=files["canonical-raw-archive-2024.json"],
        anomalies=files["anomalies.csv"],
        session_qc=files["sessions.csv"],
        conversion_manifest=files["conversion.json"],
        navigation_product=files["BRDC00IGS_R_20240260000_01D_MN.rnx.gz"],
        derived_coordinates=files["derived-coordinates.json"],
        audit_reviewed=False,
    )
    assert "phase2_audit_approved" in audit_unapproved.gate.missing_items()


def test_assemble_phase2_audit_fails_closed_on_missing_files(tmp_path: Path) -> None:
    audit = assemble_phase2_audit(
        station_registry=tmp_path / "missing.csv",
        header_registry=tmp_path / "missing.csv",
        canonical_manifest=tmp_path / "missing.json",
        anomalies=tmp_path / "missing.csv",
        session_qc=tmp_path / "missing.csv",
        conversion_manifest=tmp_path / "missing.json",
        navigation_product=tmp_path / "missing.gz",
        derived_coordinates=tmp_path / "missing.json",
        audit_reviewed=True,
    )
    assert audit.gate.missing_items(), "expected gate to fail closed with missing files"


def _inp(station: str, coord: StationCoordinate, obs: Path) -> StationExperimentInput:
    return StationExperimentInput(
        station_id=station,
        coordinate=coord,
        observation_path=obs,
        metadata_version="v1",
        observation_sha256="0" * 64,
    )


def _window() -> OverlapWindow:
    return OverlapWindow(
        start=datetime(2024, 1, 26, tzinfo=UTC),
        end=datetime(2024, 1, 26, 23, 59, 30, tzinfo=UTC),
        sampling_interval_seconds=30.0,
        stations=("ABFC00NGA", "EKAK00NGA"),
    )
