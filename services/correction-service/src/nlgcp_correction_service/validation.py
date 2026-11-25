"""Fail-closed RTCM 3.x frame validation boundary for Phase 12 publication.

Reuses Phase 9 CRC-24Q and framing constants without introducing a second CRC
implementation or RTCM encoder.  Every frame published to a synthetic caster
mountpoint must pass:
- exact preamble ``0xD3``;
- 6 reserved header bits == 0 (``header[1] & 0xFC == 0``);
- declared 10-bit payload length matches exact byte length (``3 + len + 3``);
- valid CRC-24Q checksum;
- valid 12-bit RTCM message number;
- non-operational classification (``SYNTHETIC_TEST_ONLY``).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from nlgcp_rtcm_generation.models import GeneratedCorrectionFrame, OutputClassification
from nlgcp_rtcm_generation.registry import MessageFamilyRegistry, MessageFamilyStatus
from nlgcp_rtcm_replay.crc import crc24q
from nlgcp_rtcm_replay.framing import (
    CRC_LENGTH,
    HEADER_LENGTH,
    MAX_RTCM_LENGTH,
    MIN_PAYLOAD_FOR_MESSAGE_NUMBER,
    PREAMBLE,
    extract_message_number,
)


class FrameValidationError(ValueError):
    """Raised when a candidate RTCM frame fails transport or policy checks."""


@dataclass(frozen=True, slots=True)
class ValidatedRtcmFrame:
    """An immutable, CRC-verified RTCM 3.x frame cleared for synthetic streaming."""

    raw_bytes: bytes
    message_number: int
    payload_length: int
    crc_hex: str
    frame_sha256: str
    classification: OutputClassification
    source_id: str


def validate_rtcm_bytes(
    raw_bytes: bytes,
    *,
    classification: OutputClassification = OutputClassification.SYNTHETIC_TEST_ONLY,
    source_id: str = "phase11-synthetic",
) -> ValidatedRtcmFrame:
    """Validate one raw RTCM 3.x frame; fail closed on any framing/CRC/policy error."""
    if classification == OutputClassification.OPERATIONAL_APPROVED:
        raise FrameValidationError(
            "OPERATIONAL_APPROVED classification is forbidden in Phase 12 lab mode"
        )
    if classification != OutputClassification.SYNTHETIC_TEST_ONLY:
        raise FrameValidationError(
            f"Phase 12 synthetic mountpoints accept SYNTHETIC_TEST_ONLY only, "
            f"got {classification}"
        )
    if not isinstance(raw_bytes, (bytes, bytearray)):
        raise FrameValidationError("frame must be bytes")
    data = bytes(raw_bytes)
    min_frame = HEADER_LENGTH + MIN_PAYLOAD_FOR_MESSAGE_NUMBER + CRC_LENGTH
    if len(data) < min_frame:
        raise FrameValidationError(
            f"truncated RTCM frame: {len(data)} bytes < minimum {min_frame}"
        )
    if data[0] != PREAMBLE:
        raise FrameValidationError(
            f"invalid RTCM preamble: expected 0x{PREAMBLE:02x}, got 0x{data[0]:02x}"
        )
    if data[1] & 0xFC:
        raise FrameValidationError("non-zero reserved bits in RTCM 3.x header")
    payload_length = ((data[1] & 0x03) << 8) | data[2]
    if payload_length < MIN_PAYLOAD_FOR_MESSAGE_NUMBER or payload_length > MAX_RTCM_LENGTH:
        raise FrameValidationError(f"invalid RTCM payload length: {payload_length}")
    expected_total = HEADER_LENGTH + payload_length + CRC_LENGTH
    if len(data) != expected_total:
        raise FrameValidationError(
            f"RTCM frame length mismatch: header declares {expected_total} bytes, "
            f"got {len(data)}"
        )
    body = data[:-CRC_LENGTH]
    crc_bytes = data[-CRC_LENGTH:]
    declared_crc = (crc_bytes[0] << 16) | (crc_bytes[1] << 8) | crc_bytes[2]
    computed_crc = crc24q(body)
    if declared_crc != computed_crc:
        raise FrameValidationError(
            f"CRC-24Q mismatch: declared 0x{declared_crc:06x}, computed 0x{computed_crc:06x}"
        )
    payload = data[HEADER_LENGTH:-CRC_LENGTH]
    message_number = extract_message_number(payload)
    if message_number is None:
        raise FrameValidationError("could not extract 12-bit RTCM message number")
    return ValidatedRtcmFrame(
        raw_bytes=data,
        message_number=message_number,
        payload_length=payload_length,
        crc_hex=f"{computed_crc:06x}",
        frame_sha256=hashlib.sha256(data).hexdigest(),
        classification=classification,
        source_id=source_id,
    )


def validate_generated_frame(
    frame: GeneratedCorrectionFrame,
    *,
    source_id: str = "phase11-generator",
    registry: MessageFamilyRegistry | None = None,
) -> ValidatedRtcmFrame:
    """Validate a Phase 11 ``GeneratedCorrectionFrame`` before publication."""
    active_registry = registry if registry is not None else MessageFamilyRegistry()
    family = active_registry.get(frame.message_family)
    if family is None:
        raise FrameValidationError(
            f"unsupported Phase 11 message family: {frame.message_family!r}"
        )
    if family.status != MessageFamilyStatus.SYNTHETICALLY_VALIDATED:
        raise FrameValidationError(
            f"message family {frame.message_family!r} has status {family.status}; "
            "Phase 12 lab mode permits SYNTHETICALLY_VALIDATED families only"
        )
    if frame.message_number not in family.message_numbers:
        raise FrameValidationError(
            f"message number {frame.message_number} is not permitted for family "
            f"{frame.message_family!r}"
        )
    validated = validate_rtcm_bytes(
        frame.raw_bytes,
        classification=frame.classification,
        source_id=source_id,
    )
    if validated.message_number != frame.message_number:
        raise FrameValidationError(
            f"frame message number {validated.message_number} disagrees with "
            f"Phase 11 metadata {frame.message_number}"
        )
    if validated.frame_sha256 != frame.frame_sha256:
        raise FrameValidationError("frame SHA-256 disagrees with Phase 11 metadata")
    return validated
