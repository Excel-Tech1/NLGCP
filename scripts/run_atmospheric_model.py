#!/usr/bin/env python3
"""Operator CLI for Phase 6 atmospheric & spatial error modelling."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "research" / "atmospheric_spatial_model" / "src"))

from nlgcp_atmospheric_model.pipeline import (  # noqa: E402
    derive_experiment,
    fit_experiment,
    inspect_experiment,
    load_definition_from_path,
    plan_experiment,
    resolve_data_root,
    summarize_data_root,
    validate_experiment,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, help="Override NLGCP_DATA_ROOT")
    sub = parser.add_subparsers(dest="command", required=True)

    for name, help_text in [
        ("inspect", "Audit observable availability (RINEX headers, admission)"),
        ("plan", "Validate definition, admission, geometry, LOOCV folds"),
        ("derive", "Extract satellite observables, combinations, spatial records"),
        ("fit", "Fit spatial interpolation models at the target"),
        ("validate", "Leave-one-out cross-validation and model comparison"),
        ("summarize", "Summarize processed atmospheric-model experiments"),
    ]:
        cmd = sub.add_parser(name, help=help_text)
        if name not in ("summarize",):
            cmd.add_argument("--definition", type=Path, required=True)
        cmd.add_argument("--dry-run", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    data_root = resolve_data_root(args.data_root)
    if args.command == "summarize":
        print(json.dumps(summarize_data_root(data_root), indent=2, sort_keys=True))
        return 0
    definition = load_definition_from_path(args.definition)
    if args.command == "inspect":
        payload: dict[str, Any] = inspect_experiment(data_root, definition, REPO_ROOT)
    elif args.command == "plan":
        payload = plan_experiment(data_root, definition, REPO_ROOT)
    elif args.command == "derive":
        payload = derive_experiment(data_root, definition, REPO_ROOT, dry_run=args.dry_run)
    elif args.command == "fit":
        payload = fit_experiment(data_root, definition, REPO_ROOT, dry_run=args.dry_run)
    elif args.command == "validate":
        payload = validate_experiment(data_root, definition, REPO_ROOT, dry_run=args.dry_run)
    else:
        raise SystemExit(f"unknown command {args.command}")
    print(json.dumps(payload, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
