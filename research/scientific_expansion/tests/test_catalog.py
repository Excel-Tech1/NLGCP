"""SYNTHETIC TEST DATA — NOT VALID FOR SCIENTIFIC RESULTS."""

from __future__ import annotations

from nlgcp_scientific_expansion import catalog
from nlgcp_scientific_expansion.models import OverlapDay, StationDayCoverage


def _cell(
    station: str,
    doy: int,
    *,
    accept: bool = True,
    nav: bool = True,
    coord: bool = True,
) -> StationDayCoverage:
    findings = ("FULL_SESSION",) if accept else ()
    return StationDayCoverage(
        station_id=station,
        year=2024,
        doy=doy,
        observation_available=True,
        qc_classification="ACCEPT" if accept else "BLOCKED",
        qc_findings=findings,
        navigation_available=nav,
        navigation_product="nav.gz" if nav else "",
        coordinate_eligible=coord,
    )


def test_admission_requires_two_eligible() -> None:
    cells = [_cell("ABFC00NGA", 7), _cell("EKAK00NGA", 7)]
    days = [
        OverlapDay(year=2024, doy=7, stations=("ABFC00NGA", "EKAK00NGA"),
                   candidate_experiment_type="SINGLE_BASE_CANDIDATE")
    ]
    result = catalog.build_processable_catalog(cells, days, {7: "nav.gz"})
    assert result[0].single_base_possible is True
    assert result[0].network_possible is False
    assert result[0].reason_if_blocked == ""
    assert len(result[0].single_base_pairs) == 1


def test_network_requires_four() -> None:
    stations = ("ABFC00NGA", "EKAK00NGA", "MGBO00NGA", "PHRI00NGA")
    cells = [_cell(station, 10) for station in stations]
    days = [
        OverlapDay(year=2024, doy=10, stations=stations,
                   candidate_experiment_type="NETWORK_HELD_OUT_CANDIDATE")
    ]
    result = catalog.build_processable_catalog(cells, days, {10: "nav.gz"})
    assert result[0].network_possible is True
    assert result[0].phase6_loocv_possible is True
    assert len(result[0].single_base_pairs) == 6


def test_blocked_days_retain_reasons() -> None:
    cells = [_cell("ABFC00NGA", 11, coord=False, nav=False)]
    days = [
        OverlapDay(year=2024, doy=11, stations=("ABFC00NGA",),
                   candidate_experiment_type="NONE")
    ]
    result = catalog.build_processable_catalog(cells, days, {})
    assert result[0].single_base_possible is False
    assert "BLOCKED_NAVIGATION" in result[0].reason_if_blocked
    assert "BLOCKED_COORDINATE_INTERVAL" in result[0].reason_if_blocked


def test_gates_never_loosened_for_single_eligible() -> None:
    cells = [_cell("ABFC00NGA", 12)]
    days = [
        OverlapDay(year=2024, doy=12, stations=("ABFC00NGA",),
                   candidate_experiment_type="NONE")
    ]
    result = catalog.build_processable_catalog(cells, days, {12: "nav.gz"})
    assert result[0].single_base_possible is False


def test_prioritization_prefers_overlap_then_spread() -> None:
    stations4 = ("ABFC00NGA", "EKAK00NGA", "MGBO00NGA", "PHRI00NGA")
    cells = [_cell(s, 10) for s in stations4]
    cells += [_cell(s, 60) for s in stations4]
    cells += [_cell("ABFC00NGA", 61), _cell("EKAK00NGA", 61)]
    days = [
        OverlapDay(year=2024, doy=10, stations=stations4,
                   candidate_experiment_type="NETWORK_HELD_OUT_CANDIDATE"),
        OverlapDay(year=2024, doy=60, stations=stations4,
                   candidate_experiment_type="NETWORK_HELD_OUT_CANDIDATE"),
        OverlapDay(year=2024, doy=61, stations=("ABFC00NGA", "EKAK00NGA"),
                   candidate_experiment_type="SINGLE_BASE_CANDIDATE"),
    ]
    nav = {10: "a.gz", 60: "b.gz", 61: "c.gz"}
    full = catalog.build_processable_catalog(cells, days, nav)
    ranked = catalog.prioritize_days(full, max_days=3)
    assert ranked[0].station_count == 4
    assert ranked[-1].station_count == 2
    months = set()
    for day in ranked:
        from datetime import date, timedelta

        months.add((date(2024, 1, 1) + timedelta(days=day.doy - 1)).month)
    assert len(months) >= 2
