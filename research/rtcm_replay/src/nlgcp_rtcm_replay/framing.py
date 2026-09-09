"""RTCM 3.x stream framing (§7).

Transport frame layout::

    byte 0:      preamble 0xD3
    bytes 1-2:   6 reserved bits + 10-bit payload length N (0..1023)
    bytes 3..3+N-1: payload (first 12 bits = message number)
    last 3 bytes: CRC-24Q over preamble + header + payload

The parser never invents message boundaries: every emitted frame is an
explicitly validated preamble/length/CRC triple, and every anomaly
(truncation, oversize length, CRC failure, stray bytes) becomes an
explicit finding.  Untrusted-input guards (§41): configurable maximum
frame length, bounded event counts, no unbounded buffering — the input
is scanned as bytes with O(1) extra memory per frame.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from nlgcp_rtcm_replay.crc import crc24q
from nlgcp_rtcm_replay.models import CRCStatus, FrameRecord

PREAMBLE = 0xD3
HEADER_LENGTH = 3
CRC_LENGTH = 3
LENGTH_BITS = 10
MAX_RTCM_LENGTH = (1 << LENGTH_BITS) - 1  # 1023
MIN_PAYLOAD_FOR_MESSAGE_NUMBER = 2


@dataclass(slots=True)
class ParsedFrame:
    """Internal parse result carrying raw bytes for hashing/replay."""

    record: FrameRecord
    raw: bytes


@dataclass(slots=True)
class ParseResult:
    frames: list[ParsedFrame]
    findings: list[str]
    bytes_processed: int


def encode_frame(message_number: int, payload_suffix: bytes) -> bytes:
    """Build one valid RTCM 3.x frame (fixture encoder, §32).

    ``message_number`` holds the 12-bit RTCM message number; the payload
    is the 12-bit number followed by caller-supplied suffix bytes.
    """
    if not 0 <= message_number <= 4095:
        raise ValueError(f"message_number out of 12-bit range: {message_number}")
    head = bytes([(message_number >> 4) & 0xFF, (message_number & 0x0F) << 4])
    # Keep the low nibble of the second header byte deterministic: merge
    # the first suffix byte's high nibble if present, else zero-pad.
    if payload_suffix:
        second = head[1] | (payload_suffix[0] >> 4)
        payload = bytes([head[0], second]) + payload_suffix
    else:
        payload = head + b"\x00"
    if len(payload) > MAX_RTCM_LENGTH:
        raise ValueError(f"payload too long: {len(payload)}")
    header = bytes([PREAMBLE, (len(payload) >> 8) & 0x03, len(payload) & 0xFF])
    body = header + payload
    crc = crc24q(body)
    return body + bytes([(crc >> 16) & 0xFF, (crc >> 8) & 0xFF, crc & 0xFF])


def extract_message_number(payload: bytes) -> int | None:
    """Extract the 12-bit RTCM message number where technically valid."""
    if len(payload) < MIN_PAYLOAD_FOR_MESSAGE_NUMBER:
        return None
    return ((payload[0] << 4) | (payload[1] >> 4)) & 0xFFF


def parse_stream(
    data: bytes,
    *,
    max_frame_length: int = MAX_RTCM_LENGTH,
    max_events: int = 100000,
) -> ParseResult:
    """Scan ``data`` for RTCM 3.x frames, returning frames + findings.

    Deterministic: the same bytes and limits always yield the same
    frames and findings in the same order.
    """
    frames: list[ParsedFrame] = []
    findings: list[str] = []
    pos = 0
    total = len(data)
    skipped_stray = 0

    def flush_stray(upto: int, reason: str) -> None:
        nonlocal skipped_stray
        if skipped_stray:
            findings.append(
                f"STRAY_BYTES skipped={skipped_stray} next_offset={upto} reason={reason}"
            )
            skipped_stray = 0

    while pos < total:
        if len(frames) >= max_events:
            findings.append(
                f"EVENT_LIMIT reached={max_events} remaining_bytes={total - pos}"
            )
            break
        if data[pos] != PREAMBLE:
            skipped_stray += 1
            pos += 1
            continue
        if pos + HEADER_LENGTH > total:
            findings.append(
                f"TRUNCATED_HEADER offset={pos} remaining={total - pos}"
            )
            break
        length = ((data[pos + 1] & 0x03) << 8) | data[pos + 2]
        if length > max_frame_length:
            findings.append(
                f"OVERSIZED_LENGTH offset={pos} length={length} "
                f"max={max_frame_length}"
            )
            flush_stray(pos, "oversize")
            skipped_stray += 1  # do not resync on this preamble
            pos += 1
            continue
        frame_end = pos + HEADER_LENGTH + length + CRC_LENGTH
        if frame_end > total:
            findings.append(
                f"TRUNCATED_FRAME offset={pos} length={length} "
                f"need={frame_end - pos} remaining={total - pos}"
            )
            break
        body = data[pos : frame_end - CRC_LENGTH]
        crc_bytes = data[frame_end - CRC_LENGTH : frame_end]
        expected = (crc_bytes[0] << 16) | (crc_bytes[1] << 8) | crc_bytes[2]
        crc_ok = crc24q(body) == expected
        payload = data[pos + HEADER_LENGTH : frame_end - CRC_LENGTH]
        message_number = extract_message_number(payload)
        raw = data[pos:frame_end]
        flush_stray(pos, "resync")
        record = FrameRecord(
            offset=pos,
            frame_length=length,
            message_number=message_number,
            crc_status=CRCStatus.PASS if crc_ok else CRCStatus.FAIL,
            raw_hash=hashlib.sha256(raw).hexdigest(),
        )
        frames.append(ParsedFrame(record=record, raw=raw))
        if not crc_ok:
            findings.append(
                f"CRC_FAIL offset={pos} length={length} "
                f"message={message_number} expected={expected:06x}"
            )
        pos = frame_end

    if skipped_stray:
        findings.append(
            f"STRAY_BYTES skipped={skipped_stray} next_offset={total} reason=eof"
        )
    return ParseResult(frames=frames, findings=findings, bytes_processed=total)
