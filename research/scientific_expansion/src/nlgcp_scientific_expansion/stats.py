"""Descriptive statistics with uncertainty (pure NumPy, no causality claims)."""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class SummaryStats:
    """Descriptive summary for one metric sample."""

    n: int = 0
    mean: float = math.nan
    std: float = math.nan
    minimum: float = math.nan
    first_quartile: float = math.nan
    median: float = math.nan
    third_quartile: float = math.nan
    maximum: float = math.nan


@dataclass(frozen=True)
class CorrelationResult:
    """Pearson correlation with Fisher-z 95% confidence interval."""

    n: int = 0
    method: str = "pearson"
    coefficient: float = math.nan
    ci_low: float = math.nan
    ci_high: float = math.nan


def summarize(values: list[float]) -> SummaryStats:
    """Compute descriptive statistics; empty input yields n=0 (never invented)."""
    import numpy as np

    clean = [value for value in values if value == value]
    if not clean:
        return SummaryStats()
    array = np.asarray(clean, dtype=float)
    return SummaryStats(
        n=int(array.size),
        mean=float(np.mean(array)),
        std=float(np.std(array, ddof=1)) if array.size > 1 else 0.0,
        minimum=float(np.min(array)),
        first_quartile=float(np.quantile(array, 0.25)),
        median=float(np.median(array)),
        third_quartile=float(np.quantile(array, 0.75)),
        maximum=float(np.max(array)),
    )


def pearson_with_ci(xs: list[float], ys: list[float]) -> CorrelationResult:
    """Pearson r with Fisher-z 95% CI; mismatched/empty input yields n=0."""
    import numpy as np

    pairs = [
        (x, y)
        for x, y in zip(xs, ys, strict=True)
        if x == x and y == y
    ] if len(xs) == len(ys) else []
    if len(pairs) < 3:
        return CorrelationResult(n=len(pairs))
    array = np.asarray(pairs, dtype=float)
    x_std = float(np.std(array[:, 0], ddof=1))
    y_std = float(np.std(array[:, 1], ddof=1))
    if x_std == 0.0 or y_std == 0.0:
        return CorrelationResult(n=len(pairs), coefficient=math.nan)
    coef = float(np.corrcoef(array[:, 0], array[:, 1])[0, 1])
    clipped = min(max(coef, -0.999999), 0.999999)
    z_value = math.atanh(clipped)
    half = 1.96 / math.sqrt(len(pairs) - 3)
    ci_low = min(math.tanh(z_value - half), coef)
    ci_high = max(math.tanh(z_value + half), coef)
    return CorrelationResult(
        n=len(pairs),
        coefficient=coef,
        ci_low=ci_low,
        ci_high=ci_high,
    )


def fix_rate_summary(fix_epochs: int, total_epochs: int) -> dict[str, float | int]:
    """Fix-rate fraction with explicit zero denominator handling."""
    if total_epochs <= 0:
        return {"fix_epochs": fix_epochs, "total_epochs": 0, "fix_rate": math.nan}
    return {
        "fix_epochs": fix_epochs,
        "total_epochs": total_epochs,
        "fix_rate": fix_epochs / total_epochs,
    }
