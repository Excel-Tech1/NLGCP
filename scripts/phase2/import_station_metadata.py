#!/usr/bin/env python3
"""Import a provenance-controlled Phase 2 station metadata package."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import psycopg
from nlgcp_api.config import Settings, resolve_data_root
from nlgcp_api.station_metadata.provenance import (
    ProvenanceError,
    resolve_package_sources,
)
from nlgcp_api.station_metadata.repository import (
    StationMetadataConflictError,
    StationMetadataRepository,
)
from nlgcp_api.station_metadata.validation import (
    StationMetadataValidationError,
    load_station_import_package,
)
from psycopg.conninfo import make_conninfo


def main(argv: list[str] | None = None) -> int:
    """Run the import CLI."""

    parser = argparse.ArgumentParser(
        description="Import a verified station metadata JSON package."
    )
    parser.add_argument(
        "package",
        type=Path,
        help="Path to the canonical station metadata JSON package.",
    )
    args = parser.parse_args(argv)

    try:
        data_root = resolve_data_root(Settings())
        package = load_station_import_package(args.package)
        resolved_sources = resolve_package_sources(package, data_root)
        with psycopg.connect(_database_conninfo()) as connection:
            result = StationMetadataRepository(connection).import_package(
                package,
                resolved_sources,
            )
    except (
        RuntimeError,
        StationMetadataValidationError,
        ProvenanceError,
        StationMetadataConflictError,
        psycopg.Error,
    ) as exc:
        print(f"station metadata import failed: {exc}", file=sys.stderr)
        return 1

    print(
        "station metadata import complete: "
        f"provider_id={result.provider_id} "
        f"station_id={result.station_id} "
        f"inserted_sources={result.inserted_sources} "
        f"inserted_provider={result.inserted_provider} "
        f"inserted_station={result.inserted_station} "
        f"inserted_coordinates={result.inserted_coordinates} "
        f"inserted_equipment={result.inserted_equipment}"
    )
    return 0


def _database_conninfo() -> str:
    required = ("POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB")
    missing = [name for name in required if not os.environ.get(name)]
    if missing:
        raise RuntimeError(
            "missing required PostgreSQL environment variables: "
            + ", ".join(missing)
        )
    return make_conninfo(
        "",
        user=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"],
        dbname=os.environ["POSTGRES_DB"],
        host=os.environ.get("POSTGRES_HOST", "127.0.0.1"),
        port=os.environ.get("POSTGRES_PORT", "15432"),
    )


if __name__ == "__main__":
    raise SystemExit(main())
