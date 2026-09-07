"""Typed models for Phase 6 atmospheric & spatial error modelling."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any


class StageStatus(StrEnum):
    """Machine-readable derivation stage outcome."""

    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    BLOCKED = "BLOCKED"


class ModelBlocked(RuntimeError):
    """Raised when modelling would violate scientific requirements."""


BLOCKED_MESSAGE = "SCIENTIFIC EXECUTION BLOCKED - PHASE 6 REQUIREMENTS NOT MET"


@dataclass(frozen=True, slots=True)
class ModelExperimentDefinition:
    """Complete, reviewable definition of a Phase 6 modelling experiment."""

    experiment_id: str
    research_question: str
    phase5_experiment_id: str
    year: int
    day_of_year: int
    reference_stations: tuple[str, ...]
    target_station: str
    coordinate_frame: str
    coordinate_epoch: str
    minimum_reference_station_count: int = 3
    epoch_stride: int = 1
    min_elevation_deg: float = 10.0
    gf_slip_threshold_m: float = 0.5
    notes: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def validate(self, *, minimum_required: int = 3) -> list[str]:
        problems: list[str] = []
        if not self.experiment_id:
            problems.append("experiment_id must be non-empty")
        if not self.research_question:
            problems.append("research_question must be non-empty")
        if not 1 <= self.day_of_year <= 366:
            problems.append(f"day_of_year out of range: {self.day_of_year}")
        if self.target_station in self.reference_stations:
            problems.append("target_station must not be listed as a reference station")
        if len(set(self.reference_stations)) != len(self.reference_stations):
            problems.append("reference_stations contains duplicates")
        if self.minimum_reference_station_count < minimum_required:
            problems.append(
                "minimum_reference_station_count "
                f"{self.minimum_reference_station_count} below network floor {minimum_required}"
            )
        if len(self.reference_stations) < self.minimum_reference_station_count:
            problems.append("fewer reference stations than the declared minimum")
        if self.epoch_stride < 1:
            problems.append("epoch_stride must be >= 1")
        if not 0.0 <= self.min_elevation_deg <= 90.0:
            problems.append("min_elevation_deg must be within [0, 90]")
        return problems


def definition_from_dict(payload: dict[str, Any]) -> ModelExperimentDefinition:
    refs = tuple(str(s) for s in payload.get("reference_stations", []))
    return ModelExperimentDefinition(
        experiment_id=str(payload.get("experiment_id", "")),
        research_question=str(payload.get("research_question", "")),
        phase5_experiment_id=str(payload.get("phase5_experiment_id", "")),
        year=int(payload.get("year", 2024)),
        day_of_year=int(payload.get("day_of_year", 26)),
        reference_stations=refs,
        target_station=str(payload.get("target_station", "")),
        coordinate_frame=str(payload.get("coordinate_frame", "IGS20")),
        coordinate_epoch=str(payload.get("coordinate_epoch", "")),
        minimum_reference_station_count=int(payload.get("minimum_reference_station_count", 3)),
        epoch_stride=int(payload.get("epoch_stride", 1)),
        min_elevation_deg=float(payload.get("min_elevation_deg", 10.0)),
        gf_slip_threshold_m=float(payload.get("gf_slip_threshold_m", 0.5)),
        notes=str(payload.get("notes", "")),
    )


@dataclass(frozen=True, slots=True)
class StationCoordinate:
    """Verified station position constraining the spatial model geometry."""

    station_id: str
    x_m: float
    y_m: float
    z_m: float
    frame: str
    epoch: str


@dataclass(slots=True)
class ObservationSample:
    """One satellite observation sample at one station/epoch (SI units)."""

    epoch_iso: str
    station_id: str
    satellite_id: str  # e.g. "G03" (RINEX 2 id + PRN)
    constellation: str  # "G", "R", "E", "S", ...
    phase_l1_m: float | None = None
    phase_l2_m: float | None = None
    code_c1_m: float | None = None
    code_p1_m: float | None = None
    code_p2_m: float | None = None
    obs_codes: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class CombinationResult:
    """Derived measurement combination with full provenance."""

    epoch_iso: str
    satellite_id: str
    constellation: str
    kind: str  # "GF" | "GF_SD" | "GF_DD_ARC_DETRENDED" | ...
    value_m: float | None
    value_tecu: float | None
    unit: str
    derivation_method: str
    input_obs_codes: tuple[str, ...]
    stations: tuple[str, ...]
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class SpatialRecord:
    """One network-error observation available to the interpolation layer.

    Fields unsupported by evidence are None with the reason recorded in
    ``quality_flags`` / ``provenance`` instead of being invented.
    """

    epoch_iso: str
    satellite_id: str
    constellation: str
    reference_station: str
    target_station: str
    station_x_m: float
    station_y_m: float
    station_z_m: float
    baseline_length_m: float
    azimuth_deg: float | None = None
    elevation_deg: float | None = None
    ionosphere_proxy_m: float | None = None
    troposphere_proxy_m: float | None = None
    combined_residual_m: float | None = None
    quality_flags: tuple[str, ...] = ()
    provenance: str = ""


@dataclass(frozen=True, slots=True)
class InterpolationPrediction:
    """Predicted correction/error term at a target location."""

    epoch_iso: str
    satellite_id: str
    target_station: str
    model_name: str
    predicted_m: float | None
    observed_m: float | None
    residual_m: float | None
    extrapolated: bool
    model_parameters: dict[str, Any] = field(default_factory=dict)
    reason: str | None = None
