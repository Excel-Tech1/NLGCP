"""Metric assembly (§22-§23).

Combines discovery/inventory counters with replay execution counters
into one ``ReplayMetrics`` record.  Offline replay distinguishes source
inter-arrival intervals, scheduled replay delays, and consumer
processing delays — none of which is reported as network latency.
"""

from __future__ import annotations

from nlgcp_rtcm_replay.inventory import Inventory
from nlgcp_rtcm_replay.models import ReplayMetrics


def assemble_metrics(
    inventory: Inventory,
    executed: ReplayMetrics,
    *,
    bytes_processed: int,
) -> ReplayMetrics:
    return ReplayMetrics(
        frames_discovered=inventory.frames_valid + inventory.frames_invalid,
        frames_valid=inventory.frames_valid,
        frames_invalid=inventory.frames_invalid,
        crc_failures=inventory.crc_failures,
        bytes_processed=bytes_processed,
        message_type_counts=dict(inventory.message_type_counts),
        replay_duration_ms=executed.replay_duration_ms,
        source_duration_ms=executed.source_duration_ms,
        effective_speed=executed.effective_speed,
        frames_emitted=executed.frames_emitted,
        frames_dropped=executed.frames_dropped,
        duplicates=executed.duplicates,
        sequence_gaps=executed.sequence_gaps,
        checkpoint_resumes=executed.checkpoint_resumes,
        producer_frames=executed.producer_frames,
        consumer_frames=executed.consumer_frames,
        buffer_waits=executed.buffer_waits,
        maximum_queue_depth=executed.maximum_queue_depth,
        scheduled_replay_delays_ms=list(executed.scheduled_replay_delays_ms),
        consumer_processing_delays_ms=list(executed.consumer_processing_delays_ms),
    )
