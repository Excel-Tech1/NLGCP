"""Shared synthetic fixtures for Phase 5 tests.

SYNTHETIC TEST DATA — NOT VALID FOR SCIENTIFIC RESULTS.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

SYNTHETIC_LABEL = "SYNTHETIC TEST DATA — NOT VALID FOR SCIENTIFIC RESULTS"


def write_qc_result(
    data_root: Path,
    *,
    station_id: str,
    year: int = 2024,
    doy: int = 26,
    classification: str = "ACCEPT",
    first_epoch: str = "2024-01-26T00:00:00Z",
    last_epoch: str = "2024-01-26T23:59:30Z",
    interval: float = 30.0,
    epochs: int = 2880,
    fingerprint: str = "synthetic-fingerprint",
    scientifically_valid: bool = True,
    nav_rel: str | None = "external-products/brdc/2024/BRDC00IGS_R_20240260000_01D_MN.rnx.gz",
    converted_name: str | None = None,
) -> Path:
    directory = (
        data_root / "processed" / "qc" / "profiles" / "network_rtk"
        / "sessions" / str(year) / station_id / f"{doy:03d}"
    )
    directory.mkdir(parents=True, exist_ok=True)
    obs_name = converted_name or f"{station_id[:4]}0260.24O"
    converted_path = (
        data_root / "working" / "qc-converted" / str(year) / station_id / f"{doy:03d}" / obs_name
    )
    converted_path.parent.mkdir(parents=True, exist_ok=True)
    converted_path.write_text("synthetic observation\n", encoding="utf-8")
    payload: dict[str, Any] = {
        "station_identity": {
            "canonical_station_id": station_id,
            "year": year,
            "day_of_year": doy,
        },
        "source": {
            "observed_sha256": "obs-" + station_id,
            "manifest_sha256": "obs-" + station_id,
        },
        "conversion": {
            "converted_path": str(converted_path),
            "converted_sha256": "conv-" + station_id,
            "decompressed_sha256": "decomp-" + station_id,
        },
        "rinex": {
            "first_epoch": first_epoch,
            "last_epoch": last_epoch,
            "empirical_interval_seconds": interval,
            "epochs_observed": epochs,
            "header": {
                "receiver_type": "SYNTHETIC",
                "receiver_number": "0000",
                "receiver_version": "0",
                "antenna_type": "SYNTHETIC",
                "antenna_number": "0000",
                "marker_name": station_id[:4],
                "marker_number": "00000M000",
            },
        },
        "navigation": (
            {"relative_path": nav_rel, "sha256": "nav-sha"} if nav_rel else None
        ),
        "coordinate_eligibility": {
            "reference_frame": "IGS20",
            "coordinate_epoch": "2024-01-26T11:59:42Z",
            "source_path": "processed/single-base/derived-coordinates.json",
            "source_sha256": "coord-sha",
            "scientifically_valid": scientifically_valid,
        },
        "findings": [] if classification == "ACCEPT" else [
            {
                "finding_code": "SYNTHETIC_FAIL",
                "severity": classification,
                "message": "synthetic",
            }
        ],
        "overall_classification": classification,
        "qc_profile": {"name": "network_rtk", "version": "1.0"},
        "result_fingerprint": fingerprint + "-" + station_id,
    }
    path = directory / "qc-result.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def write_derived_coordinates(
    data_root: Path, stations: dict[str, tuple[float, float, float]]
) -> Path:
    path = data_root / "processed" / "single-base" / "derived-coordinates.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "stations": {
            station: {
                "ecef": {"x_m": xyz[0], "y_m": xyz[1], "z_m": xyz[2]},
                "reference_frame": "IGS20",
                "coordinate_epoch": "2024-01-26T11:59:42Z",
                "scientifically_valid": True,
                "pos_file_path": "/synthetic",
            }
            for station, xyz in stations.items()
        }
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def write_nav_product(data_root: Path, year: int = 2024, doy: int = 26) -> Path:
    path = (
        data_root / f"external-products/brdc/{year}/BRDC00IGS_R_{year}{doy:03d}0000_01D_MN.rnx.gz"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"synthetic nav")
    return path


def make_definition(
    *,
    experiment_id: str = "net-synthetic",
    refs: tuple[str, ...] = ("ABFC00NGA", "EKAK00NGA", "MGBO00NGA"),
    rover: str = "PHRI00NGA",
    doy: int = 26,
    diagnostic: bool = False,
    minimum: int = 3,
) -> dict[str, Any]:
    return {
        "experiment_id": experiment_id,
        "research_question": "SYNTHETIC: does the framework admit and plan?",
        "year": 2024,
        "day_of_year": doy,
        "processing_mode": "static",
        "reference_stations": list(refs),
        "test_station": rover,
        "navigation_products": [
            "external-products/brdc/2024/BRDC00IGS_R_20240260000_01D_MN.rnx.gz"
        ],
        "start_time_utc": "2024-01-26T00:00:00Z",
        "end_time_utc": "2024-01-26T23:59:30Z",
        "sampling_interval_seconds": 30.0,
        "coordinate_frame": "IGS20",
        "coordinate_epoch": "2024-01-26T11:59:42Z",
        "qc_profile": "network_rtk",
        "minimum_reference_station_count": minimum,
        "diagnostic": diagnostic,
    }
