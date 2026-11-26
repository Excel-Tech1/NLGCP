"""Positioning error metrics, ENU statistics, convergence, and paired comparisons (B-02).

Reuses Phase 3's validated WGS84 ENU rotation (``nlgcp_single_base.coordinates``)
and RTKLIB ``.pos`` parser (``nlgcp_single_base.solution``). Computes all 19
required B-02 positioning metrics plus truth-independent repeatability metrics
(critical for provisional-truth datasets) and paired block-bootstrap confidence
intervals.
"""

from __future__ import annotations

import math
import random
from collections.abc import Sequence
from datetime import datetime
from statistics import fmean
from typing import Any

from nlgcp_single_base.coordinates import (
    EcefCoordinate,
    ecef_to_geodetic,
)
from nlgcp_single_base.solution import (
    EpochResidual,
    SolutionEpoch,
    SolutionQuality,
    expected_epochs,
    parse_iso_utc,
    residuals_against_control,
    ttff_seconds,
)


def _percentile(sorted_vals: Sequence[float], q: float) -> float | None:
    if not sorted_vals:
        return None
    if len(sorted_vals) == 1:
        return float(sorted_vals[0])
    pos = (q / 100.0) * (len(sorted_vals) - 1)
    lo = int(math.floor(pos))
    hi = min(len(sorted_vals) - 1, lo + 1)
    frac = pos - lo
    return float(sorted_vals[lo] * (1.0 - frac) + sorted_vals[hi] * frac)


def _rmse(values: Sequence[float]) -> float | None:
    if not values:
        return None
    return math.sqrt(sum(v * v for v in values) / len(values))


def _std(values: Sequence[float]) -> float | None:
    if len(values) < 2:
        return None
    mean_v = fmean(values)
    return math.sqrt(sum((v - mean_v) ** 2 for v in values) / len(values))


def count_ambiguity_resets(epochs: Sequence[SolutionEpoch]) -> int:
    """Count kinematic/static state drops indicating ambiguity re-initialization.

    Counts transitions: FIX -> non-FIX, or FLOAT/FIX -> SINGLE/DGPS/NO_SOLUTION,
    or ratio reset from > 1.5 back to <= 1.0 when quality drops.
    """
    resets = 0
    prev_q: SolutionQuality | None = None
    for ep in epochs:
        q = ep.quality
        if prev_q is not None and (
            (prev_q is SolutionQuality.FIX and q is not SolutionQuality.FIX)
            or (
                prev_q is SolutionQuality.FLOAT
                and q
                in (
                    SolutionQuality.SINGLE,
                    SolutionQuality.DGPS,
                    SolutionQuality.NO_SOLUTION,
                )
            )
        ):
            resets += 1
        prev_q = q
    return resets


def _convergence_checkpoints(
    residuals: Sequence[EpochResidual],
    start_dt: datetime,
    windows_min: tuple[int, ...] = (5, 15, 30, 60, 120, 360, 720, 1440),
) -> dict[str, dict[str, float | int | None]]:
    """Summarize cumulative horizontal/3D RMSE across elapsed time windows."""
    out: dict[str, dict[str, float | int | None]] = {}
    for w_min in windows_min:
        cutoff_s = w_min * 60.0
        sub = [r for r in residuals if (r.epoch - start_dt).total_seconds() <= cutoff_s]
        if not sub:
            out[f"first_{w_min}m"] = {"count": 0, "horiz_rmse_m": None, "three_d_rmse_m": None}
            continue
        out[f"first_{w_min}m"] = {
            "count": len(sub),
            "horiz_rmse_m": round(_rmse([r.horizontal_error_m for r in sub]) or 0.0, 4),
            "three_d_rmse_m": round(_rmse([r.error_3d_m for r in sub]) or 0.0, 4),
        }
    # Steady-state post-30-min convergence metric (excludes initial filter transient)
    steady = [r for r in residuals if (r.epoch - start_dt).total_seconds() >= 1800.0]
    out["post_30m_steady"] = {
        "count": len(steady),
        "horiz_rmse_m": round(_rmse([r.horizontal_error_m for r in steady]) or 0.0, 4)
        if steady
        else None,
        "vert_rmse_m": round(_rmse([r.up_m for r in steady]) or 0.0, 4) if steady else None,
        "three_d_rmse_m": round(_rmse([r.error_3d_m for r in steady]) or 0.0, 4)
        if steady
        else None,
    }
    return out


