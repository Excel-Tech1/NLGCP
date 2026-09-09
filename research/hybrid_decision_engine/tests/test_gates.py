"""Tests for fail-closed gates: network, single-base, QC, navigation.

SYNTHETIC TEST DATA — NOT VALID FOR SCIENTIFIC RESULTS.
"""

from __future__ import annotations

from nlgcp_hybrid_decision.decision import decide_full
from nlgcp_hybrid_decision.models import (
    CorrectionMode,
    DecisionStatus,
    QCStatus,
    ReasonCode,
)
from nlgcp_hybrid_decision.network import assess_network
from nlgcp_hybrid_decision.single_base import assess_single_base
from phase8_fixtures import (
    approved_spatial,
    approved_vrs,
    make_candidate,
    make_discovery,
    make_request,
    policy,
    pre_review_spatial,
    pre_review_vrs,
)


def test_network_insufficient_blocks_vrs() -> None:
    discovery = make_discovery([
        make_candidate("EKAK00NGA", distance_m=105553.0),
        make_candidate("ABFC00NGA", distance_m=470870.0),
    ])
    network = assess_network(discovery, policy=policy())
    assert network.eligible is False
    assert any("INSUFFICIENT_REFERENCES" in b for b in network.blockers)
    decision, _, _, gate = decide_full(
        make_request(), discovery, spatial=approved_spatial(),
        vrs=approved_vrs(), policy=policy(), target_leakage_pass=True,
    )
    assert gate.selectable is False
    assert decision.mode == CorrectionMode.SINGLE_BASE


def test_no_qc_admitted_stations_gives_no_correction() -> None:
    discovery = make_discovery([
        make_candidate("ABFC00NGA", qc=QCStatus.REJECT),
        make_candidate("EKAK00NGA", qc=QCStatus.BLOCKED),
    ])
    decision, _, _, _ = decide_full(
        make_request(), discovery, spatial=pre_review_spatial(),
        vrs=pre_review_vrs(), policy=policy(),
    )
    assert decision.mode == CorrectionMode.NO_CORRECTION
    assert decision.reason_code == ReasonCode.NO_QC_ADMITTED_STATIONS
    assert "NO_QC_ADMITTED_STATIONS" in decision.blockers


def test_no_navigation_gives_no_correction() -> None:
    discovery = make_discovery([
        make_candidate("ABFC00NGA", nav=False),
        make_candidate("EKAK00NGA", nav=False),
        make_candidate("MGBO00NGA", nav=False),
    ])
    decision, _, _, _ = decide_full(
        make_request(), discovery, spatial=pre_review_spatial(),
        vrs=pre_review_vrs(), policy=policy(),
    )
    assert decision.mode == CorrectionMode.NO_CORRECTION
    assert decision.reason_code == ReasonCode.NO_NAVIGATION_PRODUCT


def test_warn_never_auto_converts_to_accept() -> None:
    discovery = make_discovery([
        make_candidate("EKAK00NGA", qc=QCStatus.WARN),
        make_candidate("ABFC00NGA", qc=QCStatus.WARN),
        make_candidate("MGBO00NGA", qc=QCStatus.WARN),
    ])
    single = assess_single_base(discovery, policy=policy())
    assert single.available is False
    network = assess_network(discovery, policy=policy())
    assert network.eligible is False
    decision, _, _, _ = decide_full(
        make_request(), discovery, spatial=approved_spatial(),
        vrs=approved_vrs(), policy=policy(), target_leakage_pass=True,
    )
    assert decision.mode == CorrectionMode.NO_CORRECTION
    assert decision.fallback_used is False


def test_single_base_rejected_all_gives_no_correction() -> None:
    discovery = make_discovery([
        make_candidate("ABFC00NGA", qc=QCStatus.REJECT),
        make_candidate("EKAK00NGA", qc=QCStatus.REJECT),
        make_candidate("MGBO00NGA", qc=QCStatus.REJECT),
    ])
    decision, _, _, _ = decide_full(
        make_request(), discovery, spatial=pre_review_spatial(),
        vrs=pre_review_vrs(), policy=policy(),
    )
    assert decision.mode == CorrectionMode.NO_CORRECTION
    # Nothing admitted at all: the global AUTO gate reports first.
    assert decision.reason_code == ReasonCode.NO_QC_ADMITTED_STATIONS


