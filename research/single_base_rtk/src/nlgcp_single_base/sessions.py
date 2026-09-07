"""Session completeness QC and common observation-window selection.

File presence is not observation coverage.  Phase 2 produced per-session
parser/completeness QC in
``<data_root>/processed/qc/2024/sessions.csv``.  This module reads that QC
table and derives, for a requested set of stations on a given day, the actual
common observation window, expected epoch counts, and per-station completeness
so that RTKLIB experiments run only over genuinely overlapping, valid data.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from nlgcp_single_base.solution import parse_iso_utc


@dataclass(frozen=True)
class StationSession:
    """One station-day session from the Phase 2 QC output."""

    station_id: str
    year: int
    day_of_year: int
    canonical_relative_path: str
    sha256: str
    parser_status: str
    marker_name: str
    first_epoch: datetime
    last_epoch: datetime
    sampling_interval_seconds: float
    epoch_count: int
    internal_gap_count: int
    estimated_missing_internal_epochs: int
    expected_daily_epochs: int
    observed_epoch_fraction: float
    start_offset_seconds: float
    end_shortfall_seconds: float
    completeness: str
    warnings: str


def load_session_qc(qc_csv: Path) -> dict[int, dict[str, StationSession]]:
    """Load the Phase 2 session QC table keyed by (doy, station_id)."""
    sessions: dict[int, dict[str, StationSession]] = {}
    with qc_csv.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            doy = int(row["day_of_year"])
            station = row["station_id"]
            sessions.setdefault(doy, {})[station] = _station_session(row)
    return sessions


def _station_session(row: dict[str, str]) -> StationSession:
    return StationSession(
        station_id=row["station_id"],
        year=int(row["year"]),
        day_of_year=int(row["day_of_year"]),
        canonical_relative_path=row["canonical_relative_path"],
        sha256=row["sha256"],
        parser_status=row["parser_status"],
        marker_name=row["marker_name"],
        first_epoch=parse_iso_utc(row["first_epoch"]),
        last_epoch=parse_iso_utc(row["last_epoch"]),
        sampling_interval_seconds=float(row["sampling_interval_seconds"]),
        epoch_count=int(row["epoch_count"]),
        internal_gap_count=int(row["internal_gap_count"]),
        estimated_missing_internal_epochs=int(row["estimated_missing_internal_epochs"]),
        expected_daily_epochs=int(row["expected_daily_epochs"]),
        observed_epoch_fraction=float(row["observed_epoch_fraction"]),
        start_offset_seconds=float(row["start_offset_seconds"]),
        end_shortfall_seconds=float(row["end_shortfall_seconds"]),
        completeness=row["completeness"],
        warnings=row["warnings"],
    )


@dataclass(frozen=True)
class OverlapWindow:
    """The common observation window across a set of station sessions."""

    start: datetime
    end: datetime
    sampling_interval_seconds: float
    stations: tuple[str, ...]

    def epoch_count_at_interval(self) -> int:
        """Expected epoch count across the window at the fixed sampling interval."""
        duration = (self.end - self.start).total_seconds()
        return int(duration / self.sampling_interval_seconds) + 1

    def iso_start(self) -> str:
        return self.start.isoformat().replace("+00:00", "Z")

    def iso_end(self) -> str:
        return self.end.isoformat().replace("+00:00", "Z")


class SessionCoverageError(ValueError):
    """Raised when a session does not provide overlapping observation coverage."""


def common_overlap_window(
    sessions: dict[int, dict[str, StationSession]],
    day_of_year: int,
    stations: list[str],
    *,
    require_parsed: bool = True,
    min_fraction: float = 0.0,
) -> OverlapWindow:
    """Compute the longest contiguous common observation window for stations.

    The window is the intersection of each station's (first, last] observation
    span, snapped to whole sampling-interval boundaries.  A session that was
    not parsed, or whose observed epoch fraction is below ``min_fraction``,
    fails closed.

    Raises ``SessionCoverageError`` if any requested station lacks a session
    or the common window is empty.
    """
    day = sessions.get(day_of_year)
    if day is None:
        raise SessionCoverageError(f"no session QC for DOY {day_of_year}")

    session_list: list[StationSession] = []
    for station in stations:
        session = day.get(station)
        if session is None:
            raise SessionCoverageError(f"no session for {station} on DOY {day_of_year}")
        if require_parsed and session.parser_status != "parsed":
            raise SessionCoverageError(
                f"{station} DOY {day_of_year} not parsed: {session.parser_status}"
            )
        if session.observed_epoch_fraction < min_fraction:
            raise SessionCoverageError(
                f"{station} DOY {day_of_year} epoch fraction "
                f"{session.observed_epoch_fraction:.3f} below {min_fraction}"
            )
        session_list.append(session)

    interval = _common_interval(session_list)
    _check_missing_internal_gaps(session_list)
    return OverlapWindow(
        start=interval[0],
        end=interval[1],
        sampling_interval_seconds=session_list[0].sampling_interval_seconds,
        stations=tuple(stations),
    )


def _common_interval(sessions: list[StationSession]) -> tuple[datetime, datetime]:
    if not sessions:
        raise SessionCoverageError("no sessions supplied")
    start = max(session.first_epoch for session in sessions)
    end = min(session.last_epoch for session in sessions)
    if end <= start:
        raise SessionCoverageError("no positive common observation overlap")
    return start, end


def _check_missing_internal_gaps(sessions: list[StationSession]) -> None:
    """Do not treat internally gappy sessions as clean full coverage."""
    for session in sessions:
        if session.internal_gap_count > 0:
            raise SessionCoverageError(
                f"{session.station_id} DOY {session.day_of_year} has "
                f"{session.internal_gap_count} internal gaps "
                f"({session.estimated_missing_internal_epochs} missing epochs); "
                "not suitable for a full-window experiment without per-gap handling"
            )
