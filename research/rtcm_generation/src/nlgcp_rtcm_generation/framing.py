"""Shared Phase 9 RTCM framing adapter; no second CRC implementation."""

from __future__ import annotations

import hashlib

from nlgcp_rtcm_replay.crc import crc24q
from nlgcp_rtcm_replay.framing import encode_frame as phase9_encode_frame
from nlgcp_rtcm_replay.framing import parse_stream


def frame_payload(message_number: int, payload_suffix: bytes) -> bytes:
    """Frame a payload through Phase 9's tested preamble/length/CRC path."""
    return phase9_encode_frame(message_number, payload_suffix)


def frame_metadata(frame: bytes) -> dict[str, int | str]:
    if len(frame) < 6 or frame[0] != 0xD3:
        raise ValueError("not an RTCM 3.x frame")
    payload_length = ((frame[1] & 0x03) << 8) | frame[2]
    if len(frame) != payload_length + 6:
        raise ValueError("frame length does not match header")
    crc = (frame[-3] << 16) | (frame[-2] << 8) | frame[-1]
    return {
        "payload_length": payload_length,
        "frame_length": len(frame),
        "crc": crc,
        "crc_hex": f"{crc:06x}",
        "frame_sha256": hashlib.sha256(frame).hexdigest(),
    }


def validate_with_phase9(frame: bytes, message_number: int) -> tuple[bool, tuple[str, ...]]:
    parsed = parse_stream(frame)
    if len(parsed.frames) != 1:
        return False, tuple(parsed.findings)
    record = parsed.frames[0].record
    ok = record.crc_status.value == "PASS" and record.message_number == message_number
    return ok, tuple(parsed.findings)


def crc_for_frame(frame: bytes) -> int:
    if len(frame) < 3:
        raise ValueError("frame too short")
    return crc24q(frame[:-3])
