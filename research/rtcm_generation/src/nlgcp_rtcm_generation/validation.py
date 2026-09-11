"""Transport-level validation for generated lab frames."""

from __future__ import annotations

from dataclasses import dataclass

from nlgcp_rtcm_generation.framing import validate_with_phase9
from nlgcp_rtcm_generation.models import GeneratedCorrectionFrame


@dataclass(frozen=True, slots=True)
class FrameValidation:
    framing_valid: bool
    phase9_compatible: bool
    semantic_validation: str
    findings: tuple[str, ...]


def validate_frame(frame: GeneratedCorrectionFrame) -> FrameValidation:
    ok, findings = validate_with_phase9(frame.raw_bytes, frame.message_number)
    return FrameValidation(
        framing_valid=ok,
        phase9_compatible=ok,
        semantic_validation="NOT_PERFORMED_SYNTHETIC_PAYLOAD",
        findings=findings,
    )
