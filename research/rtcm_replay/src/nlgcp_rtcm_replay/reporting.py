"""Machine-readable output bundles (§29).

Layout under ``${NLGCP_DATA_ROOT}/processed/rtcm-replay/``::

    sources/<source-id>/{inventory.json, frames.csv, message-types.csv,
                         validation.json}
    runs/<replay-id>/{definition.json, admission.json, timeline.csv,
                      metrics.json, checkpoint.json, provenance.json,
                      validation.json}
    summaries/{sources.csv, replay-runs.csv}

Raw captures are never modified; replay state lives under
``processed/`` or ``working/`` (immutable ``raw/`` untouched).
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from nlgcp_rtcm_replay.framing import ParsedFrame
from nlgcp_rtcm_replay.inventory import Inventory
from nlgcp_rtcm_replay.models import (
    AdmissionResult,
    Checkpoint,
    ReplayConfig,
    ReplayEvent,
    ReplayMetrics,
    RTCMSource,
)


def _sanitize(value: Any) -> Any:
    """Replace non-finite floats (unpaced effective speed) with None so
    every written bundle is strict JSON.  A null ``effective_speed``
    means unpaced/max-throughput replay."""
    if isinstance(value, float) and (value != value or value in (float("inf"), float("-inf"))):
        return None
    if isinstance(value, dict):
        return {key: _sanitize(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    return value


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_sanitize(payload), indent=2, sort_keys=True) + "\n")


def read_json(path: Path) -> dict[str, Any]:
    raw = json.loads(path.read_text())
    if not isinstance(raw, dict):
        raise ValueError(f"expected JSON object in {path}")
    return raw


def write_source_bundle(
    root: Path,
    source: RTCMSource,
    *,
    frames: list[ParsedFrame],
    inventory: Inventory,
    admission: AdmissionResult,
) -> Path:
    out = root / "sources" / source.source_id
    out.mkdir(parents=True, exist_ok=True)
    write_json(out / "source.json", source.as_dict())
    write_json(out / "inventory.json", inventory.as_dict())
    write_json(out / "validation.json", admission.as_dict())
    with open(out / "frames.csv", "w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["offset", "frame_length", "message_number", "crc_status", "raw_hash"])
        for parsed in frames:
            record = parsed.record
            writer.writerow(
                [
                    record.offset,
                    record.frame_length,
                    record.message_number if record.message_number is not None else "",
                    str(record.crc_status),
                    record.raw_hash,
                ]
            )
    with open(out / "message-types.csv", "w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["message_number", "count"])
        for key in sorted(inventory.message_type_counts):
            writer.writerow([key, inventory.message_type_counts[key]])
    return out


def write_run_bundle(
    root: Path,
    replay_id: str,
    *,
    definition: dict[str, Any],
    admission: AdmissionResult,
    timeline: list[ReplayEvent],
    metrics: ReplayMetrics,
    checkpoint: Checkpoint | None,
    provenance: dict[str, Any],
    handoff: dict[str, Any] | None = None,
) -> Path:
    out = root / "runs" / replay_id
    out.mkdir(parents=True, exist_ok=True)
    write_json(out / "definition.json", definition)
    write_json(out / "admission.json", admission.as_dict())
    write_json(
        out / "validation.json",
        {
            "replay_id": replay_id,
            "frames_emitted": metrics.frames_emitted,
            "frames_dropped": metrics.frames_dropped,
            "duplicates": metrics.duplicates,
            "sequence_gaps": metrics.sequence_gaps,
            "transport_success_note": (
                "transport success != positioning success; no accuracy claimed"
            ),
        },
    )
    with open(out / "timeline.csv", "w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "sequence",
                "source_offset",
                "message_number",
                "frame_length",
                "original_timestamp",
                "relative_time_ms",
                "raw_hash",
            ]
        )
        for event in timeline:
            writer.writerow(
                [
                    event.sequence,
                    event.source_offset,
                    event.message_number if event.message_number is not None else "",
                    event.frame_length,
                    event.original_timestamp or "",
                    event.relative_time_ms,
                    event.raw_hash,
                ]
            )
    write_json(out / "metrics.json", metrics.as_dict())
    if checkpoint is not None:
        write_json(out / "checkpoint.json", checkpoint.as_dict())
    write_json(out / "provenance.json", provenance)
    if handoff is not None:
        write_json(out / "phase8-handoff.json", handoff)
    return out


def append_summary_rows(
    root: Path,
    *,
    source_rows: list[dict[str, Any]] | None = None,
    run_rows: list[dict[str, Any]] | None = None,
) -> None:
    summaries = root / "summaries"
    summaries.mkdir(parents=True, exist_ok=True)
    if source_rows is not None:
        path = summaries / "sources.csv"
        with open(path, "w", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(
                ["source_id", "source_type", "station_id", "verdict", "frames_valid", "sha256"]
            )
            for row in source_rows:
                writer.writerow(
                    [
                        row.get("source_id", ""),
                        row.get("source_type", ""),
                        row.get("station_id", ""),
                        row.get("verdict", ""),
                        row.get("frames_valid", ""),
                        row.get("sha256", ""),
                    ]
                )
    if run_rows is not None:
        path = summaries / "replay-runs.csv"
        with open(path, "w", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(
                [
                    "replay_id",
                    "source_id",
                    "mode",
                    "frames_emitted",
                    "frames_dropped",
                    "duplicates",
                    "sequence_gaps",
                    "outcome",
                ]
            )
            for row in run_rows:
                writer.writerow(
                    [
                        row.get("replay_id", ""),
                        row.get("source_id", ""),
                        row.get("mode", ""),
                        row.get("frames_emitted", ""),
                        row.get("frames_dropped", ""),
                        row.get("duplicates", ""),
                        row.get("sequence_gaps", ""),
                        row.get("outcome", ""),
                    ]
                )


def config_from_run_definition(definition: dict[str, Any]) -> ReplayConfig:
    from nlgcp_rtcm_replay.models import config_from_dict

    config_raw = definition.get("config")
    if not isinstance(config_raw, dict):
        raise ValueError("run definition lacks a config object")
    return config_from_dict(config_raw)
