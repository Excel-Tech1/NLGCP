"""VRS selection gate (Phase 8).

VRS may be automatically selected ONLY IF every gate passes:

- Phase 4 network admission PASS (ACCEPT-only references)
- network geometry PASS
- Phase 6 correction model APPROVED
- Phase 7 VRS APPROVED
- target leakage PASS
- provenance PASS
- required data/products available

Any false condition blocks automatic VRS.  Phase 8 never promotes a
model; promotion belongs to scientific validation upstream.
"""

from __future__ import annotations

from dataclasses import asdict
from dataclasses import dataclass as std_dataclass
from typing import Any

from nlgcp_hybrid_decision.models import (
    ReasonCode,
    SpatialCorrectionAssessment,
    VRSCapabilityAssessment,
)
from nlgcp_hybrid_decision.network import NetworkAssessment
from nlgcp_hybrid_decision.policy import DecisionPolicy


@std_dataclass(frozen=True, slots=True)
class VRSAssessment:
    """VRS gate evaluation outcome."""

    selectable: bool
    reason_code: ReasonCode
    reason_text: str
    experiment_id: str | None = None
    blockers: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["reason_code"] = str(self.reason_code)
        payload["blockers"] = list(self.blockers)
        payload["warnings"] = list(self.warnings)
        return payload


def assess_vrs(
    network: NetworkAssessment,
    *,
    spatial: SpatialCorrectionAssessment,
    vrs: VRSCapabilityAssessment,
    policy: DecisionPolicy,
    target_leakage_pass: bool | None = None,
    provenance_pass: bool = True,
) -> VRSAssessment:
    """Apply the conjunctive VRS approval rule (fail-closed)."""
    blockers: list[str] = list(network.blockers)
    warnings: list[str] = list(network.warnings)

    if not network.eligible:
        blockers.append("NETWORK_NOT_ELIGIBLE")
    if str(network.geometry_status) != "PASS":
        blockers.append(f"GEOMETRY_{network.geometry_status}")

    if policy.require_approved_spatial_model_for_vrs and str(
        spatial.validation_status
    ) != "APPROVED":
        blockers.append(f"SPATIAL_MODEL_{spatial.validation_status}")
    if policy.require_approved_vrs_for_vrs and str(vrs.status) != "APPROVED":
        blockers.append(f"VRS_{vrs.status}")

    leakage = _resolve_leakage(vrs, target_leakage_pass)
    if leakage is False:
        blockers.append("VRS_TARGET_LEAKAGE")
    elif leakage is None:
        blockers.append("VRS_TARGET_LEAKAGE_UNASSESSED")
    if not provenance_pass:
        blockers.append("VRS_PROVENANCE_INVALID")
    if not spatial.fingerprint:
        blockers.append("SPATIAL_FINGERPRINT_MISSING")
        warnings.append("Phase 6 assessment carries no fingerprint; provenance incomplete")
    if not vrs.fingerprint:
        blockers.append("VRS_FINGERPRINT_MISSING")
        warnings.append("Phase 7 assessment carries no fingerprint; provenance incomplete")

    if blockers:
        code, text = _blocked_code(spatial, vrs, network)
        return VRSAssessment(
            selectable=False,
            reason_code=code,
            reason_text=text,
            experiment_id=vrs.experiment_id or None,
            blockers=tuple(blockers),
            warnings=tuple(warnings),
        )
    return VRSAssessment(
        selectable=True,
        reason_code=ReasonCode.VRS_APPROVED,
        reason_text=(
            f"VRS approved: network {network.admitted_count} refs, "
            f"model {spatial.model_name} APPROVED, "
            f"experiment {vrs.experiment_id or 'unnamed'} APPROVED"
        ),
        experiment_id=vrs.experiment_id or None,
        blockers=(),
        warnings=tuple(warnings),
    )


def _resolve_leakage(
    vrs: VRSCapabilityAssessment, override: bool | None
) -> bool | None:
    if override is not None:
        return override
    status = (vrs.target_leakage_status or "").strip().upper()
    if status in ("PASS", "NO_LEAKAGE", "EXCLUDED"):
        return True
    if status in ("FAIL", "LEAKAGE", "LEAKED"):
        return False
    return None


def _blocked_code(
    spatial: SpatialCorrectionAssessment,
    vrs: VRSCapabilityAssessment,
    network: NetworkAssessment,
) -> tuple[ReasonCode, str]:
    if str(vrs.status) in ("NOT_VALIDATED", "PROVISIONAL", "UNAVAILABLE"):
        return (
            ReasonCode.VRS_UPSTREAM_REVIEW_PENDING,
            "VRS blocked: Phase 7 capability not approved "
            f"({vrs.status}); automatic VRS remains fail-closed pending review",
        )
    if str(spatial.validation_status) != "APPROVED":
        return (
            ReasonCode.VRS_MODEL_NOT_VALIDATED,
            "VRS blocked: Phase 6 spatial model not approved "
            f"({spatial.validation_status})",
        )
    if str(vrs.status) == "BLOCKED":
        return (
            ReasonCode.VRS_UPSTREAM_REVIEW_PENDING,
            "VRS blocked: upstream Phase 7 assessment BLOCKED",
        )
    if str(network.geometry_status) != "PASS" or not network.eligible:
        return (
            ReasonCode.VRS_GEOMETRY_INSUFFICIENT,
            "VRS blocked: network geometry insufficient or ineligible",
        )
    return (
        ReasonCode.VRS_UPSTREAM_REVIEW_PENDING,
        "VRS blocked: one or more approval gates failed; see blockers",
    )
