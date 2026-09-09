"""Tests for reviewed Phase 6/7 integration (geometry-v3).

SYNTHETIC TEST DATA — NOT VALID FOR SCIENTIFIC RESULTS.

Reviewed values wrap observed evidence:
- Phase 6: zero RMSE 3.076 m beats IDW 3.352 / nearest 3.757 /
  planar 14.373 m, n=15948 identical samples, all folds EXTRAPOLATION;
  BEST MODEL = ZERO; no interpolator promoted.
- Phase 7: APPROVED_WITH_PROVISIONAL_LIMITATIONS, mode
  ZERO / VRS_GEOMETRY_ONLY, promoted model NONE, leakage PASS;
  operational corrected VRS NOT APPROVED.
"""

from __future__ import annotations

from nlgcp_hybrid_decision.decision import decide_full
from nlgcp_hybrid_decision.models import (
    CorrectionMode,
    DecisionStatus,
    DesiredMode,
    ReasonCode,
)
from nlgcp_hybrid_decision.network import assess_network
from nlgcp_hybrid_decision.provenance import decision_fingerprint
from nlgcp_hybrid_decision.vrs import assess_vrs
from phase8_fixtures import (
    make_discovery,
    make_request,
    policy,
    pre_review_spatial,
    pre_review_vrs,
    reviewed_spatial,
    reviewed_vrs,
)


def test_reviewed_phase6_zero_winner() -> None:
    spatial = reviewed_spatial()
    assert spatial.model_name == "zero"
    assert spatial.validation_metric == 3.076
    assert spatial.sample_count == 15948
    assert spatial.extrapolation is True
    assert spatial.geometry_status == "EXTRAPOLATION"
    # No non-zero interpolator beats the zero control.
    assert spatial.beats_zero_control is False
    # Zero is not an APPROVED spatial correction model for VRS service.
    assert str(spatial.validation_status) != "APPROVED"


def test_reviewed_phase7_no_promoted_model_blocks_vrs() -> None:
    discovery = make_discovery()
    network = assess_network(discovery, policy=policy())
    gate = assess_vrs(
        network,
        spatial=reviewed_spatial(),
        vrs=reviewed_vrs(),
        policy=policy(),
        target_leakage_pass=True,
        provenance_pass=True,
    )
    assert gate.selectable is False
    # Operational corrected VRS must not be selectable from geometry-only.
    assert str(reviewed_vrs().status) != "APPROVED"
    assert reviewed_vrs().correction_mode == "ZERO / VRS_GEOMETRY_ONLY"
    assert str(reviewed_vrs().model_status) != "APPROVED"


def test_geometry_only_vrs_cannot_become_operational() -> None:
    decision, _, _, gate = decide_full(
        make_request(desired=DesiredMode.VRS_ONLY),
        make_discovery(),
        spatial=reviewed_spatial(),
        vrs=reviewed_vrs(),
        policy=policy(),
    )
    assert gate.selectable is False
    assert decision.mode == CorrectionMode.NO_CORRECTION
    assert decision.status == DecisionStatus.BLOCKED
    assert decision.selected_vrs_experiment is None
    assert decision.fallback_used is False


def test_reviewed_vrs_verdict_semantics() -> None:
    vrs = reviewed_vrs()
    # Review verdict lives in validation_status, not operational status.
    assert vrs.validation_status == "APPROVED_WITH_PROVISIONAL_LIMITATIONS"
    assert str(vrs.status) != "APPROVED"
    # Leakage passed, yet VRS remains blocked for operational correction.
    assert vrs.target_leakage_status == "PASS"
    discovery = make_discovery()
    network = assess_network(discovery, policy=policy())
    gate = assess_vrs(
        network,
        spatial=reviewed_spatial(),
        vrs=vrs,
        policy=policy(),
        target_leakage_pass=True,
        provenance_pass=True,
    )
    assert gate.selectable is False


def test_auto_fallback_after_scientific_review() -> None:
    decision, _, single, _ = decide_full(
        make_request(),
        make_discovery(),
        spatial=reviewed_spatial(),
        vrs=reviewed_vrs(),
        policy=policy(),
    )
    assert decision.mode == CorrectionMode.SINGLE_BASE
    assert decision.reason_code == ReasonCode.SINGLE_BASE_SELECTED
    assert decision.fallback_used is True
    assert decision.selected_reference == "EKAK00NGA"
    assert single.selected_reference == "EKAK00NGA"
    # Admission OK means gates passed, not centimetre accuracy.
    assert "no centimetre accuracy claimed" in decision.reason_text
    assert "PROVISIONAL" in decision.reason_text


def test_reviewed_fingerprints_differ_from_pre_review() -> None:
    assert (
        reviewed_spatial().fingerprint != pre_review_spatial().fingerprint
    )
    assert reviewed_vrs().fingerprint != pre_review_vrs().fingerprint
    assert str(reviewed_spatial().validation_status) != str(
        pre_review_spatial().validation_status
    )
    assert str(reviewed_vrs().status) != str(pre_review_vrs().status)


def test_stale_pre_review_decision_invalidated() -> None:
    request = make_request()
    discovery = make_discovery()
    old_fp = decision_fingerprint(
        request,
        discovery,
        spatial=pre_review_spatial(),
        vrs=pre_review_vrs(),
        policy=policy(),
    )
    new_fp = decision_fingerprint(
        request,
        discovery,
        spatial=reviewed_spatial(),
        vrs=reviewed_vrs(),
        policy=policy(),
    )
    assert old_fp != new_fp
    old_decision, _, _, _ = decide_full(
        request,
        discovery,
        spatial=pre_review_spatial(),
        vrs=pre_review_vrs(),
        policy=policy(),
    )
    new_decision, _, _, _ = decide_full(
        request,
        discovery,
        spatial=reviewed_spatial(),
        vrs=reviewed_vrs(),
        policy=policy(),
    )
    assert old_decision.decision_fingerprint != new_decision.decision_fingerprint
    # Both fail closed to the same fallback shape, but provenance differs.
    assert old_decision.mode == new_decision.mode == CorrectionMode.SINGLE_BASE
    assert (
        old_decision.provenance["phase6_assessment_fingerprint"]
        != new_decision.provenance["phase6_assessment_fingerprint"]
    )
    assert (
        old_decision.provenance["phase7_assessment_fingerprint"]
        != new_decision.provenance["phase7_assessment_fingerprint"]
    )
