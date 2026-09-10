"""SYNTHETIC TEST DATA — NOT VALID FOR SCIENTIFIC RESULTS."""

from __future__ import annotations

from nlgcp_scientific_expansion import coverage


def _manifest(station: str, doy: int) -> dict[str, object]:
    return {
        "station_id": station,
        "day_of_year": doy,
        "canonical_relative_path": f"raw/nignet/2024/{station}/{doy:03d}/obs",
        "sha256": "synthetic",
    }


def _qc(station: str, doy: int, classification: str, findings: str) -> dict[str, str]:
    return {
        "station_id": station,
        "day_of_year": str(doy),
        "classification": classification,
        "finding_codes": findings,
        "availability_percent": "100.0",
        "epochs_observed": "2880",
    }


def test_canonical_stations() -> None:
    assert len(coverage.canonical_station_ids()) == 8
    assert "ABFC00NGA" in coverage.canonical_station_ids()


def test_processable_requires_all_gates() -> None:
    full = "FULL_SESSION;NAVIGATION_PRODUCT_AVAILABLE;COORDINATE_ELIGIBLE"
    cells = coverage.build_coverage_matrix(
        [_manifest("ABFC00NGA", 26), _manifest("EKAK00NGA", 26)],
        [
            _qc("ABFC00NGA", 26, "ACCEPT", full),
            _qc("EKAK00NGA", 26, "ACCEPT", full),
        ],
        {26: "BRDC00IGS_R_20240260000_01D_MN.rnx.gz"},
        {"ABFC00NGA": {26}, "EKAK00NGA": {26}},
        year=2024,
    )
    assert len(cells) == 2
    assert all(cell.processable_single_base for cell in cells)
    assert all(cell.block_reason == "" for cell in cells)


def test_missing_navigation_blocks() -> None:
    full = "FULL_SESSION;NAVIGATION_PRODUCT_MISSING;COORDINATE_INTERVAL_UNVERIFIED"
    cells = coverage.build_coverage_matrix(
        [_manifest("ABFC00NGA", 27)],
        [_qc("ABFC00NGA", 27, "BLOCKED", full)],
        {},
        {},
        year=2024,
    )
    assert cells[0].processable_single_base is False
    assert "BLOCKED_NAVIGATION" in cells[0].block_reason
    assert "BLOCKED_COORDINATE_INTERVAL" in cells[0].block_reason


def test_reject_never_processable() -> None:
    cells = coverage.build_coverage_matrix(
        [_manifest("ABFC00NGA", 51)],
        [_qc("ABFC00NGA", 51, "REJECT", "SEVERE_SESSION_TRUNCATION")],
        {51: "nav.gz"},
        {"ABFC00NGA": {51}},
        year=2024,
    )
    assert cells[0].processable_single_base is False
    assert "BLOCKED_QC_REJECT" in cells[0].block_reason


def test_non_canonical_station_ignored() -> None:
    cells = coverage.build_coverage_matrix(
        [_manifest("FAKE00NGA", 26)],
        [],
        {},
        {},
        year=2024,
    )
    assert cells == []
