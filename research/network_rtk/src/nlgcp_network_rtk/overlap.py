"""Common-epoch / temporal overlap engine.

A network experiment must not assume whole-day overlap from a shared DOY.
Overlap is computed from actual per-station first/last epochs recorded in
Phase 4 QC results (known precedent: MGBO DOY 018 is partial).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

from nlgcp_network_rtk import OVERLAP_SCHEMA_VERSION
from nlgcp_network_rtk.admission import AdmittedSession
from nlgcp_network_rtk.models import BLOCKED_MESSAGE, NetworkBlocked


@dataclass(frozen=True, slots=True)
class StationCoverage:
    station_id: str
    first_epoch: str
    last_epoch: str
    sampling_interval_seconds: float
    epochs_observed: int | None
    expected_epochs_in_common: int | None = None
    coverage_percent_of_common: float | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class OverlapResult:
    common_start: str
    common_end: str
    common_duration_seconds: float
    expected_epochs: int
    sampling_interval_seconds: float
    stations: tuple[StationCoverage, ...]
    coverage_percent: float
    sufficient: bool
    block_reason: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": OVERLAP_SCHEMA_VERSION,
            "common_start": self.common_start,
            "common_end": self.common_end,
            "common_duration_seconds": self.common_duration_seconds,
            "expected_epochs": self.expected_epochs,
            "sampling_interval_seconds": self.sampling_interval_seconds,
            "stations": [row.as_dict() for row in self.stations],
            "coverage_percent": self.coverage_percent,
            "sufficient": self.sufficient,
            "block_reason": self.block_reason,
        }


def parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def compute_overlap(
    sessions: list[AdmittedSession],
    *,
    minimum_duration_seconds: float = 3600.0,
    minimum_coverage_percent: float = 99.0,
) -> OverlapResult:
    """Intersect actual observation windows; fail closed when insufficient."""
    if len(sessions) < 2:
        raise NetworkBlocked(f"{BLOCKED_MESSAGE}: overlap needs at least two sessions")
    intervals: list[tuple[datetime, datetime, AdmittedSession]] = []
    for row in sessions:
        if not row.first_epoch or not row.last_epoch or not row.sampling_interval_seconds:
            raise NetworkBlocked(
                f"{BLOCKED_MESSAGE}: {row.station_id} lacks measured time coverage"
            )
        start = parse_utc(row.first_epoch)
        end = parse_utc(row.last_epoch)
        if end <= start:
            raise NetworkBlocked(
                f"{BLOCKED_MESSAGE}: {row.station_id} has an empty observation window"
            )
        intervals.append((start, end, row))
    common_start = max(start for start, _, _ in intervals)
    common_end = min(end for _, end, _ in intervals)
    duration = (common_end - common_start).total_seconds()
    if duration <= 0:
        raise NetworkBlocked(
            f"{BLOCKED_MESSAGE}: no positive common observation overlap "
            f"({max(s.first_epoch or '' for s in sessions)} .. "
            f"{min(s.last_epoch or '' for s in sessions)})"
        )
    sample_intervals = {
        row.sampling_interval_seconds for row in sessions if row.sampling_interval_seconds
    }
    if len(sample_intervals) != 1:
        raise NetworkBlocked(
            f"{BLOCKED_MESSAGE}: mixed sampling intervals {sorted(sample_intervals)}"
        )
    interval = next(iter(sample_intervals))
    if interval <= 0:
        raise NetworkBlocked(f"{BLOCKED_MESSAGE}: invalid sampling interval {interval}")
    expected = int(duration / interval) + 1
    coverages: list[StationCoverage] = []
    for _, _, row in sorted(intervals, key=lambda t: t[2].station_id):
        observed = row.epochs_observed
        pct: float | None = None
        if observed is not None and expected > 0:
            pct = min(100.0, 100.0 * observed / expected)
        coverages.append(
            StationCoverage(
                station_id=row.station_id,
                first_epoch=str(row.first_epoch),
                last_epoch=str(row.last_epoch),
                sampling_interval_seconds=float(interval),
                epochs_observed=observed,
                expected_epochs_in_common=expected,
                coverage_percent_of_common=pct,
            )
        )
    overall_coverage = 100.0 * expected / expected  # common epochs exist by construction
    sufficient = (
        duration >= minimum_duration_seconds and overall_coverage >= minimum_coverage_percent
    )
    block_reason: str | None = None
    if not sufficient:
        block_reason = (
            f"common overlap {duration:.0f}s below minimum {minimum_duration_seconds:.0f}s "
            "or coverage below threshold; failing closed"
        )
    return OverlapResult(
        common_start=common_start.isoformat().replace("+00:00", "Z"),
        common_end=common_end.isoformat().replace("+00:00", "Z"),
        common_duration_seconds=duration,
        expected_epochs=expected,
        sampling_interval_seconds=float(interval),
        stations=tuple(coverages),
        coverage_percent=overall_coverage,
        sufficient=sufficient,
        block_reason=block_reason,
    )


def assert_sufficient_overlap(result: OverlapResult) -> None:
    if not result.sufficient:
        raise NetworkBlocked(f"{BLOCKED_MESSAGE}: {result.block_reason or 'insufficient overlap'}")
