"""Typed, JSON-serialisable models for Phase 4 quality control."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any


class Classification(StrEnum):
    """Auditable session admission outcome."""

    ACCEPT = "ACCEPT"
    WARN = "WARN"
    REJECT = "REJECT"
    BLOCKED = "BLOCKED"


class FindingSeverity(StrEnum):
    """Severity used to derive an overall classification."""

    PASS = "PASS"
    WARN = "WARN"
    REJECT = "REJECT"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True, slots=True)
class Finding:
    """One structured, evidence-bearing QC determination."""

    finding_code: str
    severity: FindingSeverity
    category: str
    message: str
    station_id: str
    year: int
    day_of_year: int
    file: str
    measured_value: Any = None
    expected_value: Any = None
    threshold: Any = None
    evidence: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class RinexHeader:
    """Header facts explicitly stated by a RINEX observation file."""

    rinex_version: str | None = None
    rinex_type: str | None = None
    satellite_system: str | None = None
    marker_name: str | None = None
    marker_number: str | None = None
    observer: str | None = None
    agency: str | None = None
    receiver_number: str | None = None
    receiver_type: str | None = None
    receiver_version: str | None = None
    antenna_number: str | None = None
    antenna_type: str | None = None
    approximate_xyz_m: tuple[float, float, float] | None = None
    antenna_delta_hen_m: tuple[float, float, float] | None = None
    observation_types: tuple[str, ...] = ()
    declared_interval_seconds: float | None = None
    time_of_first_observation: str | None = None
    time_of_last_observation: str | None = None
    time_system: str | None = None
    leap_seconds: int | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class GapRecord:
    """An internal epoch discontinuity."""

    start: str
    end: str
    elapsed_seconds: float
    expected_interval_seconds: float
    missing_epochs: int

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class RinexAnalysis:
    """Profile-independent measurements from one observation session."""

    header: RinexHeader
    first_epoch: str | None
    last_epoch: str | None
    session_duration_seconds: float | None
    expected_session_duration_seconds: float | None
    declared_interval_seconds: float | None
    empirical_interval_seconds: float | None
    interval_consistent: bool | None
    epochs_expected: int | None
    epochs_observed: int
    unique_epochs_observed: int
    missing_epochs: int | None
    availability_percent: float | None
    duplicate_epochs: int
    backward_epochs: int
    gap_count: int
    largest_gap_seconds: float | None
    total_missing_duration_seconds: float | None
    start_offset_seconds: float | None
    end_shortfall_seconds: float | None
    satellites_min: int | None
    satellites_median: float | None
    satellites_max: int | None
    constellation_statistics: dict[str, dict[str, int | float]]
    potential_cycle_slip_indicators: int
    gaps: tuple[GapRecord, ...]
    parser_warnings: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class SessionInput:
    """Canonical manifest record selected for session QC."""

    station_id: str
    year: int
    day_of_year: int
    relative_path: str
    source_relative_path: str
    sha256: str
    size_bytes: int
    exact_duplicate_sources: tuple[str, ...] = ()


def overall_classification(findings: list[Finding]) -> Classification:
    """Derive the outcome without hiding which gate caused it."""

    severities = {finding.severity for finding in findings}
    if FindingSeverity.REJECT in severities:
        return Classification.REJECT
    if FindingSeverity.BLOCKED in severities:
        return Classification.BLOCKED
    if FindingSeverity.WARN in severities:
        return Classification.WARN
    return Classification.ACCEPT
