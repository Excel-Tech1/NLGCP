"""Modular spatial interpolation framework (Phase 6).

Candidate estimators for the network error field at a target location:

* ``zero`` — zero-correction control (predicts 0.0);
* ``nearest`` — nearest-reference transfer control;
* ``idw`` — inverse-distance weighting (configurable power);
* ``planar`` — low-order spatial surface (least-squares plane in local ENU).

Complexity reflects the sparse DOY 026 geometry (three references): no
kriging or higher-order surfaces are implemented, because the sample count
cannot support them. Every prediction records whether the target lies
outside the reference bounding circle (``extrapolated``) and refuses to fit
when fewer than the method minimum references carry values.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any

from .models import InterpolationPrediction
from .spatial import baseline_length_m, ecef_to_local_enu

METHOD_MINIMUMS = {"zero": 0, "nearest": 1, "idw": 2, "planar": 3}
METHOD_NAMES = ("zero", "nearest", "idw", "planar")


def _extrapolated(
    target_xyz: tuple[float, float, float],
    ref_xyzs: list[tuple[float, float, float]],
    centroid: tuple[float, float, float],
) -> bool:
    if not ref_xyzs:
        return True
    radius = max(baseline_length_m(c, centroid) for c in ref_xyzs)
    return baseline_length_m(target_xyz, centroid) > radius


def _centroid(points: list[tuple[float, float, float]]) -> tuple[float, float, float]:
    n = len(points)
    return (
        sum(p[0] for p in points) / n,
        sum(p[1] for p in points) / n,
        sum(p[2] for p in points) / n,
    )


def _plane_fit(points: list[tuple[float, float, float]]) -> tuple[float, float, float] | None:
    """Least-squares plane z = a*x + b*y + c over local ENU points.

    Solved via normal equations with Gaussian elimination; returns None on
    singular (e.g. collinear) geometry instead of fabricating coefficients.
    """
    n = len(points)
    sx = sum(p[0] for p in points)
    sy = sum(p[1] for p in points)
    sz = sum(p[2] for p in points)
    sxx = sum(p[0] * p[0] for p in points)
    syy = sum(p[1] * p[1] for p in points)
    sxy = sum(p[0] * p[1] for p in points)
    sxz = sum(p[0] * p[2] for p in points)
    syz = sum(p[1] * p[2] for p in points)
    mat = [
        [sxx, sxy, sx, sxz],
        [sxy, syy, sy, syz],
        [sx, sy, float(n), sz],
    ]
    for col in range(3):
        pivot = max(range(col, 3), key=lambda r: abs(mat[r][col]))
        if abs(mat[pivot][col]) < 1e-12:
            return None
        mat[col], mat[pivot] = mat[pivot], mat[col]
        for row in range(col + 1, 3):
            factor = mat[row][col] / mat[col][col]
            for k in range(col, 4):
                mat[row][k] -= factor * mat[col][k]
    coef = [0.0, 0.0, 0.0]
    for row in (2, 1, 0):
        total = mat[row][3] - sum(mat[row][c] * coef[c] for c in range(row + 1, 3))
        coef[row] = total / mat[row][row]
    return coef[0], coef[1], coef[2]


def interpolate(
    *,
    model_name: str,
    epoch_iso: str,
    satellite_id: str,
    target_station: str,
    target_xyz: tuple[float, float, float],
    references: Sequence[tuple[str, tuple[float, float, float], float | None]],
    observed_m: float | None = None,
    power: float = 2.0,
) -> InterpolationPrediction:
    """Predict the error term at the target from reference values.

    ``references`` holds ``(station_id, xyz, value_or_None)`` triples.
    References with ``None`` values are excluded with the reason recorded;
    insufficient geometry yields a ``None`` prediction (fail-closed).
    """
    if model_name not in METHOD_MINIMUMS:
        raise ValueError(f"unknown interpolation model: {model_name}")
    usable = [(sid, xyz, value) for sid, xyz, value in references if value is not None]
    excluded = len(references) - len(usable)
    centroid = _centroid([xyz for _, xyz, _ in references]) if references else target_xyz
    extrapolated = _extrapolated(
        target_xyz, [xyz for _, xyz, _ in references], centroid
    )
    reason: str | None = None
    if excluded:
        reason = f"{excluded} reference(s) without values excluded"
    minimum = METHOD_MINIMUMS[model_name]
    predicted: float | None = None
    params: dict[str, Any] = {"power": power} if model_name == "idw" else {}
    if len(usable) < minimum:
        reason = ((reason + "; ") if reason else "") + (
            f"insufficient geometry: {len(usable)} usable references "
            f"< minimum {minimum} for {model_name}"
        )
    elif model_name == "zero":
        predicted = 0.0
    elif model_name == "nearest":
        best = min(usable, key=lambda item: baseline_length_m(item[1], target_xyz))
        predicted = best[2]
        params = {"source_station": best[0]}
    elif model_name == "idw":
        weights: list[float] = []
        for _, xyz, _ in usable:
            dist = baseline_length_m(xyz, target_xyz)
            if dist == 0.0:
                predicted = next(v for _, xyz2, v in usable if xyz2 == xyz)
                weights = []
                break
            weights.append(1.0 / (dist**power))
        if predicted is None and weights:
            assert all(v is not None for _, _, v in usable)
            total = sum(weights)
            predicted = sum(
                w * float(v) for w, (_, _, v) in zip(weights, usable, strict=True)
            ) / total
    elif model_name == "planar":
        origin = centroid
        local = [
            (*ecef_to_local_enu(xyz, origin), float(v))
            for _, xyz, v in usable
            if v is not None
        ]
        fit = _plane_fit([(p[0], p[1], p[3]) for p in local])
        if fit is None:
            reason = ((reason + "; ") if reason else "") + (
                "singular geometry: reference stations collinear, plane undefined"
            )
        else:
            a, b, c = fit
            te, tn, _ = ecef_to_local_enu(target_xyz, origin)
            predicted = a * te + b * tn + c
            params = {"a_m_per_m": a, "b_m_per_m": b, "c_m": c}
    residual: float | None = None
    if observed_m is not None and predicted is not None:
        residual = observed_m - predicted
    return InterpolationPrediction(
        epoch_iso=epoch_iso,
        satellite_id=satellite_id,
        target_station=target_station,
        model_name=model_name,
        predicted_m=predicted,
        observed_m=observed_m,
        residual_m=residual,
        extrapolated=extrapolated,
        model_parameters=params,
        reason=reason,
    )


def prediction_to_row(pred: InterpolationPrediction) -> dict[str, Any]:
    return {
        "epoch": pred.epoch_iso,
        "satellite": pred.satellite_id,
        "target_station": pred.target_station,
        "model": pred.model_name,
        "predicted_m": pred.predicted_m,
        "observed_m": pred.observed_m,
        "residual_m": pred.residual_m,
        "extrapolated": pred.extrapolated,
        "model_parameters": pred.model_parameters,
        "reason": pred.reason,
    }


def rmse(values: list[float]) -> float:
    if not values:
        raise ValueError("rmse requires at least one value")
    return math.sqrt(sum(v * v for v in values) / len(values))
