"""Multi-model spatial interpolation and stratified LOOCV (Phase 6 Workstream C).

Upgrades Phase 6 spatial modelling while preserving ``zero`` as the operational
fallback:
- True arbitrary-N 2D ENU convex hull containment (never treating extrapolation
  as ordinary interpolation);
- Five explicit models on identical comparison samples:
  ``zero``, ``nearest``, ``idw`` (p=1), ``idw2`` (p=2), ``planar``;
- Optional physically motivated ``ipp_idw2`` interpolating in Ionospheric Pierce
  Point (IPP) coordinates when IPP positions are supplied;
- Extended residual distribution metrics (bias, MAE, RMSE, std, P95 |err|,
  quantiles P05/P50/P95, min/max, Pearson correlation);
- Stratified LOOCV reporting INTERIOR (convex-hull interpolated) vs PERIMETER
  (extrapolated) performance separately so network geometry effects are transparent.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from .dataset_audit import convex_hull_2d, point_in_convex_hull_2d
from .interpolation import plane_diagnostics
from .metrics import bias, correlation, mae, rmse, std
from .spatial import baseline_length_m, ecef_to_local_enu

SPATIAL_MODELS = ("zero", "nearest", "idw", "idw2", "planar")
SPATIAL_MODEL_MINIMUMS = {
    "zero": 0,
    "nearest": 1,
    "idw": 2,
    "idw2": 2,
    "planar": 3,
    "ipp_idw2": 2,
}


@dataclass(frozen=True, slots=True)
class SpatialPrediction:
    """One model prediction with explicit geometry containment and provenance."""

    epoch_iso: str
    satellite_id: str
    target_station: str
    model_name: str
    predicted_m: float | None
    observed_m: float | None
    residual_m: float | None
    inside_convex_hull: bool
    extrapolated: bool
    usable_references: int
    reason: str | None = None


def percentile(sorted_values: Sequence[float], q: float) -> float | None:
    """Linear-interpolated percentile q in [0, 100] over pre-sorted values."""
    if not sorted_values:
        return None
    if len(sorted_values) == 1:
        return float(sorted_values[0])
    pos = (q / 100.0) * (len(sorted_values) - 1)
    lo = int(math.floor(pos))
    hi = min(len(sorted_values) - 1, lo + 1)
    frac = pos - lo
    return float(sorted_values[lo] * (1.0 - frac) + sorted_values[hi] * frac)


def extended_residual_metrics(residuals: list[float]) -> dict[str, Any]:
    """Compute bias, MAE, RMSE, std, P95 |err|, and residual distribution quantiles."""
    if not residuals:
        return {
            "count": 0,
            "bias_m": None,
            "mae_m": None,
            "rmse_m": None,
            "std_m": None,
            "p95_abs_m": None,
            "min_m": None,
            "p05_m": None,
            "median_m": None,
            "p95_m": None,
            "max_m": None,
        }
    ordered = sorted(residuals)
    abs_ordered = sorted(abs(v) for v in residuals)
    return {
        "count": len(residuals),
        "bias_m": bias(residuals),
        "mae_m": mae(residuals),
        "rmse_m": rmse(residuals),
        "std_m": std(residuals),
        "p95_abs_m": percentile(abs_ordered, 95.0),
        "min_m": ordered[0],
        "p05_m": percentile(ordered, 5.0),
        "median_m": percentile(ordered, 50.0),
        "p95_m": percentile(ordered, 95.0),
        "max_m": ordered[-1],
    }


def _target_inside_hull(
    target_xyz: tuple[float, float, float],
    ref_xyzs: list[tuple[float, float, float]],
) -> bool:
    if len(ref_xyzs) < 3:
        return False
    centroid = (
        sum(p[0] for p in ref_xyzs) / len(ref_xyzs),
        sum(p[1] for p in ref_xyzs) / len(ref_xyzs),
        sum(p[2] for p in ref_xyzs) / len(ref_xyzs),
    )
    ref_2d = [ecef_to_local_enu(p, centroid)[:2] for p in ref_xyzs]
    tgt_2d = ecef_to_local_enu(target_xyz, centroid)[:2]
    hull = convex_hull_2d(ref_2d)
    return point_in_convex_hull_2d(tgt_2d, hull)


def _great_circle_km(lat1_deg: float, lon1_deg: float, lat2_deg: float, lon2_deg: float) -> float:
    r_km = 6371.0
    p1, p2 = math.radians(lat1_deg), math.radians(lat2_deg)
    dp = math.radians(lat2_deg - lat1_deg)
    dl = math.radians(lon2_deg - lon1_deg)
    a = math.sin(dp / 2.0) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2.0) ** 2
    return 2.0 * r_km * math.asin(min(1.0, math.sqrt(max(0.0, a))))


def predict_spatial(
    *,
    model_name: str,
    epoch_iso: str,
    satellite_id: str,
    target_station: str,
    target_xyz: tuple[float, float, float],
    references: Sequence[tuple[str, tuple[float, float, float], float | None]],
    observed_m: float | None = None,
    target_ipp: tuple[float, float] | None = None,
    reference_ipps: dict[str, tuple[float, float]] | None = None,
    inside_override: bool | None = None,
) -> SpatialPrediction:
    """Predict target value using one of ``zero|nearest|idw|idw2|planar|ipp_idw2``."""
    if model_name not in SPATIAL_MODEL_MINIMUMS:
        raise ValueError(f"unsupported spatial model: {model_name!r}")
    usable = sorted((sid, xyz, float(v)) for sid, xyz, v in references if v is not None)
    inside = (
        inside_override
        if inside_override is not None
        else _target_inside_hull(target_xyz, [xyz for _, xyz, _ in usable])
    )
    minimum = SPATIAL_MODEL_MINIMUMS[model_name]
    predicted: float | None = None
    reason: str | None = None

    if len(usable) < minimum:
        reason = f"insufficient usable references: {len(usable)} < {minimum}"
    elif model_name == "zero":
        predicted = 0.0
    elif model_name == "nearest":
        nearest = min(usable, key=lambda item: baseline_length_m(item[1], target_xyz))
        predicted = nearest[2]
    elif model_name in ("idw", "idw2"):
        power = 1.0 if model_name == "idw" else 2.0
        dists = [baseline_length_m(xyz, target_xyz) for _, xyz, _ in usable]
        min_d = min(dists)
        if min_d == 0.0:
            predicted = usable[dists.index(0.0)][2]
        else:
            weights = [(min_d / d) ** power for d in dists]
            predicted = sum(w * v for w, (_, _, v) in zip(weights, usable, strict=True)) / sum(
                weights
            )
    elif model_name == "ipp_idw2":
        if target_ipp is None or reference_ipps is None:
            reason = "IPP coordinates unavailable"
        else:
            ipp_usable = [
                (sid, reference_ipps[sid], v) for sid, _, v in usable if sid in reference_ipps
            ]
            if len(ipp_usable) < minimum:
                reason = f"insufficient IPP references: {len(ipp_usable)} < {minimum}"
            else:
                dists_km = [
                    _great_circle_km(target_ipp[0], target_ipp[1], ipp[0], ipp[1])
                    for _, ipp, _ in ipp_usable
                ]
                min_d = min(dists_km)
                if min_d <= 1e-9:
                    predicted = ipp_usable[dists_km.index(min_d)][2]
                else:
                    weights = [(min_d / d) ** 2.0 for d in dists_km]
                    predicted = sum(
                        w * v for w, (_, _, v) in zip(weights, ipp_usable, strict=True)
                    ) / sum(weights)
    elif model_name == "planar":
        centroid = (
            sum(xyz[0] for _, xyz, _ in usable) / len(usable),
            sum(xyz[1] for _, xyz, _ in usable) / len(usable),
            sum(xyz[2] for _, xyz, _ in usable) / len(usable),
        )
        pts = [(*ecef_to_local_enu(xyz, centroid)[:2], v) for _, xyz, v in usable]
        diag = plane_diagnostics(pts)
        fit = diag["coefficients"]
        if fit is None:
            reason = "singular planar geometry"
        else:
            te, tn, _ = ecef_to_local_enu(target_xyz, centroid)
            predicted = fit[0] * te + fit[1] * tn + fit[2]

    residual = (
        (observed_m - predicted)
        if (observed_m is not None and predicted is not None)
        else None
    )
    return SpatialPrediction(
        epoch_iso=epoch_iso,
        satellite_id=satellite_id,
        target_station=target_station,
        model_name=model_name,
        predicted_m=predicted,
        observed_m=observed_m,
        residual_m=residual,
        inside_convex_hull=inside,
        extrapolated=not inside,
        usable_references=len(usable),
        reason=reason,
    )


def run_stratified_loocv(
    *,
    coords: dict[str, tuple[float, float, float]],
    observed: dict[tuple[str, str, str], float],
    models: tuple[str, ...] = SPATIAL_MODELS,
    ipp_by_key: dict[tuple[str, str, str], tuple[float, float]] | None = None,
    min_refs: int = 3,
    datum_station: str | None = None,
    reanchor_per_fold: bool = True,
) -> dict[str, Any]:
    """Leave-one-station-out validation stratified by INTERIOR vs PERIMETER folds.

    Every model is evaluated on the exact identical set of ``(epoch, sat, target)``
    keys where ALL requested models produced finite predictions. When
    ``reanchor_per_fold=True``, each fold's field is referenced to the nearest
    available reference station (avoiding a held-out datum station from becoming a
    trivial constant zero target).
    """
    stations = sorted(coords)
    keys_by_epoch_sat: dict[tuple[str, str], set[str]] = {}
    for ep, sat, sid in observed:
        if sid in coords:
            keys_by_epoch_sat.setdefault((ep, sat), set()).add(sid)

    per_model: dict[str, dict[tuple[str, str, str], SpatialPrediction]] = {m: {} for m in models}
    fold_meta: dict[str, dict[str, Any]] = {}
    hull_cache: dict[tuple[str, tuple[str, ...]], bool] = {}

    for target in stations:
        if not reanchor_per_fold and datum_station is not None and target == datum_station:
            continue
        refs_all = [s for s in stations if s != target]
        inside_all = _target_inside_hull(coords[target], [coords[r] for r in refs_all])
        # Nearest reference in this fold acts as fold anchor when reanchoring
        nearest_ref = min(refs_all, key=lambda r: baseline_length_m(coords[r], coords[target]))
        fold_meta[target] = {
            "target": target,
            "references": refs_all,
            "inside_convex_hull": inside_all,
            "geometry_class": "INTERIOR" if inside_all else "PERIMETER_EXTRAPOLATION",
            "nearest_ref": nearest_ref,
            "nearest_ref_km": round(
                baseline_length_m(coords[nearest_ref], coords[target]) / 1000.0, 2
            ),
        }
        if len(refs_all) < min_refs:
            continue

        for (ep, sat), present in sorted(keys_by_epoch_sat.items()):
            if target not in present:
                continue
            avail_refs = [r for r in refs_all if r in present]
            if len(avail_refs) < min_refs:
                continue
            if reanchor_per_fold:
                fold_anchor = min(
                    avail_refs, key=lambda r: baseline_length_m(coords[r], coords[target])
                )
                offset = observed[(ep, sat, fold_anchor)]
            else:
                offset = 0.0
            obs_target = observed[(ep, sat, target)] - offset
            ref_triples = [(r, coords[r], observed[(ep, sat, r)] - offset) for r in avail_refs]
            tgt_ipp = ipp_by_key.get((ep, sat, target)) if ipp_by_key else None
            ref_ipps = (
                {
                    r: ipp_by_key[(ep, sat, r)]
                    for r in avail_refs
                    if (ep, sat, r) in ipp_by_key
                }
                if ipp_by_key
                else None
            )
            key = (ep, sat, target)
            hull_key = (target, tuple(avail_refs))
            inside_subset = hull_cache.get(hull_key)
            if inside_subset is None:
                inside_subset = _target_inside_hull(coords[target], [coords[r] for r in avail_refs])
                hull_cache[hull_key] = inside_subset
            for model in models:
                pred = predict_spatial(
                    model_name=model,
                    epoch_iso=ep,
                    satellite_id=sat,
                    target_station=target,
                    target_xyz=coords[target],
                    references=ref_triples,
                    observed_m=obs_target,
                    target_ipp=tgt_ipp,
                    reference_ipps=ref_ipps,
                    inside_override=inside_subset,
                )
                if pred.predicted_m is not None and pred.residual_m is not None:
                    per_model[model][key] = pred

    common_keys = (
        sorted(set.intersection(*(set(per_model[m]) for m in models))) if models else []
    )
    interior_keys = [k for k in common_keys if fold_meta[k[2]]["inside_convex_hull"]]
    perimeter_keys = [k for k in common_keys if not fold_meta[k[2]]["inside_convex_hull"]]

    def summarize_subset(subset: list[tuple[str, str, str]]) -> dict[str, Any]:
        summary: dict[str, Any] = {}
        for m in models:
            preds = [per_model[m][k] for k in subset]
            resids = [float(p.residual_m) for p in preds if p.residual_m is not None]
            pvals = [float(p.predicted_m) for p in preds if p.predicted_m is not None]
            ovals = [float(p.observed_m) for p in preds if p.observed_m is not None]
            summary[m] = {
                **extended_residual_metrics(resids),
                "correlation_predicted_observed": correlation(pvals, ovals),
            }
        ranked = sorted(
            (m for m in models if summary[m]["rmse_m"] is not None),
            key=lambda m: float(summary[m]["rmse_m"]),
        )
        best = ranked[0] if ranked else None
        zero_rmse = summary.get("zero", {}).get("rmse_m")
        gain_pct: dict[str, float | None] = {}
        for m in models:
            m_rmse = summary[m]["rmse_m"]
            if zero_rmse and m_rmse is not None and zero_rmse > 0:
                gain_pct[m] = round((1.0 - m_rmse / zero_rmse) * 100.0, 2)
            else:
                gain_pct[m] = None
        return {
            "comparison_keys": len(subset),
            "best_model": best,
            "rmse_reduction_vs_zero_pct": gain_pct,
            "models": summary,
        }

    fold_reports: list[dict[str, Any]] = []
    for target in sorted(fold_meta):
        t_keys = [k for k in common_keys if k[2] == target]
        fold_reports.append({**fold_meta[target], **summarize_subset(t_keys)})

    return {
        "operational_default": "zero",
        "models_evaluated": list(models),
        "reanchor_per_fold": reanchor_per_fold,
        "overall": summarize_subset(common_keys),
        "interior_interpolated": summarize_subset(interior_keys),
        "perimeter_extrapolated": summarize_subset(perimeter_keys),
        "folds": fold_reports,
    }
