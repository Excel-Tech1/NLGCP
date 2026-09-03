"""Tests for Phase 3 coordinate derivation and Phase 2 audit records.

These cover real PRIDE ``pos_*`` parsing, the authoritative coordinate
registry, the scientific-validity admission check and the Phase 2 audit
record writer.  Real-format fixtures only; no scientific accuracy claims.
"""

# ruff: noqa: E501  - the fixtures reproduce fixed-width PRIDE pos data rows
from __future__ import annotations

from pathlib import Path

import pytest
from nlgcp_single_base.coordinates_derive import (
    build_authoritative_coordinate_registry,
    is_usable_pride_solution,
    load_coordinate_registry,
    parse_pride_pos,
)
from nlgcp_single_base.gate import (
    GateAudit,
    assemble_phase2_audit,
    write_audit_record,
)
from nlgcp_single_base.models import Phase2Gate

# Good station-like solution (ABFC/EKAK profile): Sig0 ~1.64 m, ~69k observations.
GOOD_POS = """\
abfc                                                        STATION
Static      10.000000 10.000000 10.000000                   POS MODE/PRIORI (meter)
WUM0MGXRAP_20240260000_01D_05M_ORB.SP3                      SAT ORBIT
IGS20_2290                                                  TABLE ANTEX
*Name         Mjd               X               Y               Z                       Sx                       Sy                       Sz                      Rxy                      Rxz                      Ryz                     Sig0           Nobs
 abfc  60335.4998   6246471.17131    820849.02064    994268.16646     0.99996176721991E+02     0.99999966379355E+02     0.99995962716871E+02    -0.30404627802768E-03     0.38327443949877E-02     0.34738294351050E-03     0.16402775689183E+01          69262
"""

# Poor station-like solution (BKFP profile): Sig0 ~12.6 m, only 64 observations.
BAD_POS = """\
bike                                                        STATION
Static      10.000000 10.000000 10.000000                   POS MODE/PRIORI (meter)
WUM0MGXRAP_20240260000_01D_05M_ORB.SP3                      SAT ORBIT
IGS20_2290                                                  TABLE ANTEX
*Name         Mjd               X               Y               Z                       Sx                       Sy                       Sz                      Rxy                      Rxz                      Ryz                     Sig0           Nobs
 bike  60335.5684   6211861.93126    459343.07387   1368131.30623     0.99996176721991E+02     0.99999966379355E+02     0.99995962716871E+02    -0.30404627802768E-03     0.38327443949877E-02     0.34738294351050E-03     0.12598482139504E+02             64
"""


def _pride_pos(tmp_path: Path, text: str, name: str = "pos_2024026_bike") -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def test_parse_real_format_pride_pos(tmp_path: Path) -> None:
    path = _pride_pos(tmp_path, BAD_POS)
    sol = parse_pride_pos(path)
    assert sol.station == "bike"
    assert sol.ecef.x_m == pytest.approx(6211861.93126)
    assert sol.ecef.y_m == pytest.approx(459343.07387)
    assert sol.ecef.z_m == pytest.approx(1368131.30623)
    assert sol.mjd == pytest.approx(60335.5684)
    assert sol.reference_frame == "IGS20"
    assert sol.coordinate_epoch == "2024-01-26T13:38:29Z"
    assert sol.product.startswith("WUM0MGXRAP")


def test_parse_pride_pos_no_data_row_fails_closed(tmp_path: Path) -> None:
    path = _pride_pos(tmp_path, "bike STATION-only header\nNOT DATA\n")
    with pytest.raises(Exception, match="no static position row"):
        parse_pride_pos(path)


def test_coordinate_registry_round_trip(tmp_path: Path) -> None:
    abfc = _pride_pos(tmp_path, GOOD_POS, "pos_2024026_abfc")
    out = tmp_path / "derived-coordinates.json"
    registry = build_authoritative_coordinate_registry({"ABFC00NGA": abfc}, out)
    assert registry["stations"]["ABFC00NGA"]["ecef"]["x_m"] == pytest.approx(6246471.17131)
    assert registry["stations"]["ABFC00NGA"]["reference_frame"] == "IGS20"
    assert registry["stations"]["ABFC00NGA"]["scientifically_valid"] is True
    assert out.is_file()
    loaded = load_coordinate_registry(out)
    assert "ABFC00NGA" in loaded


def test_load_coordinate_registry_missing_returns_empty() -> None:
    assert load_coordinate_registry(Path("/nonexistent/registry.json")) == {}


def test_is_usable_pride_solution_admits_low_sig0(tmp_path: Path) -> None:
    assert is_usable_pride_solution(_pride_pos(tmp_path, GOOD_POS)) is True


def test_is_usable_pride_solution_rejects_high_sig0(tmp_path: Path) -> None:
    assert is_usable_pride_solution(_pride_pos(tmp_path, BAD_POS)) is False


def test_write_audit_record_open_gate(tmp_path: Path) -> None:
    audit = GateAudit(
        gate=Phase2Gate(**{name: True for name in Phase2Gate().__dict__}),
        evidence=[],
    )
    out = write_audit_record(audit, tmp_path / "reports" / "phase3-phase2-audit.md")
    text = out.read_text(encoding="utf-8")
    assert "gate is **open**" in text


def test_write_audit_record_closed_gate(tmp_path: Path) -> None:
    audit = GateAudit(gate=Phase2Gate(), evidence=[])
    out = write_audit_record(audit, tmp_path / "audit.md")
    text = out.read_text(encoding="utf-8")
    assert "gate is **NOT open**" in text


def test_assemble_phase2_audit_review_controls_approval(tmp_path: Path) -> None:
    files: dict[str, Path] = {}
    for name in (
        "header.csv",
        "archive.json",
        "anomalies.csv",
        "sessions.csv",
        "conversion.json",
        "nav.gz",
        "coords.json",
    ):
        p = tmp_path / name
        p.write_text("{}", encoding="utf-8")
        files[name] = p

    approved = assemble_phase2_audit(
        station_registry=files["header.csv"],
        header_registry=files["header.csv"],
        canonical_manifest=files["archive.json"],
        anomalies=files["anomalies.csv"],
        session_qc=files["sessions.csv"],
        conversion_manifest=files["conversion.json"],
        navigation_product=files["nav.gz"],
        derived_coordinates=files["coords.json"],
        audit_reviewed=True,
    )
    assert approved.gate.missing_items() == []

    unapproved = assemble_phase2_audit(
        station_registry=files["header.csv"],
        header_registry=files["header.csv"],
        canonical_manifest=files["archive.json"],
        anomalies=files["anomalies.csv"],
        session_qc=files["sessions.csv"],
        conversion_manifest=files["conversion.json"],
        navigation_product=files["nav.gz"],
        derived_coordinates=files["coords.json"],
        audit_reviewed=False,
    )
    assert "phase2_audit_approved" in unapproved.gate.missing_items()
