"""Encoder boundary and the deliberately synthetic reference encoder."""

from __future__ import annotations

import hashlib
import json
from typing import Protocol

from nlgcp_rtcm_generation import ENCODER_VERSION
from nlgcp_rtcm_generation.framing import frame_metadata, frame_payload
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


class SyntheticMessageEncoder:
    """Byte-stable lab encoder; its payload is not a navigable RTCM message."""

    family_id = "SYNTHETIC_TEST_FRAME"
    encoder_version = ENCODER_VERSION
    message_number = 4095

    def encode(self, context: CorrectionGenerationContext) -> GeneratedCorrectionFrame:
        request = context.request
        if request.classification != OutputClassification.SYNTHETIC_TEST_ONLY:
            raise UnsupportedEncoderError("synthetic encoder requires SYNTHETIC_TEST_ONLY")
        if not request.synthetic_fixture:
            raise UnsupportedEncoderError("synthetic encoder requires explicit fixture flag")
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