def test_single_base_profile_reject_gives_qc_reason() -> None:
    # Network/single discovery ACCEPT, but the single_base_rtk profile
    # rejects every candidate: the specific single-base QC reason surfaces.
    discovery = make_discovery()
    single_qc = {
        "ABFC00NGA": QCStatus.REJECT,
        "EKAK00NGA": QCStatus.REJECT,
        "MGBO00NGA": QCStatus.REJECT,
    }
    decision, _, _, _ = decide_full(
        make_request(), discovery, spatial=pre_review_spatial(),
        vrs=pre_review_vrs(), policy=policy(), single_qc=single_qc,
    )
    assert decision.mode == CorrectionMode.NO_CORRECTION
    assert decision.reason_code == ReasonCode.SINGLE_BASE_QC_REJECTED


def test_single_base_too_distant_blocked() -> None:
    discovery = make_discovery([
        make_candidate("FAR00NGA", distance_m=5_000_000.0),
    ])
    single = assess_single_base(discovery, policy=policy())
    assert single.available is False
    assert any("TOO_DISTANT" in b for b in single.blockers)
    decision, _, _, _ = decide_full(
        make_request(), discovery, spatial=pre_review_spatial(),
        vrs=pre_review_vrs(), policy=policy(),
    )
    assert decision.mode == CorrectionMode.NO_CORRECTION
    assert decision.reason_code == ReasonCode.SINGLE_BASE_TOO_DISTANT


def test_single_base_degraded_but_allowed() -> None:
    discovery = make_discovery([
        make_candidate("EKAK00NGA", distance_m=105553.0),
    ])
    single = assess_single_base(discovery, policy=policy())
    assert single.available is True
    assert single.distance_band == "preferred"
    far = make_discovery([make_candidate("MGBO00NGA", distance_m=1029000.0)])
    single_far = assess_single_base(far, policy=policy())
    assert single_far.available is True
    assert single_far.distance_band == "maximum"
    assert any("degraded" in w.lower() or "maximum" in w.lower() for w in single_far.warnings)


def test_invalid_target_coordinate_gives_no_correction() -> None:
    discovery = make_discovery(target_ecef=None, target_station_id=None)
    decision, _, _, _ = decide_full(
        make_request(), discovery, spatial=approved_spatial(),
        vrs=approved_vrs(), policy=policy(), target_leakage_pass=True,
    )
    assert decision.mode == CorrectionMode.NO_CORRECTION
    assert decision.reason_code == ReasonCode.INVALID_TARGET_COORDINATE


def test_unverified_coordinate_rejected() -> None:
    discovery = make_discovery([
        make_candidate("EKAK00NGA", coord=False),
        make_candidate("ABFC00NGA", coord=False),
        make_candidate("MGBO00NGA", coord=False),
    ])
    single = assess_single_base(discovery, policy=policy())
    assert single.available is False
    assert all("UNVERIFIED" in r["reason"] for r in single.rejected)


def test_stale_provenance_code_exists() -> None:
    assert ReasonCode.STALE_PROVENANCE == "STALE_PROVENANCE"


def test_no_correction_carries_useful_blockers() -> None:
    discovery = make_discovery([
        make_candidate("ABFC00NGA", nav=False, qc=QCStatus.REJECT),
    ])
    decision, _, _, _ = decide_full(
        make_request(), discovery, spatial=pre_review_spatial(),
        vrs=pre_review_vrs(), policy=policy(),
    )
    assert decision.mode == CorrectionMode.NO_CORRECTION
    assert len(decision.blockers) >= 1
    assert decision.integrity_status == "BLOCKED"
    assert decision.status == DecisionStatus.BLOCKED
