"""Replay clock abstraction (§12): real monotonic time in production,
deterministic fake clock in tests.  Tests must never rely on sleeping."""

from __future__ import annotations

import time
from typing import Protocol


class ReplayClock(Protocol):
    def now_ms(self) -> int: ...
    def advance_ms(self, delta_ms: int) -> None: ...


class MonotonicClock:
    """Production clock backed by ``time.monotonic`` (milliseconds)."""

    def now_ms(self) -> int:
        return int(time.monotonic() * 1000)

    def advance_ms(self, delta_ms: int) -> None:
        if delta_ms > 0:
            time.sleep(delta_ms / 1000.0)


class FakeClock:
    """Deterministic test clock: time moves only via ``advance_ms``."""

    def __init__(self, start_ms: int = 0) -> None:
        self._now = start_ms

    def now_ms(self) -> int:
        return self._now

    def advance_ms(self, delta_ms: int) -> None:
        if delta_ms < 0:
            raise ValueError(f"clock cannot go backwards: {delta_ms}")
        self._now += delta_ms