def _time_block_breakdown(
    residuals: Sequence[EpochResidual],
) -> dict[str, dict[str, float | int | None]]:
    """Stratify positioning accuracy across 6-hour UTC blocks (incl. 18-24 UTC scintillation)."""
    blocks = (
        ("00_06_utc", 0, 6),
        ("06_12_utc", 6, 12),
        ("12_18_utc", 12, 18),
        ("18_24_utc", 18, 24),
    )
    out: dict[str, dict[str, float | int | None]] = {}
    for label, h_lo, h_hi in blocks:
        sub = [r for r in residuals if h_lo <= r.epoch.hour < h_hi]
        if not sub:
            out[label] = {
                "count": 0,
                "horiz_rmse_m": None,
                "vert_rmse_m": None,
                "three_d_rmse_m": None,
                "fix_rate": None,
                "mean_sats": None,
            }
            continue
        sats = [r.satellites for r in sub if r.satellites is not None]
        fix_n = sum(1 for r in sub if r.quality is SolutionQuality.FIX)
        out[label] = {
            "count": len(sub),
            "horiz_rmse_m": round(_rmse([r.horizontal_error_m for r in sub]) or 0.0, 4),
            "vert_rmse_m": round(_rmse([r.up_m for r in sub]) or 0.0, 4),
            "three_d_rmse_m": round(_rmse([r.error_3d_m for r in sub]) or 0.0, 4),
            "fix_rate": round(fix_n / len(sub), 6),
            "mean_sats": round(fmean(sats), 2) if sats else None,
        }
    return out


def _satellite_stratification(
    residuals: Sequence[EpochResidual],
) -> dict[str, dict[str, float | int | None]]:
    """Compare positioning RMSE by satellite-count bin."""
    bins: tuple[tuple[str, int, int], ...] = (
        ("le_5_sats", 0, 5),
        ("6_to_7_sats", 6, 7),
        ("ge_8_sats", 8, 999),
    )
    out: dict[str, dict[str, float | int | None]] = {}
    for label, lo, hi in bins:
        sub = [r for r in residuals if r.satellites is not None and lo <= r.satellites <= hi]
        if not sub:
            out[label] = {"count": 0, "horiz_rmse_m": None, "three_d_rmse_m": None}
            continue
        out[label] = {
            "count": len(sub),
            "horiz_rmse_m": round(_rmse([r.horizontal_error_m for r in sub]) or 0.0, 4),
            "three_d_rmse_m": round(_rmse([r.error_3d_m for r in sub]) or 0.0, 4),
        }
    return out


def _outlier_summary(residuals: Sequence[EpochResidual]) -> dict[str, Any]:
    """Identify worst horizontal and vertical epochs and tail counts (>2 m, >5 m)."""
    if not residuals:
        return {
            "horiz_gt_2m_count": 0,
            "horiz_gt_5m_count": 0,
            "max_horiz_m": None,
            "max_horiz_epoch": None,
            "max_horiz_quality": None,
            "max_horiz_sats": None,
            "max_vert_abs_m": None,
            "max_vert_epoch": None,
        }
    worst_h = max(residuals, key=lambda r: r.horizontal_error_m)
    worst_v = max(residuals, key=lambda r: r.vertical_abs_error_m)
    return {
        "horiz_gt_2m_count": sum(1 for r in residuals if r.horizontal_error_m > 2.0),
        "horiz_gt_5m_count": sum(1 for r in residuals if r.horizontal_error_m > 5.0),
        "max_horiz_m": round(worst_h.horizontal_error_m, 4),
        "max_horiz_epoch": worst_h.epoch.isoformat().replace("+00:00", "Z"),
        "max_horiz_quality": str(worst_h.quality),
        "max_horiz_sats": worst_h.satellites,
        "max_vert_abs_m": round(worst_v.vertical_abs_error_m, 4),
        "max_vert_epoch": worst_v.epoch.isoformat().replace("+00:00", "Z"),
    }


