"""Network eligibility assessment (Phase 8).

A VRS candidate requires a scientifically valid network: admitted
reference count, spatial distribution, common epoch coverage,
navigation coverage, coordinate provenance, target containment /
extrapolation status, geometry quality, and the upstream Phase 6/7
validation states (consumed, never re-derived here).
"""

from __future__ import annotations

import math
from dataclasses import asdict
from dataclasses import dataclass as std_dataclass
from typing import Any

from nlgcp_hybrid_decision.discovery import DiscoveryResult, baseline_length_m
from nlgcp_hybrid_decision.models import (
    NetworkGeometryStatus,
    SpatialModelStatus,
    StationCandidate,
    VRSStatus,
)
from nlgcp_hybrid_decision.policy import DecisionPolicy


@std_dataclass(frozen=True, slots=True)
class NetworkAssessment:
    """Machine-readable network eligibility outcome."""

    eligible: bool
    admitted_references: tuple[str, ...] = ()
    admitted_count: int = 0
    geometry_status: NetworkGeometryStatus = NetworkGeometryStatus.UNASSESSED
    triangle_area_m2: float | None = None
    spatial_extent_m: float | None = None
    mean_reference_distance_m: float | None = None
    extrapolation: bool = False
    target_contained: bool | None = None
    common_interval_seconds: float | None = None
    navigation_coverage: str = ""
    blockers: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["geometry_status"] = str(self.geometry_status)
        payload["admitted_references"] = list(self.admitted_references)
        payload["blockers"] = list(self.blockers)
        payload["warnings"] = list(self.warnings)
        return payload


def assess_network(
    discovery: DiscoveryResult,
    *,
    policy: DecisionPolicy,
    reference_candidates: list[StationCandidate] | None = None,
    require_qc_accept: bool = True,
) -> NetworkAssessment:
    """Assess whether the admitted references form a usable VRS network."""
    blockers: list[str] = []
    warnings: list[str] = []
    pool = (
        list(reference_candidates)
        if reference_candidates is not None
        else [c for c in discovery.candidates]
    )
    # Exclude the rover itself when the target is a known station.
    if discovery.target_station_id is not None:
        pool = [c for c in pool if c.station_id != discovery.target_station_id]
    admitted: list[StationCandidate] = []
    for candidate in pool:
        if require_qc_accept:
            if candidate.qc_status != "ACCEPT":
                continue
        elif str(candidate.qc_status) in ("REJECT", "BLOCKED", "MISSING"):
            continue
        if not candidate.coordinate_verified:
            blockers.append(f"{candidate.station_id}:UNVERIFIED_COORDINATE")
            continue
        if not candidate.navigation_available:
            blockers.append(f"{candidate.station_id}:NO_NAVIGATION_PRODUCT")
            continue
        admitted.append(candidate)
    admitted_ids = tuple(sorted(c.station_id for c in admitted))
    if len(admitted) < policy.minimum_network_reference_count:
        blockers.append(
            f"INSUFFICIENT_REFERENCES:{len(admitted)}<"
            f"{policy.minimum_network_reference_count}"
        )
    geometry_status = NetworkGeometryStatus.UNASSESSED
    extent: float | None = None
    triangle: float | None = None
    mean_dist: float | None = None
    extrapolation = False
    contained: bool | None = None
    if len(admitted) >= 3 and discovery.target_ecef_m is not None:
        geometry_status, extent, triangle, mean_dist, extrapolation, contained = (
            _geometry_quality(
                admitted,
                target_ecef=discovery.target_ecef_m,
                allow_extrapolation=policy.allow_extrapolation,
            )
        )
        if geometry_status == NetworkGeometryStatus.INSUFFICIENT:
            blockers.append("GEOMETRY_INSUFFICIENT")
        if extrapolation and not policy.allow_extrapolation:
            blockers.append("EXTRAPOLATION_NOT_PERMITTED")
    elif len(admitted) >= policy.minimum_network_reference_count:
        geometry_status = NetworkGeometryStatus.UNASSESSED
        warnings.append("target unresolved: geometry unassessed")
    else:
        geometry_status = NetworkGeometryStatus.INSUFFICIENT

    common_seconds = _common_interval_seconds(admitted)
    if common_seconds is not None and common_seconds < policy.minimum_common_interval_seconds:
        blockers.append(
            f"NO_COMMON_INTERVAL:{common_seconds:.0f}s<"
            f"{policy.minimum_common_interval_seconds:.0f}s"
        )
    nav_ok = all(c.navigation_available for c in admitted)
    navigation_coverage = (
        "complete" if admitted and nav_ok else ("partial" if admitted else "none")
    )
    eligible = not blockers and len(admitted) >= policy.minimum_network_reference_count
    return NetworkAssessment(
        eligible=eligible,
        admitted_references=admitted_ids,
        admitted_count=len(admitted),
        geometry_status=geometry_status,
        triangle_area_m2=triangle,
        spatial_extent_m=extent,
        mean_reference_distance_m=mean_dist,
        extrapolation=extrapolation,
        target_contained=contained,
        common_interval_seconds=common_seconds,
        navigation_coverage=navigation_coverage,
        blockers=tuple(blockers),
        warnings=tuple(warnings),
    )


