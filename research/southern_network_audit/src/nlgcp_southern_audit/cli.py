"""Command line entry point for a local Southern Nigeria archive audit."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from .pipeline import run_audit


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--station-registry", type=Path)
    parser.add_argument(
        "--southern-max-latitude",
        type=float,
        default=8.5,
        help="Approximate geographic inclusion bound for Southern Nigeria geometry only.",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=4,
        help="Concurrent independent ZIP member readers used for hashes and epoch scans.",
    )
    args = parser.parse_args()
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    output = args.output_root / f"run-{stamp}"
    summary = run_audit(
        args.archive,
        output,
        args.station_registry,
        args.southern_max_latitude,
        args.workers,
    )
    print(json.dumps({"output": str(output), "summary": summary}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
