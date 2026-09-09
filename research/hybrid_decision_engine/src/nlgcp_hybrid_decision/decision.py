"""Decision orchestration (Phase 8).

Priority: validated VRS -> acceptable single-base fallback -> no correction.

Fail-closed: any missing mandatory dependency yields NO_CORRECTION (or a
BLOCKED / DIAGNOSTIC_ONLY status) with machine-readable blockers.  WARN
is never auto-converted to ACCEPT.  Scientific requirements are never
silently downgraded.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Any

from nlgcp_hybrid_decision import ENGINE_VERSION
from nlgcp_hybrid_decision.discovery import DiscoveryResult
from nlgcp_hybrid_decision.integrity import derive_integrity
from nlgcp_hybrid_decision.models import (
    CorrectionDecision,
    CorrectionMode,
    DecisionRequest,
    DecisionStatus,
    DesiredMode,
    IntegrityStatus,
    QCStatus,
    ReasonCode,
    SpatialCorrectionAssessment,
    VRSCapabilityAssessment,
)
from nlgcp_hybrid_decision.network import NetworkAssessment, assess_network
from nlgcp_hybrid_decision.policy import DecisionPolicy
from nlgcp_hybrid_decision.provenance import (
    build_provenance,
    decision_fingerprint,
)
from nlgcp_hybrid_decision.single_base import SingleBaseAssessment, assess_single_base
from nlgcp_hybrid_decision.vrs import VRSAssessment, assess_vrs


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def decide(
    request: DecisionRequest,
    discovery: DiscoveryResult,
    *,
    network: NetworkAssessment,
    single_base: SingleBaseAssessment,
    vrs_gate: VRSAssessment,
    spatial: SpatialCorrectionAssessment,
    vrs: VRSCapabilityAssessment,
    policy: DecisionPolicy,
    execution_timestamp: str | None = None,
    git_commit: str = "recorded-at-runtime",
    single_qc_summary: str = "",
) -> CorrectionDecision:
    """Combine gate outcomes into the final fail-closed decision."""
    request.assert_valid()
    timestamp = execution_timestamp or utc_now_iso()
    decision_id = _decision_id(request.request_id, timestamp)
    provenance = build_provenance(
        request,
        discovery,
        spatial=spatial,
        vrs=vrs,
        policy=policy,
        execution_timestamp=timestamp,
        git_commit=git_commit,
    )
    fingerprint = decision_fingerprint(
        request, discovery, spatial=spatial, vrs=vrs, policy=policy
    )
    provenance["decision_fingerprint"] = fingerprint

    candidates = tuple(sorted(c.station_id for c in discovery.candidates))
    qc_summary = single_qc_summary or _qc_summary(discovery)

    if discovery.target_ecef_m is None:
        return _no_correction(
            decision_id=decision_id,
            request=request,
            timestamp=timestamp,
            reason_code=ReasonCode.INVALID_TARGET_COORDINATE,
            reason_text=(
                "No verified target coordinate: supply explicit target_ecef or a "
                "verified target_station_id; coordinates are never invented"
            ),
            discovery=discovery,
            network=network,
            spatial=spatial,
            vrs=vrs,
            provenance=provenance,
            fingerprint=fingerprint,
            candidates=candidates,
            qc_summary=qc_summary,
            blockers=("INVALID_TARGET_COORDINATE",),
            warnings=tuple(discovery.warnings),
        )

    admitted_any = any(c.qc_status == QCStatus.ACCEPT for c in discovery.candidates)

    # Route by requested mode.  Mode-specific branches own the
    # NO_QC / NO_NAV gates so each mode reports its most specific reason
    # code (VRS_ONLY reports the VRS gate; SINGLE_BASE_ONLY reports the
    # single-base assessment); AUTO applies the global gates first.
    if request.desired_mode == DesiredMode.VRS_ONLY:
        return _decide_vrs_only(
            decision_id=decision_id,
            request=request,
            timestamp=timestamp,
            discovery=discovery,
            network=network,
            vrs_gate=vrs_gate,
            spatial=spatial,
            vrs=vrs,
            policy=policy,
            provenance=provenance,
            fingerprint=fingerprint,
            candidates=candidates,
            qc_summary=qc_summary,
            admitted_any=admitted_any,
        )
    if request.desired_mode == DesiredMode.SINGLE_BASE_ONLY:
        return _decide_single_only(
            decision_id=decision_id,
            request=request,
            timestamp=timestamp,
            discovery=discovery,
            network=network,
            single_base=single_base,
            spatial=spatial,
            vrs=vrs,
            policy=policy,
            provenance=provenance,
            fingerprint=fingerprint,
            candidates=candidates,
            qc_summary=qc_summary,
        )
    return _decide_auto(
        decision_id=decision_id,
        request=request,
        timestamp=timestamp,
        discovery=discovery,
        network=network,
        single_base=single_base,
        vrs_gate=vrs_gate,
        spatial=spatial,
        vrs=vrs,
        policy=policy,
        provenance=provenance,
        fingerprint=fingerprint,
        candidates=candidates,
        qc_summary=qc_summary,
    )


def decide_full(
    request: DecisionRequest,
    discovery: DiscoveryResult,
    *,
    spatial: SpatialCorrectionAssessment,
    vrs: VRSCapabilityAssessment,
    policy: DecisionPolicy,
    single_qc: dict[str, QCStatus] | None = None,
    target_leakage_pass: bool | None = None,
    provenance_pass: bool = True,
    execution_timestamp: str | None = None,
    git_commit: str = "recorded-at-runtime",
) -> tuple[CorrectionDecision, NetworkAssessment, SingleBaseAssessment, VRSAssessment]:
    """Run discovery-level gates then orchestrate (convenience entry point)."""
    network = assess_network(discovery, policy=policy)
    single_base = assess_single_base(discovery, policy=policy, single_qc=single_qc)
    vrs_gate = assess_vrs(
        network,
        spatial=spatial,
        vrs=vrs,
        policy=policy,
        target_leakage_pass=target_leakage_pass,
        provenance_pass=provenance_pass,
    )
    decision = decide(
        request,
        discovery,
        network=network,
        single_base=single_base,
        vrs_gate=vrs_gate,
        spatial=spatial,
        vrs=vrs,
        policy=policy,
        execution_timestamp=execution_timestamp,
        git_commit=git_commit,
    )
    return (decision, network, single_base, vrs_gate)


def _decide_auto(
    *,
    decision_id: str,
    request: DecisionRequest,
    timestamp: str,
    discovery: DiscoveryResult,
    network: NetworkAssessment,
    single_base: SingleBaseAssessment,
    vrs_gate: VRSAssessment,
    spatial: SpatialCorrectionAssessment,
    vrs: VRSCapabilityAssessment,
    policy: DecisionPolicy,
    provenance: dict[str, Any],
    fingerprint: str,
    candidates: tuple[str, ...],
    qc_summary: str,
) -> CorrectionDecision:
    warnings = list(discovery.warnings)
    # 0. Global fail-closed gates for AUTO (mode branches below own theirs).
    admitted_any = any(c.qc_status == QCStatus.ACCEPT for c in discovery.candidates)
    nav_any = any(c.navigation_available for c in discovery.candidates)
    if not admitted_any:
        blockers = ("NO_QC_ADMITTED_STATIONS", *network.blockers)
        if request.diagnostic and policy.diagnostic_preview_enabled:
            return _diagnostic_preview(
                decision_id=decision_id, request=request, timestamp=timestamp,
                discovery=discovery, network=network, single_base=single_base,
                vrs_gate=vrs_gate, spatial=spatial, vrs=vrs,
                provenance=provenance, fingerprint=fingerprint,
                candidates=candidates, qc_summary=qc_summary,
                warnings=tuple(warnings), blockers=blockers, note="",
            )
        return _no_correction(
            decision_id=decision_id, request=request, timestamp=timestamp,
            reason_code=ReasonCode.NO_QC_ADMITTED_STATIONS,
            reason_text="No Phase 4 QC-admitted stations for the requested day",
            discovery=discovery, network=network, spatial=spatial, vrs=vrs,
            provenance=provenance, fingerprint=fingerprint,
            candidates=candidates, qc_summary=qc_summary,
            blockers=blockers, warnings=tuple(warnings),
        )
    if not nav_any:
        blockers = ("NO_NAVIGATION_PRODUCT",)
        if request.diagnostic and policy.diagnostic_preview_enabled:
            return _diagnostic_preview(
                decision_id=decision_id, request=request, timestamp=timestamp,
                discovery=discovery, network=network, single_base=single_base,
                vrs_gate=vrs_gate, spatial=spatial, vrs=vrs,
                provenance=provenance, fingerprint=fingerprint,
                candidates=candidates, qc_summary=qc_summary,
                warnings=tuple(warnings), blockers=blockers, note="",
            )
        return _no_correction(
            decision_id=decision_id, request=request, timestamp=timestamp,
            reason_code=ReasonCode.NO_NAVIGATION_PRODUCT,
            reason_text="No candidate station carries a navigation product",
            discovery=discovery, network=network, spatial=spatial, vrs=vrs,
            provenance=provenance, fingerprint=fingerprint,
            candidates=candidates, qc_summary=qc_summary,
            blockers=blockers, warnings=tuple(warnings),
        )
    # 1. Validated VRS.
    if vrs_gate.selectable:
        status = DecisionStatus.DIAGNOSTIC_ONLY if request.diagnostic else DecisionStatus.OK
        integrity = derive_integrity(
            mode=CorrectionMode.VRS, status=status,
            warnings=tuple(warnings), blockers=(), fallback_used=False,
        )
        return CorrectionDecision(
            decision_id=decision_id,
            request_id=request.request_id,
            timestamp=timestamp,
            mode=CorrectionMode.VRS,
            status=status,
            reason_code=ReasonCode.VRS_APPROVED,
            reason_text=vrs_gate.reason_text,
            selected_reference=None,
            selected_network=network.admitted_references,
            selected_vrs_experiment=vrs_gate.experiment_id,
            candidate_references=candidates,
            distance_to_selected_reference_m=None,
            network_station_count=network.admitted_count,
            network_geometry_status=network.geometry_status,
            qc_status=qc_summary,
            spatial_model_status=spatial.validation_status,
            vrs_status=vrs.status,
            integrity_status=integrity,
            provenance=provenance,
            fallback_used=False,
            warnings=tuple(warnings),
            blockers=(),
            decision_fingerprint=fingerprint,
            diagnostic=request.diagnostic,
        )
    vrs_blockers = tuple(vrs_gate.blockers)
    warnings.extend(vrs_gate.warnings)
    # 2. Single-base fallback (if permitted).
    if policy.single_base_fallback_enabled and request.allow_fallback and single_base.available:
        degraded = single_base.distance_band in ("degraded", "maximum", "unknown")
        status = DecisionStatus.DEGRADED if degraded else DecisionStatus.OK
        if request.diagnostic:
            status = DecisionStatus.DIAGNOSTIC_ONLY
        integrity = derive_integrity(
            mode=CorrectionMode.SINGLE_BASE, status=status,
            warnings=tuple([*warnings, *single_base.warnings]),
            blockers=(), fallback_used=True,
            distance_band=single_base.distance_band,
        )
        reason_text = (
            f"SINGLE_BASE fallback {single_base.selected_reference} "
            f"({(single_base.distance_m or 0.0) / 1000.0:.3f} km, "
            f"band {single_base.distance_band} PROVISIONAL); VRS blocked: "
            f"{vrs_gate.reason_code}; no centimetre accuracy claimed"
        )
        return CorrectionDecision(
            decision_id=decision_id,
            request_id=request.request_id,
            timestamp=timestamp,
            mode=CorrectionMode.SINGLE_BASE,
            status=status,
            reason_code=ReasonCode.SINGLE_BASE_SELECTED,
            reason_text=reason_text,
            selected_reference=single_base.selected_reference,
            selected_network=network.admitted_references,
            selected_vrs_experiment=None,
            candidate_references=candidates,
            distance_to_selected_reference_m=single_base.distance_m,
            network_station_count=network.admitted_count,
            network_geometry_status=network.geometry_status,
            qc_status=qc_summary,
            spatial_model_status=spatial.validation_status,
            vrs_status=vrs.status,
            integrity_status=integrity,
            provenance=provenance,
            fallback_used=True,
            warnings=tuple([*warnings, *single_base.warnings]),
            blockers=vrs_blockers,
            decision_fingerprint=fingerprint,
            diagnostic=request.diagnostic,
        )
    # 3. No correction (fail closed).
    fallback_note = ""
    if not policy.single_base_fallback_enabled or not request.allow_fallback:
        fallback_note = "fallback disabled; "
    blockers = (*vrs_blockers, *single_base.blockers)
    code = _no_correction_code(single_base, discovery)
    if request.diagnostic and policy.diagnostic_preview_enabled:
        return _diagnostic_preview(
            decision_id=decision_id, request=request, timestamp=timestamp,
            discovery=discovery, network=network, single_base=single_base,
            vrs_gate=vrs_gate, spatial=spatial, vrs=vrs, provenance=provenance,
            fingerprint=fingerprint, candidates=candidates, qc_summary=qc_summary,
            warnings=tuple(warnings), blockers=blockers,
            note=fallback_note,
        )
    return _no_correction(
        decision_id=decision_id, request=request, timestamp=timestamp,
        reason_code=code,
        reason_text=(
            f"{fallback_note}no acceptable correction source: "
            f"VRS {vrs_gate.reason_code}; single-base unavailable "
            f"({'; '.join(single_base.blockers) or 'no candidate'})"
        ),
        discovery=discovery, network=network, spatial=spatial, vrs=vrs,
        provenance=provenance, fingerprint=fingerprint, candidates=candidates,
        qc_summary=qc_summary, blockers=blockers,
        warnings=tuple([*warnings, *single_base.warnings]),
    )


def _decide_vrs_only(
    *,
    decision_id: str,
    request: DecisionRequest,
    timestamp: str,
    discovery: DiscoveryResult,
    network: NetworkAssessment,
    vrs_gate: VRSAssessment,
    spatial: SpatialCorrectionAssessment,
    vrs: VRSCapabilityAssessment,
    policy: DecisionPolicy,
    provenance: dict[str, Any],
    fingerprint: str,
    candidates: tuple[str, ...],
    qc_summary: str,
    admitted_any: bool = True,
) -> CorrectionDecision:
    _ = policy
    warnings = tuple([*discovery.warnings, *vrs_gate.warnings])
    if not admitted_any:
        blockers = ("NO_QC_ADMITTED_STATIONS", *vrs_gate.blockers)
        if request.diagnostic:
            return _diagnostic_preview(
                decision_id=decision_id, request=request, timestamp=timestamp,
                discovery=discovery, network=network,
                single_base=None, vrs_gate=vrs_gate, spatial=spatial, vrs=vrs,
                provenance=provenance, fingerprint=fingerprint,
                candidates=candidates, qc_summary=qc_summary,
                warnings=warnings, blockers=blockers, note="VRS_ONLY; ",
            )
        return _no_correction(
            decision_id=decision_id, request=request, timestamp=timestamp,
            reason_code=ReasonCode.NO_QC_ADMITTED_STATIONS,
            reason_text=(
                "VRS_ONLY requested but no Phase 4 QC-admitted stations; "
                "no fallback permitted under VRS_ONLY"
            ),
            discovery=discovery, network=network, spatial=spatial, vrs=vrs,
            provenance=provenance, fingerprint=fingerprint, candidates=candidates,
            qc_summary=qc_summary, blockers=blockers, warnings=warnings,
        )
    if vrs_gate.selectable and not request.diagnostic:
        integrity = derive_integrity(
            mode=CorrectionMode.VRS, status=DecisionStatus.OK,
            warnings=warnings, blockers=(), fallback_used=False,
        )
        return CorrectionDecision(
            decision_id=decision_id, request_id=request.request_id, timestamp=timestamp,
            mode=CorrectionMode.VRS, status=DecisionStatus.OK,
            reason_code=ReasonCode.VRS_APPROVED, reason_text=vrs_gate.reason_text,
            selected_network=network.admitted_references,
            selected_vrs_experiment=vrs_gate.experiment_id,
            candidate_references=candidates,
            network_station_count=network.admitted_count,
            network_geometry_status=network.geometry_status,
            qc_status=qc_summary,
            spatial_model_status=spatial.validation_status,
            vrs_status=vrs.status, integrity_status=integrity,
            provenance=provenance, fallback_used=False,
            warnings=warnings, blockers=(),
            decision_fingerprint=fingerprint, diagnostic=request.diagnostic,
        )
    if request.diagnostic:
        preview = _diagnostic_preview(
            decision_id=decision_id, request=request, timestamp=timestamp,
            discovery=discovery, network=network,
            single_base=None, vrs_gate=vrs_gate, spatial=spatial, vrs=vrs,
            provenance=provenance, fingerprint=fingerprint,
            candidates=candidates, qc_summary=qc_summary,
            warnings=warnings, blockers=tuple(vrs_gate.blockers), note="VRS_ONLY; ",
        )
        return preview
    return _no_correction(
        decision_id=decision_id, request=request, timestamp=timestamp,
        reason_code=ReasonCode.VRS_MODE_NOT_PERMITTED
        if vrs_gate.selectable and request.diagnostic
        else vrs_gate.reason_code,
        reason_text=(
            f"VRS_ONLY requested but VRS not selectable: {vrs_gate.reason_code}; "
            "no fallback permitted under VRS_ONLY"
        ),
        discovery=discovery, network=network, spatial=spatial, vrs=vrs,
        provenance=provenance, fingerprint=fingerprint, candidates=candidates,
        qc_summary=qc_summary, blockers=tuple(vrs_gate.blockers), warnings=warnings,
    )


def _decide_single_only(
    *,
    decision_id: str,
    request: DecisionRequest,
    timestamp: str,
    discovery: DiscoveryResult,
    network: NetworkAssessment,
    single_base: SingleBaseAssessment,
    spatial: SpatialCorrectionAssessment,
    vrs: VRSCapabilityAssessment,
    policy: DecisionPolicy,
    provenance: dict[str, Any],
    fingerprint: str,
    candidates: tuple[str, ...],
    qc_summary: str,
) -> CorrectionDecision:
    _ = policy
    warnings = tuple([*discovery.warnings, *single_base.warnings])
    if single_base.available:
        degraded = single_base.distance_band in ("degraded", "maximum", "unknown")
        status = DecisionStatus.DEGRADED if degraded else DecisionStatus.OK
        if request.diagnostic:
            status = DecisionStatus.DIAGNOSTIC_ONLY
        integrity = derive_integrity(
            mode=CorrectionMode.SINGLE_BASE, status=status,
            warnings=warnings, blockers=(), fallback_used=False,
            distance_band=single_base.distance_band,
        )
        return CorrectionDecision(
            decision_id=decision_id, request_id=request.request_id, timestamp=timestamp,
            mode=CorrectionMode.SINGLE_BASE, status=status,
            reason_code=ReasonCode.SINGLE_BASE_SELECTED,
            reason_text=(
                f"SINGLE_BASE_ONLY: {single_base.selected_reference} "
                f"({(single_base.distance_m or 0.0) / 1000.0:.3f} km, "
                f"band {single_base.distance_band}); VRS never considered"
            ),
            selected_reference=single_base.selected_reference,
            selected_network=network.admitted_references,
            candidate_references=candidates,
            distance_to_selected_reference_m=single_base.distance_m,
            network_station_count=network.admitted_count,
            network_geometry_status=network.geometry_status,
            qc_status=qc_summary,
            spatial_model_status=spatial.validation_status,
            vrs_status=vrs.status, integrity_status=integrity,
            provenance=provenance, fallback_used=False,
            warnings=warnings, blockers=(),
            decision_fingerprint=fingerprint, diagnostic=request.diagnostic,
        )
    if request.diagnostic:
        return _diagnostic_preview(
            decision_id=decision_id, request=request, timestamp=timestamp,
            discovery=discovery, network=network, single_base=single_base,
            vrs_gate=None, spatial=spatial, vrs=vrs, provenance=provenance,
            fingerprint=fingerprint, candidates=candidates, qc_summary=qc_summary,
            warnings=warnings,
            blockers=tuple(single_base.blockers),
            note="SINGLE_BASE_ONLY; ",
        )
    return _no_correction(
        decision_id=decision_id, request=request, timestamp=timestamp,
        reason_code=_no_correction_code(single_base, discovery),
        reason_text=(
            "SINGLE_BASE_ONLY requested but no acceptable physical reference: "
            f"{'; '.join(single_base.blockers) or 'no candidate'}; VRS never considered"
        ),
        discovery=discovery, network=network, spatial=spatial, vrs=vrs,
        provenance=provenance, fingerprint=fingerprint, candidates=candidates,
        qc_summary=qc_summary, blockers=tuple(single_base.blockers),
        warnings=warnings,
    )


def _no_correction_code(
    single_base: SingleBaseAssessment, discovery: DiscoveryResult
) -> ReasonCode:
    joined = " ".join([*single_base.blockers, *[r.get("reason", "") for r in single_base.rejected]])
    if "NAVIGATION" in joined:
        return ReasonCode.SINGLE_BASE_NAVIGATION_MISSING
    if "TOO_DISTANT" in joined:
        return ReasonCode.SINGLE_BASE_TOO_DISTANT
    if "QC" in joined:
        return ReasonCode.SINGLE_BASE_QC_REJECTED
    if discovery.candidates and not any(c.navigation_available for c in discovery.candidates):
        return ReasonCode.NO_NAVIGATION_PRODUCT
    return ReasonCode.NO_ACCEPTABLE_CORRECTION_SOURCE


def _no_correction(
    *,
    decision_id: str,
    request: DecisionRequest,
    timestamp: str,
    reason_code: ReasonCode,
    reason_text: str,
    discovery: DiscoveryResult,
    network: NetworkAssessment,
    spatial: SpatialCorrectionAssessment,
    vrs: VRSCapabilityAssessment,
    provenance: dict[str, Any],
    fingerprint: str,
    candidates: tuple[str, ...],
    qc_summary: str,
    blockers: tuple[str, ...],
    warnings: tuple[str, ...] = (),
) -> CorrectionDecision:
    status = DecisionStatus.DIAGNOSTIC_ONLY if request.diagnostic else DecisionStatus.BLOCKED
    integrity = IntegrityStatus.BLOCKED
    return CorrectionDecision(
        decision_id=decision_id, request_id=request.request_id, timestamp=timestamp,
        mode=CorrectionMode.NO_CORRECTION, status=status,
        reason_code=reason_code, reason_text=reason_text,
        candidate_references=candidates,
        network_station_count=network.admitted_count,
        network_geometry_status=network.geometry_status,
        qc_status=qc_summary,
        spatial_model_status=spatial.validation_status,
        vrs_status=vrs.status, integrity_status=integrity,
        provenance=provenance, fallback_used=False,
        warnings=warnings, blockers=blockers,
        decision_fingerprint=fingerprint, diagnostic=request.diagnostic,
    )


def _diagnostic_preview(
    *,
    decision_id: str,
    request: DecisionRequest,
    timestamp: str,
    discovery: DiscoveryResult,
    network: NetworkAssessment,
    single_base: SingleBaseAssessment | None,
    vrs_gate: VRSAssessment | None,
    spatial: SpatialCorrectionAssessment,
    vrs: VRSCapabilityAssessment,
    provenance: dict[str, Any],
    fingerprint: str,
    candidates: tuple[str, ...],
    qc_summary: str,
    warnings: tuple[str, ...],
    blockers: tuple[str, ...],
    note: str,
) -> CorrectionDecision:
    _ = single_base
    preview_warnings = (
        *warnings,
        "DIAGNOSTIC_ONLY: preview of unvalidated candidates; NOT_FOR_OPERATIONAL_CORRECTION",
    )
    experiment = vrs_gate.experiment_id if vrs_gate else (vrs.experiment_id or None)
    return CorrectionDecision(
        decision_id=decision_id, request_id=request.request_id, timestamp=timestamp,
        mode=CorrectionMode.NO_CORRECTION, status=DecisionStatus.DIAGNOSTIC_ONLY,
        reason_code=ReasonCode.DIAGNOSTIC_PREVIEW,
        reason_text=(
            f"{note}diagnostic preview only (NOT_FOR_OPERATIONAL_CORRECTION): "
            f"VRS {vrs.status}/{spatial.validation_status}, "
            f"network {network.admitted_count} refs {network.geometry_status}"
        ),
        selected_network=network.admitted_references,
        selected_vrs_experiment=experiment,
        candidate_references=candidates,
        network_station_count=network.admitted_count,
        network_geometry_status=network.geometry_status,
        qc_status=qc_summary,
        spatial_model_status=spatial.validation_status,
        vrs_status=vrs.status,
        integrity_status=IntegrityStatus.BLOCKED,
        provenance=provenance, fallback_used=False,
        warnings=preview_warnings, blockers=blockers,
        decision_fingerprint=fingerprint, diagnostic=True,
    )


def _decision_id(request_id: str, timestamp: str) -> str:
    digest = hashlib.sha256(f"{request_id}|{timestamp}|{ENGINE_VERSION}".encode()).hexdigest()
    return f"dec-{digest[:12]}"


def _qc_summary(discovery: DiscoveryResult) -> str:
    accepted = sorted(c.station_id for c in discovery.candidates if c.qc_status == QCStatus.ACCEPT)
    if accepted:
        return f"ACCEPT:{','.join(accepted)}"
    return "NO_ACCEPT"
