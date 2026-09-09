"""Tests for ranking, determinism, fingerprints, diagnostic, provenance.

SYNTHETIC TEST DATA — NOT VALID FOR SCIENTIFIC RESULTS.
"""

from __future__ import annotations

from typing import Any

from nlgcp_hybrid_decision.decision import decide_full
from nlgcp_hybrid_decision.discovery import candidate_from_dict
from nlgcp_hybrid_decision.models import (
    CorrectionDecision,
    CorrectionMode,
    DecisionBlocked,
    DecisionStatus,
    DesiredMode,
    QCStatus,
    ReasonCode,
    phase9_view,
)
from nlgcp_hybrid_decision.provenance import decision_fingerprint
from nlgcp_hybrid_decision.reporting import render_trace
from nlgcp_hybrid_decision.single_base import assess_single_base
from phase8_fixtures import (
    TARGET_ECEF,
    approved_spatial,
    approved_vrs,
    make_candidate,
    make_discovery,
    make_request,
    policy,
    pre_review_spatial,
    pre_review_vrs,
)


def test_qc_beats_distance_in_ranking() -> None:
    discovery = make_discovery([
        make_candidate("NEAR00NGA", distance_m=10000.0, qc=QCStatus.REJECT),
        make_candidate("FAR00NGA", distance_m=400000.0, qc=QCStatus.ACCEPT),
    ])
    single = assess_single_base(discovery, policy=policy())
    assert single.available is True
    assert single.selected_reference == "FAR00NGA"


def test_distance_orders_survivors() -> None:
    discovery = make_discovery([
        make_candidate("ABFC00NGA", distance_m=470870.0),
        make_candidate("EKAK00NGA", distance_m=105553.0),
        make_candidate("MGBO00NGA", distance_m=1029000.0),
    ])
    single = assess_single_base(discovery, policy=policy())
    assert single.ranked == ("EKAK00NGA", "ABFC00NGA", "MGBO00NGA")
    assert single.selected_reference == "EKAK00NGA"


def test_rover_itself_never_selected() -> None:
    discovery = make_discovery(
        [make_candidate("PHRI00NGA", distance_m=0.0),
         make_candidate("EKAK00NGA", distance_m=105553.0)],
        target_station_id="PHRI00NGA",
    )
    single = assess_single_base(discovery, policy=policy())
    assert single.selected_reference == "EKAK00NGA"


def test_decision_deterministic() -> None:
    kwargs: dict[str, Any] = {
        "spatial": pre_review_spatial(), "vrs": pre_review_vrs(),
        "policy": policy(),
    }
    first, _, _, _ = decide_full(make_request(), make_discovery(), **kwargs)
    second, _, _, _ = decide_full(make_request(), make_discovery(), **kwargs)
    assert first.decision_fingerprint == second.decision_fingerprint
    assert first.decision_id != second.decision_id  # id binds wall-clock time

    def timeless(decision: CorrectionDecision) -> dict[str, Any]:
        payload = decision.as_dict()
        payload["decision_id"] = ""
        payload["timestamp"] = ""
        provenance = dict(decision.provenance)
        provenance["execution_timestamp"] = ""
        payload["provenance"] = provenance
        return payload

    assert timeless(first) == timeless(second)


def test_fingerprint_changes_on_target_change() -> None:
    base = make_discovery()
    moved = make_discovery(target_ecef=(TARGET_ECEF[0] + 1.0, TARGET_ECEF[1], TARGET_ECEF[2]))
    assert decision_fingerprint(
        make_request(), base, spatial=pre_review_spatial(),
        vrs=pre_review_vrs(), policy=policy(),
    ) != decision_fingerprint(
        make_request(), moved, spatial=pre_review_spatial(),
        vrs=pre_review_vrs(), policy=policy(),
    )


def test_fingerprint_changes_on_phase6_change() -> None:
    assert decision_fingerprint(
        make_request(), make_discovery(), spatial=pre_review_spatial(),
        vrs=pre_review_vrs(), policy=policy(),
    ) != decision_fingerprint(
        make_request(), make_discovery(), spatial=approved_spatial(),
        vrs=pre_review_vrs(), policy=policy(),
    )


def test_fingerprint_changes_on_phase7_change() -> None:
    assert decision_fingerprint(
        make_request(), make_discovery(), spatial=pre_review_spatial(),
        vrs=pre_review_vrs(), policy=policy(),
    ) != decision_fingerprint(
        make_request(), make_discovery(), spatial=pre_review_spatial(),
        vrs=approved_vrs(), policy=policy(),
    )


