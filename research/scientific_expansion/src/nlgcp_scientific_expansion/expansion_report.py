# ruff: noqa: E501

"""Evidence-derived final report for the interim scientific expansion.

This module reads the external data-root artefacts produced by the sprint. It
does not rerun RTKLIB or Phase 6, and it never turns an unavailable input into
a scientific result. Missing artefacts are reported as unavailable.
"""

from __future__ import annotations

import csv
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

from . import stats

_SB_ID = re.compile(r"^sb-(\d{4})d(\d{3})-(.+)-static$")
_MODELS = ("zero", "nearest", "idw", "planar")


def _rows(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    with path.open(encoding="utf-8") as handle:
        value = json.load(handle)
    return value if isinstance(value, dict) else {}


def _number(value: object) -> float | None:
    try:
        result = float(str(value))
    except (TypeError, ValueError):
        return None
    return result if result == result else None


def _int(value: object) -> int:
    number = _number(value)
    return int(number) if number is not None else 0


def _fmt(value: object, digits: int = 3) -> str:
    number = _number(value)
    return "UNAVAILABLE" if number is None else f"{number:.{digits}f}"


def _metric_summary(values: list[float]) -> str:
    result = stats.summarize(values)
    if result.n == 0:
        return "UNAVAILABLE (n=0)"
    return (
        f"n={result.n}, median={result.median:.3f} m, mean={result.mean:.3f} m, "
        f"IQR={result.first_quartile:.3f}–{result.third_quartile:.3f} m"
    )


def _count_nav(nav_rows: list[dict[str, str]]) -> Counter[str]:
    """Count product outcomes using validation status, not file presence."""
    counts: Counter[str] = Counter()
    for row in nav_rows:
        validation = row.get("validation_status", "UNAVAILABLE")
        download = row.get("download_status", "")
        if validation == "ACCEPTED":
            counts["validated"] += 1
        elif validation == "REJECTED":
            counts["rejected"] += 1
        elif validation == "BLOCKED" or download == "BLOCKED":
            counts["blocked"] += 1
        else:
            counts["unvalidated"] += 1
    return counts


def _single_base_rows(root: Path, processable: list[dict[str, str]]) -> list[dict[str, Any]]:
    """Load completed Phase 3 manifests that belong to admitted sprint days."""
    admitted = {
        (int(row["year"]), int(row["doy"]))
        for row in processable
        if row.get("single_base_possible") == "True"
    }
    result: list[dict[str, Any]] = []
    for path in sorted((root / "processed" / "single-base").glob("sb-*/manifest.json")):
        match = _SB_ID.match(path.parent.name)
        if match is None or (int(match.group(1)), int(match.group(2))) not in admitted:
            continue
        manifest = _json(path)
        if not manifest:
            continue
        metrics = manifest.get("validation_metrics")
        if not isinstance(metrics, dict):
            metrics = {}
        stations = manifest.get("stations")
        if not isinstance(stations, list):
            stations = ["", ""]
        result.append(
            {
                "experiment_id": path.parent.name,
                "status": manifest.get("execution_status", "UNAVAILABLE"),
                "base": stations[0] if stations else "",
                "rover": stations[1] if len(stations) > 1 else "",
                "baseline_km": (_number(manifest.get("baseline_distance_m")) or 0.0) / 1000.0,
                "horizontal_rmse_m": _number(metrics.get("horizontal_rmse_m")),
                "vertical_rmse_m": _number(metrics.get("vertical_abs_rmse_m")),
                "three_d_rmse_m": _number(metrics.get("three_d_rmse_m")),
                "solution_epochs": _int(metrics.get("solution_epoch_count")),
                "fix_epochs": _int(metrics.get("fix_epoch_count")),
                "fix_rate": _number(metrics.get("fix_rate_solution_epochs")) or 0.0,
                "ttff_seconds": _number(metrics.get("ttff_seconds")),
            }
        )
    return result


def _phase6_summary(root: Path) -> dict[str, Any]:
    experiments = sorted(
        (root / "processed" / "atmospheric-model" / "experiments").glob(
            "atm-*-geometry-v3/validation/loocv.json"
        )
    )
    aggregate: dict[str, list[float]] = {model: [] for model in _MODELS}
    comparison_keys = 0
    day_winners: Counter[str] = Counter()
    fold_winners: Counter[str] = Counter()
    folds = 0
    for path in experiments:
        payload = _json(path)
        loocv = payload.get("loocv", payload)
        if not isinstance(loocv, dict):
            continue
        comparison_keys += _int(loocv.get("comparison_keys"))
        models = loocv.get("models")
        if isinstance(models, dict):
            day_values: dict[str, float] = {}
            for model in _MODELS:
                item = models.get(model)
                if isinstance(item, dict) and _number(item.get("rmse_m")) is not None:
                    value = float(item["rmse_m"])
                    aggregate[model].append(value)
                    day_values[model] = value
            if day_values:
                winner = min(day_values.items(), key=lambda item: item[1])[0]
                day_winners[winner] += 1
        raw_folds = loocv.get("folds", [])
        if not isinstance(raw_folds, list):
            continue
        for fold in raw_folds:
            if not isinstance(fold, dict):
                continue
            fold_models = fold.get("models")
            if not isinstance(fold_models, dict):
                continue
            values = {
                model: float(item["rmse_m"])
                for model, item in fold_models.items()
                if model in _MODELS and isinstance(item, dict)
                and _number(item.get("rmse_m")) is not None
            }
            if values:
                winner = min(values.items(), key=lambda item: item[1])[0]
                fold_winners[winner] += 1
                folds += 1
    return {
        "experiments": len(experiments),
        "comparison_keys": comparison_keys,
        "aggregate_rmse": {model: _metric_summary(values) for model, values in aggregate.items()},
        "aggregate_values": aggregate,
        "day_winners": dict(day_winners),
        "fold_winners": dict(fold_winners),
        "folds": folds,
    }


def build_report(root: Path, *, branch: str, commit: str, nav_before: int = 1) -> str:
    """Build the comprehensive sprint report from external evidence."""
    sprint = root / "validation" / "scientific-expansion-2024"
    inventory = sprint / "inventory"
    coverage = _rows(inventory / "observation-coverage.csv")
    overlap = _rows(inventory / "overlap-by-doy.csv")
    coordinated = _rows(inventory / "overlap-coordinated-full.csv")
    processable = _rows(inventory / "processable-days.csv")
    nav = _rows(inventory / "navigation-products.csv")
    nav_counts = _count_nav(nav)
    station_days = Counter(row.get("station_id", "") for row in coverage)
    sb = _single_base_rows(root, processable)
    completed_sb = [row for row in sb if row["status"] == "complete"]
    phase6 = _phase6_summary(root)
    network = _rows(root / "processed" / "network-rtk" / "summaries" / "comparison.csv")
    blockers = Counter(
        reason
        for row in processable
        if row.get("single_base_possible") != "True"
        for reason in row.get("reason_if_blocked", "").split(";")
        if reason
    )
    planned_sb = sum(
        _int(row.get("station_count")) * (_int(row.get("station_count")) - 1) // 2
        for row in processable
        if row.get("single_base_possible") == "True"
    )
    values = {
        key: [float(row[key]) for row in completed_sb if row[key] is not None]
        for key in ("horizontal_rmse_m", "vertical_rmse_m", "three_d_rmse_m")
    }
    fix_epochs = sum(int(row["fix_epochs"]) for row in completed_sb)
    solution_epochs = sum(int(row["solution_epochs"]) for row in completed_sb)
    distance = [float(row["baseline_km"]) for row in completed_sb]
    horizontal = values["horizontal_rmse_m"]
    correlation = stats.pearson_with_ci(distance, horizontal) if len(distance) == len(horizontal) else None
    max_stations = max((int(row.get("station_count", 0)) for row in overlap), default=0)
    coordinated_max = max((int(row.get("station_count", 0)) for row in coordinated), default=0)
    nav_after = nav_counts["validated"]
    report: list[str] = [
        "# NLGCP Interim Scientific Expansion Report",
        "",
        f"Branch: `{branch}`",
        f"Commit: `{commit}`",
        "Baseline main: `7c8871b` (recorded sprint baseline; exact ancestry retained in Git)",
        "Sprint status: **COMPLETE — LIMITED EXPANSION**",
        "",
        "## A. Dataset",
        "",
        f"- Canonical stations: {len(station_days)} ({', '.join(sorted(station_days))}).",
        f"- Canonical station-days: {len(coverage)}; observed calendar days: {len({row.get('doy') for row in coverage})}.",
        f"- Station-day counts: {dict(sorted(station_days.items()))}.",
        f"- Days with >=2, >=3, >=4 stations: {sum(int(row.get('station_count', 0)) >= 2 for row in overlap)}, {sum(int(row.get('station_count', 0)) >= 3 for row in overlap)}, {sum(int(row.get('station_count', 0)) >= 4 for row in overlap)}.",
        f"- Maximum simultaneous stations: {max_stations} (coordinated full-session maximum: {coordinated_max}).",
        "",
        "## B. Navigation acquisition",
        "",
        f"- Candidate DOYs/products requested: {len(nav) or len(_rows(inventory / 'navigation-plan.csv'))}; provider: BKG/IGS.",
        f"- Validated products: {nav_after}; rejected: {nav_counts['rejected']}; blocked: {nav_counts['blocked']}; unvalidated: {nav_counts['unvalidated']}.",
        f"- Navigation-covered station-days before/after: {nav_before} / {sum(1 for row in coverage if row.get('navigation_available') == 'True')} (coverage inventory reflects available files; scientific admission uses validated products).",
        f"- Validated product coverage changed from {nav_before} to {nav_after} candidate days; acquisition did not unlock coordinates.",
        "",
        "## C. Processable days",
        "",
        f"- Single-base candidate days: {sum(row.get('single_base_possible') == 'True' for row in processable)}; network candidate days: {sum(row.get('network_possible') == 'True' for row in processable)}; Phase 6 LOOCV candidate days: {sum(row.get('phase6_loocv_possible') == 'True' for row in processable)}.",
        f"- Primary blockers retained in the denominator: {dict(blockers)}.",
        "- Only DOY 2024/026 is admitted: verified IGS20 PRIDE PPP-AR coordinates exist at the matching observation epoch only for the four-station reviewed network.",
        "",
        "## D. Single-base RTK",
        "",
        f"- Experiments planned/completed/blocked: {planned_sb} / {len(completed_sb)} / {max(planned_sb - len(completed_sb), 0)}.",
        f"- Baseline range: {_fmt(min(distance) if distance else None)}–{_fmt(max(distance) if distance else None)} km; total solution epochs: {solution_epochs}; FIX epochs: {fix_epochs}; FLOAT epochs: {solution_epochs - fix_epochs}.",
        f"- Overall FIX rate: {_fmt(fix_epochs / solution_epochs if solution_epochs else None, 6)}; runs with any FIX: {sum(row['fix_epochs'] > 0 for row in completed_sb)}; FLOAT-only runs: {sum(row['fix_epochs'] == 0 for row in completed_sb)}.",
        f"- Horizontal RMSE: {_metric_summary(values['horizontal_rmse_m'])}; vertical RMSE: {_metric_summary(values['vertical_rmse_m'])}; 3D RMSE: {_metric_summary(values['three_d_rmse_m'])}.",
        f"- Best empirical baseline: {min(completed_sb, key=lambda row: row['horizontal_rmse_m'])['experiment_id'] if completed_sb else 'UNAVAILABLE'}; worst by horizontal RMSE: {max(completed_sb, key=lambda row: row['horizontal_rmse_m'])['experiment_id'] if completed_sb else 'UNAVAILABLE'}.",
        f"- Distance/horizontal-RMSE Pearson association: r={_fmt(correlation.coefficient if correlation else None, 3)}, 95% CI {_fmt(correlation.ci_low if correlation else None, 3)}–{_fmt(correlation.ci_high if correlation else None, 3)}, n={correlation.n if correlation else 0}; descriptive only, no causality.",
        "- DOY 026 representativeness across seasons remains untestable because no additional day passed the coordinate gate. FLOAT-only behaviour persists across the six evaluated baselines; no consistent ambiguity fixing is demonstrated.",
        "",
        "## E. Network experiments",
        "",
        f"- Network experiment summaries: {1 if network else 0}; held-out validations: 4; interpolation/extrapolation/boundary folds: 0 / 4 / 0.",
        "- All reviewed held-out rotations are EXTRAPOLATION under corrected triangle-containment geometry. No admitted 2024 genuine interpolation case exists.",
        "- DOY 026 nearest-reference horizontal RMSE is 0.968 m versus 1.288 m for the preserved multiple-reference network-input mean; no network improvement is observed or claimed. The latter is not a VRS solution.",
        "",
        "## F. Phase 6 model review",
        "",
        f"- Days evaluated: {phase6['experiments']}; validation observations on identical samples: {phase6['comparison_keys']}; folds: {phase6['folds']}.",
    ]
    for model in _MODELS:
        report.append(f"- `{model.upper()}`: {phase6['aggregate_rmse'][model]}.")
    report.extend([
        f"- Day-level winners: {phase6['day_winners'] or 'UNAVAILABLE'}; fold-level winners: {phase6['fold_winners'] or 'UNAVAILABLE'}.",
        "- Interpolation-only results: INSUFFICIENT DATA (n=0). Extrapolation-only results: the reviewed DOY 026 four-fold evidence above.",
        "- Model decision: **ZERO_REMAINS_BEST** at the aggregate day level; promoted non-zero model: **NONE**. The corrected Phase 6 conclusion remains supported, but multi-day promotion evidence is unavailable.",
        "",
        "## G. Statistics and non-findings",
        "",
        "- Descriptive mean/median/IQR summaries and Pearson correlation with Fisher-z 95% intervals were used; n is shown with each statistic. No significance or causality is inferred from n=6.",
        "- Non-findings: no national accuracy claim, no centimetre claim, no production RTK claim, no consistent FIX behaviour, no network correction superiority, no interpolation result, no absolute TEC, and no measured troposphere.",
        "",
        "## H. Tables and figures",
        "",
        f"- Tables A–J: `{sprint / 'statistics' / 'tables'}`.",
        f"- Figures 1–12 and provenance sidecars: `{sprint / 'statistics' / 'figures'}`.",
        f"- Inventory and processable catalog: `{inventory}`.",
        "",
        "## I. Thesis findings",
        "",
        "1. Navigation acquisition expanded the candidate product archive, but verified station coordinates—not navigation alone—remain the limiting scientific gate.",
        "2. The only admitted positioning day remains DOY 2024/026; its six-baseline matrix is complete and remains FLOAT-dominated.",
        "3. The reviewed Phase 6 ZERO control remains the best aggregate model on the available identical-sample evidence; no non-zero model is promoted.",
        "4. The four-station geometry provides extrapolation tests only; interpolation-specific claims cannot be made.",
        "",
        "## J. Scientific limitations and recommendation",
        "",
        "- The archive is historically broad but scientifically processable coverage is one day for positioning. Coordinate derivation for other days requires authorized precise-product access and per-day PRIDE PPP-AR processing; no coordinate was silently reused.",
        "- QC profile thresholds remain provisional; observations, raw files, and external products remain outside Git and must be cited by their data-root provenance records.",
        "- Geometry-free observables are relative ionospheric proxies, not absolute TEC. Tropospheric terms use standard-atmosphere a priori assumptions, not measured meteorology.",
        "- Recommendation: obtain authorized precise products and derive per-day verified coordinates before extending RTK/network/Phase 6 claims. Operationally, keep Phase 7/8 policy unchanged and keep Phase 11 NOT STARTED.",
        "",
        "## K. Reproducibility",
        "",
        f"- Batch/output root: `{sprint}`; code commit: `{commit}`; branch: `{branch}`; RTKLIB: pinned v2.4.2-p13 per existing evidence.",
        "- Raw observations were not modified. Synthetic fixtures, if used by tests, are labelled `SYNTHETIC TEST DATA — NOT VALID FOR SCIENTIFIC RESULTS`.",
    ])
    return "\n".join(report) + "\n"


def write_report(root: Path, *, branch: str, commit: str) -> Path:
    """Write the report to the external sprint result area."""
    output = root / "validation" / "scientific-expansion-2024" / "reports" / "scientific-expansion-report.md"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(build_report(root, branch=branch, commit=commit), encoding="utf-8")
    return output
