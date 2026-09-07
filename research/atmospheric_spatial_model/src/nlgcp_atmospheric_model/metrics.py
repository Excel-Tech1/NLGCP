"""Validation metrics and spatial-decorrelation analysis (Phase 6)."""

from __future__ import annotations

import math
from typing import Any


def bias(values: list[float]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


def mae(values: list[float]) -> float | None:
    if not values:
        return None
    return sum(abs(v) for v in values) / len(values)


def rmse(values: list[float]) -> float | None:
    if not values:
        return None
    return math.sqrt(sum(v * v for v in values) / len(values))


def std(values: list[float]) -> float | None:
    if len(values) < 2:
        return None
    mean = sum(values) / len(values)
    return math.sqrt(sum((v - mean) ** 2 for v in values) / (len(values) - 1))


def correlation(xs: list[float], ys: list[float]) -> float | None:
    """Pearson correlation; None when undefined (constant series)."""
    if len(xs) != len(ys) or len(xs) < 2:
        return None
    mx = sum(xs) / len(xs)
    my = sum(ys) / len(ys)
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    if sxx == 0.0 or syy == 0.0:
        return None
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True)) / math.sqrt(
        sxx * syy
    )


def prediction_metrics(residuals: list[float], *, tolerance_m: float = 0.05) -> dict[str, Any]:
    """bias/MAE/RMSE/std plus coverage within tolerance (all SI metres)."""
    covered = sum(1 for r in residuals if abs(r) <= tolerance_m)
    return {
        "count": len(residuals),
        "bias_m": bias(residuals),
        "mae_m": mae(residuals),
        "rmse_m": rmse(residuals),
        "std_m": std(residuals),
        "coverage_within_tolerance": (covered / len(residuals)) if residuals else None,
        "tolerance_m": tolerance_m,
    }


def decorrelation_fit(
    distances_m: list[float], rms_values_m: list[float]
) -> dict[str, Any]:
    """Least-squares RMS-vs-distance fit (pilot evidence only, documented).

    Returns slope (m per km), intercept, correlation, and sample count. With
    one day and a handful of baselines this cannot establish a national
    decorrelation law; callers must label it representative/pilot evidence.
    """
    if len(distances_m) != len(rms_values_m) or len(distances_m) < 2:
        return {
            "slope_m_per_km": None,
            "intercept_m": None,
            "correlation": None,
            "pair_count": len(distances_m),
            "note": "insufficient pairs for a decorrelation fit",
        }
    xs = [d / 1000.0 for d in distances_m]
    ys = list(rms_values_m)
    mx = sum(xs) / len(xs)
    my = sum(ys) / len(ys)
    sxx = sum((x - mx) ** 2 for x in xs)
    slope = (
        sum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True)) / sxx
        if sxx > 0
        else None
    )
    return {
        "slope_m_per_km": slope,
        "intercept_m": (my - slope * mx) if slope is not None else None,
        "correlation": correlation(xs, ys),
        "pair_count": len(xs),
        "note": (
            "representative/pilot evidence only: one day, "
            f"{len(xs)} baseline pairs; not a national decorrelation law"
        ),
    }
