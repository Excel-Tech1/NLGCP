"""Arrival timing: genuine network timestamps, never GNSS epochs.

Every live frame records ``connection_id``, a global capture sequence,
a monotonic timestamp, a UTC timestamp, and a byte offset.  Arrival
time is explicitly NOT a GNSS measurement epoch.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Protocol

from nlgcp_ntrip_ingest.models import ArrivalRecord


class Clock(Protocol):
    def monotonic_ns(self) -> int: ...
    def utc_now_iso(self) -> str: ...


class SystemClock:
    """Production clock (wall + monotonic)."""

    def monotonic_ns(self) -> int:
        return time.monotonic_ns()

    def utc_now_iso(self) -> str:
        return datetime.now(UTC).isoformat()


class FakeClock:
    """Deterministic test clock: time advances only when told to."""

    def __init__(self, *, start_ns: int = 0, start_utc: str = "2026-01-01T00:00:00+00:00") -> None:
        self._now_ns = start_ns
        self._utc = start_utc

    def monotonic_ns(self) -> int:
        return self._now_ns

    def utc_now_iso(self) -> str:
        return self._utc

    def advance_ns(self, delta_ns: int) -> None:
        if delta_ns < 0:
            raise ValueError("FakeClock cannot go backwards")
        self._now_ns += delta_ns

    def advance_s(self, delta_s: float) -> None:
        self.advance_ns(int(delta_s * 1_000_000_000))


class ArrivalRecorder:
    """Assigns global capture sequences and arrival timestamps."""

    def __init__(self, connection_id: str, clock: Clock | None = None) -> None:
        self._connection_id = connection_id
        self._clock: Clock = clock or SystemClock()
        self._sequence = 0

    @property
    def connection_id(self) -> str:
        return self._connection_id

    def next(
        self,
        *,
        byte_offset: int,
        frame_length: int,
        message_number: int | None,
        crc_status: str,
        frame_sha256: str,
    ) -> ArrivalRecord:
        record = ArrivalRecord(
            connection_id=self._connection_id,
            sequence=self._sequence,
            arrival_monotonic_ns=self._clock.monotonic_ns(),
            arrival_utc=self._clock.utc_now_iso(),
            byte_offset=byte_offset,
            frame_length=frame_length,
            message_number=message_number,
            crc_status=crc_status,
            frame_sha256=frame_sha256,
        )
        self._sequence += 1
        return record
