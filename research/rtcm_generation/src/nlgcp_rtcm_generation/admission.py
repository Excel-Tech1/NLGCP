"""Scientific and operational admission gates for Phase 11."""

from __future__ import annotations

from dataclasses import dataclass

from nlgcp_rtcm_generation.models import (
    CorrectionGenerationRequest,
    GenerationMode,
    OutputClassification,
    ReasonCode,
)
from nlgcp_rtcm_generation.registry import MessageFamilyRegistry


@dataclass(frozen=True, slots=True)
class AdmissionDecision:
    admissible: bool
    status: str
    reason_codes: tuple[ReasonCode, ...]


def admit_request(
    request: CorrectionGenerationRequest,
    *,
    registry: MessageFamilyRegistry | None = None,
) -> AdmissionDecision:
    """Return a complete, deterministic gate result without generating bytes."""
    reasons: list[ReasonCode] = []
    if request.mode == GenerationMode.NO_CORRECTION:
        return AdmissionDecision(False, "NO_CORRECTION", (ReasonCode.NO_CORRECTION_REQUESTED,))
    if not request.request_id or not request.decision_id or not request.decision_fingerprint:
        reasons.extend((ReasonCode.PROVENANCE_INCOMPLETE, ReasonCode.MISSING_REQUIRED_FIELD))
    if request.decision_status not in {"OK", "PASS", "ADMISSIBLE"}:
        reasons.append(ReasonCode.DECISION_NOT_ADMISSIBLE)
    if not request.input_source_fingerprint:
        reasons.append(ReasonCode.INPUT_SOURCE_UNAVAILABLE)
    if not request.input_source_admitted:
        reasons.append(ReasonCode.INPUT_SOURCE_UNVERIFIED)
        if request.mode == GenerationMode.SINGLE_BASE:
            reasons.append(ReasonCode.AUTHENTIC_INPUT_SOURCE_UNAVAILABLE)
    if not request.station_identity_verified:
        reasons.append(ReasonCode.STATION_IDENTITY_UNVERIFIED)
    if request.coordinate is None or not request.coordinate_verified:
        reasons.append(ReasonCode.COORDINATE_UNVERIFIED)
    elif request.coordinate.validate():
        reasons.extend((ReasonCode.COORDINATE_UNVERIFIED, ReasonCode.MISSING_REQUIRED_FIELD))
    if request.epoch.gnss_epoch is None:
        reasons.append(ReasonCode.GNSS_EPOCH_UNAVAILABLE)
    if not request.gnss_systems or not request.output_message_family or not request.encoder_version:
        reasons.append(ReasonCode.MISSING_REQUIRED_FIELD)
    if request.mode == GenerationMode.VRS:
        reasons.extend(
            [ReasonCode.VRS_OPERATIONAL_NOT_APPROVED, ReasonCode.CORRECTION_MODEL_NOT_APPROVED]
        )
    elif not request.correction_model_approved:
        reasons.append(ReasonCode.CORRECTION_MODEL_NOT_APPROVED)
    elif not request.correction_model_fingerprint:
        reasons.append(ReasonCode.PROVENANCE_INCOMPLETE)
    if request.classification == OutputClassification.OPERATIONAL_APPROVED:
        reasons.append(ReasonCode.OPERATIONAL_CLASSIFICATION_FORBIDDEN)
    if registry is None:
        registry = MessageFamilyRegistry()
    family = registry.get(request.output_message_family)
    if family is None or family.encoder_key is None:
        reasons.append(ReasonCode.UNSUPPORTED_MESSAGE_TYPE)
    elif request.output_message_family == "SYNTHETIC_TEST_FRAME" and not request.synthetic_fixture:
        reasons.append(ReasonCode.ENCODER_NOT_VALIDATED)
    if reasons:
        return AdmissionDecision(False, "BLOCKED", tuple(dict.fromkeys(reasons)))
    return AdmissionDecision(True, "ADMITTED", ())
