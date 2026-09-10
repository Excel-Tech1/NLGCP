"""Processable-day admission and preregistered prioritization.

Admission reuses frozen Phase 3/5 policy: no gate is loosened here. Days that
fail admission keep an explicit ``reason_if_blocked`` and are retained in the
catalog (failure retention).
"""

from __future__ import annotations

from itertools import combinations

from nlgcp_scientific_expansion.coverage import COORDINATED_STATIONS
from nlgcp_scientific_expansion.models import OverlapDay, ProcessableDay, StationDayCoverage

# Preregistered selection weights (recorded before performance analysis).
_WEIGHT_FOUR_STATION = 4.0
_WEIGHT_THREE_STATION = 2.0
_WEIGHT_TWO_STATION = 1.0
_WEIGHT_MONTH_SPREAD = 1.5


def build_processable_catalog(
    cells: list[StationDayCoverage],
    overlap_days: list[OverlapDay],
    nav_by_day: dict[int, str],
) -> list[ProcessableDay]:
    """Admit days for single-base / network / Phase-6 LOOCV experiments."""
    by_day: dict[int, list[StationDayCoverage]] = {}
    for cell in cells:
        by_day.setdefault(cell.doy, []).append(cell)
    by_overlap = {day.doy: day for day in overlap_days}

    catalog: list[ProcessableDay] = []
    for doy in sorted(by_day):
        members = by_day[doy]
        eligible = [
            cell
            for cell in members
            if cell.station_id in COORDINATED_STATIONS
            and cell.qc_classification == "ACCEPT"
            and "FULL_SESSION" in cell.qc_findings
            and cell.navigation_available
            and cell.coordinate_eligible
        ]
        stations = tuple(sorted(cell.station_id for cell in eligible))
        pairs = tuple(
            (a, b)
            for a, b in combinations(stations, 2)
        )
        single_possible = len(stations) >= 2
        network_possible = len(stations) >= 4
        loocv_possible = len(stations) >= 4
        overlap = by_overlap.get(doy)
        raw_count = overlap.station_count if overlap else 0
        reason = _blocked_reason(
            raw_count, len(stations), nav_by_day.get(doy, ""), members
        )
        catalog.append(
            ProcessableDay(
                year=members[0].year,
                doy=doy,
                stations=stations,
                station_count=len(stations),
                nav_product=nav_by_day.get(doy, ""),
                single_base_possible=single_possible,
                single_base_pairs=pairs,
                network_possible=network_possible,
                network_references=stations if network_possible else (),
                phase6_loocv_possible=loocv_possible,
                reason_if_blocked="" if single_possible else reason,
            )
        )
    return catalog


def _blocked_reason(
    raw_count: int,
    eligible_count: int,
    nav_product: str,
    members: list[StationDayCoverage],
) -> str:
    if eligible_count >= 2:
        return ""
    parts: list[str] = []
    if raw_count < 2:
        parts.append("INSUFFICIENT_OVERLAP")
    if not nav_product:
        parts.append("BLOCKED_NAVIGATION")
    coord_ok = sum(1 for cell in members if cell.coordinate_eligible)
    if coord_ok < 2:
        parts.append("BLOCKED_COORDINATE_INTERVAL")
    qc_ok = sum(
        1
        for cell in members
        if cell.qc_classification == "ACCEPT"
        and "FULL_SESSION" in cell.qc_findings
    )
    if qc_ok < 2:
        parts.append("BLOCKED_QC")
    return ";".join(parts) if parts else "BLOCKED_UNKNOWN"


def prioritize_days(
    catalog: list[ProcessableDay],
    *,
    max_days: int = 12,
    require_network: bool = False,
) -> list[ProcessableDay]:
    """Rank admitted days by preregistered scientific value (not performance).

    Criteria, fixed before any accuracy is observed: largest eligible overlap
    first, then seasonal (month) spread, then lowest DOY for determinism.
    """
    pool = [
        day
        for day in catalog
        if day.single_base_possible and (day.network_possible or not require_network)
    ]
    if require_network:
        pool = [day for day in pool if day.network_possible]
    scored = [(day, _priority_score(day)) for day in pool]
    scored.sort(key=lambda item: (-item[1], item[0].doy))
    chosen: list[ProcessableDay] = []
    used_months: set[int] = set()
    for day, score in scored:
        if len(chosen) >= max_days:
            break
        month = _month_of_doy(day.year, day.doy)
        bonus = 0.0 if month in used_months else _WEIGHT_MONTH_SPREAD
        used_months.add(month)
        chosen.append(
            ProcessableDay(
                year=day.year,
                doy=day.doy,
                stations=day.stations,
                station_count=day.station_count,
                nav_product=day.nav_product,
                single_base_possible=day.single_base_possible,
                single_base_pairs=day.single_base_pairs,
                network_possible=day.network_possible,
                network_references=day.network_references,
                phase6_loocv_possible=day.phase6_loocv_possible,
                reason_if_blocked=day.reason_if_blocked,
                priority_score=round(score + bonus, 3),
                selection_reason=_selection_reason(day),
            )
        )
    chosen.sort(key=lambda day: (-day.priority_score, day.doy))
    return chosen


def _priority_score(day: ProcessableDay) -> float:
    if day.station_count >= 4:
        return _WEIGHT_FOUR_STATION + day.station_count
    if day.station_count == 3:
        return _WEIGHT_THREE_STATION + day.station_count
    return _WEIGHT_TWO_STATION + day.station_count


def _selection_reason(day: ProcessableDay) -> str:
    if day.station_count >= 4:
        return "four-station held-out network/spatial validation candidate"
    if day.station_count == 3:
        return "three-station limited network candidate"
    return "two-station single-base candidate"


def _month_of_doy(year: int, doy: int) -> int:
    from datetime import date, timedelta

    return (date(year, 1, 1) + timedelta(days=doy - 1)).month