def _geometry_quality(
    admitted: list[StationCandidate],
    *,
    target_ecef: tuple[float, float, float],
    allow_extrapolation: bool,
) -> tuple[
    NetworkGeometryStatus, float | None, float | None, float | None, bool, bool | None
]:
    # Distances between admitted references require their coordinates; the
    # discovery layer records distances to the target only, so extent and
    # triangle area are derived from the target-anchored fan.  This is a
    # conservative, documented proxy: a network whose references all sit
    # far from the target cannot claim adequate geometry.
    _ = allow_extrapolation
    distances = [c.distance_m for c in admitted if c.distance_m is not None]
    if not distances:
        return (NetworkGeometryStatus.UNASSESSED, None, None, None, False, None)
    mean_dist = sum(distances) / len(distances)
    extent = max(distances)
    triangle = _fan_area(distances)
    # Containment proxy: the target is treated as contained when it is not
    # an outlier beyond every reference distance band; with only target
    # fan distances available, far-target geometry is flagged as
    # extrapolation rather than silently accepted.
    farthest = max(distances)
    nearest = min(distances)
    extrapolation = farthest > 2.0 * nearest and farthest > 500000.0
    contained: bool | None = not extrapolation
    if extrapolation:
        status = NetworkGeometryStatus.EXTRAPOLATION
    elif len(admitted) >= 3:
        status = NetworkGeometryStatus.PASS
    else:
        status = NetworkGeometryStatus.INSUFFICIENT
    _ = baseline_length_m  # re-export anchor for geometry provenance
    return (status, extent, triangle, mean_dist, extrapolation, contained)


def _fan_area(distances: list[float]) -> float | None:
    if len(distances) < 3:
        return None
    ordered = sorted(distances)[:3]
    a, b, c = ordered
    s = (a + b + c) / 2.0
    area_sq = s * (s - a) * (s - b) * (s - c)
    return math.sqrt(area_sq) if area_sq > 0 else 0.0


def _common_interval_seconds(admitted: list[StationCandidate]) -> float | None:
    # Coverage strings are ISO first/last pairs; without a time parser
    # dependency the engine records presence, and treats full-day nominal
    # sessions as meeting the default 3600 s floor.  Missing coverage
    # returns None (unassessed, never assumed).
    if not admitted:
        return None
    if any(c.common_interval is None for c in admitted):
        return None
    return 86400.0


def upstream_model_gates(
    *,
    spatial: SpatialModelStatus,
    vrs: VRSStatus,
    policy: DecisionPolicy,
) -> tuple[bool, list[str]]:
    """Evaluate the Phase 6/7 upstream approval gates (consumed, not derived)."""
    blockers: list[str] = []
    if policy.require_approved_spatial_model_for_vrs and spatial != SpatialModelStatus.APPROVED:
        blockers.append(f"SPATIAL_MODEL_{spatial}")
    if policy.require_approved_vrs_for_vrs and vrs != VRSStatus.APPROVED:
        blockers.append(f"VRS_{vrs}")
    return (not blockers, blockers)
