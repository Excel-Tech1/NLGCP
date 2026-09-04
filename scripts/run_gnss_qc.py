#!/usr/bin/env python3
"""Operator CLI for Phase 4 GNSS QC and station-health processing."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from nlgcp_gnss_qc.aggregate import summarize_profile
from nlgcp_gnss_qc.dataset import load_session_inputs
from nlgcp_gnss_qc.engine import (
    plan_dataset,
    profile_objects,
    resolve_data_root,
    run_dataset,
    select_sessions,
)

DEFAULT_PROFILES = ["archive", "single_base_rtk", "network_rtk"]


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--data-root", type=Path, help="Override NLGCP_DATA_ROOT")
    result.add_argument("--profile-config", type=Path)
    subparsers = result.add_subparsers(dest="command", required=True)

    for name in ("session", "station", "date-range", "dataset"):
        command = subparsers.add_parser(name)
        command.add_argument("--profiles", nargs="+", default=DEFAULT_PROFILES)
        command.add_argument("--dry-run", action="store_true")
        command.add_argument(
            "--stream-only",
            action="store_true",
            help="Analyse through a conversion pipe without retaining converted observations",
        )
        if name in {"session", "station"}:
            command.add_argument("--station", required=True)
        if name == "session":
            command.add_argument("--doy", required=True, type=int)
        if name == "date-range":
            command.add_argument("--start-doy", required=True, type=int)
            command.add_argument("--end-doy", required=True, type=int)

    summary = subparsers.add_parser("summarize")
    summary.add_argument("--profile", required=True, choices=DEFAULT_PROFILES)
    return result


def main() -> int:
    args = parser().parse_args()
    data_root = resolve_data_root(args.data_root)
    if args.command == "summarize":
        print(json.dumps(summarize_profile(data_root, args.profile), indent=2, sort_keys=True))
        return 0

    profiles = profile_objects(args.profiles, args.profile_config)
    sessions = load_session_inputs(data_root)
    if args.command == "session":
        sessions = select_sessions(
            sessions, station_ids={args.station}, start_doy=args.doy, end_doy=args.doy
        )
    elif args.command == "station":
        sessions = select_sessions(sessions, station_ids={args.station})
    elif args.command == "date-range":
        sessions = select_sessions(sessions, start_doy=args.start_doy, end_doy=args.end_doy)
    if not sessions:
        raise SystemExit("selection contains no canonical observation sessions")
    if args.dry_run:
        print(
            json.dumps(
                plan_dataset(data_root, sessions, profiles, convert=not args.stream_only),
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    rows = run_dataset(data_root, sessions, profiles, convert=not args.stream_only)
    counts: dict[str, dict[str, int]] = {}
    for row in rows:
        profile = row["qc_profile"]["name"]
        classification = row["overall_classification"]
        counts.setdefault(profile, {}).setdefault(classification, 0)
        counts[profile][classification] += 1
    print(json.dumps({"profile_results": len(rows), "counts": counts}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
