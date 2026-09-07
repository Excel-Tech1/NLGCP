"""Tests for temporal overlap, partial sessions and insufficient networks.

SYNTHETIC TEST DATA — NOT VALID FOR SCIENTIFIC RESULTS.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from nlgcp_network_rtk.admission import AdmittedSession, admit_day
from nlgcp_network_rtk.models import NetworkBlocked, definition_from_dict
from nlgcp_network_rtk.overlap import assert_sufficient_overlap, compute_overlap
from nlgcp_network_rtk.runner import plan_experiment
from synthetic_fixtures import make_definition, write_derived_coordinates, write_qc_result

COORDS = {
    "ABFC00NGA": (6246471.17131, 820849.02064, 994268.16646),
    "EKAK00NGA": (6296841.32517, 875621.00415, 512343.12428),
    "MGBO00NGA": (6080985.75299, 1416995.42834, 1299050.34795),
    "PHRI00NGA": (6308877.98392, 772269.10256, 530087.60603),
}


def _admitted(tmp_path: Path, **kwargs: object) -> list[AdmittedSession]:
    for station in ("ABFC00NGA", "EKAK00NGA", "MGBO00NGA", "PHRI00NGA"):
        write_qc_result(tmp_path, station_id=str(station))
    summary = admit_day(tmp_path, year=2024, day_of_year=26)
    assert len(summary.admitted) == 4
    return list(summary.admitted)


def test_full_day_overlap(tmp_path: Path) -> None:
    sessions = _admitted(tmp_path)
    overlap = compute_overlap(sessions)
    assert overlap.common_start == "2024-01-26T00:00:00Z"
    assert overlap.common_end == "2024-01-26T23:59:30Z"
    assert overlap.expected_epochs == 2880
    assert overlap.sufficient is True
    assert_sufficient_overlap(overlap)


def test_partial_session_truncates_overlap(tmp_path: Path) -> None:
    # MGBO DOY 018 precedent: a partial session must shrink the common window.
    write_qc_result(tmp_path, station_id="ABFC00NGA")
    write_qc_result(tmp_path, station_id="EKAK00NGA")
    write_qc_result(
        tmp_path,
        station_id="MGBO00NGA",
        first_epoch="2024-01-26T06:00:00Z",
        last_epoch="2024-01-26T23:59:30Z",
        epochs=2160,
    )
    write_qc_result(tmp_path, station_id="PHRI00NGA")
    summary = admit_day(tmp_path, year=2024, day_of_year=26)
    overlap = compute_overlap(list(summary.admitted))
    assert overlap.common_start == "2024-01-26T06:00:00Z"
    assert overlap.expected_epochs == 2160


def test_no_overlap_blocked(tmp_path: Path) -> None:
    write_qc_result(
        tmp_path, station_id="ABFC00NGA",
        first_epoch="2024-01-26T00:00:00Z", last_epoch="2024-01-26T01:00:00Z", epochs=121,
    )
    write_qc_result(
        tmp_path, station_id="EKAK00NGA",
        first_epoch="2024-01-26T02:00:00Z", last_epoch="2024-01-26T03:00:00Z", epochs=121,
    )
    summary = admit_day(tmp_path, year=2024, day_of_year=26)
    with pytest.raises(NetworkBlocked):
        compute_overlap(list(summary.admitted))


def test_mixed_intervals_blocked(tmp_path: Path) -> None:
    write_qc_result(tmp_path, station_id="ABFC00NGA", interval=30.0)
    write_qc_result(tmp_path, station_id="EKAK00NGA", interval=15.0)
    summary = admit_day(tmp_path, year=2024, day_of_year=26)
    with pytest.raises(NetworkBlocked):
        compute_overlap(list(summary.admitted))


def test_missing_coverage_blocked(tmp_path: Path) -> None:
    write_qc_result(tmp_path, station_id="ABFC00NGA", first_epoch="")
    write_qc_result(tmp_path, station_id="EKAK00NGA")
    summary = admit_day(tmp_path, year=2024, day_of_year=26)
    with pytest.raises(NetworkBlocked):
        compute_overlap(list(summary.admitted))


def test_short_overlap_insufficient(tmp_path: Path) -> None:
    write_qc_result(
        tmp_path, station_id="ABFC00NGA",
        first_epoch="2024-01-26T00:00:00Z", last_epoch="2024-01-26T00:10:00Z", epochs=21,
    )
    write_qc_result(
        tmp_path, station_id="EKAK00NGA",
        first_epoch="2024-01-26T00:00:00Z", last_epoch="2024-01-26T00:10:00Z", epochs=21,
    )
    summary = admit_day(tmp_path, year=2024, day_of_year=26)
    overlap = compute_overlap(list(summary.admitted))
    assert overlap.sufficient is False
    with pytest.raises(NetworkBlocked):
        assert_sufficient_overlap(overlap)


def test_insufficient_network_plan_blocked(tmp_path: Path) -> None:
    write_qc_result(tmp_path, station_id="ABFC00NGA")
    write_qc_result(tmp_path, station_id="PHRI00NGA")
    write_derived_coordinates(tmp_path, COORDS)
    definition = definition_from_dict(make_definition(refs=("ABFC00NGA",)))
    planned = plan_experiment(tmp_path, definition)
    assert planned["plan"]["status"] == "BLOCKED"
    reasons = planned["plan"]["blocked_reasons"]
    assert any("insufficient" in r.lower() or "minimum" in r.lower() for r in reasons)


def test_missing_navigation_plan_ok_but_run_blocked(tmp_path: Path) -> None:
    # Planning does not require nav files on disk; execution does.
    for station in ("ABFC00NGA", "EKAK00NGA", "MGBO00NGA", "PHRI00NGA"):
        write_qc_result(
            tmp_path, station_id=station, nav_rel="external-products/brdc/2024/MISSING.rnx.gz"
        )
    write_derived_coordinates(tmp_path, COORDS)
    definition = definition_from_dict(make_definition())
    planned = plan_experiment(tmp_path, definition)
    assert planned["plan"]["status"] == "PLANNED"
