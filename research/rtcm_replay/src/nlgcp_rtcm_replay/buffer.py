"""Bounded buffering with explicit backpressure (§19-§20).

Default behaviour never loses a frame silently: when the buffer is
full the producer either BLOCKs (waits, counted) or, under the explicit
DROP_NEWEST_EXPLICIT policy, drops the newest frame with a counted,
reported drop.  Occupancy, high-water mark, waits and drops are all
recorded for metrics.
"""

from __future__ import annotations

from collections import deque

from nlgcp_rtcm_replay.models import BackpressurePolicy


class BoundedBuffer[T]:
    def __init__(
        self, capacity: int, *, policy: BackpressurePolicy = BackpressurePolicy.BLOCK
    ) -> None:
        if capacity < 1:
            raise ValueError(f"capacity must be >= 1: {capacity}")
        self._capacity = capacity
        self._policy = policy
        self._queue: deque[T] = deque()
        self.high_water_mark = 0
        self.dropped_frames = 0
        self.buffer_waits = 0
        self.maximum_queue_depth = 0

    @property
    def capacity(self) -> int:
        return self._capacity

    @property
    def occupancy(self) -> int:
        return len(self._queue)

    @property
    def policy(self) -> BackpressurePolicy:
        return self._policy

    def try_put(self, item: T) -> bool:
        """Non-blocking put.  Returns True if accepted, False if full."""
        if len(self._queue) >= self._capacity:
            if self._policy == BackpressurePolicy.DROP_NEWEST_EXPLICIT:
                self.dropped_frames += 1
                return False
            self.buffer_waits += 1
            return False
        self._queue.append(item)
        if len(self._queue) > self.high_water_mark:
            self.high_water_mark = len(self._queue)
        if len(self._queue) > self.maximum_queue_depth:
            self.maximum_queue_depth = len(self._queue)
        return True

    def force_put(self, item: T) -> None:
        """Blocking-path put used after the controller records a wait."""
        if len(self._queue) >= self._capacity:
            raise BufferError("buffer full: force_put requires occupancy < capacity")
        self._queue.append(item)
        if len(self._queue) > self.high_water_mark:
            self.high_water_mark = len(self._queue)
        if len(self._queue) > self.maximum_queue_depth:
            self.maximum_queue_depth = len(self._queue)

    def take(self) -> T | None:
        if not self._queue:
            return None
        return self._queue.popleft()

    def drain(self) -> list[T]:
        items = list(self._queue)
        self._queue.clear()
        return items
