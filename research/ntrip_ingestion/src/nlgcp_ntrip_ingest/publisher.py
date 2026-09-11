"""Optional bounded publishing boundary for NATS/JetStream.

The core ingestor depends only on this protocol. Tests use the in-memory
publisher; a future NATS implementation can satisfy the same interface
without making live NATS availability a prerequisite for capture.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Protocol

from nlgcp_ntrip_ingest.models import LiveFrame
from nlgcp_ntrip_ingest.subjects import envelope, live_subject


class Publisher(Protocol):
    def publish(self, frame: LiveFrame) -> bool: ...

    def close(self) -> None: ...


@dataclass(frozen=True, slots=True)
class PublishMetrics:
    attempted: int = 0
    published: int = 0
    failed: int = 0
    dropped: int = 0
    high_water_mark: int = 0


class BoundedPublisher:
    """Deterministic adapter boundary; no network or NATS dependency."""

    def __init__(self, capacity: int = 64) -> None:
        if capacity < 1:
            raise ValueError("capacity must be >= 1")
        self._capacity = capacity
        self._queue: deque[dict[str, object]] = deque()
        self.metrics = PublishMetrics()
        self.closed = False

    def publish(self, frame: LiveFrame) -> bool:
        attempted = self.metrics.attempted + 1
        if self.closed:
            self.metrics = PublishMetrics(
                attempted, self.metrics.published, self.metrics.failed + 1,
                self.metrics.dropped, self.metrics.high_water_mark
            )
            return False
        if len(self._queue) >= self._capacity:
            self.metrics = PublishMetrics(
                attempted, self.metrics.published, self.metrics.failed,
                self.metrics.dropped + 1, self.metrics.high_water_mark
            )
            return False
        self._queue.append({"subject": live_subject(frame.station_id), **envelope(frame)})
        depth = len(self._queue)
        self.metrics = PublishMetrics(
            attempted, self.metrics.published + 1, self.metrics.failed,
            self.metrics.dropped, max(depth, self.metrics.high_water_mark)
        )
        return True

    def take(self) -> dict[str, object] | None:
        return self._queue.popleft() if self._queue else None

    def close(self) -> None:
        self.closed = True
