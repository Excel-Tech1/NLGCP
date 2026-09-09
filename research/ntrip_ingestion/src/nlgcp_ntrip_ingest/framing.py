"""Streaming RTCM 3.x framer for live TCP chunks.

Reuses the tested Phase 9 CRC-24Q and message-number conventions; the
difference is incrementality: arbitrary TCP splits are buffered until a
full frame is available, and multiple frames per read are all emitted.
Never loads a whole live stream into memory (O(max frame) buffering).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from nlgcp_rtcm_replay.crc import crc24q
from nlgcp_rtcm_replay.framing import (
    CRC_LENGTH,
    HEADER_LENGTH,
    MAX_RTCM_LENGTH,
    PREAMBLE,
    extract_message_number,
)


@dataclass(slots=True)
class StreamedFrame:
    """One validated transport frame with its global byte offset."""

    byte_offset: int
    raw: bytes
    message_number: int | None
    crc_ok: bool
    frame_sha256: str


class StreamingFramer:
    """Incremental RTCM 3.x framer over arbitrary TCP chunk boundaries."""

    def __init__(self, *, max_frame_length: int = MAX_RTCM_LENGTH) -> None:
        if not 1 <= max_frame_length <= MAX_RTCM_LENGTH:
            raise ValueError(f"max_frame_length must be within 1..1023: {max_frame_length}")
        self._max_frame_length = max_frame_length
        self._buffer = bytearray()
        self._byte_offset = 0
        self.findings: list[str] = []
        self.stray_bytes = 0
        self._pending_stray = 0

    @property
    def pending_bytes(self) -> int:
        return len(self._buffer)

    def feed(self, chunk: bytes) -> list[StreamedFrame]:
        """Consume one TCP read; return zero or more complete frames."""
        self._buffer.extend(chunk)
        frames: list[StreamedFrame] = []
        skipped = self._pending_stray
        self._pending_stray = 0
        while True:
            if not self._buffer:
                break
            if self._buffer[0] != PREAMBLE:
                skipped += 1
                self._buffer.pop(0)
                self._byte_offset += 1
                continue
            if len(self._buffer) < HEADER_LENGTH:
                break
            length = ((self._buffer[1] & 0x03) << 8) | self._buffer[2]
            if length > self._max_frame_length:
                self.findings.append(
                    f"OVERSIZED_LENGTH offset={self._byte_offset} length={length}"
                )
                skipped += 1
                self._buffer.pop(0)
                self._byte_offset += 1
                continue
            need = HEADER_LENGTH + length + CRC_LENGTH
            if len(self._buffer) < need:
                self._pending_stray = skipped
                break
            raw = bytes(self._buffer[:need])
            body, crc_bytes = raw[:-CRC_LENGTH], raw[-CRC_LENGTH:]
            expected = (crc_bytes[0] << 16) | (crc_bytes[1] << 8) | crc_bytes[2]
            crc_ok = crc24q(body) == expected
            payload = raw[HEADER_LENGTH:-CRC_LENGTH] if length else b""
            message_number = extract_message_number(payload)
            if skipped:
                self.stray_bytes += skipped
                self.findings.append(
                    f"STRAY_BYTES skipped={skipped} next_offset={self._byte_offset}"
                )
                skipped = 0
            frames.append(
                StreamedFrame(
                    byte_offset=self._byte_offset,
                    raw=raw,
                    message_number=message_number,
                    crc_ok=crc_ok,
                    frame_sha256=hashlib.sha256(raw).hexdigest(),
                )
            )
            if not crc_ok:
                self.findings.append(
                    f"CRC_FAIL offset={self._byte_offset} length={length} "
                    f"message={message_number}"
                )
            del self._buffer[:need]
            self._byte_offset += need
        if skipped:
            # Non-preamble bytes already consumed from the wire that never
            # resynchronised (EOF or waiting for more data) are reported
            # as stray so no input byte is silently ignored.
            self.stray_bytes += skipped
            self.findings.append(
                f"STRAY_BYTES skipped={skipped} next_offset={self._byte_offset + len(self._buffer)}"
            )
        return frames

    def flush_findings(self) -> list[str]:
        findings = list(self.findings)
        self.findings.clear()
        return findings
