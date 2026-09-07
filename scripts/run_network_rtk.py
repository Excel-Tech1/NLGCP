#!/usr/bin/env python3
"""Operator CLI for Phase 5 offline network RTK processing."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "research" / "network_rtk" / "src"))
sys.path.insert(0, str(REPO_ROOT / "research" / "single_base_rtk" / "src"))
sys.path.insert(0, str(REPO_ROOT / "research" / "gnss_qc" / "src"))
sys.path.insert(0, str(REPO_ROOT / "apps" / "api" / "src"))

from nlgcp_network_rtk import MIN_REFERENCE_STATIONS  # noqa: E402
from nlgcp_network_rtk.admission import admit_day  # noqa: E402
from nlgcp_network_rtk.io import resolve_data_root  # noqa: E402
from nlgcp_network_rtk.models import (  # noqa: E402
    NetworkExperimentDefinition,
    definition_from_dict,
)
from nlgcp_network_rtk.runner import (  # noqa: E402
    plan_experiment,
    run_experiment,
    validate_experiment,
)
from nlgcp_network_rtk.summarize import summarize_data_root  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, help="Override NLGCP_DATA_ROOT")
    sub = parser.add_subparsers(dest="command", required=True)

    plan = sub.add_parser("plan", help="Dry-run admission/geometry/overlap planning")
    plan.add_argument("--definition", type=Path)
    plan.add_argument("--year", type=int)
    plan.add_argument("--doy", type=int)
    plan.add_argument("--rover", type=str)
    plan.add_argument("--references", nargs="+", default=[])
    plan.add_argument("--diagnostic", action="store_true")

    validate = sub.add_parser("validate", help="Validate an experiment definition")
    validate.add_argument("--definition", type=Path, required=True)

    run = sub.add_parser("run", help="Execute a network experiment (multi-baseline)")
    run.add_argument("--definition", type=Path, required=True)
    run.add_argument("--workers", type=int, default=2)
    run.add_argument("--dry-run", action="store_true")

    discover = sub.add_parser("discover", help="Discover eligible network days")
    discover.add_argument("--min-stations", type=int, default=MIN_REFERENCE_STATIONS)

    summary = sub.add_parser("summarize", help="Summarize processed network experiments")
    _ = summary
    return parser


def main() -> int:
    args = build_parser().parse_args()
    data_root = resolve_data_root(args.data_root)
    if args.command == "discover":
        print(json.dumps(discover_eligible(data_root, args.min_stations), indent=2, sort_keys=True))
        return 0
    if args.command == "summarize":
        print(json.dumps(summarize_data_root(data_root), indent=2, sort_keys=True))
        return 0
    definition = load_definition(args, data_root)
    if args.command == "plan":
        print(json.dumps(plan_experiment(data_root, definition), indent=2, sort_keys=True))
        return 0
    if args.command == "validate":
        print(json.dumps(validate_experiment(data_root, definition), indent=2, sort_keys=True))
        return 0
    if args.command == "run":
        manifest = run_experiment(
            data_root, definition, workers=args.workers, dry_run=args.dry_run
        )
        print(json.dumps({
            "experiment_id": manifest["experiment_id"],
            "status": manifest["status"],
            "baselines": manifest.get("baselines", []),
            "block_reason": manifest.get("block_reason"),
        }, indent=2, sort_keys=True))
        return 0
    raise SystemExit(f"unknown command {args.command}")


def load_definition(
    args: argparse.Namespace, data_root: Path
) -> NetworkExperimentDefinition:
    if getattr(args, "definition", None):
        payload: dict[str, Any] = json.loads(Path(args.definition).read_text(encoding="utf-8"))
        payload = _default_navigation(payload, data_root)
        return definition_from_dict(payload)
    # Ad-hoc plan from flags: build a minimal definition for discovery/planning.
    year = int(args.year or 2024)
    doy = int(args.doy or 26)
    rover = str(args.rover or "PHRI00NGA")
    refs = list(args.references) or ["ABFC00NGA", "EKAK00NGA", "MGBO00NGA"]
    nav_product = f"external-products/brdc/{year}/BRDC00IGS_R_{year}{doy:03d}0000_01D_MN.rnx.gz"
    return NetworkExperimentDefinition(
        experiment_id=f"net-{year}d{doy:03d}-{rover[:4].lower()}-plan",
        research_question="Ad-hoc network planning probe (dry run).",
        year=year,
        day_of_year=doy,
        processing_mode="static",
        reference_stations=tuple(refs),
        test_station=rover,
        navigation_products=(nav_product,),
        start_time_utc=f"{year}-01-01T00:00:00Z",
        end_time_utc=f"{year}-01-01T23:59:30Z",
        sampling_interval_seconds=30.0,
        coordinate_frame="IGS20",
        coordinate_epoch="",
        qc_profile="network_rtk",
        minimum_reference_station_count=MIN_REFERENCE_STATIONS,
        diagnostic=bool(getattr(args, "diagnostic", False)),
    )


def _default_navigation(payload: dict[str, Any], data_root: Path) -> dict[str, Any]:
    _ = data_root
    return payload


def discover_eligible(data_root: Path, min_stations: int) -> dict[str, Any]:
    days: list[dict[str, Any]] = []
    for doy in range(1, 367):
        summary = admit_day(data_root, year=2024, day_of_year=doy)
        admitted = sorted(r.station_id for r in summary.admitted)
        if len(admitted) >= min_stations:
            days.append({"year": 2024, "doy": doy, "admitted": admitted, "count": len(admitted)})
    blocked_verdict = "Phase 5 real network experiment: BLOCKED"
    verdict = "eligible network exists" if days else blocked_verdict
    return {
        "qc_profile": "network_rtk",
        "minimum_reference_stations": min_stations,
        "eligible_days": days,
        "eligible_day_count": len(days),
        "verdict": verdict,
    }


if __name__ == "__main__":
    raise SystemExit(main())
