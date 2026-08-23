"""CLI entry point for Phase 3 single-base RTK experiment preparation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from nlgcp_single_base.coordinates import EcefCoordinate, GeodeticCoordinate
from nlgcp_single_base.io import resolve_data_root
from nlgcp_single_base.models import (
    ExperimentDefinition,
    NavigationInput,
    Phase2Gate,
    ProcessingMode,
    StationCoordinate,
    StationInput,
)
from nlgcp_single_base.pipeline import prepare_or_run_experiment


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("definition", type=Path, help="JSON experiment definition")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="prepare artefacts without RTKLIB execution",
    )
    args = parser.parse_args()

    definition = _load_definition(args.definition)
    manifest = prepare_or_run_experiment(definition, resolve_data_root(), dry_run=args.dry_run)
    print(
        json.dumps(
            {"experiment_id": manifest["experiment_id"], "status": manifest["execution_status"]}
        )
    )


def _load_definition(path: Path) -> ExperimentDefinition:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return ExperimentDefinition(
        experiment_id=payload["experiment_id"],
        research_question=payload["research_question"],
        processing_mode=ProcessingMode(payload["processing_mode"]),
        start_time_utc=payload["start_time_utc"],
        end_time_utc=payload["end_time_utc"],
        sampling_rate_hz=float(payload["sampling_rate_hz"]),
        base=_station(payload["base"]),
        rover=_station(payload["rover"]),
        navigation=[
            NavigationInput(Path(item["path"]), item.get("sha256"))
            for item in payload["navigation"]
        ],
        phase2_gate=Phase2Gate(**payload.get("phase2_gate", {})),
        notes=payload.get("notes", ""),
        extra_metadata=payload.get("extra_metadata", {}),
    )


def _station(payload: dict[str, Any]) -> StationInput:
    return StationInput(
        station_id=payload["station_id"],
        coordinate=_coordinate(payload["coordinate"]),
        observation_path=Path(payload["observation_path"]),
        metadata_version=payload["metadata_version"],
        observation_sha256=payload.get("observation_sha256"),
    )


def _coordinate(payload: dict[str, Any]) -> StationCoordinate:
    ecef_payload = payload.get("ecef")
    geodetic_payload = payload.get("geodetic")
    return StationCoordinate(
        reference_frame=payload["reference_frame"],
        coordinate_epoch=payload["coordinate_epoch"],
        ecef=EcefCoordinate(**ecef_payload) if ecef_payload else None,
        geodetic=GeodeticCoordinate(**geodetic_payload) if geodetic_payload else None,
    )


if __name__ == "__main__":
    main()
