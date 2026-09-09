"""Deterministic synthetic byte fixtures (§32).

SYNTHETIC TEST DATA — NOT VALID FOR SCIENTIFIC RESULTS.

Fixtures are small, deterministic, obviously test-only (station ids use
the ``SYN``/``TEST`` prefix, mountpoints carry ``SYNTHETIC``), and use
valid RTCM framing/CRC so the transport path is exercised faithfully.
They are never represented as field data and carry no station
performance evidence.
"""

from __future__ import annotations

from nlgcp_rtcm_replay import SYNTHETIC_LABEL
from nlgcp_rtcm_replay.framing import encode_frame

SYNTHETIC_NOTICE = SYNTHETIC_LABEL

#: Deterministic payload suffix per message number (fixed pattern bytes).
_MESSAGE_PAYLOADS: dict[int, bytes] = {
    1005: bytes([0x11, 0x22, 0x33, 0x44, 0x55]),
    1006: bytes([0x66, 0x77, 0x88, 0x99, 0xAA, 0xBB]),
    1077: bytes([0x01, 0x02, 0x03, 0x04]),
    1087: bytes([0x05, 0x06, 0x07, 0x08]),
    1230: bytes([0x0A, 0x0B, 0x0C]),
}


def payload_for(message_number: int) -> bytes:
    base = _MESSAGE_PAYLOADS.get(message_number, bytes([0xDE, 0xAD]))
    # Deterministic per-message suffix: message number echoed + fixed tail.
    return bytes([(message_number >> 4) & 0xFF, message_number & 0xFF]) + base


def build_stream(message_numbers: list[int]) -> bytes:
    """Encode a deterministic stream for the given message sequence."""
    return b"".join(encode_frame(m, payload_for(m)) for m in message_numbers)


def valid_fixture_stream() -> tuple[bytes, list[int]]:
    """Small valid fixture: 8 frames across common message numbers."""
    sequence = [1005, 1077, 1087, 1005, 1230, 1077, 1006, 1087]
    return build_stream(sequence), sequence


def corrupt_fixture_stream() -> tuple[bytes, list[int]]:
    """Valid prefix + one CRC-corrupted frame + valid suffix.

    Corruption flips a payload bit without fixing the CRC, so framing
    still detects the boundary but CRC validation fails.
    """
    good, sequence = valid_fixture_stream()
    frames = [encode_frame(m, payload_for(m)) for m in sequence]
    bad = bytearray(frames[3])
    bad[5] ^= 0x01
    corrupted = b"".join([*frames[:3], bytes(bad), *frames[4:]])
    return corrupted, sequence


def truncated_fixture_stream() -> bytes:
    """Valid fixture cut mid-frame (source truncation fault)."""
    good, _ = valid_fixture_stream()
    return good[: len(good) - 4]


def garbage_prefix_stream() -> tuple[bytes, list[int]]:
    """Stray non-RTCM bytes ahead of a valid fixture (resync path)."""
    good, sequence = valid_fixture_stream()
    return b"\x00\xFFNLC" + good, sequence


def synthetic_schedule(count: int, interval_ms: int = 1000) -> list[int]:
    """Deterministic synthetic arrival schedule (lab timing only)."""
    return [i * interval_ms for i in range(count)]
