"""Fail-closed request-to-frame orchestration."""

from __future__ import annotations

from nlgcp_rtcm_generation import SCHEMA_VERSION
from nlgcp_rtcm_generation.admission import admit_request
from nlgcp_rtcm_generation.encoder import MessageEncoder, SyntheticMessageEncoder
from nlgcp_rtcm_generation.handoff import CorrectionStreamArtifact
from nlgcp_rtcm_generation.models import (
    CorrectionGenerationContext,
    CorrectionGenerationRequest,
    CorrectionGenerationResult,
    GenerationMode,
    GenerationStatus,
    OutputClassification,
    ReasonCode,
)
from nlgcp_rtcm_generation.provenance import build_provenance, fingerprint
from nlgcp_rtcm_generation.registry import MessageFamilyRegistry


class CorrectionGenerator:
    def __init__(
        self,
        *,
        registry: MessageFamilyRegistry | None = None,
        encoders: dict[str, MessageEncoder] | None = None,
    ) -> None:
        self.registry = registry or MessageFamilyRegistry()
        self.encoders = encoders or {"SYNTHETIC_TEST_FRAME": SyntheticMessageEncoder()}

    def generate(
        self,
        request: CorrectionGenerationRequest,
        *,
        fields: dict[str, object] | None = None,
        observations: tuple[dict[str, object], ...] = (),
    ) -> CorrectionGenerationResult:
        decision = admit_request(request, registry=self.registry)
        provenance = build_provenance(
            request,
            registry_version=SCHEMA_VERSION,
            encoder_version=request.encoder_version,
        )
        if request.mode == GenerationMode.NO_CORRECTION:
            return CorrectionGenerationResult(
                request.request_id,
                request.decision_id,
                GenerationStatus.NO_CORRECTION,
                decision.reason_codes,
                (),
                request.classification,
                provenance,
                request.mode,
                request.reference_station_id,
                request.virtual_station_id,
            )
        if not decision.admissible:
            return CorrectionGenerationResult(
                request.request_id,
                request.decision_id,
                GenerationStatus.BLOCKED,
                decision.reason_codes,
                (),
                request.classification,
                provenance,
                request.mode,
                request.reference_station_id,
                request.virtual_station_id,
            )
        encoder = self.encoders.get(request.output_message_family)
        if encoder is None:
            return CorrectionGenerationResult(
                request.request_id,
                request.decision_id,
                GenerationStatus.BLOCKED,
                (ReasonCode.ENCODER_NOT_VALIDATED,),
                (),
                request.classification,
                provenance,
                request.mode,
                request.reference_station_id,
                request.virtual_station_id,
            )
        try:
            frame = encoder.encode(
                CorrectionGenerationContext(
                    request=request,
                    fields=fields or {},
                    observations=observations,
                )
            )
        except (ValueError, RuntimeError) as exc:
            reason = (
                ReasonCode.OUT_OF_RANGE_FIELD
                if "fit" in str(exc) or "range" in str(exc)
                else ReasonCode.ENCODER_NOT_VALIDATED
            )
            return CorrectionGenerationResult(
                request.request_id,
                request.decision_id,
                GenerationStatus.BLOCKED,
                (reason,),
                (),
                request.classification,
                {**provenance, "encoder_error": type(exc).__name__},
                request.mode,
                request.reference_station_id,
                request.virtual_station_id,
            )
        return CorrectionGenerationResult(
            request.request_id,
            request.decision_id,
            GenerationStatus.ENCODED,
            (),
            (frame,),
            request.classification,
            provenance,
            request.mode,
            request.reference_station_id,
            request.virtual_station_id,
        )

    def handoff(self, result: CorrectionGenerationResult) -> CorrectionStreamArtifact:
        request_family = result.frames[0].message_family if result.frames else ""
        provenance_fp = fingerprint(result.provenance)
        return CorrectionStreamArtifact(
            schema_version=SCHEMA_VERSION,
            stream_id=f"phase11-{result.request_id}",
            decision_id=result.decision_id,
            mode=str(result.mode),
            station_id=result.reference_station_id,
            virtual_station_id=result.virtual_station_id,
            message_families=(request_family,) if request_family else (),
            generation_status=str(result.status),
            frame_source="research-scaffold",
            validity_start=None,
            validity_end=None,
            classification=str(result.classification),
            provenance_fingerprint=provenance_fp,
        )
