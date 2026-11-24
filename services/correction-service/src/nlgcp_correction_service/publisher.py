"""Stream publication and bounded per-client fan-out for Phase 12 mountpoints.

Decouples RTCM frame producers (Phase 11 synthetic generator, NTRIP source
push, or future authentic validated sources) from connected NTRIP client
sockets while enforcing:
- fail-closed mountpoint classification checks;
- fail-closed CRC-24Q and RTCM framing validation;
- FIFO message ordering per client;
- bounded per-client queues (no unbounded memory growth, explicit overflow
  accounting instead of silent drop).
"""

from __future__ import annotations

import queue
import threading
from contextlib import suppress
from dataclasses import dataclass

from nlgcp_rtcm_generation.handoff import CorrectionStreamArtifact
from nlgcp_rtcm_generation.models import (
    CorrectionGenerationResult,
    GenerationStatus,
    OutputClassification,
)

from nlgcp_correction_service.diagnostics import CasterDiagnostics
from nlgcp_correction_service.mountpoints import MountpointDefinition, MountpointRegistry
from nlgcp_correction_service.validation import (
    FrameValidationError,
    ValidatedRtcmFrame,
    validate_generated_frame,
    validate_rtcm_bytes,
)


class PublicationError(ValueError):
    """Raised when a mountpoint or frame cannot be published."""


@dataclass(slots=True)
class ClientSubscription:
    """Bounded FIFO frame queue for one authenticated NTRIP client."""

    client_id: str
    mountpoint: str
    username: str
    queue: queue.Queue[ValidatedRtcmFrame | None]
    closed: bool = False


