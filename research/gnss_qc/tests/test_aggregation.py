"""SYNTHETIC TEST DATA — NOT VALID FOR SCIENTIFIC RESULTS."""

from __future__ import annotations

import json
from pathlib import Path

from nlgcp_gnss_qc.aggregate import summarize_profile


def result(station: str, doy: int, classification: str) -> dict[str, object]:
    return {
        "station_identity": {
            "canonical_station_id": station,
            "year": 2024,
            "day_of_year": doy,
            "resolution": "CANONICAL_MATCH",
        },
        "source": {
            "relative_path": f"raw/{station}/{doy:03d}/x.24D.Z",
            "observed_sha256": f"hash-{station}-{doy}",
            "manifest_sha256": f"hash-{station}-{doy}",
            "exact_duplicate_sources": [],
        },
        "rinex": {
            "first_epoch": "2024-01-01T00:00:00Z",
            "last_epoch": "2024-01-01T23:59:30Z",
            "availability_percent": 100.0,
            "epochs_observed": 2880,
            "epochs_expected": 2880,
            "gap_count": 0,
            "largest_gap_seconds": None,
            "satellites_median": 8.0,
            "potential_cycle_slip_indicators": 0,
            "header": {
                "marker_name": station[:4],
                "observation_types": ["C1", "L1", "L2", "P2"],
                "receiver_number": "RX",
                "receiver_type": "TEST",
                "receiver_version": "1",
                "antenna_number": "ANT",
                "antenna_type": "TEST",
                "antenna_delta_hen_m": [0.1, 0, 0],
            },
        },
        "navigation": None,
        "findings": [{"finding_code": "FULL_SESSION"}],
        "overall_classification": classification,
        "qc_profile": {
            "name": "archive",
            "version": "1.0",
            "status": "PROVISIONAL — synthetic",
        },
    }


def write_result(root: Path, payload: dict[str, object]) -> None:
    identity = payload["station_identity"]
    assert isinstance(identity, dict)
    path = (
        root
        / "processed"
        / "qc"
        / "profiles"
        / "archive"
        / "sessions"
        / "2024"
        / str(identity["canonical_station_id"])
        / f"{int(identity['day_of_year']):03d}"
        / "qc-result.json"
    )
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_station_health_and_network_overlap(tmp_path: Path) -> None:
    for station in ("ABFC00NGA", "EKAK00NGA", "MGBO00NGA"):
        write_result(tmp_path, result(station, 1, "ACCEPT"))
        write_result(tmp_path, result(station, 2, "ACCEPT"))
    write_result(tmp_path, result("PHRI00NGA", 1, "WARN"))
    summary = summarize_profile(tmp_path, "archive")
    assert summary["sessions_processed"] == 7
    assert summary["classification_counts"]["ACCEPT"] == 6
    assert summary["classification_counts"]["WARN"] == 1
    windows = summary["network_overlap_windows"]
    three_station = [row for row in windows if row["minimum_station_count"] == 3]
    assert three_station[0]["duration_days"] == 2


def test_required_tables_figures_and_report_created(tmp_path: Path) -> None:
    write_result(tmp_path, result("ABFC00NGA", 1, "BLOCKED"))
    summary = summarize_profile(tmp_path, "archive")
    assert len(summary["tables"]) == 9
    assert all(Path(path).is_file() for path in summary["tables"].values())
    assert len(summary["figures"]) == 4
    assert all(Path(path).is_file() for path in summary["figures"])
    assert Path(summary["validation_report"]).is_file()


def test_equipment_transition_remains_transparent(tmp_path: Path) -> None:
    first = result("ABFC00NGA", 1, "ACCEPT")
    second = result("ABFC00NGA", 2, "ACCEPT")
    rinex = second["rinex"]
    assert isinstance(rinex, dict)
    header = rinex["header"]
    assert isinstance(header, dict)
    header["receiver_number"] = "RX2"
    write_result(tmp_path, first)
    write_result(tmp_path, second)
    summary = summarize_profile(tmp_path, "archive")
    assert summary["equipment_changes"] == 1
    equipment_path = Path(summary["tables"]["equipment_history"])
    assert "authoritative effective-date metadata unavailable" in equipment_path.read_text(
        encoding="utf-8"
    )
