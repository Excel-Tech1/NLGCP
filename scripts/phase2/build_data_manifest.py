#!/usr/bin/env python3
"""Build a deterministic report-only scientific-data manifest."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path, PurePosixPath

from nlgcp_api.config import Settings, resolve_data_root
from nlgcp_api.data_manifest import (
    build_data_manifest,
    default_manifest_output_path,
    write_data_manifest,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build a deterministic report-only scientific-data manifest."
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help=(
            "Output JSON path. Defaults to "
            "NLGCP_DATA_ROOT/manifests/scientific-data-manifest.json."
        ),
    )
    args = parser.parse_args(argv)

    try:
        data_root = resolve_data_root(Settings())
        output_path = args.output or default_manifest_output_path(data_root)
        excluded = _excluded_output_path(output_path, data_root)
        manifest = build_data_manifest(data_root, exclude_paths=excluded)
        write_data_manifest(manifest, output_path)
    except (RuntimeError, ValueError) as exc:
        print(f"data manifest build failed: {exc}", file=sys.stderr)
        return 1

    print(
        f"data manifest written: {output_path} "
        f"({len(manifest.artifacts)} artifacts, "
        f"{len(manifest.duplicate_checksums)} duplicate checksum groups)"
    )
    return 0


def _excluded_output_path(output_path: Path, data_root: Path) -> set[PurePosixPath]:
    try:
        return {PurePosixPath(output_path.resolve().relative_to(data_root).as_posix())}
    except ValueError:
        return set()


if __name__ == "__main__":
    raise SystemExit(main())
