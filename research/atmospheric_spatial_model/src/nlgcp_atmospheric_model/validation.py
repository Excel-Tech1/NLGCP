"""Leave-one-out cross-validation over reference/target rotations (Phase 6).

Conceptually: use stations A/B/C to predict the correction/error term at D,
compare against the observed evidence at D, rotate the held-out station where
geometry permits. Minimum reference counts are enforced per model; folds that
cannot meet them are recorded as inadmissible, never silently skipped.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from . import MIN_REFS_FOR_LOOCV_FOLD
from .interpolation import METHOD_NAMES, interpolate
from .metrics import correlation, prediction_metrics

PredictFn = Callable[
    [str, tuple[float, float, float], list[tuple[str, tuple[float, float, float], float | None]]],
    float | None,
]


def _reference_value(
    observed: dict[tuple[str, str, str], float],
    epoch: str,
    sat: str,
    station: str,
    datum_defaults: dict[str, float] | None,
) -> float | None:
    value = observed.get((epoch, sat, station))
    if value is None and datum_defaults is not None:
        return datum_defaults.get(station)
    return value


def loocv_folds(
    stations: list[str], *, min_refs: int = MIN_REFS_FOR_LOOCV_FOLD
) -> list[dict[str, Any]]:
    """Enumerate admissible held-out rotations for a station set."""
    folds: list[dict[str, Any]] = []
    for held in stations:
        refs = [s for s in stations if s != held]
        folds.append(
            {
                "target": held,
                "references": refs,
                "admissible": len(refs) >= min_refs,
                "reason": None
                if len(refs) >= min_refs
                else (f"only {len(refs)} references remain < minimum {min_refs}"),
            }
        )
    return folds


def run_loocv(
    *,
    epochs: list[str],
    satellites: list[str],
    coords: dict[str, tuple[float, float, float]],
    observed: dict[tuple[str, str, str], float],
    models: tuple[str, ...] = METHOD_NAMES,
    min_refs: int = MIN_REFS_FOR_LOOCV_FOLD,
    datum_defaults: dict[str, float] | None = None,
    reference_datum: bool = False,
) -> dict[str, Any]:
    """Run leave-one-out validation over all admissible folds.

    ``observed`` maps ``(epoch, satellite, station)`` to the measured error
    term at that station. Every model is compared against the zero and
    nearest controls on the identical set of comparison samples (only
    ``(epoch, satellite, target)`` keys predicted by every model enter the
    ranking); a model is never declared better unless its residuals beat
    the controls on the same evidence.

    ``datum_defaults`` optionally maps a station to its definitional field
    value (e.g. the datum-anchored zero). Such values may fill *reference*
    slots only: a held-out target still requires a real measurement in
    ``observed``, so a definitional zero can never be a validation target.
    Without this, datum-anchored designs would leave every fold containing
    the datum with one fewer usable reference.
    """
    if reference_datum and datum_defaults:
        raise ValueError("fold-local datums require independent station fields")
    stations = sorted(coords)
    folds = loocv_folds(stations, min_refs=min_refs)
    # Per-model predictions keyed by (epoch, satellite, target): the final
    # metric comparison uses only keys predicted by EVERY model, so the
    # ranking is on identical samples (counts are then equal by construction;
    # keys no model could predict are reported as skipped).
    per_model_pred: dict[str, dict[tuple[str, str, str], tuple[float, float]]] = {
        m: {} for m in models
    }
    fold_rows: list[dict[str, Any]] = []
    skipped = 0
    comparison_observed: dict[tuple[str, str, str], float] = {}
    for fold in folds:
        if not fold["admissible"]:
            fold_rows.append({**fold, "evaluated": 0, "skipped": 0})
            continue
        target = str(fold["target"])
        refs = [str(r) for r in fold["references"]]
        datum = refs[0] if reference_datum else None
        evaluated = 0
        fold_skipped = 0
        for epoch in epochs:
            for sat in satellites:
                key = (epoch, sat, target)
                if key not in observed:
                    skipped += 1
                    fold_skipped += 1
                    continue
                offset = observed.get((epoch, sat, datum)) if datum else 0.0
                if offset is None:
                    skipped += 1
                    fold_skipped += 1
                    continue
                comparison_observed[key] = observed[key] - offset
                ref_values = [
                    (r, coords[r], _reference_value(observed, epoch, sat, r, datum_defaults))
                    for r in refs
                ]
                ref_values = [
                    (r, xyz, value - offset if value is not None else None)
                    for r, xyz, value in ref_values
                ]
                for model in models:
                    pred = interpolate(
                        model_name=model,
                        epoch_iso=epoch,
                        satellite_id=sat,
                        target_station=target,
                        target_xyz=coords[target],
                        references=ref_values,
                        observed_m=comparison_observed[key],
                    )
                    if pred.predicted_m is None or pred.residual_m is None:
                        continue
                    per_model_pred[model][key] = (pred.predicted_m, pred.residual_m)
                evaluated += 1
        fold_rows.append({**fold, "evaluated": evaluated, "skipped": fold_skipped, "datum": datum})
    common_keys = set.intersection(*(set(per_model_pred[m]) for m in models)) if models else set()
    summary: dict[str, Any] = {}
    for model in models:
        residuals = [per_model_pred[model][key][1] for key in sorted(common_keys)]
        predicted = [per_model_pred[model][key][0] for key in sorted(common_keys)]
        observed_list = [comparison_observed[key] for key in sorted(common_keys)]
        summary[model] = {
            **prediction_metrics(residuals),
            "correlation_predicted_observed": correlation(predicted, observed_list),
            "evaluable_keys": len(per_model_pred[model]),
        }
    for fold in fold_rows:
        keys = sorted(k for k in common_keys if k[2] == fold["target"])
        fold["comparison_keys"] = len(keys)
        fold["models"] = {
            m: prediction_metrics([per_model_pred[m][k][1] for k in keys]) for m in models
        }
    samples = [
        {
            "epoch": k[0],
            "satellite": k[1],
            "target": k[2],
            "model": m,
            "observed_m": comparison_observed[k],
            "predicted_m": per_model_pred[m][k][0],
            "residual_m": per_model_pred[m][k][1],
        }
        for k in sorted(common_keys)
        for m in models
    ]
    ordered = sorted(
        ((m, (summary[m]["rmse_m"] is not None, summary[m]["rmse_m"])) for m in models),
        key=lambda item: (
            item[1][0] is None,
            item[1][1] if item[1][1] is not None else float("inf"),
        ),
    )
    best = ordered[0][0] if ordered and summary[ordered[0][0]]["rmse_m"] is not None else None
    return {
        "folds": fold_rows,
        "comparison_samples": samples,
        "datum_policy": "lexical first reference per fold" if reference_datum else "input datum",
        "models": summary,
        "best_model": best,
        "comparison_keys": len(common_keys),
        "best_model_note": (
            "lowest RMSE on identical comparison samples across all models; "
            "report when a simpler control wins"
            if best is not None
            else "not established: no model produced predictions"
        ),
        "missing_observations_skipped": skipped,
    }
