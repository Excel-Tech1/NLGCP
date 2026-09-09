"""Restartable replay checkpoints (§14, §44).

A checkpoint records source + configuration fingerprints alongside the
resume position.  A changed source, config, timing selection, message
filter, or parser version invalidates the checkpoint instead of
resuming from a stale position.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from nlgcp_rtcm_replay.models import Checkpoint


@dataclass(frozen=True, slots=True)
class CheckpointCheck:
    valid: bool
    reason: str


def _as_int(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"malformed checkpoint: {name} must be an integer")
    return value


def checkpoint_from_dict(payload: dict[str, Any]) -> Checkpoint:
    try:
        return Checkpoint(
            source_fingerprint=str(payload["source_fingerprint"]),
            config_fingerprint=str(payload["config_fingerprint"]),
            last_emitted_sequence=_as_int(
                payload["last_emitted_sequence"], "last_emitted_sequence"
            ),
            source_byte_offset=_as_int(payload["source_byte_offset"], "source_byte_offset"),
            last_replay_timestamp=str(payload["last_replay_timestamp"]),
            cycle=_as_int(payload.get("cycle", 0), "cycle"),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"malformed checkpoint: {exc}") from exc


def validate_checkpoint(
    checkpoint: Checkpoint,
    *,
    source_fingerprint: str,
    config_fingerprint: str,
) -> CheckpointCheck:
    """A changed source/config must invalidate the checkpoint."""
    if checkpoint.source_fingerprint != source_fingerprint:
        return CheckpointCheck(
            valid=False,
            reason=(
                "CHECKPOINT_SOURCE_MISMATCH expected="
                f"{source_fingerprint} found={checkpoint.source_fingerprint}"
            ),
        )
    if checkpoint.config_fingerprint != config_fingerprint:
        return CheckpointCheck(
            valid=False,
            reason=(
                "CHECKPOINT_CONFIG_MISMATCH expected="
                f"{config_fingerprint} found={checkpoint.config_fingerprint}"
            ),
        )
    return CheckpointCheck(valid=True, reason="CHECKPOINT_VALID")
