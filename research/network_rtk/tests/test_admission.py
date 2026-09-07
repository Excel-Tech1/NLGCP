"""Tests for experiment definitions, admission, aliases and malformed input.

SYNTHETIC TEST DATA — NOT VALID FOR SCIENTIFIC RESULTS.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from nlgcp_network_rtk.admission import admit_day, session_eligibility_rows
from nlgcp_network_rtk.models import NetworkBlocked, definition_from_dict
from synthetic_fixtures import make_definition, write_nav_product, write_qc_result


def test_valid_definition_passes(tmp_path: Path) -> None:
    definition = definition_from_dict(make_definition())
    assert definition.validate() == []


def test_rover_as_reference_blocked(tmp_path: Path) -> None:
    payload = make_definition(refs=("ABFC00NGA", "PHRI00NGA"), rover="PHRI00NGA")
    definition = definition_from_dict(payload)
    assert any("must not be listed" in problem for problem in definition.validate())
    with pytest.raises(NetworkBlocked):
        definition.assert_valid()


def test_duplicate_references_blocked(tmp_path: Path) -> None:
    payload = make_definition(refs=("ABFC00NGA", "ABFC00NGA", "EKAK00NGA"))
    definition = definition_from_dict(payload)
    with pytest.raises(NetworkBlocked):
        definition.assert_valid()


def test_minimum_below_justified_floor_blocked(tmp_path: Path) -> None:
    payload = make_definition(refs=("ABFC00NGA",), minimum=1)
    definition = definition_from_dict(payload)
    assert any("scientifically justified" in p for p in definition.validate())


def test_insufficient_reference_count_blocked(tmp_path: Path) -> None:
    payload = make_definition(refs=("ABFC00NGA", "EKAK00NGA"), minimum=3)
    definition = definition_from_dict(payload)
    assert any("only 2 reference" in p for p in definition.validate())


def test_malformed_definition_missing_key(tmp_path: Path) -> None:
    payload = make_definition()
    del payload["test_station"]
    with pytest.raises(NetworkBlocked):
        definition_from_dict(payload)


def test_malformed_definition_bad_doy(tmp_path: Path) -> None:
    payload = make_definition()
    payload["day_of_year"] = 999
    definition = definition_from_dict(payload)
    assert any("out of range" in p for p in definition.validate())


def test_admission_accepts_only_accept(tmp_path: Path) -> None:
    cases = (
        ("ABFC00NGA", "ACCEPT"),
        ("EKAK00NGA", "ACCEPT"),
        ("MGBO00NGA", "REJECT"),
        ("PHRI00NGA", "ACCEPT"),
    )
    for station, cls in cases:
        write_qc_result(tmp_path, station_id=station, classification=cls)
    summary = admit_day(tmp_path, year=2024, day_of_year=26)
    admitted = sorted(r.station_id for r in summary.admitted)
    assert admitted == ["ABFC00NGA", "EKAK00NGA", "PHRI00NGA"]
    assert any(r["station_id"] == "MGBO00NGA" for r in summary.rejected)
    rows = session_eligibility_rows(summary)
    assert {r["station_id"] for r in rows} == {"ABFC00NGA", "EKAK00NGA", "MGBO00NGA", "PHRI00NGA"}


def test_admission_records_provenance_fields(tmp_path: Path) -> None:
    write_qc_result(tmp_path, station_id="ABFC00NGA")
    summary = admit_day(tmp_path, year=2024, day_of_year=26)
    row = summary.admitted[0]
    assert row.qc_profile == "network_rtk"
    assert row.phase4_result_fingerprint.startswith("synthetic-fingerprint")
    assert row.sampling_interval_seconds == 30.0
    assert row.first_epoch == "2024-01-26T00:00:00Z"
    assert row.equipment_metadata["marker_name"] == "ABFC"
    assert row.station_metadata_provenance is not None


def test_missing_qc_result_is_blocked(tmp_path: Path) -> None:
    summary = admit_day(tmp_path, year=2024, day_of_year=26, candidate_stations=["ABFC00NGA"])
    assert summary.admitted == ()
    assert summary.rejected[0]["decision"] == "BLOCKED"


def test_malformed_qc_result_is_blocked(tmp_path: Path) -> None:
    directory = (
        tmp_path / "processed" / "qc" / "profiles" / "network_rtk"
        / "sessions" / "2024" / "ABFC00NGA" / "026"
    )
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "qc-result.json").write_text("{not json", encoding="utf-8")
    summary = admit_day(tmp_path, year=2024, day_of_year=26, candidate_stations=["ABFC00NGA"])
    assert summary.rejected[0]["decision"] == "BLOCKED"


def test_diagnostic_experiment_labels_alias_state(tmp_path: Path) -> None:
    write_qc_result(tmp_path, station_id="ABFC00NGA", classification="REJECT")
    summary = admit_day(tmp_path, year=2024, day_of_year=26, diagnostic=True)
    assert len(summary.admitted) == 1
    assert summary.diagnostic is True
    assert summary.admitted[0].equipment_metadata["diagnostic_experiment"] is True


def test_blocked_qc_status_recorded_with_reason(tmp_path: Path) -> None:
    write_qc_result(tmp_path, station_id="BKFP00NGA", classification="BLOCKED")
    summary = admit_day(tmp_path, year=2024, day_of_year=26)
    assert summary.rejected[0]["decision"] == "BLOCKED"
    assert "Phase 4 BLOCKED" in summary.rejected[0]["reason"]


def test_station_alias_marker_preserved(tmp_path: Path) -> None:
    # BKFP canonical station uses BIKE marker; admission must keep canonical id
    # while recording the header marker from Phase 4.
    path = write_qc_result(tmp_path, station_id="BKFP00NGA", classification="ACCEPT")
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["rinex"]["header"]["marker_name"] = "BIKE"
    path.write_text(json.dumps(payload), encoding="utf-8")
    summary = admit_day(tmp_path, year=2024, day_of_year=26)
    assert summary.admitted[0].station_id == "BKFP00NGA"
    assert summary.admitted[0].equipment_metadata["marker_name"] == "BIKE"


def test_nav_product_recorded(tmp_path: Path) -> None:
    write_nav_product(tmp_path)
    write_qc_result(tmp_path, station_id="ABFC00NGA")
    summary = admit_day(tmp_path, year=2024, day_of_year=26)
    assert summary.admitted[0].navigation_path is not None
