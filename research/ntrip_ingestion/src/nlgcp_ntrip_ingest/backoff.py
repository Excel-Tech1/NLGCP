"""Bounded reconnection: exponential backoff with cap and jitter.

Transient failures (timeouts, stalls, lost connections) reconnect with
a bounded schedule; terminal failures (bad credentials, unknown
mountpoint, explicit authorization rejection, invalid configuration)
never reconnect.  Delays are computed arithmetically so tests use a
fake clock without sleeping; callers perform the actual wait.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from nlgcp_ntrip_ingest.models import TERMINAL_FAILURES, FailureClass


@dataclass(frozen=True, slots=True)
class ReconnectPolicy:
    base_delay_s: float = 1.0
    max_delay_s: float = 30.0
    max_attempts: int = 8

    def validate(self) -> list[str]:
        problems: list[str] = []
        if self.base_delay_s <= 0:
            problems.append("base_delay_s must be > 0")
        if self.max_delay_s <= 0:
            problems.append("max_delay_s must be > 0")
        if self.max_delay_s < self.base_delay_s:
            problems.append("max_delay_s must be >= base_delay_s")
        if self.max_attempts < 0:
            problems.append("max_attempts must be >= 0")
        return problems

    def delay_for_attempt(self, attempt: int, *, jitter_seed: int | None = None) -> float:
        """Attempt is 1-indexed: 1s, 2s, 4s, ... capped at max_delay_s."""
        if attempt < 1:
            raise ValueError(f"attempt must be >= 1: {attempt}")
        delay = self.base_delay_s * (2.0 ** (attempt - 1))
        delay = min(delay, self.max_delay_s)
        if jitter_seed is not None:
            rng = random.Random(jitter_seed)
            delay = delay * (0.9 + 0.2 * rng.random())
        return delay

    def attempts_exhausted(self, attempts_made: int) -> bool:
        return attempts_made >= self.max_attempts


def is_terminal(failure: FailureClass) -> bool:
    """Terminal failures must not reconnect without config change."""
    return failure in TERMINAL_FAILURES


def classify_status_code(code: int | None) -> FailureClass | None:
    if code == 401:
        return FailureClass.AUTH_FAILURE
    if code == 403:
        return FailureClass.AUTHORIZATION_REJECTED
    if code == 404:
        return FailureClass.MOUNTPOINT_NOT_FOUND
    if code is None:
        return FailureClass.PROTOCOL_ERROR
    return FailureClass.PROTOCOL_ERROR
