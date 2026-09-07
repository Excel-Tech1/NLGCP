"""Thesis-ready tables and figures for Phase 6 (reproducibly generated).

All values are read from stored experiment artefacts; nothing is edited by
hand. Figures use the headless Agg backend. If matplotlib is unavailable the
tables are still written and the omission is recorded with a reason.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any


def baseline_matrix_rows(
    coord_map: dict[str, tuple[float, float, float]],
) -> list[dict[str, Any]]:
    """Unordered station-pair distances (km) for geometry tables/figures."""
    import math

    stations = sorted(coord_map)
    rows: list[dict[str, Any]] = []
    for i in range(len(stations)):
        for j in range(i + 1, len(stations)):
            a, b = stations[i], stations[j]
            dist_m = math.dist(coord_map[a], coord_map[b])
            rows.append({
                "station_a": a,
                "station_b": b,
                "baseline_m": dist_m,
                "baseline_km": dist_m / 1000.0,
            })
    return rows


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key) for key in fieldnames})


def loocv_summary_rows(loocv: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for model in sorted(loocv.get("models") or {}):
        metrics = loocv["models"][model]
        rows.append({
            "model": model,
            "comparison_keys": loocv.get("comparison_keys"),
            "evaluable_keys": metrics.get("evaluable_keys"),
            "bias_m": metrics.get("bias_m"),
            "mae_m": metrics.get("mae_m"),
            "rmse_m": metrics.get("rmse_m"),
            "std_m": metrics.get("std_m"),
            "correlation_predicted_observed": metrics.get(
                "correlation_predicted_observed"
            ),
            "coverage_within_tolerance": metrics.get("coverage_within_tolerance"),
            "tolerance_m": metrics.get("tolerance_m"),
            "best_model": loocv.get("best_model"),
        })
    return rows


def write_validation_reports(
    out: Path,
    *,
    coord_map: dict[str, tuple[float, float, float]],
    loocv: dict[str, Any],
    decorr: dict[str, Any],
    common_epoch_csv: Path | None = None,
) -> dict[str, Any]:
    """Write tables/ and figures/ under an experiment directory."""
    tables = out / "tables"
    figures = out / "figures"
    tables.mkdir(parents=True, exist_ok=True)
    figures.mkdir(parents=True, exist_ok=True)

    matrix = baseline_matrix_rows(coord_map)
    write_csv(tables / "baseline-matrix.csv", matrix,
              ["station_a", "station_b", "baseline_m", "baseline_km"])
    write_csv(tables / "loocv-summary.csv", loocv_summary_rows(loocv),
              ["model", "comparison_keys", "evaluable_keys", "bias_m", "mae_m",
               "rmse_m", "std_m", "correlation_predicted_observed",
               "coverage_within_tolerance", "tolerance_m", "best_model"])
    write_csv(tables / "decorrelation.csv", list(decorr.get("pairs", [])),
              ["pair", "baseline_m", "rms_m", "count"])

    report: dict[str, Any] = {
        "tables": [str(tables / "baseline-matrix.csv"),
                   str(tables / "loocv-summary.csv"),
                   str(tables / "decorrelation.csv")],
        "figures": [],
        "figure_reasons": [],
    }
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError as exc:
        report["figure_reasons"].append(f"matplotlib unavailable: {exc}")
        return report

    # Per-model RMSE bar chart (identical comparison samples).
    models = sorted(loocv.get("models") or {})
    rmse_values = [(loocv["models"][m].get("rmse_m") or 0.0) for m in models]
    fig, ax = plt.subplots()
    ax.bar(models, rmse_values)
    ax.set_ylabel("LOOCV RMSE (m)")
    ax.set_title("Leave-one-out RMSE by model (identical samples)")
    fig.tight_layout()
    rmse_path = figures / "loocv-rmse.png"
    fig.savefig(rmse_path, dpi=150)
    plt.close(fig)
    report["figures"].append(str(rmse_path))

    # Distance-vs-RMS scatter with the pilot least-squares line.
    pairs = list(decorr.get("pairs", []))
    if len(pairs) >= 2:
        xs = [p["baseline_m"] / 1000.0 for p in pairs]
        ys = [p["rms_m"] for p in pairs]
        slope = decorr.get("slope_m_per_km")
        intercept = decorr.get("intercept_m")
        fig2, ax2 = plt.subplots()
        ax2.scatter(xs, ys)
        for x, y, p in zip(xs, ys, pairs, strict=True):
            ax2.annotate(p["pair"].split("00NGA")[0], (x, y), fontsize=6)
        if slope is not None and intercept is not None:
            lo, hi = min(xs), max(xs)
            ax2.plot([lo, hi], [intercept + slope * lo, intercept + slope * hi])
        ax2.set_xlabel("Baseline length (km)")
        ax2.set_ylabel("Pair SD-proxy RMS (m)")
        ax2.set_title("Pilot spatial decorrelation (one day: not a national law)")
        fig2.tight_layout()
        decorr_path = figures / "decorrelation.png"
        fig2.savefig(decorr_path, dpi=150)
        plt.close(fig2)
        report["figures"].append(str(decorr_path))

    # Common-satellite availability over the experiment.
    if common_epoch_csv is not None and common_epoch_csv.is_file():
        epochs: list[str] = []
        common: list[float] = []
        gps: list[float] = []
        with common_epoch_csv.open(encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                epochs.append(row.get("epoch", ""))
                try:
                    common.append(float(row.get("common_satellites", 0) or 0))
                    gps.append(float(row.get("gps_l1l2_common", 0) or 0))
                except (TypeError, ValueError):
                    continue
        if epochs and len(epochs) == len(common) == len(gps):
            fig3, ax3 = plt.subplots()
            ax3.plot(range(len(epochs)), common, label="common satellites")
            ax3.plot(range(len(epochs)), gps, label="GPS L1/L2 common")
            ax3.set_xlabel("Common epoch index")
            ax3.set_ylabel("Satellite count")
            ax3.set_title("Common-satellite availability")
            ax3.legend()
            fig3.tight_layout()
            avail_path = figures / "common-satellites.png"
            fig3.savefig(avail_path, dpi=150)
            plt.close(fig3)
            report["figures"].append(str(avail_path))
    return report
