"""Tests for metrics, residuals, comparison, fingerprints and determinism.

SYNTHETIC TEST DATA — NOT VALID FOR SCIENTIFIC RESULTS.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from nlgcp_network_rtk.admission import admission_fingerprint, admit_day
from nlgcp_network_rtk.baselines import BaselineResult
from nlgcp_network_rtk.geometry import compute_geometry, load_verified_coordinates
from nlgcp_network_rtk.metrics import comparison_rows, compute_metrics
from nlgcp_network_rtk.models import definition_from_dict
from nlgcp_network_rtk.overlap import compute_overlap
from nlgcp_network_rtk.residuals import (
    UNAVAILABLE_SATELLITE_FIELDS,
    residual_rows_for_baseline,
    write_residual_dataset,
)
from nlgcp_network_rtk.runner import experiment_fingerprint, plan_experiment, run_experiment
from synthetic_fixtures import make_definition, write_derived_coordinates, write_qc_result

COORDS = {
    "ABFC00NGA": (6246471.17131, 820849.02064, 994268.16646),
    "EKAK00NGA": (6296841.32517, 875621.00415, 512343.12428),
    "MGBO00NGA": (6080985.75299, 1416995.42834, 1299050.34795),
    "PHRI00NGA": (6308877.98392, 772269.10256, 530087.60603),
}


def _baseline(
    baseline_id: str, ref: str, horiz: float, fix: int = 0, epochs: int = 2880
) -> BaselineResult:
    return BaselineResult(
        baseline_id=baseline_id,
        reference_station=ref,
        test_station="PHRI00NGA",
        outcome="COMPLETE",
        detail="synthetic",
        solution_metrics={
            "solution_epoch_count": epochs,
            "expected_epoch_count": 2880,
            "solution_availability": epochs / 2880,
            "fix_epoch_count": fix,
            "fix_rate_expected_epochs": fix / 2880,
            "ttff_seconds": None,
            "horizontal_rmse_m": horiz,
            "up_rmse_m": horiz / 2,
            "three_d_rmse_m": horiz * 1.1,
            "quality_counts": {"FLOAT": epochs - fix, "FIX": fix},
        },
        rtklib_provenance={},
        config_hash="cfg",
        baseline_distance_m=100000.0,
    )


def _setup(tmp_path: Path) -> None:
    for station in ("ABFC00NGA", "EKAK00NGA", "MGBO00NGA", "PHRI00NGA"):
        write_qc_result(tmp_path, station_id=station)
    write_derived_coordinates(tmp_path, COORDS)


def test_metrics_distinguish_single_vs_aggregate(tmp_path: Path) -> None:
    _setup(tmp_path)
    verified = load_verified_coordinates(tmp_path)
    geometry = compute_geometry(
        reference_stations=["ABFC00NGA", "EKAK00NGA", "MGBO00NGA"],
        test_station="PHRI00NGA",
        verified=verified,
    )
    admission = admit_day(tmp_path, year=2024, day_of_year=26)
    overlap = compute_overlap(list(admission.admitted))
    baselines = [
        _baseline("ABFC00NGA-to-PHRI00NGA", "ABFC00NGA", 1.0),
        _baseline("EKAK00NGA-to-PHRI00NGA", "EKAK00NGA", 2.0),
    ]
    metrics = compute_metrics(
        experiment_id="net-test", admitted_count=4, rejected_count=0,
        geometry=geometry, overlap=overlap, baselines=baselines,
    )
    assert len(metrics["single_baseline_metrics"]) == 2
    assert metrics["network_aggregate_metrics"]["mean_horizontal_rmse_m"] == pytest.approx(1.5)
    assert "NOT a VRS solution" in metrics["network_aggregate_metrics"]["label"]
    assert metrics["network_aggregate_metrics"]["inter_baseline_consistency_m"] is not None


def test_comparison_does_not_claim_improvement(tmp_path: Path) -> None:
    _setup(tmp_path)
    verified = load_verified_coordinates(tmp_path)
    geometry = compute_geometry(
        reference_stations=["ABFC00NGA", "EKAK00NGA", "MGBO00NGA"],
        test_station="PHRI00NGA",
        verified=verified,
    )
    admission = admit_day(tmp_path, year=2024, day_of_year=26)
    overlap = compute_overlap(list(admission.admitted))
    baselines = [_baseline("EKAK00NGA-to-PHRI00NGA", "EKAK00NGA", 0.9)]
    metrics = compute_metrics(
        experiment_id="net-test", admitted_count=4, rejected_count=0,
        geometry=geometry, overlap=overlap, baselines=baselines,
    )
    rows = comparison_rows(metrics=metrics, nearest_reference=geometry.nearest_reference)
    assert rows[0]["comparison"] == "single_nearest_reference"
    assert rows[1]["comparison"] == "multiple_reference_network_input"
    assert "NOT a VRS" in rows[1]["note"]


def test_residual_dataset_fields_and_unavailable_documented(tmp_path: Path) -> None:
    epochs_csv = tmp_path / "epochs.csv"
    header = (
        "epoch,quality_code,quality,satellites,east_m,north_m,up_m,"
        "horizontal_error_m,vertical_abs_error_m,error_3d_m\n"
    )
    epochs_csv.write_text(
        header + "2024-01-26T00:00:00+00:00,2,FLOAT,9,0.1,0.2,0.3,0.22,0.3,0.37\n",
        encoding="utf-8",
    )
    rows = residual_rows_for_baseline(
        baseline_id="ABFC00NGA-to-PHRI00NGA", test_station="PHRI00NGA",
        baseline_length_m=470869.0, epochs_csv=epochs_csv,
    )
    assert len(rows) == 1
    assert rows[0]["satellite_id"] is None
    assert set(UNAVAILABLE_SATELLITE_FIELDS) >= {"satellite_id", "constellation"}
    out = tmp_path / "network-residuals.csv"
    write_residual_dataset(out, rows)
    assert out.is_file()


def test_fingerprint_changes_with_inputs(tmp_path: Path) -> None:
    _setup(tmp_path)
    definition = definition_from_dict(make_definition())
    admission = admit_day(tmp_path, year=2024, day_of_year=26)
    verified = load_verified_coordinates(tmp_path)
    geometry = compute_geometry(
        reference_stations=list(definition.reference_stations),
        test_station=definition.test_station, verified=verified,
    )
    overlap = compute_overlap(list(admission.admitted))
    first = experiment_fingerprint(
        definition=definition, admission=admission, geometry=geometry, overlap=overlap,
        rtklib_config_hashes={"a": "1"}, rtklib_binary_sha256="sha",
    )
    second = experiment_fingerprint(
        definition=definition, admission=admission, geometry=geometry, overlap=overlap,
        rtklib_config_hashes={"a": "2"}, rtklib_binary_sha256="sha",
    )
    assert first != second
    # Deterministic: same inputs give same fingerprint.
    repeat = experiment_fingerprint(
        definition=definition, admission=admission, geometry=geometry, overlap=overlap,
        rtklib_config_hashes={"a": "1"}, rtklib_binary_sha256="sha",
    )
    assert first == repeat


def test_admission_fingerprint_stable(tmp_path: Path) -> None:
    _setup(tmp_path)
    first = admission_fingerprint(admit_day(tmp_path, year=2024, day_of_year=26))
    second = admission_fingerprint(admit_day(tmp_path, year=2024, day_of_year=26))
    assert first == second


def _nav_product(tmp_path: Path) -> None:
    nav = (
        tmp_path / "external-products" / "brdc" / "2024"
        / "BRDC00IGS_R_20240260000_01D_MN.rnx.gz"
    )
    nav.parent.mkdir(parents=True, exist_ok=True)
    nav.write_bytes(b"nav")


def test_resumability_reuses_matching_fingerprint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _setup(tmp_path)
    # Navigation file must exist for run; create the referenced product.
    _nav_product(tmp_path)
    import nlgcp_network_rtk.runner as runner_mod
    from nlgcp_network_rtk.baselines import BaselineRequest

    calls = {"count": 0}

    def _fake_execute(
        request: BaselineRequest, output_dir: Path, *, dry_run: bool = False
    ) -> BaselineResult:
        _ = (output_dir, dry_run)
        calls["count"] += 1
        return BaselineResult(
            baseline_id=request.baseline_id,
            reference_station=request.reference_station,
            test_station=request.test_station,
            outcome="COMPLETE",
            detail="synthetic",
            solution_metrics={"solution_epoch_count": 10},
            rtklib_provenance={},
            config_hash="cfg",
            baseline_distance_m=1.0,
        )

    monkeypatch.setattr(runner_mod, "execute_baseline", _fake_execute)
    definition = definition_from_dict(make_definition())
    first = run_experiment(tmp_path, definition, workers=2)
    assert calls["count"] == 3
    second = run_experiment(tmp_path, definition, workers=2)
    assert second.get("reused_verified_result") is True
    assert calls["count"] == 3  # no re-execution
    assert first["experiment_fingerprint"] == second["experiment_fingerprint"]


def test_parallel_determinism_sorted_outputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _setup(tmp_path)
    _nav_product(tmp_path)
    import nlgcp_network_rtk.runner as runner_mod
    from nlgcp_network_rtk.baselines import BaselineRequest

    def _fake_execute(
        request: BaselineRequest, output_dir: Path, *, dry_run: bool = False
    ) -> BaselineResult:
        import time as _time

        _ = (output_dir, dry_run)
        # Sleep inversely to name so completion order differs from sorted order.
        _time.sleep(0.05 if "MGBO" in request.baseline_id else 0.0)
        return BaselineResult(
            baseline_id=request.baseline_id,
            reference_station=request.reference_station,
            test_station=request.test_station,
            outcome="COMPLETE",
            detail="synthetic",
            solution_metrics={"solution_epoch_count": 10},
            rtklib_provenance={},
            config_hash="cfg",
            baseline_distance_m=1.0,
        )

    monkeypatch.setattr(runner_mod, "execute_baseline", _fake_execute)
    definition = definition_from_dict(make_definition(experiment_id="net-determinism"))
    manifest = run_experiment(tmp_path, definition, workers=3)
    ids = [b["baseline_id"] for b in manifest["baselines"]]
    assert ids == sorted(ids)


def test_rtklib_provenance_constant_matches_phase1(tmp_path: Path) -> None:
    from nlgcp_single_base.rtklib import RECORDED_RNX2RTKP_SHA256

    _ = tmp_path
    expected = "b4a96cd0d5ffc00b44dab3a4fda214318c9f69cccee52128aec8bc26ad4f7d21"
    assert expected == RECORDED_RNX2RTKP_SHA256


def test_run_blocked_when_insufficient_admitted(tmp_path: Path) -> None:
    write_qc_result(tmp_path, station_id="ABFC00NGA")
    write_qc_result(tmp_path, station_id="PHRI00NGA", classification="REJECT")
    write_derived_coordinates(tmp_path, COORDS)
    definition = definition_from_dict(make_definition())
    manifest = run_experiment(tmp_path, definition, workers=1)
    assert manifest["status"] == "BLOCKED"


def test_reproducibility_plan_twice_identical(tmp_path: Path) -> None:
    _setup(tmp_path)
    definition = definition_from_dict(make_definition())
    first = plan_experiment(tmp_path, definition)
    second = plan_experiment(tmp_path, definition)
    assert first["geometry"] == second["geometry"]
    assert first["overlap"] == second["overlap"]