class MountpointBroker:
    """Thread-safe publisher/subscriber hub for local synthetic mountpoints."""

    def __init__(
        self,
        registry: MountpointRegistry,
        diagnostics: CasterDiagnostics,
        *,
        max_queue_frames: int = 256,
    ) -> None:
        self._registry = registry
        self._diagnostics = diagnostics
        self._max_queue_frames = max_queue_frames
        self._lock = threading.Lock()
        self._subscribers: dict[str, dict[str, ClientSubscription]] = {
            name: {} for name in registry.names()
        }
        self._backlog: dict[str, list[ValidatedRtcmFrame]] = {
            name: [] for name in registry.names()
        }

    def _require_mountpoint(self, mountpoint: str) -> MountpointDefinition:
        cleaned = mountpoint.lstrip("/")
        definition = self._registry.get(cleaned)
        if definition is None:
            raise PublicationError(f"unknown mountpoint: {mountpoint!r}")
        return definition

    def subscribe(
        self,
        client_id: str,
        mountpoint: str,
        username: str,
        *,
        replay_backlog: bool = True,
    ) -> ClientSubscription:
        definition = self._require_mountpoint(mountpoint)
        q: queue.Queue[ValidatedRtcmFrame | None] = queue.Queue(
            maxsize=self._max_queue_frames
        )
        sub = ClientSubscription(
            client_id=client_id,
            mountpoint=definition.name,
            username=username,
            queue=q,
        )
        with self._lock:
            if replay_backlog:
                for frame in self._backlog[definition.name]:
                    try:
                        q.put_nowait(frame)
                    except queue.Full:
                        self._diagnostics.record_queue_overflow()
                        break
            self._subscribers[definition.name][client_id] = sub
        return sub

    def unsubscribe(self, sub: ClientSubscription) -> None:
        with self._lock:
            sub.closed = True
            self._subscribers.get(sub.mountpoint, {}).pop(sub.client_id, None)
            self._enqueue_sentinel(sub)

    def close_all(self) -> None:
        """Signal end-of-stream to every active subscriber cleanly."""
        with self._lock:
            for subs in self._subscribers.values():
                for sub in subs.values():
                    sub.closed = True
                    self._enqueue_sentinel(sub)
                subs.clear()

    def close_mountpoint_clients(self, mountpoint: str) -> None:
        """Signal end-of-stream to clients on a specific mountpoint."""
        definition = self._require_mountpoint(mountpoint)
        with self._lock:
            subs = self._subscribers[definition.name]
            for sub in subs.values():
                sub.closed = True
                self._enqueue_sentinel(sub)
            subs.clear()

    def clear_backlog(self, mountpoint: str) -> None:
        definition = self._require_mountpoint(mountpoint)
        with self._lock:
            self._backlog[definition.name].clear()

    def publish_validated(
        self,
        mountpoint: str,
        frame: ValidatedRtcmFrame,
        *,
        retain_in_backlog: bool = True,
    ) -> ValidatedRtcmFrame:
        definition = self._require_mountpoint(mountpoint)
        if not definition.accepts_classification(frame.classification):
            self._diagnostics.record_rejected_frame()
            raise PublicationError(
                f"mountpoint {definition.name!r} rejected classification "
                f"{frame.classification}"
            )
        self._diagnostics.record_frame_received(
            frame.message_number, len(frame.raw_bytes)
        )
        with self._lock:
            if retain_in_backlog:
                ring = self._backlog[definition.name]
                ring.append(frame)
                if len(ring) > self._max_queue_frames:
                    del ring[: len(ring) - self._max_queue_frames]
            for sub in list(self._subscribers[definition.name].values()):
                if sub.closed:
                    continue
                try:
                    sub.queue.put_nowait(frame)
                except queue.Full:
                    self._diagnostics.record_queue_overflow()
        return frame

    def publish_raw_frame(
        self,
        mountpoint: str,
        raw_bytes: bytes,
        *,
        classification: OutputClassification = OutputClassification.SYNTHETIC_TEST_ONLY,
        source_id: str = "raw-source",
        retain_in_backlog: bool = True,
    ) -> ValidatedRtcmFrame:
        try:
            validated = validate_rtcm_bytes(
                raw_bytes, classification=classification, source_id=source_id
            )
        except FrameValidationError as exc:
            if "CRC-24Q" in str(exc):
                self._diagnostics.record_crc_failure()
            else:
                self._diagnostics.record_rejected_frame()
            raise PublicationError(str(exc)) from exc
        return self.publish_validated(
            mountpoint, validated, retain_in_backlog=retain_in_backlog
        )

    def publish_phase11_result(
        self,
        mountpoint: str,
        result: CorrectionGenerationResult,
        *,
        artifact: CorrectionStreamArtifact | None = None,
        retain_in_backlog: bool = True,
    ) -> tuple[ValidatedRtcmFrame, ...]:
        """Publish frames from a Phase 11 ``CorrectionGenerationResult``."""
        definition = self._require_mountpoint(mountpoint)
        if result.status != GenerationStatus.ENCODED or not result.frames:
            self._diagnostics.record_rejected_frame()
            raise PublicationError(
                f"cannot publish Phase 11 result with status={result.status} "
                f"and {len(result.frames)} frame(s)"
            )
        if not definition.accepts_classification(result.classification):
            self._diagnostics.record_rejected_frame()
            raise PublicationError(
                f"mountpoint {definition.name!r} rejected Phase 11 classification "
                f"{result.classification}"
            )
        if artifact is not None:
            if artifact.decision_id != result.decision_id:
                self._diagnostics.record_rejected_frame()
                raise PublicationError("Phase 12 handoff artifact decision_id mismatch")
            if not definition.accepts_classification(artifact.classification):
                self._diagnostics.record_rejected_frame()
                raise PublicationError(
                    f"mountpoint {definition.name!r} rejected artifact classification "
                    f"{artifact.classification}"
                )
        published: list[ValidatedRtcmFrame] = []
        for frame in result.frames:
            try:
                validated = validate_generated_frame(
                    frame, source_id=f"phase11:{result.request_id}"
                )
            except FrameValidationError as exc:
                if "CRC-24Q" in str(exc):
                    self._diagnostics.record_crc_failure()
                else:
                    self._diagnostics.record_rejected_frame()
                raise PublicationError(str(exc)) from exc
            published.append(
                self.publish_validated(
                    definition.name,
                    validated,
                    retain_in_backlog=retain_in_backlog,
                )
            )
        return tuple(published)

    @staticmethod
    def _enqueue_sentinel(sub: ClientSubscription) -> None:
        try:
            sub.queue.put_nowait(None)
        except queue.Full:
            with suppress(queue.Empty):
                sub.queue.get_nowait()
            with suppress(queue.Full):
                sub.queue.put_nowait(None)
