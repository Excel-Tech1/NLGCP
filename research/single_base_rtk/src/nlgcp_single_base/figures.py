"""Thesis-ready figure generation for Phase 3.

All figures are generated from stored measured results; no illustrative
curves are fabricated.  Plotting is moved into this versioned module (not
left in notebooks) so the figures are reproducible from the result files.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from nlgcp_single_base.coordinates import EcefCoordinate, ecef_to_geodetic  # noqa: E402


def _style() -> None:
    plt.rcParams.update(
        {
            "figure.dpi": 150,
            "savefig.dpi": 300,
            "font.size": 9,
            "axes.titlesize": 10,
            "axes.labelsize": 9,
            "legend.fontsize": 8,
            "grid.alpha": 0.3,
        }
    )


def station_map_figure(
    stations: dict[str, EcefCoordinate],
    labels: dict[str, str],
    out_path: Path,
) -> Path:
    """Figure 1: coarse map of Phase 3 stations (geodetic projection)."""
    _style()
    fig, ax = plt.subplots(figsize=(7, 7))
    for station, ecef in stations.items():
        geod = ecef_to_geodetic(ecef)
        ax.plot(geod.longitude_deg, geod.latitude_deg, "o", color="#1f77b4")
        ax.annotate(
            labels.get(station, station),
            (geod.longitude_deg, geod.latitude_deg),
            xytext=(5, 5),
            textcoords="offset points",
        )
    ax.set_xlabel("Longitude (deg)")
    ax.set_ylabel("Latitude (deg)")
    ax.set_title("NLGCP Phase 3 single-base RTK stations")
    ax.grid(True)
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path)
    plt.close(fig)
    return out_path


def baseline_network_figure(
    stations: dict[str, EcefCoordinate],
    pairs: list[tuple[str, str]],
    out_path: Path,
) -> Path:
    """Figure 2: baseline network geometry."""
    _style()
    fig, ax = plt.subplots(figsize=(7, 7))
    for a, b in pairs:
        ga = ecef_to_geodetic(stations[a])
        gb = ecef_to_geodetic(stations[b])
        ax.plot(
            [ga.longitude_deg, gb.longitude_deg],
            [ga.latitude_deg, gb.latitude_deg],
            "-",
            color="#7f7f7f",
            lw=0.8,
        )
    for station, ecef in stations.items():
        geod = ecef_to_geodetic(ecef)
        ax.plot(geod.longitude_deg, geod.latitude_deg, "o", color="#d62728")
        ax.annotate(
            station,
            (geod.longitude_deg, geod.latitude_deg),
            xytext=(4, 4),
            textcoords="offset points",
        )
    ax.set_xlabel("Longitude (deg)")
    ax.set_ylabel("Latitude (deg)")
    ax.set_title("Baseline network geometry")
    ax.grid(True)
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path)
    plt.close(fig)
    return out_path


def distance_vs_metric_figure(
    rows: list[dict[str, Any]],
    *,
    metric_key: str,
    ylabel: str,
    title: str,
    out_path: Path,
) -> Path:
    """Figure: scatter of a metric against baseline distance.

    Only rows with a valid distance and non-null metric are plotted; failed
    sessions are not silently dropped from the underlying data, only absent
    here with a clear reason recorded in the report.
    """
    _style()
    points = [
        (row["baseline_distance_km"], row[metric_key])
        for row in rows
        if row.get(metric_key) is not None
    ]
    fig, ax = plt.subplots(figsize=(7, 5))
    if points:
        xs = [p[0] for p in points]
        ys = [p[1] for p in points]
        ax.plot(xs, ys, "o", color="#2ca02c")
        ax.set_xlabel("Baseline distance (km)")
        ax.set_ylabel(ylabel)
        ax.set_title(title)
        ax.grid(True)
        if len(points) >= 3:
            _fit_line(ax, xs, ys)
    else:
        ax.text(
            0.5,
            0.5,
            "No valid metric values for this figure",
            ha="center",
            va="center",
            transform=ax.transAxes,
        )
        ax.set_title(title)
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path)
    plt.close(fig)
    return out_path


def solution_status_timeline(
    epochs: list[dict[str, Any]],
    out_path: Path,
) -> Path:
    """Figure: FIX / FLOAT / other status timeline for one experiment."""
    _style()
    status_map = {"FIX": 3, "FLOAT": 2, "SINGLE": 1, "DGPS": 0}
    values = [
        status_map.get(epoch.get("quality", ""), -1) for epoch in epochs if epoch.get("quality")
    ]
    fig, ax = plt.subplots(figsize=(10, 3))
    if values:
        ax.plot(range(len(values)), values, drawstyle="steps-post", lw=1.0)
        ax.set_yticks([-1, 0, 1, 2, 3])
        ax.set_yticklabels(["other", "DGPS", "SINGLE", "FLOAT", "FIX"])
        ax.set_ylim(-1.5, 3.5)
        ax.set_xlabel("Epoch index")
        ax.set_ylabel("Solution status")
        ax.set_title("Single-base RTK solution-status timeline")
        ax.grid(True, axis="y")
    else:
        ax.text(
            0.5,
            0.5,
            "No parsed epochs",
            ha="center",
            va="center",
            transform=ax.transAxes,
        )
        ax.set_title("Single-base RTK solution-status timeline")
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path)
    plt.close(fig)
    return out_path


def enu_residual_timeseries(
    epochs: list[dict[str, Any]],
    out_path: Path,
) -> Path:
    """Figure: ENU residual time series for one experiment."""
    _style()
    east = [float(e["east_m"]) for e in epochs if e.get("east_m") is not None]
    north = [float(e["north_m"]) for e in epochs if e.get("north_m") is not None]
    up = [float(e["up_m"]) for e in epochs if e.get("up_m") is not None]

    fig, axes = plt.subplots(3, 1, figsize=(10, 7), sharex=True)
    if east and north and up:
        axes[0].plot(range(len(east)), east, lw=0.8, color="#1f77b4")
        axes[1].plot(range(len(north)), north, lw=0.8, color="#ff7f0e")
        axes[2].plot(range(len(up)), up, lw=0.8, color="#2ca02c")
        axes[0].set_ylabel("East (m)")
        axes[1].set_ylabel("North (m)")
        axes[2].set_ylabel("Up (m)")
        axes[0].set_title("ENU residuals against control coordinate")
        axes[0].grid(True)
        axes[1].grid(True)
        axes[2].grid(True)
        axes[2].set_xlabel("Epoch index")
    else:
        axes[0].text(
            0.5,
            0.5,
            "No residual values",
            ha="center",
            va="center",
            transform=axes[0].transAxes,
        )
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path)
    plt.close(fig)
    return out_path


def per_baseline_comparison(
    aggregates: dict[str, dict[str, Any]],
    out_path: Path,
) -> Path:
    """Figure: per-baseline comparison of mean horizontal RMSE."""
    _style()
    labels = sorted(aggregates, key=lambda k: aggregates[k]["mean_baseline_distance_km"])
    fig, ax = plt.subplots(figsize=(8, 5))
    if labels:
        xs = [aggregates[k]["mean_baseline_distance_km"] for k in labels]
        ys = [aggregates[k]["mean_horizontal_rmse_m"] for k in labels]
        names = [k for k in labels]
        ax.plot(xs, ys, "o-", color="#9467bd")
        for x, y, name in zip(xs, ys, names, strict=True):
            ax.annotate(name, (x, y), xytext=(4, 4), textcoords="offset points", fontsize=7)
        ax.set_xlabel("Baseline distance (km)")
        ax.set_ylabel("Mean horizontal RMSE (m)")
        ax.set_title("Per-baseline mean horizontal RMSE")
        ax.grid(True)
    else:
        ax.text(
            0.5,
            0.5,
            "No aggregates available",
            ha="center",
            va="center",
            transform=ax.transAxes,
        )
        ax.set_title("Per-baseline mean horizontal RMSE")
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path)
    plt.close(fig)
    return out_path


def baseline_distance_distribution(
    rows: list[dict[str, Any]],
    out_path: Path,
) -> Path:
    """Figure: histogram of baseline distances across experiments."""
    _style()
    distances = [
        row["baseline_distance_km"]
        for row in rows
        if row.get("baseline_distance_km") is not None
    ]
    fig, ax = plt.subplots(figsize=(7, 5))
    if distances:
        ax.hist(distances, bins=10, color="#1f77b4", edgecolor="black")
        ax.set_xlabel("Baseline distance (km)")
        ax.set_ylabel("Number of experiments")
        ax.set_title("Baseline-distance distribution")
        ax.grid(True, axis="y")
    else:
        ax.text(
            0.5,
            0.5,
            "No baseline rows",
            ha="center",
            va="center",
            transform=ax.transAxes,
        )
        ax.set_title("Baseline-distance distribution")
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path)
    plt.close(fig)
    return out_path


def _fit_line(ax: Any, xs: list[float], ys: list[float]) -> None:
    import numpy as np

    coeffs = np.polyfit(xs, ys, 1)
    poly = np.poly1d(coeffs)
    ordered_x = sorted(xs)
    ax.plot(
        ordered_x,
        [poly(x) for x in ordered_x],
        "--",
        color="#d62728",
        label=f"linear fit r={_corr(xs, ys):.2f}",
    )
    ax.legend()
    ax.grid(True)


def _corr(xs: list[float], ys: list[float]) -> float:
    import numpy as np

    if len(xs) < 2:
        return 0.0
    return float(np.corrcoef(xs, ys)[0][1])
