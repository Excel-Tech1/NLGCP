#!/usr/bin/env python3
"""Milestone B-09 CLI: Nigerian CORS Provider Assessment & Stage A Recorded Ingestion.

Strictly read-only and credential-free:
- Assesses Nigerian CORS providers (SOGPOS / sacredioncors.com, NIGNET / OSGoF,
  CORSLocate / corslocate.ng, and local Stage A) fail-closed;
- Never opens external internet connections when Stage B credentials/authorization
  are absent (reports ``BLOCKED_EXTERNAL_ACCESS`` honestly);
- Optionally ingests a local recorded RTCM 3.x file through Phase 10
  ``StreamingFramer`` into B-08's ``BoundedEventBus`` (``nlgcp.events.v1``).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[1]
for _rel in (
    "research/ntrip_ingestion/src",
    "services/correction-service/src",
    "research/rtcm_replay/src",
    "research/rtcm_generation/src",
):
    _p = str(_REPO_ROOT / _rel)
    if _p not in sys.path:
        sys.path.insert(0, _p)

from nlgcp_correction_service.events import BoundedEventBus  # noqa: E402
from nlgcp_ntrip_ingest.b09_ingestion import (  # noqa: E402
    ingest_recorded_rtcm_file_to_event_bus,
)
from nlgcp_ntrip_ingest.providers import (  # noqa: E402
    NIGERIAN_CORS_PROVIDERS,
    evaluate_stage_b_provider_gate,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="B-09 Nigerian CORS Provider Assessment & Stage A Recorded Ingestion"
    )
    parser.add_argument(
        "--recorded-rtcm",
        type=Path,
        default=None,
        help="Optional local recorded .rtcm3 file for Stage A replay ingestion into B-08 event bus",
    )
    parser.add_argument("--mountpoint", default="NLGCP_VRS_EXP")
    parser.add_argument("--station-id", default="EKAK00NGA")
    parser.add_argument("--out", type=Path, default=None, help="Optional JSON output report path")
    args = parser.parse_args()

    provider_assessments = [
        {
            "profile": profile.as_dict(),
            "stage_b_gate": evaluate_stage_b_provider_gate(profile.provider_code).as_dict(),
        }
        for profile in NIGERIAN_CORS_PROVIDERS
    ]

    report: dict[str, Any] = {
        "schema_version": "nlgcp.b09.cors_assessment.v1",
        "operational_approved": False,
        "external_network_dialed": False,
        "providers": provider_assessments,
        "stage_a_recorded_ingestion": None,
    }

    if args.recorded_rtcm is not None:
        bus = BoundedEventBus(max_retained=10_000)
        summary, _ = ingest_recorded_rtcm_file_to_event_bus(
            args.recorded_rtcm,
            event_bus=bus,
            mountpoint=args.mountpoint,
            station_registry={args.mountpoint: args.station_id},
            data_classification="RESEARCH_VALIDATION",
            allow_unverified_station_events=True,
        )
        report["stage_a_recorded_ingestion"] = {
            "summary": summary.as_dict(),
            "event_bus_stats": bus.stats(),
        }

    rendered = json.dumps(report, indent=2, sort_keys=True)
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
