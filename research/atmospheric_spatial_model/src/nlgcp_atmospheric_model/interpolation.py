"""Modular spatial interpolation framework (Phase 6).

Candidate estimators for the network error field at a target location:

* ``zero`` — zero-correction control (predicts 0.0);
* ``nearest`` — nearest-reference transfer control;
* ``idw`` — inverse-distance weighting (configurable power);
* ``planar`` — low-order spatial surface (least-squares plane in local ENU).

Complexity reflects the sparse DOY 026 geometry (three references): no
kriging or higher-order surfaces are implemented, because the sample count
cannot support them. Every prediction records whether the target lies
outside the reference triangle (``extrapolated``; bounding circle fallback
when the reference count is not three) and refuses to fit when fewer than
the method minimum references carry values, when the triangle is
degenerate, or when the plane is singular/collinear.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any

import numpy as np

from .models import InterpolationPrediction
from .spatial import baseline_length_m, ecef_to_local_enu

METHOD_MINIMUMS = {"zero": 0, "nearest": 1, "idw": 2, "planar": 3}
METHOD_NAMES = ("zero", "nearest", "idw", "planar")


def _extrapolated(
    target_xyz: tuple[float, float, float],
    ref_xyzs: list[tuple[float, float, float]],
    centroid: tuple[float, float, float],
) -> bool:
    """Classify whether the target requires extrapolation.

    With exactly three references the test is a robust point-in-triangle
    check in the shared local ENU frame (barycentric, with a 1e-9
    tolerance); degenerate (near-zero-area) triangles always count as
    extrapolation. With any other reference count it falls back to the
    bounding-circle rule (target farther from the centroid than the
    farthest reference). A previous revision used only the bounding
    circle, misclassifying outside-triangle targets inside the circle.
    """
    if not ref_xyzs:
        return True
    if len(ref_xyzs) == 3:
        tri = [enu_2d(xyz, centroid) for xyz in ref_xyzs]
        tgt = enu_2d(target_xyz, centroid)
        _, _, _, inside = barycentric_coordinates(tri[0], tri[1], tri[2], tgt)
        return not inside
    radius = max(baseline_length_m(c, centroid) for c in ref_xyzs)
    return baseline_length_m(target_xyz, centroid) > radius


def enu_2d(
    xyz: tuple[float, float, float], origin: tuple[float, float, float]
) -> tuple[float, float]:
    """East/North projection of an ECEF point in the shared ENU frame (m)."""
    east, north, _ = ecef_to_local_enu(xyz, origin)
    return east, north


def reference_triangle_area_m2(
    ref_xyzs: list[tuple[float, float, float]],
    origin: tuple[float, float, float],
) -> float:
    """Planar reference-triangle area (m^2) in the shared ENU frame.

    Must be called with exactly three references sharing ``origin``; areas
    are never computed directly from latitude/longitude degrees.
    """
    if len(ref_xyzs) != 3:
        raise ValueError("triangle area requires exactly three references")
    tri = [enu_2d(xyz, origin) for xyz in ref_xyzs]
    return (
        abs(
            tri[0][0] * (tri[1][1] - tri[2][1])
            + tri[1][0] * (tri[2][1] - tri[0][1])
            + tri[2][0] * (tri[0][1] - tri[1][1])
        )
        / 2.0
    )


def barycentric_coordinates(
    a: tuple[float, float],
    b: tuple[float, float],
    c: tuple[float, float],
    p: tuple[float, float],
    *,
    tol: float = 1e-9,
) -> tuple[float, float, float, bool]:
    """Barycentric weights of ``p`` in triangle ``abc`` plus containment."""
    denom = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1])
    scale = max(math.dist(a, b), math.dist(b, c), math.dist(c, a))
    if not math.isfinite(denom) or abs(denom) <= 32 * math.ulp(1.0) * scale**2:
        return 0.0, 0.0, 0.0, False
    w1 = ((b[1] - c[1]) * (p[0] - c[0]) + (c[0] - b[0]) * (p[1] - c[1])) / denom
    w2 = ((c[1] - a[1]) * (p[0] - c[0]) + (a[0] - c[0]) * (p[1] - c[1])) / denom
    w3 = 1.0 - w1 - w2
    inside = (w1 >= -tol) and (w2 >= -tol) and (w3 >= -tol)
    return w1, w2, w3, inside


def _centroid(points: list[tuple[float, float, float]]) -> tuple[float, float, float]:
    n = len(points)
    return (
        sum(p[0] for p in points) / n,
        sum(p[1] for p in points) / n,
        sum(p[2] for p in points) / n,
    )


def plane_diagnostics(points: list[tuple[float, float, float]]) -> dict[str, Any]:
    """Scaled SVD: rank/condition are numerical diagnostics, not admission criteria."""
    data = np.asarray(points, dtype=float)
    if len(points) < 3 or not np.isfinite(data).all():
        return {"rank": 0, "condition_number": None, "coefficients": None}
    center = data[:, :2].mean(axis=0)
    scale = float(np.max(np.abs(data[:, :2] - center)))
    if scale == 0:
        return {"rank": 1, "condition_number": None, "coefficients": None}
    design = np.column_stack(((data[:, :2] - center) / scale, np.ones(len(points))))
    coeff, _, rank, singular = np.linalg.lstsq(design, data[:, 2], rcond=None)
    condition = float(singular[0] / singular[-1]) if singular[-1] > 0 else None
    result: dict[str, Any] = {
        "rank": int(rank),
        "condition_number": condition,
        "coordinate_scale_m": scale,
        "coefficients": None,
    }
    # Reject when conditioning loses at least half of double precision digits.
    # This is a numerical safeguard (sqrt(machine epsilon)), not a field threshold.
    if rank < 3 or condition is None or condition * math.sqrt(np.finfo(float).eps) >= 1:
        return result
    slopes = coeff[:2] / scale
    result["coefficients"] = (float(slopes[0]), float(slopes[1]), float(coeff[2] - slopes @ center))
    return result


def _plane_fit(points: list[tuple[float, float, float]]) -> tuple[float, float, float] | None:
    result = plane_diagnostics(points)["coefficients"]
    if result is None:
        return None
    return float(result[0]), float(result[1]), float(result[2])


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
    if model_name == "idw" and not (math.isfinite(power) and power > 0.0):
        raise ValueError(f"IDW power must be positive, got {power}")
    if not all(math.isfinite(x) for xyz in [target_xyz, *(r[1] for r in references)] for x in xyz):
        raise ValueError("non-finite spatial coordinate")
    if any(v is not None and not math.isfinite(v) for _, _, v in references):
        raise ValueError("non-finite reference value")
    usable = sorted((sid, xyz, value) for sid, xyz, value in references if value is not None)
    excluded = len(references) - len(usable)
    centroid = _centroid([xyz for _, xyz, _ in usable]) if usable else target_xyz
    extrapolated = _extrapolated(target_xyz, [xyz for _, xyz, _ in usable], centroid)
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
            nearest_distance = min(baseline_length_m(x, target_xyz) for _, x, _ in usable)
            weights.append((nearest_distance / dist) ** power)
        if predicted is None and weights:
            assert all(v is not None for _, _, v in usable)
            total = sum(weights)
            predicted = (
                sum(w * float(v) for w, (_, _, v) in zip(weights, usable, strict=True)) / total
            )
    elif model_name == "planar":
        origin = centroid
        local = [
            (*ecef_to_local_enu(xyz, origin), float(v)) for _, xyz, v in usable if v is not None
        ]
        diagnostics = plane_diagnostics([(p[0], p[1], p[3]) for p in local])
        fit = diagnostics.pop("coefficients")
        params.update(diagnostics)
        params["origin_ecef_m"] = origin
        if fit is None:
            reason = ((reason + "; ") if reason else "") + (
                "singular geometry: reference stations collinear/degenerate, plane undefined"
            )
        else:
            a, b, c = fit
            te, tn, _ = ecef_to_local_enu(target_xyz, origin)
            predicted = a * te + b * tn + c
            params.update({"a_m_per_m": a, "b_m_per_m": b, "c_m": c})
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
