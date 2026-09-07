"""Typed models for Phase 5 offline network RTK experiments."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any


class NetworkStatus(StrEnum):
    """Machine-readable experiment/session admission outcome."""

    PLANNED = "PLANNED"
    VALIDATED = "VALIDATED"
    BLOCKED = "BLOCKED"
    RUNNING = "RUNNING"
    COMPLETE = "COMPLETE"
    FAILED_UNEXPECTED = "FAILED_UNEXPECTED"


class AdmissionDecision(StrEnum):
    """Per-session QC admission outcome consumed from Phase 4."""

    ACCEPT = "ACCEPT"
    REJECT = "REJECT"
    BLOCKED = "BLOCKED"


class BaselineOutcome(StrEnum):
    """Per-baseline processing outcome."""

    COMPLETE = "COMPLETE"
    BLOCKED = "BLOCKED"
    FAILED_RTKLB = "FAILED_RTKLB"
    FAILED_OUTPUT = "FAILED_OUTPUT"
    FAILED_UNEXPECTED = "FAILED_UNEXPECTED"


BLOCKED_MESSAGE = "SCIENTIFIC EXECUTION BLOCKED - PHASE 5 NETWORK REQUIREMENTS NOT MET"


class NetworkBlocked(RuntimeError):
    """Raised when a network experiment would violate scientific requirements."""


@dataclass(frozen=True, slots=True)
class NetworkStation:
    """One station participating in a network experiment."""

    station_id: str
    role: str  # "reference" or "rover"
    observation_path: str
    observation_sha256: str | None = None
    metadata_version: str = "v1"


@dataclass(frozen=True, slots=True)
class NetworkExperimentDefinition:
    """Complete, reviewable definition of an offline network experiment."""

    experiment_id: str
    research_question: str
    year: int
    day_of_year: int
    processing_mode: str  # "static" | "kinematic"
    reference_stations: tuple[str, ...]
    test_station: str
    navigation_products: tuple[str, ...]
    start_time_utc: str
    end_time_utc: str
    sampling_interval_seconds: float
    coordinate_frame: str
    coordinate_epoch: str
    qc_profile: str
    minimum_reference_station_count: int
    software_provenance: str = ""
    diagnostic: bool = False
    notes: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def validate(self, *, minimum_required: int = 3) -> list[str]:
        """Return human-readable problems; empty means structurally valid."""
        problems: list[str] = []
        if not self.experiment_id:
            problems.append("experiment_id must be non-empty")
        if not self.research_question:
            problems.append("research_question must be non-empty")
        if not 1 <= self.day_of_year <= 366:
            problems.append(f"day_of_year out of range: {self.day_of_year}")
        if self.processing_mode not in {"static", "kinematic"}:
            problems.append(f"unknown processing_mode: {self.processing_mode}")
        if self.test_station in self.reference_stations:
            problems.append("test_station must not be listed as a reference station")
        if len(set(self.reference_stations)) != len(self.reference_stations):
            problems.append("reference_stations contains duplicates")
        if self.minimum_reference_station_count < minimum_required:
            problems.append(
                "minimum_reference_station_count "
                f"{self.minimum_reference_station_count} is below the scientifically "
                f"justified network minimum {minimum_required}"
            )
        if len(self.reference_stations) < self.minimum_reference_station_count:
            problems.append(
                f"only {len(self.reference_stations)} reference stations supplied, "
                f"minimum is {self.minimum_reference_station_count}"
            )
        if not self.navigation_products:
            problems.append("at least one navigation product is required")
        if self.sampling_interval_seconds <= 0:
            problems.append("sampling_interval_seconds must be positive")
        if not self.coordinate_frame:
            problems.append("coordinate_frame must be non-empty")
        if not self.qc_profile:
            problems.append("qc_profile must be non-empty")
        return problems

    def assert_valid(self) -> None:
        problems = self.validate()
        if problems:
            raise NetworkBlocked(f"{BLOCKED_MESSAGE}: {'; '.join(problems)}")

    def fingerprint_material(self) -> dict[str, Any]:
        return {
            "experiment_id": self.experiment_id,
            "research_question": self.research_question,
            "year": self.year,
            "day_of_year": self.day_of_year,
            "processing_mode": self.processing_mode,
            "reference_stations": sorted(self.reference_stations),
            "test_station": self.test_station,
            "navigation_products": sorted(self.navigation_products),
            "start_time_utc": self.start_time_utc,
            "end_time_utc": self.end_time_utc,
            "sampling_interval_seconds": self.sampling_interval_seconds,
            "coordinate_frame": self.coordinate_frame,
            "coordinate_epoch": self.coordinate_epoch,
            "qc_profile": self.qc_profile,
            "minimum_reference_station_count": self.minimum_reference_station_count,
            "diagnostic": self.diagnostic,
        }


def definition_from_dict(payload: dict[str, Any]) -> NetworkExperimentDefinition:
    """Build a definition from JSON, failing closed on malformed input."""
    try:
        return NetworkExperimentDefinition(
            experiment_id=str(payload["experiment_id"]),
            research_question=str(payload["research_question"]),
            year=int(payload["year"]),
            day_of_year=int(payload["day_of_year"]),
            processing_mode=str(payload["processing_mode"]),
            reference_stations=tuple(str(s) for s in payload["reference_stations"]),
            test_station=str(payload["test_station"]),
            navigation_products=tuple(str(s) for s in payload["navigation_products"]),
            start_time_utc=str(payload["start_time_utc"]),
            end_time_utc=str(payload["end_time_utc"]),
            sampling_interval_seconds=float(payload["sampling_interval_seconds"]),
            coordinate_frame=str(payload["coordinate_frame"]),
            coordinate_epoch=str(payload.get("coordinate_epoch", "")),
            qc_profile=str(payload["qc_profile"]),
            minimum_reference_station_count=int(
                payload.get("minimum_reference_station_count", 3)
            ),
            software_provenance=str(payload.get("software_provenance", "")),
            diagnostic=bool(payload.get("diagnostic", False)),
            notes=str(payload.get("notes", "")),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise NetworkBlocked(f"{BLOCKED_MESSAGE}: malformed experiment definition: {exc}") from exc


@dataclass(frozen=True, slots=True)
class ExperimentPlan:
    """Dry-run plan summary (no processing performed)."""

    experiment_id: str
    status: str
    admitted_stations: tuple[str, ...] = ()
    rejected_stations: tuple[str, ...] = ()
    blocked_reasons: tuple[str, ...] = ()
    baseline_pairs: tuple[tuple[str, str], ...] = ()
    warnings: tuple[str, ...] = field(default_factory=tuple)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)
