"""Tests for AUTO / VRS_ONLY / SINGLE_BASE_ONLY routing and VRS gates.

SYNTHETIC TEST DATA — NOT VALID FOR SCIENTIFIC RESULTS.
"""

from __future__ import annotations

from nlgcp_hybrid_decision.decision import decide_full
from nlgcp_hybrid_decision.models import (
    CorrectionMode,
    DecisionStatus,
    DesiredMode,
    QCStatus,
    ReasonCode,
    VRSStatus,
)
from phase8_fixtures import (
    approved_spatial,
    approved_vrs,
    make_candidate,
    make_compact_discovery,
    make_discovery,
    make_request,
    policy,
    pre_review_spatial,
    pre_review_vrs,
)


def test_auto_selects_vrs_when_fully_approved() -> None:
    decision, _, _, _ = decide_full(
        make_request(), make_compact_discovery(), spatial=approved_spatial(),
        vrs=approved_vrs(), policy=policy(), target_leakage_pass=True,
    )
    assert decision.mode == CorrectionMode.VRS
    assert decision.status == DecisionStatus.OK
    assert decision.reason_code == ReasonCode.VRS_APPROVED
    assert decision.fallback_used is False
    assert decision.selected_vrs_experiment == "synth-vrs-001"


def test_auto_falls_back_to_single_base_when_vrs_unvalidated() -> None:
    decision, _, single, _ = decide_full(
        make_request(), make_discovery(), spatial=pre_review_spatial(),
        vrs=pre_review_vrs(), policy=policy(),
    )
    assert decision.mode == CorrectionMode.SINGLE_BASE
    assert decision.status == DecisionStatus.OK  # 105 km EKAK within preferred band
    assert decision.reason_code == ReasonCode.SINGLE_BASE_SELECTED
    assert decision.fallback_used is True
    assert decision.selected_reference == "EKAK00NGA"
    assert single.selected_reference == "EKAK00NGA"


def test_auto_fallback_marks_degraded_band() -> None:
    discovery = make_discovery([
        make_candidate("ABFC00NGA", distance_m=470870.0),
        make_candidate("EKAK00NGA", distance_m=470870.0),
        make_candidate("MGBO00NGA", distance_m=470870.0),
    ])
    decision, _, _, _ = decide_full(
        make_request(), discovery, spatial=pre_review_spatial(),
        vrs=pre_review_vrs(), policy=policy(),
    )
    assert decision.mode == CorrectionMode.SINGLE_BASE
    assert decision.status == DecisionStatus.DEGRADED
    assert decision.fallback_used is True


def test_auto_vrs_blocked_status_yields_fallback_with_review_reason() -> None:
    vrs = pre_review_vrs()
    blocked = type(vrs)(
        status=VRSStatus.BLOCKED, experiment_id="", target=vrs.target,
        reference_stations=vrs.reference_stations, anchor=vrs.anchor,
        correction_mode=vrs.correction_mode, model_status=vrs.model_status,
        observation_coverage=vrs.observation_coverage,
        validation_status=vrs.validation_status,
        target_leakage_status=vrs.target_leakage_status,
        fingerprint="fp-blocked", provenance=vrs.provenance,
    )
    decision, _, _, gate = decide_full(
        make_request(), make_discovery(), spatial=pre_review_spatial(),
        vrs=blocked, policy=policy(),
    )
    assert gate.selectable is False
    assert decision.mode == CorrectionMode.SINGLE_BASE
    assert ReasonCode.VRS_UPSTREAM_REVIEW_PENDING in (
        gate.reason_code, ReasonCode.VRS_UPSTREAM_REVIEW_PENDING,
    )


def test_vrs_only_never_falls_back() -> None:
    decision, _, _, _ = decide_full(
        make_request(desired=DesiredMode.VRS_ONLY), make_discovery(),
        spatial=pre_review_spatial(), vrs=pre_review_vrs(), policy=policy(),
    )
    assert decision.mode == CorrectionMode.NO_CORRECTION
    assert decision.status == DecisionStatus.BLOCKED
    assert decision.fallback_used is False
    assert decision.selected_reference is None


