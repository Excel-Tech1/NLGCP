"""Domain contracts, truth records, and leakage guards for B-02 rover benchmarking.

Strictly distinguishes verified IGS20 PPP-AR coordinate truth from provisional
historical coordinates and prevents held-out rover data leakage into VRS
atmospheric modelling or synthesis.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any


class BenchmarkFailure(RuntimeError):
    """Fail-closed exception raised on invalid inputs, leakage, or RTKLIB failure."""


class TruthTier(StrEnum):
    """Explicit classification of rover reference coordinate defensibility."""

    VERIFIED_IGS20_PPP_AR = "VERIFIED_IGS20_PPP_AR"
    VERIFIED_ITRF = "VERIFIED_ITRF"
    PROVISIONAL_OSGOF_LIMITED = "PROVISIONAL_OSGOF_LIMITED"
    UNAVAILABLE_EXPLORATORY_ONLY = "UNAVAILABLE_EXPLORATORY_ONLY"


class BenchmarkOutcome(StrEnum):
    """Fail-closed execution outcome for one benchmark configuration."""

    COMPLETED = "COMPLETED"
    FAILED_MISSING_ROVER_OBS = "FAILED_MISSING_ROVER_OBS"
    FAILED_MISSING_REFERENCE_OBS = "FAILED_MISSING_REFERENCE_OBS"
    FAILED_MISSING_NAVIGATION = "FAILED_MISSING_NAVIGATION"
    FAILED_INVALID_RTCM = "FAILED_INVALID_RTCM"
    FAILED_TRUNCATED_RTCM = "FAILED_TRUNCATED_RTCM"
    FAILED_INSUFFICIENT_SATELLITES = "FAILED_INSUFFICIENT_SATELLITES"
    FAILED_EPOCH_MISMATCH = "FAILED_EPOCH_MISMATCH"
    FAILED_INVALID_COORDINATE_PROVENANCE = "FAILED_INVALID_COORDINATE_PROVENANCE"
    FAILED_ATMOSPHERIC_MODEL_UNAVAILABLE = "FAILED_ATMOSPHERIC_MODEL_UNAVAILABLE"
    FAILED_OUTSIDE_CONVEX_HULL = "FAILED_OUTSIDE_CONVEX_HULL"
    FAILED_AMBIGUITY_RESOLUTION_NONE = "FAILED_AMBIGUITY_RESOLUTION_NONE"
    FAILED_RTKLIB_EXECUTION = "FAILED_RTKLIB_EXECUTION"


class ProcessingProfile(StrEnum):
    """Comparable RTKLIB processing profiles evaluated identically across variants."""

    KINEMATIC_BRDC_SAAS = "kinematic_brdc_saas"
    STATIC_BRDC_SAAS = "static_brdc_saas"
    KINEMATIC_VRS_IONO_OFF = "kinematic_vrs_iono_off"
    DGPS_CODE_DIFF = "dgps_code_diff"
    SPP_SINGLE = "spp_single"


@dataclass(frozen=True, slots=True)
class RoverTruthRecord:
    """Traceable reference coordinate record for one withheld rover station."""

    station_id: str
    truth_tier: TruthTier
    accuracy_claim_permitted: bool
    ecef_xyz_m: tuple[float, float, float]
    reference_frame: str
    coordinate_epoch: str
    provenance_source: str
    provenance_sha256: str | None
    antenna_model: str
    antenna_delta_hen_m: tuple[float, float, float]
    formal_sigma_xyz_m: tuple[float, float, float] | None = None
    processing_method: str = ""
    precise_products: tuple[str, ...] = ()
    bias_products_available: bool = False
    notes: str = ""

    def validate(self) -> None:
        if not self.station_id or not self.reference_frame or not self.coordinate_epoch:
            raise BenchmarkFailure("incomplete rover coordinate provenance metadata")
        if len(self.ecef_xyz_m) != 3 or not all(math.isfinite(v) for v in self.ecef_xyz_m):
            raise BenchmarkFailure("non-finite rover truth ECEF coordinate")
        radius = math.hypot(*self.ecef_xyz_m)
        if not (6_300_000.0 <= radius <= 6_450_000.0):
            raise BenchmarkFailure(
                f"rover truth radius {radius:.1f} m outside Earth surface bounds"
            )
        if (
            self.truth_tier not in (TruthTier.VERIFIED_IGS20_PPP_AR, TruthTier.VERIFIED_ITRF)
            and self.accuracy_claim_permitted
        ):
            raise BenchmarkFailure(
                "verified accuracy claims are forbidden without VERIFIED_IGS20_PPP_AR "
                "or VERIFIED_ITRF truth"
            )

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["truth_tier"] = str(self.truth_tier)
        payload["ecef_xyz_m"] = list(self.ecef_xyz_m)
        payload["antenna_delta_hen_m"] = list(self.antenna_delta_hen_m)
        if self.formal_sigma_xyz_m is not None:
            payload["formal_sigma_xyz_m"] = list(self.formal_sigma_xyz_m)
        payload["precise_products"] = list(self.precise_products)
        return payload


@dataclass(frozen=True, slots=True)
class DatasetWindowSpec:
    """Immutable manifest specification for one B-02 rover benchmark dataset."""

    dataset_id: str
    date_iso: str
    year: int
    doy: int
    start_time_utc: str
    end_time_utc: str
    sampling_interval_s: float
    rover_station_id: str
    rover_obs_path: Path
    rover_obs_sha256: str
    physical_anchor_id: str
    physical_anchor_obs_path: Path
    physical_anchor_obs_sha256: str
    physical_anchor_ecef_m: tuple[float, float, float]
    reference_stations: tuple[str, ...]
    nav_path: Path
    nav_sha256: str
    rover_inside_convex_hull: bool
    anchor_baseline_km: float
    rover_truth: RoverTruthRecord
    notes: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "dataset_id": self.dataset_id,
            "date_iso": self.date_iso,
            "year": self.year,
            "doy": self.doy,
            "start_time_utc": self.start_time_utc,
            "end_time_utc": self.end_time_utc,
            "sampling_interval_s": self.sampling_interval_s,
            "rover_station_id": self.rover_station_id,
            "rover_obs_path": str(self.rover_obs_path),
            "rover_obs_sha256": self.rover_obs_sha256,
            "physical_anchor_id": self.physical_anchor_id,
            "physical_anchor_obs_path": str(self.physical_anchor_obs_path),
            "physical_anchor_obs_sha256": self.physical_anchor_obs_sha256,
            "physical_anchor_ecef_m": list(self.physical_anchor_ecef_m),
            "reference_stations": list(self.reference_stations),
            "nav_path": str(self.nav_path),
            "nav_sha256": self.nav_sha256,
            "rover_inside_convex_hull": self.rover_inside_convex_hull,
            "anchor_baseline_km": round(self.anchor_baseline_km, 3),
            "rover_truth": self.rover_truth.as_dict(),
            "notes": self.notes,
        }


@dataclass(frozen=True, slots=True)
class LeakageAuditResult:
    """Explicit verification that held-out rover data never leaked into VRS generation."""

    rover_station_id: str
    rover_excluded_from_reference_coords: bool
    rover_excluded_from_reference_datasets: bool
    rover_excluded_from_iono_field: bool
    rover_excluded_from_ztd_field: bool
    physical_anchor_distinct_from_rover: bool
    passed: bool
    vrs_virtual_position_source: str = "ROVER_EPOCH0_SPP_GGA"
    vrs_virtual_offset_from_truth_m: float | None = None
    findings: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["findings"] = list(self.findings)
        return payload


def assert_no_rover_leakage(
    *,
    rover_station_id: str,
    physical_anchor_id: str,
    reference_coord_ids: set[str],
    reference_dataset_ids: set[str],
    iono_field_station_ids: set[str],
    ztd_station_ids: set[str],
    vrs_virtual_position_source: str = "ROVER_EPOCH0_SPP_GGA",
    vrs_virtual_offset_from_truth_m: float | None = None,
) -> LeakageAuditResult:
    """Fail closed if the withheld rover appears in any reference training input."""
    findings: list[str] = []
    c1 = rover_station_id not in reference_coord_ids
    if not c1:
        findings.append(f"LEAKAGE: rover {rover_station_id} found in reference_coords")
    c2 = rover_station_id not in reference_dataset_ids
    if not c2:
        findings.append(f"LEAKAGE: rover {rover_station_id} found in reference_datasets")
    c3 = rover_station_id not in iono_field_station_ids
    if not c3:
        findings.append(f"LEAKAGE: rover {rover_station_id} found in iono_field")
    c4 = rover_station_id not in ztd_station_ids
    if not c4:
        findings.append(f"LEAKAGE: rover {rover_station_id} found in reference ZTD inputs")
    c5 = physical_anchor_id != rover_station_id
    if not c5:
        findings.append(f"INVALID: physical_anchor_id == rover_station_id ({rover_station_id})")
    passed = c1 and c2 and c3 and c4 and c5
    result = LeakageAuditResult(
        rover_station_id=rover_station_id,
        rover_excluded_from_reference_coords=c1,
        rover_excluded_from_reference_datasets=c2,
        rover_excluded_from_iono_field=c3,
        rover_excluded_from_ztd_field=c4,
        physical_anchor_distinct_from_rover=c5,
        passed=passed,
        vrs_virtual_position_source=vrs_virtual_position_source,
        vrs_virtual_offset_from_truth_m=vrs_virtual_offset_from_truth_m,
        findings=tuple(findings),
    )
    if not passed:
        raise BenchmarkFailure("; ".join(findings))
    return result


@dataclass(frozen=True, slots=True)
class VariantRunResult:
    """Structured provenance and metric record for one (variant, profile) RTKLIB run."""

    dataset_id: str
    variant_id: str
    profile: ProcessingProfile
    outcome: BenchmarkOutcome
    truth_tier: TruthTier
    base_station_label: str
    base_ecef_m: tuple[float, float, float]
    rtcm_source_path: str | None
    rtcm_source_sha256: str | None
    base_rinex_path: str | None
    base_rinex_sha256: str | None
    rtklib_config_path: str | None
    rtklib_config_sha256: str | None
    solution_pos_path: str | None
    solution_pos_sha256: str | None
    metrics: dict[str, Any] = field(default_factory=dict)
    conversion_summary: dict[str, Any] = field(default_factory=dict)
    execution_summary: dict[str, Any] = field(default_factory=dict)
    error_detail: str | None = None

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["profile"] = str(self.profile)
        payload["outcome"] = str(self.outcome)
        payload["truth_tier"] = str(self.truth_tier)
        payload["base_ecef_m"] = list(self.base_ecef_m)
        return payload
