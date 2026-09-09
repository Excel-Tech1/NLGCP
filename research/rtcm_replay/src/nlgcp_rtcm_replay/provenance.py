"""Provenance and fingerprinting (§43-§44).

Every replay run records source SHA-256, frame inventory fingerprint,
Phase 8 decision fingerprint, replay config fingerprint, software
version, Git commit, working-tree state, and execution time.  Changing
source bytes, metadata, the Phase 8 decision, timing configuration,
message filters, or parser version invalidates stored outputs.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from nlgcp_rtcm_replay import ENGINE_VERSION, PARSER_VERSION, REPLAY_SCHEMA_VERSION
from nlgcp_rtcm_replay.models import ReplayConfig

GIT_COMMIT = "recorded-at-runtime"


def sha256_canonical(payload: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def config_material(config: ReplayConfig) -> dict[str, Any]:
    return {
        "schema_version": REPLAY_SCHEMA_VERSION,
        "parser_version": PARSER_VERSION,
        "speed": config.speed,
        "start_sequence": config.start_sequence,
        "end_sequence": config.end_sequence,
        "start_time": config.start_time,
        "end_time": config.end_time,
        "message_filter": sorted(config.message_filter),
        "loop_cycles": config.loop_cycles,
        "buffer_capacity": config.buffer_capacity,
        "backpressure_policy": str(config.backpressure_policy),
        "max_frame_length": config.max_frame_length,
        "max_events": config.max_events,
    }


def config_fingerprint(config: ReplayConfig) -> str:
    return sha256_canonical(config_material(config))


def build_provenance(
    *,
    source_sha256: str,
    source_metadata: dict[str, Any],
    frame_inventory_fingerprint: str,
    phase8_decision_fingerprint: str,
    selected_correction_source: str,
    replay_config_fingerprint: str,
    execution_timestamp: str,
    git_commit: str = GIT_COMMIT,
    working_tree_clean: bool = False,
) -> dict[str, Any]:
    return {
        "source_sha256": source_sha256,
        "source_metadata": source_metadata,
        "frame_inventory_fingerprint": frame_inventory_fingerprint,
        "phase8_decision_fingerprint": phase8_decision_fingerprint,
        "selected_correction_source": selected_correction_source,
        "replay_config_fingerprint": replay_config_fingerprint,
        "software_version": ENGINE_VERSION,
        "replay_schema_version": REPLAY_SCHEMA_VERSION,
        "parser_version": PARSER_VERSION,
        "git_commit": git_commit,
        "working_tree_clean": working_tree_clean,
        "execution_timestamp": execution_timestamp,
    }
