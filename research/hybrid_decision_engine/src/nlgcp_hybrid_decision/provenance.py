"""Provenance and fingerprinting (Phase 8).

Every decision preserves upstream fingerprints.  A changed upstream
fingerprint invalidates cached decisions; the same exact inputs produce
the same decision fingerprint.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from nlgcp_hybrid_decision import DECISION_SCHEMA_VERSION, ENGINE_VERSION
from nlgcp_hybrid_decision.discovery import DiscoveryResult
from nlgcp_hybrid_decision.models import (
    DecisionRequest,
    SpatialCorrectionAssessment,
    VRSCapabilityAssessment,
)
from nlgcp_hybrid_decision.policy import DecisionPolicy, policy_fingerprint

GIT_COMMIT = "recorded-at-runtime"
CONFIG_FINGERPRINT = "recorded-at-runtime"


def sha256_canonical(payload: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def decision_material(
    request: DecisionRequest,
    discovery: DiscoveryResult,
    *,
    spatial: SpatialCorrectionAssessment,
    vrs: VRSCapabilityAssessment,
    policy: DecisionPolicy,
    software_version: str = ENGINE_VERSION,
) -> dict[str, Any]:
    """Fingerprint inputs: changing any entry must invalidate the cache."""
    return {
        "schema_version": DECISION_SCHEMA_VERSION,
        "software_version": software_version,
        "target_ecef_m": list(discovery.target_ecef_m) if discovery.target_ecef_m else None,
        "target_station_id": discovery.target_station_id,
        "request_time": request.request_time,
        "year": request.year,
        "day_of_year": request.day_of_year,
        "desired_mode": str(request.desired_mode),
        "allow_fallback": request.allow_fallback,
        "diagnostic": request.diagnostic,
        "station_set": sorted(c.station_id for c in discovery.candidates),
        "qc_fingerprints": sorted(
            (c.station_id, c.phase4_fingerprint) for c in discovery.candidates
        ),
        "navigation_hashes": sorted(
            (c.station_id, c.navigation_sha256 or "") for c in discovery.candidates
        ),
        "coordinates_fingerprint": discovery.verified_coordinates_fingerprint,
        "spatial_fingerprint": spatial.fingerprint,
        "spatial_status": str(spatial.validation_status),
        "vrs_fingerprint": vrs.fingerprint,
        "vrs_status": str(vrs.status),
        "policy_fingerprint": policy_fingerprint(policy),
        "policy_version": policy.policy_version,
    }


def decision_fingerprint(
    request: DecisionRequest,
    discovery: DiscoveryResult,
    *,
    spatial: SpatialCorrectionAssessment,
    vrs: VRSCapabilityAssessment,
    policy: DecisionPolicy,
) -> str:
    return sha256_canonical(
        decision_material(
            request, discovery, spatial=spatial, vrs=vrs, policy=policy
        )
    )


def build_provenance(
    request: DecisionRequest,
    discovery: DiscoveryResult,
    *,
    spatial: SpatialCorrectionAssessment,
    vrs: VRSCapabilityAssessment,
    policy: DecisionPolicy,
    execution_timestamp: str,
    git_commit: str = GIT_COMMIT,
    decision_engine_version: str = ENGINE_VERSION,
) -> dict[str, Any]:
    """Assemble the full provenance record attached to every decision."""
    return {
        "phase4_qc_fingerprints": {
            c.station_id: c.phase4_fingerprint for c in discovery.candidates
        },
        "phase6_assessment_fingerprint": spatial.fingerprint,
        "phase6_model": spatial.model_name,
        "phase6_provenance": spatial.provenance,
        "phase7_assessment_fingerprint": vrs.fingerprint,
        "phase7_experiment": vrs.experiment_id,
        "phase7_provenance": vrs.provenance,
        "station_metadata_provenance": {
            c.station_id: (c.coordinate_frame, c.coordinate_epoch)
            for c in discovery.candidates
        },
        "navigation_hashes": {
            c.station_id: c.navigation_sha256 for c in discovery.candidates
        },
        "coordinate_frame": _common_frame(discovery),
        "coordinate_epoch": _common_epoch(discovery),
        "decision_engine_version": decision_engine_version,
        "decision_schema_version": DECISION_SCHEMA_VERSION,
        "git_commit": git_commit,
        "policy_version": policy.policy_version,
        "policy_fingerprint": policy_fingerprint(policy),
        "execution_timestamp": execution_timestamp,
        "request_id": request.request_id,
    }


def _common_frame(discovery: DiscoveryResult) -> str | None:
    frames = {c.coordinate_frame for c in discovery.candidates if c.coordinate_frame}
    if len(frames) == 1:
        return next(iter(frames))
    return None


def _common_epoch(discovery: DiscoveryResult) -> str | None:
    epochs = {c.coordinate_epoch for c in discovery.candidates if c.coordinate_epoch}
    if len(epochs) == 1:
        return next(iter(epochs))
    return None
