"""Data models and input gates for Phase 3 single-base RTK experiments."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

from nlgcp_single_base.coordinates import (
    EcefCoordinate,
    GeodeticCoordinate,
    ecef_distance_m,
    geodetic_to_ecef,
)

BLOCKED_MESSAGE = "SCIENTIFIC EXECUTION BLOCKED - PHASE 2 INPUTS NOT VERIFIED"


class ScientificExecutionBlocked(RuntimeError):
    """Raised when real scientific processing would violate the Phase 2 input gate."""


class ProcessingMode(StrEnum):
    """Supported RTKLIB relative-positioning modes for the Phase 3 pipeline."""

    STATIC = "static"
    KINEMATIC = "kinematic"


@dataclass(frozen=True)
class StationCoordinate:
    """Station coordinate plus reproducibility-critical frame metadata."""

    reference_frame: str
    coordinate_epoch: str
    ecef: EcefCoordinate | None = None
    geodetic: GeodeticCoordinate | None = None
    provenance: str | None = None

    def require_verified_ecef(self) -> EcefCoordinate:
        """Return explicitly supplied ECEF coordinates for scientific processing."""

        if self.ecef is not None:
            return self.ecef
        raise ScientificExecutionBlocked(
            f"{BLOCKED_MESSAGE}: verified Phase 2 ECEF coordinate required"
        )

    def assert_ecef_geodetic_consistent(self, tolerance_m: float = 0.05) -> None:
        """Check supplied ECEF and geodetic values under the explicit WGS84 convention."""

        if self.ecef is None or self.geodetic is None:
            return
        converted = geodetic_to_ecef(self.geodetic)
        if ecef_distance_m(self.ecef, converted) > tolerance_m:
            raise ScientificExecutionBlocked(
                f"{BLOCKED_MESSAGE}: ECEF/geodetic coordinate consistency check failed"
            )


@dataclass(frozen=True)
class StationInput:
    """Verified station identity and observation input paths."""

    station_id: str
    coordinate: StationCoordinate
    observation_path: Path
    metadata_version: str
    observation_sha256: str | None = None


@dataclass(frozen=True)
class NavigationInput:
    """Navigation or precise-product input used by RTKLIB."""

    path: Path
    sha256: str | None = None
    product_type: str = "broadcast_navigation"


@dataclass(frozen=True)
class Phase2Gate:
    """Explicit evidence flags required before real Phase 3 execution."""

    base_station_verified: bool = False
    rover_station_verified: bool = False
    coordinates_verified: bool = False
    reference_frame_verified: bool = False
    coordinate_epoch_verified: bool = False
    equipment_interval_verified: bool = False
    real_observations_present: bool = False
    navigation_present: bool = False
    overlapping_interval_verified: bool = False
    sampling_interval_verified: bool = False
    file_provenance_verified: bool = False
    hashes_verified: bool = False
    phase2_audit_approved: bool = False

    def missing_items(self) -> list[str]:
        """Return gate conditions that are not yet satisfied."""

        return [name for name, value in self.__dict__.items() if value is not True]

    def assert_open(self) -> None:
        """Fail closed unless every Phase 2 scientific input condition is true."""

        missing = self.missing_items()
        if missing:
            details = ", ".join(missing)
            raise ScientificExecutionBlocked(f"{BLOCKED_MESSAGE}: {details}")


@dataclass(frozen=True)
class ExperimentDefinition:
    """Complete definition needed to prepare or execute an RTKLIB experiment."""

    experiment_id: str
    research_question: str
    processing_mode: ProcessingMode
    start_time_utc: str
    end_time_utc: str
    sampling_rate_hz: float
    base: StationInput
    rover: StationInput
    navigation: list[NavigationInput]
    phase2_gate: Phase2Gate
    notes: str = ""
    extra_metadata: dict[str, Any] = field(default_factory=dict)

    def assert_scientifically_runnable(self) -> None:
        """Apply the Phase 2 scientific input gate."""

        self.phase2_gate.assert_open()
        if self.base.coordinate.reference_frame != self.rover.coordinate.reference_frame:
            raise ScientificExecutionBlocked(
                f"{BLOCKED_MESSAGE}: base and rover reference frames differ"
            )
        if not self.navigation:
            raise ScientificExecutionBlocked(f"{BLOCKED_MESSAGE}: navigation input missing")
