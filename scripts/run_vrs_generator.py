#!/usr/bin/env python3
"""Offline Phase 7 VRS scientific controls; every response is JSON."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
for package in ("vrs_generator", "atmospheric_spatial_model", "single_base_rtk"):
    sys.path.insert(0, str(REPO / "research" / package / "src"))

from nlgcp_vrs.models import Definition  # noqa: E402
from nlgcp_vrs.pipeline import generate, plan, read_json  # noqa: E402
from nlgcp_vrs.validation import validate, verified_validation  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=os.environ.get("NLGCP_DATA_ROOT"))
    parser.add_argument("--rtklib-source", type=Path, default=os.environ.get("RTKLIB_SOURCE"))
    parser.add_argument("command", choices=("inspect", "plan", "generate", "validate", "summarize"))
    parser.add_argument("--definition", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    try:
        if args.data_root is None or args.rtklib_source is None:
            raise ValueError(
                "--data-root/NLGCP_DATA_ROOT and --rtklib-source/RTKLIB_SOURCE required"
            )
        definition = Definition.model_validate(read_json(args.definition))
        result: dict[str, Any]
        if args.command in ("inspect", "plan") or (args.dry_run and args.command == "summarize"):
            result = plan(args.data_root, definition, REPO, args.rtklib_source)
        elif args.command == "validate":
            result = validate(
                args.data_root, definition, REPO, args.rtklib_source, dry_run=args.dry_run
            )
        elif args.command == "summarize":
            from nlgcp_vrs.pipeline import experiment_dir, read_verified_outputs

            planned = plan(args.data_root, definition, REPO, args.rtklib_source)
            out = experiment_dir(args.data_root, definition)
            result = read_verified_outputs(out, planned["fingerprint"])
            if (out / "validation.json").exists():
                result["validation"] = verified_validation(out, planned["fingerprint"])
        else:
            result = generate(
                args.data_root, definition, REPO, args.rtklib_source, dry_run=args.dry_run
            )
    except (
        OSError,
        ValueError,
        KeyError,
        TypeError,
        StopIteration,
        subprocess.SubprocessError,
    ) as exc:
        result = {"status": "BLOCKED", "reason": str(exc)}
    print(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))
    return 2 if result.get("status") == "BLOCKED" else 0


if __name__ == "__main__":
    raise SystemExit(main())