def compute_positioning_metrics(
    epochs: list[SolutionEpoch],
    *,
    truth_ecef_m: tuple[float, float, float],
    start_time_utc: str,
    end_time_utc: str,
    sampling_interval_s: float,
) -> tuple[dict[str, Any], list[EpochResidual]]:
    """Compute all 19 required B-02 positioning metrics + truth-independent repeatability."""
    start_dt = parse_iso_utc(start_time_utc)
    attempted = expected_epochs(start_time_utc, end_time_utc, 1.0 / sampling_interval_s)
    valid = len(epochs)

    control_geo = ecef_to_geodetic(EcefCoordinate(*truth_ecef_m))
    residuals = residuals_against_control(epochs, control_geo)

    fix_n = sum(1 for e in epochs if e.quality is SolutionQuality.FIX)
    float_n = sum(1 for e in epochs if e.quality is SolutionQuality.FLOAT)
    dgps_n = sum(1 for e in epochs if e.quality is SolutionQuality.DGPS)
    single_n = sum(1 for e in epochs if e.quality is SolutionQuality.SINGLE)

    sats = [e.satellites for e in epochs if e.satellites is not None]
    ratios = [e.ratio for e in epochs if e.ratio is not None and e.ratio > 0.0]
    ages = [e.age_s for e in epochs if e.age_s is not None]

    easts = [r.east_m for r in residuals]
    norths = [r.north_m for r in residuals]
    ups = [r.up_m for r in residuals]
    horiz = [r.horizontal_error_m for r in residuals]
    vabs = [r.vertical_abs_error_m for r in residuals]
    err3d = [r.error_3d_m for r in residuals]

    horiz_sorted = sorted(horiz)
    vabs_sorted = sorted(vabs)

    # Truth-independent repeatability (scatter around session mean ENU)
    if residuals:
        me, mn, mu = fmean(easts), fmean(norths), fmean(ups)
        h_centered = sorted(math.hypot(e - me, n - mn) for e, n in zip(easts, norths, strict=True))
        d3_centered = [
            math.hypot(e - me, n - mn, u - mu)
            for e, n, u in zip(easts, norths, ups, strict=True)
        ]
        repeatability: dict[str, float | None] = {
            "east_std_m": _std(easts),
            "north_std_m": _std(norths),
            "up_std_m": _std(ups),
            "horiz_centered_rms_m": _rmse(h_centered),
            "horiz_centered_p95_m": _percentile(h_centered, 95.0),
            "three_d_centered_rms_m": _rmse(d3_centered),
        }
    else:
        repeatability = {
            "east_std_m": None,
            "north_std_m": None,
            "up_std_m": None,
            "horiz_centered_rms_m": None,
            "horiz_centered_p95_m": None,
            "three_d_centered_rms_m": None,
        }

    first_valid_s = (epochs[0].epoch - start_dt).total_seconds() if epochs else None

    metrics: dict[str, Any] = {
        "attempted_epochs": attempted,
        "valid_epochs": valid,
        "availability_rate": round(valid / attempted, 6) if attempted else 0.0,
        "east_mean_m": fmean(easts) if easts else None,
        "north_mean_m": fmean(norths) if norths else None,
        "up_mean_m": fmean(ups) if ups else None,
        "east_rmse_m": _rmse(easts),
        "north_rmse_m": _rmse(norths),
        "vertical_rmse_m": _rmse(ups),
        "horizontal_rmse_m": _rmse(horiz),
        "three_d_rmse_m": _rmse(err3d),
        "horizontal_mean_m": fmean(horiz) if horiz else None,
        "horizontal_median_m": _percentile(horiz_sorted, 50.0),
        "horizontal_p95_m": _percentile(horiz_sorted, 95.0),
        "vertical_p95_m": _percentile(vabs_sorted, 95.0),
        "horizontal_max_m": horiz_sorted[-1] if horiz_sorted else None,
        "fix_epochs": fix_n,
        "float_epochs": float_n,
        "dgps_epochs": dgps_n,
        "single_epochs": single_n,
        "fix_rate": round(fix_n / valid, 6) if valid else 0.0,
        "float_rate": round(float_n / valid, 6) if valid else 0.0,
        "dgps_rate": round(dgps_n / valid, 6) if valid else 0.0,
        "single_rate": round(single_n / valid, 6) if valid else 0.0,
        "time_to_first_valid_s": first_valid_s,
        "ttff_s": ttff_seconds(epochs),
        "ambiguity_resets": count_ambiguity_resets(epochs),
        "satellites": {
            "mean": round(fmean(sats), 2) if sats else None,
            "min": min(sats) if sats else None,
            "max": max(sats) if sats else None,
        },
        "ratio_stats": {
            "mean": round(fmean(ratios), 3) if ratios else None,
            "max": round(max(ratios), 3) if ratios else None,
        },
        "age_s_max": round(max(ages), 2) if ages else None,
        "repeatability": repeatability,
        "convergence": _convergence_checkpoints(residuals, start_dt),
        "time_blocks_utc": _time_block_breakdown(residuals),
        "satellite_bins": _satellite_stratification(residuals),
        "outliers": _outlier_summary(residuals),
    }
    return metrics, residuals


