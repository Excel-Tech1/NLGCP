"""Multi-station overlap analysis over coverage cells (pure functions)."""

from __future__ import annotations

from nlgcp_scientific_expansion.coverage import COORDINATED_STATIONS
from nlgcp_scientific_expansion.models import OverlapDay, StationDayCoverage


def overlap_by_day(
    cells: list[StationDayCoverage],
    *,
    coordinated_only: bool = False,
    require_full_session: bool = False,
) -> list[OverlapDay]:
    """Group coverage cells by DOY and classify experiment candidacy."""
    by_day: dict[int, list[StationDayCoverage]] = {}
    for cell in cells:
        if coordinated_only and cell.station_id not in COORDINATED_STATIONS:
            continue
        if require_full_session and "FULL_SESSION" not in cell.qc_findings:
            continue
        by_day.setdefault(cell.doy, []).append(cell)

    days: list[OverlapDay] = []
    for doy in sorted(by_day):
        members = sorted(by_day[doy], key=lambda cell: cell.station_id)
        stations = tuple(cell.station_id for cell in members)
        full = tuple(
            cell.station_id for cell in members if "FULL_SESSION" in cell.qc_findings
        )
        days.append(
            OverlapDay(
                year=members[0].year,
                doy=doy,
                stations=stations,
                full_session_stations=full,
                candidate_experiment_type=classify_overlap(len(stations)),
            )
        )
    return days


def classify_overlap(station_count: int) -> str:
    """Classify a day by station count (never invents processability)."""
    if station_count >= 4:
        return "NETWORK_HELD_OUT_CANDIDATE"
    if station_count == 3:
        return "LIMITED_NETWORK_CANDIDATE"
    if station_count == 2:
        return "SINGLE_BASE_CANDIDATE"
    return "NONE"


def count_days_by_overlap(days: list[OverlapDay]) -> dict[str, int]:
    """Count days with at least N stations (keys ``>=1`` ... ``>=8``)."""
    counts: dict[str, int] = {}
    for threshold in range(1, 9):
        counts[f">={threshold}"] = sum(
            1 for day in days if day.station_count >= threshold
        )
    return counts