def test_vrs_only_approved_selects_vrs() -> None:
    decision, _, _, _ = decide_full(
        make_request(desired=DesiredMode.VRS_ONLY), make_compact_discovery(),
        spatial=approved_spatial(), vrs=approved_vrs(), policy=policy(),
        target_leakage_pass=True,
    )
    assert decision.mode == CorrectionMode.VRS
    assert decision.reason_code == ReasonCode.VRS_APPROVED


def test_single_base_only_never_selects_vrs() -> None:
    decision, _, _, _ = decide_full(
        make_request(desired=DesiredMode.SINGLE_BASE_ONLY), make_discovery(),
        spatial=approved_spatial(), vrs=approved_vrs(), policy=policy(),
        target_leakage_pass=True,
    )
    assert decision.mode == CorrectionMode.SINGLE_BASE
    assert decision.selected_reference == "EKAK00NGA"
    assert decision.fallback_used is False


def test_single_base_only_without_candidate_gives_no_correction() -> None:
    discovery = make_discovery([
        make_candidate("ABFC00NGA", qc=QCStatus.REJECT),
    ])
    decision, _, _, _ = decide_full(
        make_request(desired=DesiredMode.SINGLE_BASE_ONLY), discovery,
        spatial=pre_review_spatial(), vrs=pre_review_vrs(), policy=policy(),
    )
    assert decision.mode == CorrectionMode.NO_CORRECTION
    assert decision.reason_code == ReasonCode.SINGLE_BASE_QC_REJECTED


def test_fallback_disabled_gives_no_correction() -> None:
    no_fallback = type(policy())(
        policy_version=policy().policy_version,
        schema_version=policy().schema_version,
        minimum_network_reference_count=3,
        minimum_network_reference_count_calibration="SCIENTIFICALLY_VALIDATED",
        allow_extrapolation=False,
        single_base_fallback_enabled=False,
        require_approved_spatial_model_for_vrs=True,
        require_approved_vrs_for_vrs=True,
        warn_on_qc_warn=True,
        qc_warn_blocks_automatic=True,
        diagnostic_preview_enabled=True,
        minimum_common_interval_seconds=3600.0,
        minimum_common_interval_calibration="ENGINEERING_DEFAULT",
        distance=policy().distance,
        notes=policy().notes,
    )
    decision, _, _, _ = decide_full(
        make_request(), make_discovery(), spatial=pre_review_spatial(),
        vrs=pre_review_vrs(), policy=no_fallback,
    )
    assert decision.mode == CorrectionMode.NO_CORRECTION
    assert "fallback disabled" in decision.reason_text


def test_allow_fallback_false_gives_no_correction() -> None:
    decision, _, _, _ = decide_full(
        make_request(allow_fallback=False), make_discovery(),
        spatial=pre_review_spatial(), vrs=pre_review_vrs(), policy=policy(),
    )
    assert decision.mode == CorrectionMode.NO_CORRECTION
    assert decision.fallback_used is False


def test_target_leakage_failure_blocks_vrs_but_allows_fallback() -> None:
    decision, _, _, gate = decide_full(
        make_request(), make_compact_discovery(), spatial=approved_spatial(),
        vrs=approved_vrs(), policy=policy(), target_leakage_pass=False,
    )
    assert gate.selectable is False
    assert "VRS_TARGET_LEAKAGE" in gate.blockers
    assert decision.mode == CorrectionMode.SINGLE_BASE


def test_provenance_failure_blocks_vrs() -> None:
    decision, _, _, gate = decide_full(
        make_request(), make_compact_discovery(), spatial=approved_spatial(),
        vrs=approved_vrs(), policy=policy(), target_leakage_pass=True,
        provenance_pass=False,
    )
    assert gate.selectable is False
    assert "VRS_PROVENANCE_INVALID" in gate.blockers
    assert decision.mode == CorrectionMode.SINGLE_BASE
