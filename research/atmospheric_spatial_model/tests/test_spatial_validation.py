"""Tests for spatial records, interpolation, metrics, and LOOCV (synthetic)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from nlgcp_atmospheric_model.interpolation import interpolate, prediction_to_row  # noqa: E402
from nlgcp_atmospheric_model.metrics import (  # noqa: E402
    bias,
    correlation,
    decorrelation_fit,
    mae,
    prediction_metrics,
    rmse,
    std,
)
from nlgcp_atmospheric_model.models import StationCoordinate  # noqa: E402
from nlgcp_atmospheric_model.spatial import (  # noqa: E402
    baseline_length_m,
    build_spatial_records,
    records_to_rows,
)
from nlgcp_atmospheric_model.validation import loocv_folds, run_loocv  # noqa: E402


def coord(station_id: str, x: float, y: float = 0.0, z: float = 0.0) -> StationCoordinate:
    return StationCoordinate(
        station_id=station_id, x_m=x, y_m=y, z_m=z, frame="IGS20", epoch="e"
    )


RefTriple = tuple[str, tuple[float, float, float], float | None]


def refs_plane() -> tuple[tuple[float, float, float], list[RefTriple]]:
    # Non-collinear surface triangle (spread in longitude and latitude).
    target = (6_378_137.0 + 100.0, 50_000.0, 0.0)
    references: list[RefTriple] = [
        ("A", (6_378_137.0, 0.0, 0.0), 1.0),
        ("B", (6_378_137.0, 1_000.0, 0.0), 3.0),
        ("C", (6_378_137.0, 0.0, 1_000.0), 1.0),
    ]
    return target, references


def test_plane_fit_unit_coefficients() -> None:
    from nlgcp_atmospheric_model.interpolation import _plane_fit  # noqa: SLF001

    fit = _plane_fit([(0.0, 0.0, 1.0), (1.0, 0.0, 3.0), (0.0, 1.0, 2.0)])
    assert fit is not None
    assert fit[0] == pytest.approx(2.0, rel=1e-9)
    assert fit[1] == pytest.approx(1.0, rel=1e-9)
    assert fit[2] == pytest.approx(1.0, rel=1e-9)


def test_planar_passes_through_reference_points() -> None:
    # A plane fitted through 3 non-collinear references must reproduce each
    # reference value exactly at its own location (interpolation property).
    _, references = refs_plane()
    for station, xyz, value in references:
        assert value is not None
        pred = interpolate(
            model_name="planar", epoch_iso="e", satellite_id="G01",
            target_station=station, target_xyz=xyz, references=references,
        )
        assert pred.predicted_m == pytest.approx(float(value), rel=1e-9)
        assert pred.reason is None


def test_idw_weights_nearest_more() -> None:
    target = (0.0, 0.0, 0.0)
    references = [("A", (1.0, 0.0, 0.0), 0.0), ("B", (3.0, 0.0, 0.0), 3.0)]
    pred = interpolate(
        model_name="idw", epoch_iso="e", satellite_id="G01",
        target_station="T", target_xyz=target, references=references, power=1.0,
    )
    # weights 1 and 1/3 -> (0*1 + 3/3)/ (4/3) = 0.75
    assert pred.predicted_m == pytest.approx(0.75)


def test_nearest_and_zero_controls() -> None:
    target = (0.0, 0.0, 0.0)
    references = [("A", (1.0, 0.0, 0.0), 5.0), ("B", (9.0, 0.0, 0.0), 1.0)]
    nearest = interpolate(
        model_name="nearest", epoch_iso="e", satellite_id="G01",
        target_station="T", target_xyz=target, references=references,
    )
    assert nearest.predicted_m == 5.0
    assert nearest.model_parameters["source_station"] == "A"
    zero = interpolate(
        model_name="zero", epoch_iso="e", satellite_id="G01",
        target_station="T", target_xyz=target, references=references,
        observed_m=2.0,
    )
    assert zero.predicted_m == 0.0
    assert zero.residual_m == 2.0


def test_insufficient_geometry_fail_closed() -> None:
    pred = interpolate(
        model_name="planar", epoch_iso="e", satellite_id="G01",
        target_station="T", target_xyz=(0.0, 0.0, 0.0),
        references=[("A", (1.0, 0.0, 0.0), 1.0), ("B", (2.0, 0.0, 0.0), 2.0)],
    )
    assert pred.predicted_m is None
    assert "insufficient geometry" in (pred.reason or "")


def test_collinear_planar_singular() -> None:
    references = [
        ("A", (1.0, 0.0, 0.0), 1.0),
        ("B", (2.0, 0.0, 0.0), 2.0),
        ("C", (3.0, 0.0, 0.0), 3.0),
    ]
    pred = interpolate(
        model_name="planar", epoch_iso="e", satellite_id="G01",
        target_station="T", target_xyz=(0.0, 0.0, 0.0), references=references,
    )
    assert pred.predicted_m is None
    assert "collinear" in (pred.reason or "")


def test_none_values_excluded_with_reason() -> None:
    pred = interpolate(
        model_name="nearest", epoch_iso="e", satellite_id="G01",
        target_station="T", target_xyz=(0.0, 0.0, 0.0),
        references=[("A", (1.0, 0.0, 0.0), None), ("B", (2.0, 0.0, 0.0), 7.0)],
    )
    assert pred.predicted_m == 7.0
    assert "excluded" in (pred.reason or "")


def test_extrapolation_flag() -> None:
    inside = interpolate(
        model_name="nearest", epoch_iso="e", satellite_id="G01",
        target_station="T", target_xyz=(0.0, 0.0, 0.0),
        references=[("A", (1.0, 0.0, 0.0), 1.0), ("B", (-1.0, 0.0, 0.0), 2.0)],
    )
    outside = interpolate(
        model_name="nearest", epoch_iso="e", satellite_id="G01",
        target_station="T", target_xyz=(100.0, 0.0, 0.0),
        references=[("A", (1.0, 0.0, 0.0), 1.0), ("B", (-1.0, 0.0, 0.0), 2.0)],
    )
    assert inside.extrapolated is False
    assert outside.extrapolated is True


def test_unknown_model_rejected() -> None:
    with pytest.raises(ValueError):
        interpolate(
            model_name="kriging", epoch_iso="e", satellite_id="G01",
            target_station="T", target_xyz=(0.0, 0.0, 0.0), references=[],
        )


def test_prediction_row_serialises() -> None:
    target, references = refs_plane()
    pred = interpolate(
        model_name="idw", epoch_iso="e", satellite_id="G01",
        target_station="T", target_xyz=target, references=references,
    )
    row = prediction_to_row(pred)
    assert row["model"] == "idw"
    assert row["predicted_m"] is not None


def test_spatial_records_null_with_reasons() -> None:
    records = build_spatial_records(
        epoch_iso="e", satellite_id="G01", constellation="G",
        target=coord("T", 1.0), references=[coord("A", 0.0)],
        iono_by_station={}, tropo_by_station={},
        elevation_by_station={}, azimuth_by_station={},
        provenance="synthetic",
    )
    assert records[0].combined_residual_m is None
    assert any("unavailable" in flag for flag in records[0].quality_flags)
    rows = records_to_rows(records)
    assert rows[0]["baseline_length_m"] == pytest.approx(1.0)


def test_spatial_records_combined_sum() -> None:
    records = build_spatial_records(
        epoch_iso="e", satellite_id="G01", constellation="G",
        target=coord("T", 3.0, 4.0), references=[coord("A", 0.0, 0.0)],
        iono_by_station={"A": 1.5}, tropo_by_station={"A": 0.5},
        elevation_by_station={"A": 45.0}, azimuth_by_station={"A": 90.0},
        provenance="synthetic",
    )
    assert records[0].combined_residual_m == pytest.approx(2.0)
    assert records[0].baseline_length_m == pytest.approx(5.0)
    assert baseline_length_m((0, 0, 0), (3, 4, 0)) == pytest.approx(5.0)


def test_metrics_edge_cases() -> None:
    assert bias([]) is None
    assert mae([]) is None
    assert rmse([]) is None
    assert std([1.0]) is None
    assert correlation([1.0, 1.0], [2.0, 3.0]) is None
    assert correlation([1.0], [2.0]) is None
    assert correlation([0.0, 1.0], [0.0, 2.0]) == pytest.approx(1.0)
    assert bias([1.0, -1.0, 3.0]) == pytest.approx(1.0)
    assert mae([-2.0, 2.0]) == pytest.approx(2.0)
    assert rmse([3.0, 4.0]) == pytest.approx(3.5355339, rel=1e-6)
    metrics = prediction_metrics([0.01, -0.02, 0.06])
    assert metrics["count"] == 3
    assert metrics["coverage_within_tolerance"] == pytest.approx(2 / 3)


def test_decorrelation_fit_and_insufficient() -> None:
    fit = decorrelation_fit([100e3, 500e3, 1000e3], [0.1, 0.5, 1.0])
    assert fit["slope_m_per_km"] == pytest.approx(0.001, rel=1e-6)
    assert fit["correlation"] == pytest.approx(1.0)
    assert "pilot" in fit["note"]
    short = decorrelation_fit([100e3], [0.1])
    assert short["slope_m_per_km"] is None


def test_loocv_folds_enforce_minimum() -> None:
    folds = loocv_folds(["A", "B", "C", "D"])
    assert all(f["admissible"] for f in folds)
    strict = loocv_folds(["A", "B", "C", "D"], min_refs=4)
    assert not any(f["admissible"] for f in strict)


def test_run_loocv_best_model_and_controls() -> None:
    coords = {
        "A": (0.0, 0.0, 0.0),
        "B": (1000.0, 0.0, 500.0),
        "C": (0.0, 1000.0, -300.0),
        "D": (1000.0, 1000.0, 200.0),
    }
    # Observed field is exactly zero: the zero control must win honestly
    # (ties broken towards the first-listed control).
    observed = {
        (epoch, "G01", station): 0.0
        for epoch in ["e1", "e2"]
        for station in coords
    }
    result = run_loocv(
        epochs=["e1", "e2"], satellites=["G01"], coords=coords, observed=observed
    )
    assert result["best_model"] == "zero"
    assert result["models"]["zero"]["rmse_m"] == pytest.approx(0.0)
    # Identical-sample comparison: every model reports the same count.
    counts = {result["models"][m]["count"] for m in ("zero", "nearest", "idw", "planar")}
    assert len(counts) == 1
    assert result["comparison_keys"] == result["models"]["zero"]["count"]
    assert "simpler control" in result["best_model_note"] or "identical" in result[
        "best_model_note"
    ]


def test_run_loocv_skips_missing_observations() -> None:
    coords = {"A": (0.0, 0.0, 0.0), "B": (1.0, 0.0, 0.0), "C": (0.0, 1.0, 0.0)}
    result = run_loocv(epochs=["e1"], satellites=["G01"], coords=coords, observed={})
    assert result["best_model"] is None
    assert result["missing_observations_skipped"] == 3
