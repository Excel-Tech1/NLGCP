#!/usr/bin/env python3
"""Reproducible local Phase 11 -> Phase 12 NTRIP -> RTKLIB synthetic demo CLI.

SYNTHETIC TEST DATA — NOT VALID FOR NAVIGATION OR SCIENTIFIC POSITIONING RESULTS.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

_SERVICE_SRC = Path(__file__).resolve().parents[1] / "services" / "correction-service" / "src"
if str(_SERVICE_SRC) not in sys.path:
    sys.path.insert(0, str(_SERVICE_SRC))

from nlgcp_correction_service.pipeline import run_local_end_to_end_demo  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run the local loopback-only Phase 12 synthetic NTRIP integration demo "
            "(SYNTHETIC TEST DATA — NOT VALID FOR NAVIGATION OR SCIENTIFIC POSITIONING)."
        )
    )
    parser.add_argument(
        "--ntrip-version",
        choices=("1.0", "2.0"),
        default="2.0",
        help="NTRIP protocol version for the local loopback client (default: 2.0).",
    )
    parser.add_argument(
        "--mountpoint",
        default="NLGCP_TEST",
        help="Synthetic mountpoint name (default: NLGCP_TEST).",
    )
    args = parser.parse_args()

    rtklib_env = os.environ.get("RTKLIB_SOURCE")
    rtklib_source = Path(rtklib_env) if rtklib_env else None
    repo_root = Path(__file__).resolve().parents[1]

    report = run_local_end_to_end_demo(
        ntrip_version=args.ntrip_version,
        mountpoint=args.mountpoint,
        rtklib_source=rtklib_source,
        repo_root=repo_root,
    )
    payload = {
        "ok": report.ok,
        "mountpoint": report.mountpoint,
        "sent_message_numbers": list(report.sent_message_numbers),
        "received_message_numbers": list(report.received_message_numbers),
        "byte_exact_match": report.byte_exact_match,
        "caster_diagnostics": report.caster_diagnostics,
        "client_diagnostics": report.client_result.diagnostics,
        "rtklib_validation": report.rtklib_validation,
        "scientific_readiness": report.scientific_readiness,
    }
    print(json.dumps(payload, indent=2, sort_keys=True, default=str))
    return 0 if report.ok else 1


if __name__ == "__main__":
    sys.exit(main())
