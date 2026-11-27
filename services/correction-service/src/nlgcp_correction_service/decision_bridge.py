"""Phase 8 -> Phase 11 runtime decision bridge (B-08 / Day 7 BE-01 remediation).

Programmatically maps a Phase 8 ``CorrectionDecision`` (or ``CorrectionDecisionPhase9``)
into a Phase 11 ``CorrectionGenerationRequest`` without recalculating science or
bypassing any fail-closed admission gate.

Hard scientific & safety invariants (ADR-011, ADR-012):
- ``OPERATIONAL_APPROVED`` is unconditionally rejected;
- A Phase 8 ``VRS`` decision is faithfully mapped to ``GenerationMode.VRS``,
  which Phase 11 ``admit_request()`` continues to block fail-closed
  (``VRS_OPERATIONAL_NOT_APPROVED``);
- A Phase 8 ``NO_CORRECTION`` or ``BLOCKED`` decision maps fail-closed to
  ``GenerationMode.NO_CORRECTION`` or non-admissible status;
- Authentic decisions without an admitted live input stream remain honestly
  blocked (``input_source_admitted=False`` -> ``AUTHENTIC_INPUT_SOURCE_UNAVAILABLE``);
- Synthetic lab fixture execution requires explicit ``synthetic_fixture=True``
  and ``SYNTHETIC_TEST_ONLY`` coordinate verification state.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from nlgcp_hybrid_decision.models import (
    CorrectionDecision,
    CorrectionMode,
    DecisionStatus,
)
from nlgcp_rtcm_generation.generator import CorrectionGenerator
from nlgcp_rtcm_generation.models import (
    CoordinateProvenance,
    CorrectionGenerationRequest,
    CorrectionGenerationResult,
    EpochContract,
    GenerationMode,
    OutputClassification,
    VerificationState,
)
from nlgcp_rtcm_generation.provenance import fingerprint


class DecisionBridgeError(ValueError):
    """Raised when a bridge invocation attempts to violate fail-closed invariants."""


@dataclass(frozen=True, slots=True)
class BridgeInputContext:
    """Explicit runtime provenance supplied alongside a Phase 8 decision."""

    gnss_epoch: str | None
    coordinate: CoordinateProvenance | None
    output_message_family: str
    encoder_version: str
    gnss_systems: tuple[str, ...] = ("GPS",)
    input_source_fingerprint: str = ""
    input_source_admitted: bool = False
    station_identity_verified: bool = False
    coordinate_verified: bool = False
    correction_model_fingerprint: str | None = None
    correction_model_approved: bool = False
    classification: OutputClassification = OutputClassification.DIAGNOSTIC_ONLY
    synthetic_fixture: bool = False
    source_arrival_time: str | None = None


def map_decision_mode(mode: CorrectionMode) -> GenerationMode:
    if mode == CorrectionMode.VRS:
        return GenerationMode.VRS
    if mode == CorrectionMode.SINGLE_BASE:
        return GenerationMode.SINGLE_BASE
    return GenerationMode.NO_CORRECTION


def map_decision_status(status: DecisionStatus) -> str:
    if status == DecisionStatus.OK:
        return "OK"
    if status == DecisionStatus.DEGRADED:
        return "DEGRADED"
    if status == DecisionStatus.DIAGNOSTIC_ONLY:
        return "DIAGNOSTIC_ONLY"
    return "BLOCKED"


def decision_to_generation_request(
    decision: CorrectionDecision,
    context: BridgeInputContext,
    *,
    request_id_suffix: str = "phase11",
) -> CorrectionGenerationRequest:
    """Translate a Phase 8 ``CorrectionDecision`` into a Phase 11 request fail-closed."""
    if context.classification == OutputClassification.OPERATIONAL_APPROVED:
        raise DecisionBridgeError(
            "OPERATIONAL_APPROVED classification is forbidden in the Phase 8 -> Phase 11 bridge"
        )
    gen_mode = map_decision_mode(decision.mode)
    decision_fp = decision.decision_fingerprint or fingerprint(decision.as_dict())
    dec_status = map_decision_status(decision.status)
    if decision.diagnostic:
        dec_status = "DIAGNOSTIC_ONLY"

    # Never upgrade unverified coordinates or authentic un-admitted streams.
    coord_verified = (
        context.coordinate_verified
        and context.coordinate is not None
        and context.coordinate.verification_state
        in (VerificationState.VERIFIED, VerificationState.SYNTHETIC_TEST_ONLY)
    )
    scientific_status = (
        "SYNTHETIC_TEST_ONLY"
        if context.synthetic_fixture
        and context.classification == OutputClassification.SYNTHETIC_TEST_ONLY
        else f"PHASE8_{decision.mode}_{decision.status}_{decision.reason_code}"
    )
    return CorrectionGenerationRequest(
        request_id=f"{decision.request_id}:{request_id_suffix}",
        decision_id=decision.decision_id,
        decision_fingerprint=decision_fp,
        decision_status=dec_status,
        mode=gen_mode,
        reference_station_id=decision.selected_reference,
        virtual_station_id=(
            decision.selected_vrs_experiment if gen_mode == GenerationMode.VRS else None
        ),
        coordinate=context.coordinate,
        epoch=EpochContract(
            gnss_epoch=context.gnss_epoch,
            source_arrival_time=context.source_arrival_time,
        ),
        gnss_systems=context.gnss_systems,
        input_source_fingerprint=context.input_source_fingerprint,
        input_source_admitted=context.input_source_admitted,
        station_identity_verified=context.station_identity_verified,
        coordinate_verified=coord_verified,
        correction_model_fingerprint=context.correction_model_fingerprint,
        correction_model_approved=(
            False if gen_mode == GenerationMode.VRS else context.correction_model_approved
        ),
        output_message_family=context.output_message_family,
        encoder_version=context.encoder_version,
        scientific_status=scientific_status,
        classification=context.classification,
        synthetic_fixture=context.synthetic_fixture,
    )


def execute_decision_to_rtcm(
    decision: CorrectionDecision,
    context: BridgeInputContext,
    *,
    fields: dict[str, Any] | None = None,
    observations: tuple[dict[str, Any], ...] = (),
    generator: CorrectionGenerator | None = None,
) -> tuple[CorrectionGenerationRequest, CorrectionGenerationResult]:
    """Map Phase 8 decision to Phase 11 request and run fail-closed generation."""
    request = decision_to_generation_request(decision, context)
    gen = generator or CorrectionGenerator()
    result = gen.generate(request, fields=fields, observations=observations)
    return request, result