def test_fingerprint_changes_on_qc_change() -> None:
    changed = make_discovery([
        make_candidate("ABFC00NGA", distance_m=470870.0, fingerprint="fp-CHANGED-"),
        make_candidate("EKAK00NGA", distance_m=105553.0),
        make_candidate("MGBO00NGA", distance_m=1029000.0),
    ])
    assert decision_fingerprint(
        make_request(), make_discovery(), spatial=pre_review_spatial(),
        vrs=pre_review_vrs(), policy=policy(),
    ) != decision_fingerprint(
        make_request(), changed, spatial=pre_review_spatial(),
        vrs=pre_review_vrs(), policy=policy(),
    )


def test_diagnostic_mode_watermarked() -> None:
    discovery = make_discovery([
        make_candidate("ABFC00NGA", qc=QCStatus.REJECT),
    ])
    decision, _, _, _ = decide_full(
        make_request(diagnostic=True), discovery, spatial=pre_review_spatial(),
        vrs=pre_review_vrs(), policy=policy(),
    )
    assert decision.mode == CorrectionMode.NO_CORRECTION
    assert decision.status == DecisionStatus.DIAGNOSTIC_ONLY
    assert decision.reason_code == ReasonCode.DIAGNOSTIC_PREVIEW
    assert any("NOT_FOR_OPERATIONAL_CORRECTION" in w for w in decision.warnings)
    assert decision.diagnostic is True


def test_diagnostic_vrs_only_preview_never_operational() -> None:
    decision, _, _, _ = decide_full(
        make_request(desired=DesiredMode.VRS_ONLY, diagnostic=True),
        make_discovery(), spatial=pre_review_spatial(), vrs=pre_review_vrs(),
        policy=policy(),
    )
    assert decision.mode == CorrectionMode.NO_CORRECTION
    assert decision.status == DecisionStatus.DIAGNOSTIC_ONLY


def test_reason_codes_stable_strings() -> None:
    assert ReasonCode.VRS_APPROVED == "VRS_APPROVED"
    assert ReasonCode.VRS_UPSTREAM_REVIEW_PENDING == "VRS_UPSTREAM_REVIEW_PENDING"
    assert ReasonCode.SINGLE_BASE_SELECTED == "SINGLE_BASE_SELECTED"
    assert ReasonCode.NO_ACCEPTABLE_CORRECTION_SOURCE == "NO_ACCEPTABLE_CORRECTION_SOURCE"
    assert ReasonCode.NO_NAVIGATION_PRODUCT == "NO_NAVIGATION_PRODUCT"
    assert ReasonCode.NO_QC_ADMITTED_STATIONS == "NO_QC_ADMITTED_STATIONS"
    assert ReasonCode.INVALID_TARGET_COORDINATE == "INVALID_TARGET_COORDINATE"


def test_malformed_candidate_blocked() -> None:
    try:
        candidate_from_dict({"station_id": "X"})
    except DecisionBlocked as exc:
        assert "malformed station candidate" in str(exc)
    else:
        raise AssertionError("expected DecisionBlocked")


def test_trace_explains_itself() -> None:
    request = make_request()
    discovery = make_discovery()
    decision, network, single, gate = decide_full(
        request, discovery, spatial=pre_review_spatial(), vrs=pre_review_vrs(),
        policy=policy(),
    )
    trace = render_trace(
        request, discovery, network=network, single_base=single,
        vrs_gate=gate, spatial=pre_review_spatial(), vrs=pre_review_vrs(),
        decision=decision, policy=policy(),
    )
    assert "REQUEST" in trace and "DECISION" in trace and "REASON" in trace
    assert "SINGLE_BASE" in trace
    assert "VRS_UPSTREAM_REVIEW_PENDING" in trace or "NOT_VALIDATED" in trace


def test_phase9_handoff_minimal() -> None:
    request = make_request()
    decision, _, _, _ = decide_full(
        request, make_discovery(), spatial=pre_review_spatial(),
        vrs=pre_review_vrs(), policy=policy(),
    )
    handoff = phase9_view(decision, request)
    assert handoff.mode == CorrectionMode.SINGLE_BASE
    assert handoff.reference_station == "EKAK00NGA"
    assert handoff.virtual_station is None
    assert handoff.correction_artifact is None
    payload = handoff.as_dict()
    assert set(payload) == {
        "mode", "source", "reference_station", "virtual_station",
        "correction_artifact", "status", "valid_from", "valid_until",
        "provenance",
    }


def test_provenance_records_upstream_fingerprints() -> None:
    decision, _, _, _ = decide_full(
        make_request(), make_discovery(), spatial=pre_review_spatial(),
        vrs=pre_review_vrs(), policy=policy(),
    )
    provenance = decision.provenance
    assert provenance["phase6_assessment_fingerprint"] == "phase6-pre-review-no-promoted-model"
    assert provenance["phase7_assessment_fingerprint"] == "phase7-pre-review-not-validated"
    assert provenance["policy_version"] == "v1.0"
    assert "decision_fingerprint" in provenance
    assert provenance["decision_engine_version"]
