"""Encoder boundary for the synthetic lab payload and RTCM 1005/MSM4."""

from __future__ import annotations

import hashlib
import json
from typing import Protocol

from nlgcp_rtcm_generation import (
    ENCODER_VERSION,
    ENCODER_VERSION_1005,
    ENCODER_VERSION_MSM4,
)
from nlgcp_rtcm_generation.framing import (
    frame_message_payload,
    frame_metadata,
    frame_payload,
)
from nlgcp_rtcm_generation.messages import (
    MESSAGE_NUMBER_1005,
    MESSAGE_NUMBER_1074,
    MESSAGE_NUMBER_1084,
    Msm4Message,
    MsmSystem,
    ReferenceStation1005,
)
from nlgcp_rtcm_generation.models import (
    CorrectionGenerationContext,
    GeneratedCorrectionFrame,
    OutputClassification,
)
from nlgcp_rtcm_generation.provenance import request_fingerprint


class MessageEncoder(Protocol):
    family_id: str
    encoder_version: str

    def encode(self, context: CorrectionGenerationContext) -> GeneratedCorrectionFrame: ...


class UnsupportedEncoderError(RuntimeError):
    pass


def _require_synthetic_context(
    context: CorrectionGenerationContext, encoder_version: str
) -> None:
    request = context.request
    if request.classification != OutputClassification.SYNTHETIC_TEST_ONLY:
        raise UnsupportedEncoderError("RTCM encoders require SYNTHETIC_TEST_ONLY output")
    if not request.synthetic_fixture:
        raise UnsupportedEncoderError("RTCM encoders require an explicit synthetic fixture")
    if request.encoder_version != encoder_version:
        raise UnsupportedEncoderError(
            f"request encoder_version {request.encoder_version!r} does not match "
            f"{encoder_version!r}"
        )


def _build_frame(
    context: CorrectionGenerationContext,
    *,
    family_id: str,
    message_number: int,
    encoder_version: str,
    payload: bytes,
) -> GeneratedCorrectionFrame:
    frame = frame_message_payload(payload)
    metadata = frame_metadata(frame)
    request = context.request
    return GeneratedCorrectionFrame(
        message_family=family_id,
        message_number=message_number,
        payload_length=int(metadata["payload_length"]),
        frame_length=int(metadata["frame_length"]),
        crc_hex=str(metadata["crc_hex"]),
        frame_sha256=hashlib.sha256(frame).hexdigest(),
        raw_bytes=frame,
        request_fingerprint=request_fingerprint(request),
        encoder_version=encoder_version,
        input_status=request.scientific_status,
        classification=request.classification,
        scientific_status=request.scientific_status,
    )


class SyntheticMessageEncoder:
    """Byte-stable lab encoder; its payload is not a navigable RTCM message."""

    family_id = "SYNTHETIC_TEST_FRAME"
    encoder_version = ENCODER_VERSION
    message_number = 4095

    def encode(self, context: CorrectionGenerationContext) -> GeneratedCorrectionFrame:
        request = context.request
        _require_synthetic_context(context, self.encoder_version)
        # Canonical JSON is test payload content only; it is not an RTCM semantic layout.
        content = {
            "label": "SYNTHETIC TEST DATA — NOT VALID FOR SCIENTIFIC RESULTS",
            "request_id": request.request_id,
            "decision_id": request.decision_id,
            "mode": str(request.mode),
            "epoch": request.epoch.gnss_epoch,
            "fields": context.fields,
            "observations": list(context.observations),
        }
        suffix = b"NLGCP-SYN1\x00" + json.dumps(
            content, sort_keys=True, separators=(",", ":"), ensure_ascii=True
        ).encode("ascii")
        frame = frame_payload(self.message_number, suffix)
        metadata = frame_metadata(frame)
        return GeneratedCorrectionFrame(
            message_family=self.family_id,
            message_number=self.message_number,
            payload_length=int(metadata["payload_length"]),
            frame_length=int(metadata["frame_length"]),
            crc_hex=str(metadata["crc_hex"]),
            frame_sha256=hashlib.sha256(frame).hexdigest(),
            raw_bytes=frame,
            request_fingerprint=request_fingerprint(request),
            encoder_version=self.encoder_version,
            input_status=request.scientific_status,
            classification=request.classification,
            scientific_status=request.scientific_status,
        )


class ReferenceStation1005Encoder:
    """RTCM 1005 encoder over caller-supplied synthetic fixture fields."""

    family_id = "REFERENCE_STATION_1005"
    message_number = MESSAGE_NUMBER_1005
    encoder_version = ENCODER_VERSION_1005

    def encode(self, context: CorrectionGenerationContext) -> GeneratedCorrectionFrame:
        _require_synthetic_context(context, self.encoder_version)
        message = ReferenceStation1005.from_mapping(context.fields)
        return _build_frame(
            context,
            family_id=self.family_id,
            message_number=self.message_number,
            encoder_version=self.encoder_version,
            payload=message.encode(),
        )


class _Msm4Encoder:
    system: MsmSystem
    family_id: str
    message_number: int
    encoder_version = ENCODER_VERSION_MSM4

    def encode(self, context: CorrectionGenerationContext) -> GeneratedCorrectionFrame:
        _require_synthetic_context(context, self.encoder_version)
        message = Msm4Message.from_mapping(
            self.system, context.fields, context.observations
        )
        return _build_frame(
            context,
            family_id=self.family_id,
            message_number=self.message_number,
            encoder_version=self.encoder_version,
            payload=message.encode(),
        )


class GpsMsm4Encoder(_Msm4Encoder):
    """RTCM 1074 GPS MSM4 encoder over synthetic fixture fields."""

    system = MsmSystem.GPS
    family_id = "MSM4_GPS_1074"
    message_number = MESSAGE_NUMBER_1074


class GlonassMsm4Encoder(_Msm4Encoder):
    """RTCM 1084 GLONASS MSM4 encoder over synthetic fixture fields."""

    system = MsmSystem.GLONASS
    family_id = "MSM4_GLONASS_1084"
    message_number = MESSAGE_NUMBER_1084


class ScaffoldOnlyEncoder:
    """Explicit placeholder for message families without a permitted layout."""

    def __init__(self, family_id: str) -> None:
        self.family_id = family_id
        self.encoder_version = "scaffold-only"

    def encode(self, context: CorrectionGenerationContext) -> GeneratedCorrectionFrame:
        del context
        raise UnsupportedEncoderError(
            f"{self.family_id} has a scaffold boundary but no validated encoder"
        )


def default_encoders() -> dict[str, MessageEncoder]:
    return {
        "SYNTHETIC_TEST_FRAME": SyntheticMessageEncoder(),
        "REFERENCE_STATION_1005": ReferenceStation1005Encoder(),
        "MSM4_GPS_1074": GpsMsm4Encoder(),
        "MSM4_GLONASS_1084": GlonassMsm4Encoder(),
    }