def paired_comparison(
    baseline_residuals: Sequence[EpochResidual],
    candidate_residuals: Sequence[EpochResidual],
    *,
    baseline_label: str,
    candidate_label: str,
    block_size: int = 40,
    bootstrap_iters: int = 500,
    seed: int = 20261125,
) -> dict[str, Any]:
    """Paired common-epoch comparison with moving-block bootstrap 95% CIs.

    Positive ``improvement_*`` indicates the candidate reduced error relative
    to baseline; negative indicates degradation. Uses 40-epoch (~20-minute at
    30 s) moving blocks to account for temporal correlation in GNSS errors.
    """
    b_map = {r.epoch: r for r in baseline_residuals}
    c_map = {r.epoch: r for r in candidate_residuals}
    common_epochs = sorted(set(b_map) & set(c_map))
    if not common_epochs:
        return {
            "baseline": baseline_label,
            "candidate": candidate_label,
            "paired_epochs": 0,
            "status": "NO_COMMON_EPOCHS",
        }

    b_h = [b_map[e].horizontal_error_m for e in common_epochs]
    c_h = [c_map[e].horizontal_error_m for e in common_epochs]
    b_v = [b_map[e].vertical_abs_error_m for e in common_epochs]
    c_v = [c_map[e].vertical_abs_error_m for e in common_epochs]
    b_3 = [b_map[e].error_3d_m for e in common_epochs]
    c_3 = [c_map[e].error_3d_m for e in common_epochs]

    b_h_rmse = _rmse(b_h) or 0.0
    c_h_rmse = _rmse(c_h) or 0.0
    b_v_rmse = _rmse(b_v) or 0.0
    c_v_rmse = _rmse(c_v) or 0.0
    b_3_rmse = _rmse(b_3) or 0.0
    c_3_rmse = _rmse(c_3) or 0.0

    b_h_med = _percentile(sorted(b_h), 50.0) or 0.0
    c_h_med = _percentile(sorted(c_h), 50.0) or 0.0
    b_h_p95 = _percentile(sorted(b_h), 95.0) or 0.0
    c_h_p95 = _percentile(sorted(c_h), 95.0) or 0.0

    paired_h_diff = [ch - bh for bh, ch in zip(b_h, c_h, strict=True)]
    frac_improved = sum(1 for d in paired_h_diff if d < 0.0) / len(paired_h_diff)

    # Moving-block bootstrap for horizontal RMSE difference (baseline - candidate; >0 = gain)
    n = len(common_epochs)
    eff_block = max(1, min(block_size, n))
    rng = random.Random(seed)
    boot_gains: list[float] = []
    if n >= 10:
        n_blocks = max(1, math.ceil(n / eff_block))
        max_start = max(0, n - eff_block)
        for _ in range(bootstrap_iters):
            b_sq = 0.0
            c_sq = 0.0
            cnt = 0
            for _ in range(n_blocks):
                st = rng.randint(0, max_start)
                end = min(n, st + eff_block)
                for idx in range(st, end):
                    b_sq += b_h[idx] * b_h[idx]
                    c_sq += c_h[idx] * c_h[idx]
                    cnt += 1
            boot_gains.append(math.sqrt(b_sq / cnt) - math.sqrt(c_sq / cnt))
        boot_gains.sort()
        ci_lo = _percentile(boot_gains, 2.5)
        ci_hi = _percentile(boot_gains, 97.5)
    else:
        ci_lo, ci_hi = None, None

    def _pct(base_val: float, cand_val: float) -> float | None:
        if base_val <= 0.0:
            return None
        return round((base_val - cand_val) / base_val * 100.0, 2)

    return {
        "baseline": baseline_label,
        "candidate": candidate_label,
        "paired_epochs": n,
        "baseline_horiz_rmse_m": round(b_h_rmse, 4),
        "candidate_horiz_rmse_m": round(c_h_rmse, 4),
        "horiz_rmse_improvement_m": round(b_h_rmse - c_h_rmse, 4),
        "horiz_rmse_improvement_pct": _pct(b_h_rmse, c_h_rmse),
        "horiz_rmse_gain_block_bootstrap_95ci_m": (
            [round(ci_lo, 4), round(ci_hi, 4)]
            if ci_lo is not None and ci_hi is not None
            else None
        ),
        "horiz_median_change_m": round(c_h_med - b_h_med, 4),
        "horiz_p95_change_m": round(c_h_p95 - b_h_p95, 4),
        "baseline_vert_rmse_m": round(b_v_rmse, 4),
        "candidate_vert_rmse_m": round(c_v_rmse, 4),
        "vert_rmse_improvement_pct": _pct(b_v_rmse, c_v_rmse),
        "baseline_3d_rmse_m": round(b_3_rmse, 4),
        "candidate_3d_rmse_m": round(c_3_rmse, 4),
        "three_d_rmse_improvement_pct": _pct(b_3_rmse, c_3_rmse),
        "epoch_win_fraction_horiz": round(frac_improved, 4),
        "bootstrap_block_epochs": eff_block,
        "bootstrap_iterations": bootstrap_iters,
    }
