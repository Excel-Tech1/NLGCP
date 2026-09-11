#!/usr/bin/env python3
"""Operator CLI for Phase 10 live CORS / NTRIP ingestion.

Safe operations only: ``sourcetable`` (bounded retrieval), ``probe``
(bounded, non-invasive stream check), ``capture`` (bounded authentic
recording), ``validate-capture`` (offline), ``summarize`` (offline).
Every operation supports ``--dry-run`` (validate configuration without
authenticating or streaming; never claims connectivity).
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "research" / "ntrip_ingestion" / "src"))

from nlgcp_ntrip_ingest import ENGINE_VERSION  # noqa: E402
from nlgcp_ntrip_ingest.admission import map_station  # noqa: E402
from nlgcp_ntrip_ingest.auth import redact_text  # noqa: E402
from nlgcp_ntrip_ingest.client import NtripClient  # noqa: E402
from nlgcp_ntrip_ingest.models import NtripConfig, config_from_env  # noqa: E402
from nlgcp_ntrip_ingest.reporting import summarize_capture, validate_capture  # noqa: E402
from nlgcp_ntrip_ingest.sourcetable import find_stream  # noqa: E402


def _redact(obj: Any, secrets: tuple[str, ...]) -> Any:
    if isinstance(obj, str):
        return redact_text(obj, secrets)
    if isinstance(obj, dict):
        return {k: _redact(v, secrets) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_redact(v, secrets) for v in obj]
    return obj


def _emit(payload: dict[str, Any], secrets: tuple[str, ...]) -> int:
    print(json.dumps(_redact(payload, secrets), indent=2, sort_keys=True, default=str))
    return 0


def _client_from_env(args: argparse.Namespace) -> tuple[NtripClient, NtripConfig, tuple[str, ...]]:
    env = dict(os.environ)
    if args.host:
        env["NLGCP_NTRIP_HOST"] = args.host
    if args.port:
        env["NLGCP_NTRIP_PORT"] = str(args.port)
    if args.mountpoint:
        env["NLGCP_NTRIP_MOUNTPOINT"] = args.mountpoint
    config = config_from_env(env)
    secrets = tuple(s for s in (config.password,) if s)
    registry: dict[str, str] = {}
    if args.station_map:
        for item in args.station_map.split(","):
            if "=" in item:
                mount, station = item.split("=", 1)
                registry[mount.strip()] = station.strip()
    client = NtripClient(
        config,
        provider=args.provider,
        station_registry=registry,
        authorization_basis=args.auth_basis
        or ("anonymous" if not config.username else "env-credentials"),
    )
    return client, config, secrets


def _common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--host", default="", help="Caster host (or NLGCP_NTRIP_HOST)")
    parser.add_argument("--port", type=int, default=0, help="Caster port (or NLGCP_NTRIP_PORT)")
    parser.add_argument("--mountpoint", default="", help="Mountpoint (or NLGCP_NTRIP_MOUNTPOINT)")
    parser.add_argument("--provider", default="unknown", help="Provider label for provenance")
    parser.add_argument("--auth-basis", default="", help="Authorization basis description")
    parser.add_argument("--station-map", default="", help="mount=STATION,... registry mapping")
    parser.add_argument("--dry-run", action="store_true", help="Validate config only; no network")


def cmd_sourcetable(args: argparse.Namespace) -> int:
    client, config, secrets = _client_from_env(args)
    if args.dry_run:
        return _emit({"op": "sourcetable", **client.dry_run()}, secrets)
    problems = config.validate()
    if problems:
        return _emit({"op": "sourcetable", "ok": False, "config_problems": problems}, secrets)
    try:
        table, provenance = client.fetch_sourcetable()
    except Exception as exc:  # noqa: BLE001 - operator-facing failure record
        return _emit({"op": "sourcetable", "ok": False,
                      "reason": f"{type(exc).__name__}: {exc}"}, secrets)
    entry = find_stream(table, config.mountpoint) if config.mountpoint else None
    mapping = map_station(config.mountpoint, client._registry) if config.mountpoint else None
    return _emit({"op": "sourcetable", "ok": True, "engine_version": ENGINE_VERSION,
                  "provenance": provenance, "table": table.as_dict(),
                  "selected_stream": entry.as_dict() if entry else None,
                  "mapping": mapping.as_dict() if mapping else None}, secrets)


def cmd_probe(args: argparse.Namespace) -> int:
    client, config, secrets = _client_from_env(args)
    if args.dry_run:
        return _emit({"op": "probe", **client.dry_run()}, secrets)
    result = client.probe_stream(duration_s=args.duration, max_bytes=args.max_bytes)
    return _emit({"op": "probe", "ok": result.ok,
                  "failure": str(result.failure) if result.failure else None,
                  "reason": result.reason, "bytes_received": result.bytes_received,
                  "frames_received": result.frames_received,
                  "frames_crc_valid": result.frames_crc_valid,
                  "frames_crc_invalid": result.frames_crc_invalid,
                  "message_types": result.message_types,
                  "duration_s": result.duration_s,
                  "transitions": client.transitions}, secrets)


def cmd_capture(args: argparse.Namespace) -> int:
    client, config, secrets = _client_from_env(args)
    if args.dry_run:
        plan = client.dry_run()
        plan["capture_plan"] = {"capture_id": args.capture_id, "duration_s": args.duration,
                                "output_root": args.output_root}
        return _emit({"op": "capture", **plan}, secrets)
    def _shutdown(_signum: int, _frame: Any) -> None:
        client.request_shutdown()

    previous_term = signal.signal(signal.SIGTERM, _shutdown)
    previous_int = signal.signal(signal.SIGINT, _shutdown)
    try:
        result = client.capture_stream(
            args.output_root, capture_id=args.capture_id,
            duration_s=args.duration, max_bytes=args.max_bytes,
        )
    except (ValueError, PermissionError) as exc:
        return _emit({"op": "capture", "ok": False, "reason": str(exc),
                      "transitions": client.transitions}, secrets)
    finally:
        signal.signal(signal.SIGTERM, previous_term)
        signal.signal(signal.SIGINT, previous_int)
    return _emit({"op": "capture", "ok": True, "status": result.status,
                  "capture_dir": result.capture_dir, "metadata": result.metadata,
                  "metrics": result.metrics, "admission": result.admission,
                  "frames_forwarded": result.frames_forwarded,
                  "transitions": client.transitions}, secrets)


def cmd_validate_capture(args: argparse.Namespace) -> int:
    report = validate_capture(Path(args.capture_dir))
    return _emit({"op": "validate-capture", **report}, ())


def cmd_summarize(args: argparse.Namespace) -> int:
    report = summarize_capture(Path(args.capture_dir))
    return _emit({"op": "summarize", **report}, ())


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Phase 10 live NTRIP ingestion CLI")
    sub = parser.add_subparsers(dest="op", required=True)
    p_table = sub.add_parser("sourcetable", help="Bounded source-table retrieval")
    _common(p_table)
    p_table.set_defaults(func=cmd_sourcetable)
    p_probe = sub.add_parser("probe", help="Bounded non-invasive stream probe")
    _common(p_probe)
    p_probe.add_argument("--duration", type=float, default=5.0)
    p_probe.add_argument("--max-bytes", type=int, default=65536)
    p_probe.set_defaults(func=cmd_probe)
    p_cap = sub.add_parser("capture", help="Bounded authentic capture")
    _common(p_cap)
    p_cap.add_argument("--capture-id", default="pilot")
    p_cap.add_argument("--output-root", default=".")
    p_cap.add_argument("--duration", type=float, default=20.0)
    p_cap.add_argument("--max-bytes", type=int, default=1048576)
    p_cap.set_defaults(func=cmd_capture)
    p_val = sub.add_parser("validate-capture", help="Offline capture validation")
    p_val.add_argument("--capture-dir", required=True)
    p_val.set_defaults(func=cmd_validate_capture)
    p_sum = sub.add_parser("summarize", help="Offline capture summary")
    p_sum.add_argument("--capture-dir", required=True)
    p_sum.set_defaults(func=cmd_summarize)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
