#!/usr/bin/env python3
"""Operator CLI for the Phase 9 recorded RTCM replay system."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "research" / "rtcm_replay" / "src"))
sys.path.insert(0, str(REPO_ROOT / "research" / "rtcm_replay" / "tests"))

from nlgcp_rtcm_replay import (  # noqa: E402
    ENGINE_VERSION,  # noqa: E402
    PARSER_VERSION,  # noqa: E402
)
from nlgcp_rtcm_replay.admission import admit_source  # noqa: E402
from nlgcp_rtcm_replay.checkpoint import (  # noqa: E402
    checkpoint_from_dict,
    validate_checkpoint,
)
from nlgcp_rtcm_replay.clock import FakeClock  # noqa: E402
from nlgcp_rtcm_replay.framing import parse_stream  # noqa: E402
from nlgcp_rtcm_replay.handoff import (  # noqa: E402
    handoff_from_dict,
    resolve_handoff,
)
from nlgcp_rtcm_replay.inventory import build_inventory  # noqa: E402
from nlgcp_rtcm_replay.metrics import assemble_metrics  # noqa: E402
from nlgcp_rtcm_replay.models import (  # noqa: E402
    AdmissionVerdict,
    ReplayConfig,
    ReplayEvent,
    RTCMSource,
    config_from_dict,
    source_from_dict,
)
from nlgcp_rtcm_replay.provenance import (  # noqa: E402
    build_provenance,
    config_fingerprint,
)
from nlgcp_rtcm_replay.replay import (  # noqa: E402
    CollectedRun,
    FaultPlan,
    ReplayController,
    apply_plan,
)
from nlgcp_rtcm_replay.reporting import (  # noqa: E402
    append_summary_rows,
    read_json,
    write_json,
    write_run_bundle,
    write_source_bundle,
)
from nlgcp_rtcm_replay.timing import (  # noqa: E402
    build_timeline,
    classify_timing,
)


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def git_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, text=True
        ).strip()
    except Exception:  # noqa: BLE001 - provenance best-effort
        return "unknown"


def working_tree_clean() -> bool:
    try:
        out = subprocess.check_output(
            ["git", "status", "--short"], cwd=REPO_ROOT, text=True
        )
        return out.strip() == ""
    except Exception:  # noqa: BLE001 - provenance best-effort
        return False


def default_out_root(explicit: str | None) -> Path:
    if explicit:
        return Path(explicit)
    root = os.environ.get("NLGCP_DATA_ROOT", "")
    if not root:
        raise SystemExit("NLGCP_DATA_ROOT must be set or --out provided")
    return Path(root) / "processed" / "rtcm-replay"


def load_source(path: str) -> RTCMSource:
    return source_from_dict(read_json(Path(path)))


def load_config(path: str | None) -> ReplayConfig:
    if path is None:
        return ReplayConfig(speed=0.0)
    return config_from_dict(read_json(Path(path)))


def load_schedule(path: str | None, interval_ms: int) -> list[int] | None:
    if path is not None:
        raw = json.loads(Path(path).read_text())
        if not isinstance(raw, list):
            raise SystemExit("schedule file must hold a JSON list of milliseconds")
        return [int(v) for v in raw]
    return None


def parse_and_inventory(
    raw: bytes, *, max_frame_length: int
) -> tuple[list[Any], Any, bytes]:
    parsed = parse_stream(raw, max_frame_length=max_frame_length)
    inventory = build_inventory(parsed, parser_version=PARSER_VERSION)
    return parsed.frames, inventory, raw


def cmd_inspect(args: argparse.Namespace) -> int:
    source = load_source(args.source)
    raw = Path(source.source_path).read_bytes()
    frames, inventory, _ = parse_and_inventory(raw, max_frame_length=1023)
    summary = {
        "source_id": source.source_id,
        "byte_size": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "frames_discovered": len(frames),
        "frames_valid": inventory.frames_valid,
        "frames_invalid": inventory.frames_invalid,
        "message_type_counts": inventory.message_type_counts,
        "findings": inventory.findings,
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    source = load_source(args.source)
    admission = admit_source(source)
    out_root = default_out_root(args.out)
    if args.dry_run:
        print(json.dumps(admission.as_dict(), indent=2, sort_keys=True))
        return 0
    out = out_root / "sources" / source.source_id
    out.mkdir(parents=True, exist_ok=True)
    write_json(out / "validation.json", admission.as_dict())
    print(json.dumps(admission.as_dict(), indent=2, sort_keys=True))
    return 0 if admission.verdict in (AdmissionVerdict.ACCEPT, AdmissionVerdict.WARN) else 2


def cmd_index(args: argparse.Namespace) -> int:
    source = load_source(args.source)
    config = load_config(args.config)
    raw = Path(source.source_path).read_bytes()
    frames, inventory, _ = parse_and_inventory(raw, max_frame_length=config.max_frame_length)
    admission = admit_source(source, max_frame_length=config.max_frame_length)
    out_root = default_out_root(args.out)
    if args.dry_run:
        print(
            json.dumps(
                {
                    "source_id": source.source_id,
                    "frames_discovered": len(frames),
                    "admission": str(admission.verdict),
                    "out": str(out_root / "sources" / source.source_id),
                },
                indent=2,
            )
        )
        return 0
    write_source_bundle(out_root, source, frames=frames, inventory=inventory, admission=admission)
    append_summary_rows(
        out_root,
        source_rows=[
            {
                "source_id": source.source_id,
                "source_type": str(source.source_type),
                "station_id": source.station_id,
                "verdict": str(admission.verdict),
                "frames_valid": inventory.frames_valid,
                "sha256": source.sha256,
            }
        ],
    )
    print(
        json.dumps(
            {
                "source_id": source.source_id,
                "verdict": str(admission.verdict),
                "frames_valid": inventory.frames_valid,
            },
            indent=2,
        )
    )
    return 0


def _build_plan(
    source: RTCMSource, config: ReplayConfig, schedule: list[int] | None, interval_ms: int
) -> tuple[list[ReplayEvent], list[str], str, Any, Any]:
    raw = Path(source.source_path).read_bytes()
    frames, inventory, _ = parse_and_inventory(raw, max_frame_length=config.max_frame_length)
    timing = classify_timing(
        source, schedule, nominal_interval_ms=interval_ms if schedule is None else None
    )
    parsed = parse_stream(raw, max_frame_length=config.max_frame_length).frames
    events, _ = build_timeline(
        parsed, arrival_ms=schedule, nominal_interval_ms=interval_ms
    )
    fingerprint = config_fingerprint(config)
    plan = apply_plan(events, config, config_fingerprint=fingerprint)
    return plan.events, [*timing.findings, *plan.findings], fingerprint, inventory, timing


def cmd_plan(args: argparse.Namespace) -> int:
    source = load_source(args.source)
    config = load_config(args.config)
    schedule = load_schedule(args.schedule, args.interval_ms)
    events, findings, fingerprint, inventory, timing = _build_plan(
        source, config, schedule, args.interval_ms
    )
    replay_id = args.replay_id or f"plan-{source.source_id}"
    definition = {
        "replay_id": replay_id,
        "source": source.as_dict(),
        "config": config.as_dict(),
        "timing_quality": str(timing.quality),
        "planned_events": len(events),
        "findings": findings,
        "inventory_fingerprint": inventory.inventory_fingerprint,
        "config_fingerprint": fingerprint,
        "engine_version": ENGINE_VERSION,
    }
    out_root = default_out_root(args.out)
    if args.dry_run:
        print(json.dumps(definition, indent=2, sort_keys=True))
        return 0
    out = out_root / "runs" / replay_id
    out.mkdir(parents=True, exist_ok=True)
    write_json(out / "definition.json", definition)
    import csv as csv_module

    with open(out / "timeline.csv", "w", newline="") as handle:
        writer = csv_module.writer(handle)
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
        for event in events:
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
    print(json.dumps(definition, indent=2, sort_keys=True))
    return 0


def _resolve_handoff_gate(
    args: argparse.Namespace, source: RTCMSource
) -> tuple[dict[str, Any] | None, str]:
    if args.phase8_handoff is None:
        return None, ""
    payload = read_json(Path(args.phase8_handoff))
    decision = handoff_from_dict(payload)
    outcome = resolve_handoff(decision, [source])
    record = {
        "handoff": payload,
        "outcome": {
            "admitted": outcome.admitted,
            "reason": outcome.reason,
            "selected_source_id": outcome.selected_source_id,
        },
    }
    return record, decision.decision_fingerprint


def cmd_replay(args: argparse.Namespace) -> int:
    source = load_source(args.source)
    config = load_config(args.config)
    schedule = load_schedule(args.schedule, args.interval_ms)
    admission = admit_source(source, max_frame_length=config.max_frame_length)
    if admission.verdict in (AdmissionVerdict.REJECT, AdmissionVerdict.BLOCKED):
        print(json.dumps(admission.as_dict(), indent=2, sort_keys=True))
        return 2
    handoff_record, phase8_fp = _resolve_handoff_gate(args, source)
    if handoff_record is not None and not handoff_record["outcome"]["admitted"]:
        print(json.dumps(handoff_record, indent=2, sort_keys=True))
        return 3
    raw = Path(source.source_path).read_bytes()
    result = parse_stream(raw, max_frame_length=config.max_frame_length)
    parsed = result.frames
    inventory = build_inventory(result, parser_version=PARSER_VERSION)
    timing = classify_timing(
        source, schedule, nominal_interval_ms=args.interval_ms if schedule is None else None
    )
    events, _ = build_timeline(parsed, arrival_ms=schedule, nominal_interval_ms=args.interval_ms)
    fingerprint = config_fingerprint(config)
    plan = apply_plan(events, config, config_fingerprint=fingerprint)
    faults = FaultPlan(
        corrupt_sequence=args.fault_corrupt,
        truncate_after_sequence=args.fault_truncate,
        stall_consumer_after=args.fault_stall,
    )

    collected = CollectedRun()
    controller = ReplayController(
        plan=plan,
        config=config,
        source_id=source.source_id,
        station_id=source.station_id,
        mountpoint=source.mountpoint,
        source_bytes=raw,
        clock=FakeClock(),
        faults=faults,
        provenance={"source_id": source.source_id},
    )
    if args.phase8_handoff is not None and handoff_record is not None:
        mode = handoff_record["handoff"].get("mode")
        if mode == "NO_CORRECTION":
            executed = controller.metrics()
            assembled = assemble_metrics(inventory, executed, bytes_processed=len(raw))
            summary = {
                "replay_id": args.replay_id or f"replay-{source.source_id}",
                "outcome": "NO_CORRECTION_NO_STREAM",
                "frames_emitted": 0,
            }
            print(json.dumps(summary, indent=2, sort_keys=True))
            if not args.dry_run:
                out_root = default_out_root(args.out)
                replay_id = args.replay_id or f"replay-{source.source_id}"
                provenance = build_provenance(
                    source_sha256=source.sha256,
                    source_metadata=source.as_dict(),
                    frame_inventory_fingerprint=inventory.inventory_fingerprint,
                    phase8_decision_fingerprint=phase8_fp,
                    selected_correction_source="NO_CORRECTION",
                    replay_config_fingerprint=fingerprint,
                    execution_timestamp=utc_now_iso(),
                    git_commit=git_commit(),
                    working_tree_clean=working_tree_clean(),
                )
                write_run_bundle(
                    out_root,
                    replay_id,
                    definition={
                        "replay_id": replay_id,
                        "source": source.as_dict(),
                        "config": config.as_dict(),
                    },
                    admission=admission,
                    timeline=[],
                    metrics=assembled,
                    checkpoint=None,
                    provenance=provenance,
                    handoff=handoff_record,
                )
            return 0
    try:
        executed = controller.run(collected.consumer)
    except Exception as exc:  # noqa: BLE001 - faults surface as findings + nonzero exit
        print(json.dumps({"fault": str(exc), "findings": controller.findings}, indent=2))
        return 4
    assembled = assemble_metrics(inventory, executed, bytes_processed=len(raw))
    replay_id = args.replay_id or f"replay-{source.source_id}"
    checkpoint = controller.make_checkpoint(
        source_fingerprint=admission.source_fingerprint,
        config_fingerprint=fingerprint,
    )
    provenance = build_provenance(
        source_sha256=source.sha256,
        source_metadata=source.as_dict(),
        frame_inventory_fingerprint=inventory.inventory_fingerprint,
        phase8_decision_fingerprint=phase8_fp,
        selected_correction_source=source.source_id,
        replay_config_fingerprint=fingerprint,
        execution_timestamp=utc_now_iso(),
        git_commit=git_commit(),
        working_tree_clean=working_tree_clean(),
    )
    summary = {
        "replay_id": replay_id,
        "verdict": str(admission.verdict),
        "timing_quality": str(timing.quality),
        "frames_emitted": assembled.frames_emitted,
        "frames_dropped": assembled.frames_dropped,
        "duplicates": assembled.duplicates,
        "sequence_gaps": assembled.sequence_gaps,
        "note": "transport success != positioning success; no accuracy claimed",
    }
    if args.dry_run:
        print(json.dumps(summary, indent=2, sort_keys=True))
        return 0
    out_root = default_out_root(args.out)
    write_run_bundle(
        out_root,
        replay_id,
        definition={
            "replay_id": replay_id,
            "source": source.as_dict(),
            "config": config.as_dict(),
            "timing_quality": str(timing.quality),
            "config_fingerprint": fingerprint,
            "engine_version": ENGINE_VERSION,
        },
        admission=admission,
        timeline=plan.events[: controller.position],
        metrics=assembled,
        checkpoint=checkpoint,
        provenance=provenance,
        handoff=handoff_record,
    )
    append_summary_rows(
        out_root,
        run_rows=[
            {
                "replay_id": replay_id,
                "source_id": source.source_id,
                "mode": (handoff_record or {}).get("handoff", {}).get("mode", ""),
                "frames_emitted": assembled.frames_emitted,
                "frames_dropped": assembled.frames_dropped,
                "duplicates": assembled.duplicates,
                "sequence_gaps": assembled.sequence_gaps,
                "outcome": "COMPLETE",
            }
        ],
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


def cmd_resume(args: argparse.Namespace) -> int:
    out_root = default_out_root(args.out)
    run_dir = out_root / "runs" / args.replay_id
    definition = read_json(run_dir / "definition.json")
    checkpoint_raw = read_json(run_dir / "checkpoint.json")
    checkpoint = checkpoint_from_dict(checkpoint_raw)
    source = source_from_dict(definition["source"])
    config = config_from_dict(definition["config"])
    raw = Path(source.source_path).read_bytes()
    result = parse_stream(raw, max_frame_length=config.max_frame_length)
    parsed = result.frames
    schedule = load_schedule(args.schedule, args.interval_ms)
    events, _ = build_timeline(parsed, arrival_ms=schedule, nominal_interval_ms=args.interval_ms)
    fingerprint = config_fingerprint(config)
    plan = apply_plan(events, config, config_fingerprint=fingerprint)
    admission = admit_source(source, max_frame_length=config.max_frame_length)

    collected = CollectedRun()
    controller = ReplayController(
        plan=plan,
        config=config,
        source_id=source.source_id,
        station_id=source.station_id,
        mountpoint=source.mountpoint,
        source_bytes=raw,
        clock=FakeClock(),
        provenance={"source_id": source.source_id},
    )
    ok = controller.resume_from_checkpoint(
        checkpoint,
        source_fingerprint=checkpoint.source_fingerprint,
        config_fingerprint=checkpoint.config_fingerprint,
    )
    # Re-validate fingerprints against current inputs (cache invalidation).
    current = validate_checkpoint(
        checkpoint,
        source_fingerprint=admission.source_fingerprint,
        config_fingerprint=fingerprint,
    )
    if not current.valid or not ok:
        print(json.dumps({"resumed": False, "reason": current.reason}, indent=2))
        return 2
    try:
        executed = controller.run(collected.consumer)
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"fault": str(exc)}, indent=2))
        return 4
    inventory = build_inventory(result, parser_version=PARSER_VERSION)
    assembled = assemble_metrics(inventory, executed, bytes_processed=len(raw))
    new_checkpoint = controller.make_checkpoint(
        source_fingerprint=admission.source_fingerprint,
        config_fingerprint=fingerprint,
    )
    if args.dry_run:
        print(
            json.dumps(
                {
                    "resumed": True,
                    "frames_emitted": assembled.frames_emitted,
                    "checkpoint_resumes": 1,
                },
                indent=2,
            )
        )
        return 0
    write_json(run_dir / "checkpoint.json", new_checkpoint.as_dict())
    write_json(run_dir / "metrics.json", assembled.as_dict())
    print(
        json.dumps(
            {
                "resumed": True,
                "frames_emitted": assembled.frames_emitted,
                "checkpoint_resumes": 1,
            },
            indent=2,
        )
    )
    return 0


def cmd_summarize(args: argparse.Namespace) -> int:
    out_root = default_out_root(args.out)
    sources_dir = out_root / "sources"
    runs_dir = out_root / "runs"
    source_rows: list[dict[str, Any]] = []
    run_rows: list[dict[str, Any]] = []
    if sources_dir.is_dir():
        for child in sorted(sources_dir.iterdir()):
            validation = child / "validation.json"
            inventory = child / "inventory.json"
            definition = child / "source.json"
            if validation.is_file():
                payload = read_json(validation)
                inv = read_json(inventory) if inventory.is_file() else {}
                src = read_json(definition) if definition.is_file() else {}
                source_rows.append(
                    {
                        "source_id": child.name,
                        "source_type": src.get("source_type", ""),
                        "station_id": src.get("station_id", ""),
                        "verdict": payload.get("verdict", ""),
                        "frames_valid": inv.get("frames_valid", ""),
                        "sha256": src.get("sha256", ""),
                    }
                )
    if runs_dir.is_dir():
        for child in sorted(runs_dir.iterdir()):
            metrics = child / "metrics.json"
            definition = child / "definition.json"
            handoff_path = child / "phase8-handoff.json"
            if metrics.is_file():
                payload = read_json(metrics)
                definition_payload = read_json(definition) if definition.is_file() else {}
                source_payload = definition_payload.get("source", {})
                mode = ""
                if handoff_path.is_file():
                    handoff_payload = read_json(handoff_path)
                    inner = handoff_payload.get("handoff", handoff_payload)
                    if isinstance(inner, dict):
                        mode = str(inner.get("mode", ""))
                run_rows.append(
                    {
                        "replay_id": child.name,
                        "source_id": source_payload.get("source_id", "")
                        if isinstance(source_payload, dict)
                        else "",
                        "mode": mode,
                        "frames_emitted": payload.get("frames_emitted", ""),
                        "frames_dropped": payload.get("frames_dropped", ""),
                        "duplicates": payload.get("duplicates", ""),
                        "sequence_gaps": payload.get("sequence_gaps", ""),
                        "outcome": "COMPLETE",
                    }
                )
    summary = {
        "sources": len(source_rows),
        "runs": len(run_rows),
        "out": str(out_root / "summaries"),
    }
    if args.dry_run:
        print(json.dumps(summary, indent=2, sort_keys=True))
        return 0
    append_summary_rows(out_root, source_rows=source_rows, run_rows=run_rows)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Phase 9 recorded RTCM replay")
    sub = parser.add_subparsers(dest="op", required=True)
    for op in ("inspect", "validate", "index", "plan", "replay", "resume", "summarize"):
        child = sub.add_parser(op)
        child.add_argument("--source", default=None)
        child.add_argument("--config", default=None)
        child.add_argument("--out", default=None)
        child.add_argument("--replay-id", default=None)
        child.add_argument("--phase8-handoff", default=None)
        child.add_argument("--schedule", default=None)
        child.add_argument("--interval-ms", type=int, default=1000)
        child.add_argument("--dry-run", action="store_true")
        child.add_argument("--fault-corrupt", type=int, default=None)
        child.add_argument("--fault-truncate", type=int, default=None)
        child.add_argument("--fault-stall", type=int, default=None)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if args.op == "inspect":
        return cmd_inspect(args)
    if args.op == "validate":
        return cmd_validate(args)
    if args.op == "index":
        return cmd_index(args)
    if args.op == "plan":
        return cmd_plan(args)
    if args.op == "replay":
        return cmd_replay(args)
    if args.op == "resume":
        return cmd_resume(args)
    if args.op == "summarize":
        return cmd_summarize(args)
    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
