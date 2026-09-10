"""SYNTHETIC TEST DATA — NOT VALID FOR SCIENTIFIC RESULTS."""

from __future__ import annotations

from nlgcp_scientific_expansion import overlap
from nlgcp_scientific_expansion.models import StationDayCoverage


def _cell(station: str, doy: int, full: bool = True) -> StationDayCoverage:
    return StationDayCoverage(
        station_id=station,
        year=2024,
        doy=doy,
        observation_available=True,
        qc_classification="ACCEPT" if full else "BLOCKED",
        qc_findings=("FULL_SESSION",) if full else (),
    )


def test_classify_overlap_thresholds() -> None:
    assert overlap.classify_overlap(1) == "NONE"
    assert overlap.classify_overlap(2) == "SINGLE_BASE_CANDIDATE"
    assert overlap.classify_overlap(3) == "LIMITED_NETWORK_CANDIDATE"
    assert overlap.classify_overlap(4) == "NETWORK_HELD_OUT_CANDIDATE"
    assert overlap.classify_overlap(8) == "NETWORK_HELD_OUT_CANDIDATE"


def test_overlap_groups_by_day() -> None:
    cells = [
        _cell("ABFC00NGA", 7),
        _cell("EKAK00NGA", 7),
        _cell("PHRI00NGA", 8),
    ]
    days = overlap.overlap_by_day(cells)
    assert len(days) == 2
    assert days[0].doy == 7
    assert days[0].station_count == 2
    assert days[0].candidate_experiment_type == "SINGLE_BASE_CANDIDATE"


def test_coordinated_full_filter() -> None:
    cells = [
        _cell("ABFC00NGA", 9),
        _cell("BKFP00NGA", 9),
        _cell("EKAK00NGA", 9, full=False),
    ]
    days = overlap.overlap_by_day(
        cells, coordinated_only=True, require_full_session=True
    )
    assert len(days) == 1
    assert days[0].stations == ("ABFC00NGA",)


def test_count_days_by_overlap() -> None:
    cells = [
        _cell("ABFC00NGA", 7),
        _cell("EKAK00NGA", 7),
        _cell("MGBO00NGA", 7),
        _cell("PHRI00NGA", 8),
    ]
    counts = overlap.count_days_by_overlap(overlap.overlap_by_day(cells))
    assert counts[">=2"] == 1
    assert counts[">=3"] == 1
    assert counts[">=4"] == 0
    assert counts[">=1"] == 2
