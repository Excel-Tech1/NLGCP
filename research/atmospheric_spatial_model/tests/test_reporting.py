"""Tests for thesis-ready tables/figures and summary CSVs (synthetic)."""

from __future__ import annotations

import csv
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from nlgcp_atmospheric_model.reporting import (  # noqa: E402
    baseline_matrix_rows,
    loocv_summary_rows,
    write_validation_reports,
)


def toy_loocv() -> dict[str, Any]:
    return {
        "best_model": "zero",
        "comparison_keys": 10,
        "models": {
            "zero": {
                "count": 10, "evaluable_keys": 12, "bias_m": 0.1,
                "mae_m": 0.2, "rmse_m": 0.3, "std_m": 0.25,
                "correlation_predicted_observed": None,
                "coverage_within_tolerance": 0.5, "tolerance_m": 0.05,
            },
            "nearest": {
                "count": 10, "evaluable_keys": 11, "bias_m": 0.4,
                "mae_m": 0.5, "rmse_m": 0.6, "std_m": 0.55,
                "correlation_predicted_observed": 0.7,
                "coverage_within_tolerance": 0.4, "tolerance_m": 0.05,
            },
        },
    }


def test_baseline_matrix_pairwise() -> None:
    rows = baseline_matrix_rows({"A": (0.0, 0.0, 0.0), "B": (3.0, 4.0, 0.0)})
    assert len(rows) == 1
    assert rows[0]["station_a"] == "A"
    assert rows[0]["station_b"] == "B"
    assert rows[0]["baseline_m"] == 5.0
    assert rows[0]["baseline_km"] == 0.005


def test_loocv_summary_rows_sorted() -> None:
    rows = loocv_summary_rows(toy_loocv())
    assert [r["model"] for r in rows] == ["nearest", "zero"]
    assert rows[1]["rmse_m"] == 0.3
    assert rows[1]["best_model"] == "zero"


def test_validation_reports_write_tables_and_figures(tmp_path: Path) -> None:
    out = tmp_path / "exp"
    decorr = {
        "slope_m_per_km": 0.001, "intercept_m": 1.0, "correlation": 0.9,
        "pairs": [
            {"pair": "A-B", "baseline_m": 100_000.0, "rms_m": 1.1, "count": 5},
            {"pair": "A-C", "baseline_m": 500_000.0, "rms_m": 1.5, "count": 6},
        ],
    }
    common_csv = tmp_path / "per-epoch-common.csv"
    with common_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=["epoch", "common_satellites", "gps_l1l2_common"]
        )
        writer.writeheader()
        for k in range(4):
            writer.writerow({
                "epoch": f"e{k}", "common_satellites": 14 + k,
                "gps_l1l2_common": 8 + k,
            })
    report = write_validation_reports(
        out,
        coord_map={"A": (0.0, 0.0, 0.0), "B": (100_000.0, 0.0, 0.0)},
        loocv=toy_loocv(),
        decorr=decorr,
        common_epoch_csv=common_csv,
    )
    assert (out / "tables" / "baseline-matrix.csv").is_file()
    assert (out / "tables" / "loocv-summary.csv").is_file()
    assert (out / "tables" / "decorrelation.csv").is_file()
    assert len(report["tables"]) == 3
    # Figures are written when matplotlib is available; otherwise a reason
    # is recorded and tables still stand.
    figures = [Path(p) for p in report["figures"]]
    assert figures, report["figure_reasons"]
    assert all(p.is_file() for p in figures)
