#!/usr/bin/env python3
"""Discover RINEX files under NLGCP_DATA_ROOT and write an inventory manifest."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from nlgcp_api.config import Settings, resolve_data_root
from nlgcp_api.rinex_inventory import (
    default_inventory_output_path,
    discover_rinex_inventory,
    write_inventory,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Create a report-only RINEX inventory manifest."
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output JSON path. Defaults to NLGCP_DATA_ROOT/manifests/rinex-inventory.json.",
    )
    args = parser.parse_args(argv)

    try:
        data_root = resolve_data_root(Settings())
        output_path = args.output or default_inventory_output_path(data_root)
        records = discover_rinex_inventory(data_root)
        write_inventory(records, output_path)
    except RuntimeError as exc:
        print(f"RINEX inventory discovery failed: {exc}", file=sys.stderr)
        return 1

    print(f"RINEX inventory written: {output_path} ({len(records)} records)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
