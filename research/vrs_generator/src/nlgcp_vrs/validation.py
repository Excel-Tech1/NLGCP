"""Held-out diagnostic residuals with explicit clock and ambiguity datums."""

from __future__ import annotations

import csv
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from statistics import fmean
from typing import Any

from nlgcp_atmospheric_model.metrics import prediction_metrics
from nlgcp_atmospheric_model.provenance import fingerprint, sha256_file, utc_now_iso

from .models import Blocked, Definition
from .observations import WAVELENGTHS, Dataset, Measurement, read_observations
from .pipeline import (
    checked_hash,
    experiment_dir,
    plan,
    read_json,
    read_verified_outputs,
    write_csv,
    write_json,
)


def residuals(
    rows: list[dict[str, Any]], target: Dataset, interval: float
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    paired: dict[tuple[str, str], dict[str, tuple[float, int, int, Measurement]]] = defaultdict(
        dict
    )
    totals: dict[str, int] = defaultdict(int)
    matches: dict[str, int] = defaultdict(int)
    for row in rows:
        code, epoch, sat = row["observation_code"], row["epoch_gpst"], row["satellite"]
        totals[code] += 1
        actual = target.data.get(epoch, {}).get(sat, {}).get(code)
        if actual is None:
            continue
        matches[code] += 1
        difference = (float(row["virtual_observation"]) - actual.value) * WAVELENGTHS.get(code, 1.0)
        paired[(code, epoch)][sat] = (
            difference,
            int(row.get("source_lli") or 0),
            int(row.get("epoch_flag") or 0),
            actual,
        )
    output: list[dict[str, Any]] = []
    summaries: dict[str, Any] = {}
    for code in sorted(totals):
        epochs = sorted(e for c, e in paired if c == code)
        values = []
        previous: str | None = None
        for epoch in epochs:
            current = paired[(code, epoch)]
            if code not in WAVELENGTHS:
                # Estimate only the common receiver-clock/code datum per epoch.
                # This is an in-sample nuisance fit, never positioning accuracy.
                if len(current) >= 2:
                    bias = fmean(v[0] for v in current.values())
                    for sat, value in sorted(current.items()):
                        residual = value[0] - bias
                        output.append(
                            {
                                "epoch_gpst": epoch,
                                "previous_epoch_gpst": "",
                                "satellite": sat,
                                "pivot_satellite": "",
                                "code": code,
                                "method": "CODE_SD_EPOCH_MEAN_REMOVED",
                                "residual_m": residual,
                                "removed_clock_code_datum_m": bias,
                            }
                        )
                        values.append(residual)
            elif (
                previous
                and (
                    datetime.fromisoformat(epoch) - datetime.fromisoformat(previous)
                ).total_seconds()
                == interval
            ):
                old = paired[(code, previous)]
                common = []
                for sat in sorted(set(current) & set(old)):
                    a, b = old[sat], current[sat]
                    # No bridging gaps, loss-of-lock, half cycles, power failures
                    # or changing quality annotations at either receiver.
                    if (
                        any(
                            (r[1] & 3) or r[2] or ((r[3].lli or 0) & 3) or r[3].epoch_flag
                            for r in (a, b)
                        )
                        or a[1] != b[1]
                        or a[3].lli != b[3].lli
                    ):
                        continue
                    common.append(sat)
                if len(common) >= 2:
                    pivot = common[0]
                    delta_pivot = current[pivot][0] - old[pivot][0]
                    for sat in common[1:]:
                        residual = current[sat][0] - old[sat][0] - delta_pivot
                        output.append(
                            {
                                "epoch_gpst": epoch,
                                "previous_epoch_gpst": previous,
                                "satellite": sat,
                                "pivot_satellite": pivot,
                                "code": code,
                                "method": "PHASE_TIME_DIFFERENCED_DOUBLE_DIFFERENCE",
                                "residual_m": residual,
                                "removed_clock_code_datum_m": "",
                            }
                        )
                        values.append(residual)
            previous = epoch
        summaries[code] = {
            **prediction_metrics(values),
            "generated_count": totals[code],
            "matched_count": matches[code],
            "match_coverage": matches[code] / totals[code],
            "method": (
                "PHASE_TIME_DIFFERENCED_DOUBLE_DIFFERENCE"
                if code in WAVELENGTHS
                else "CODE_SD_EPOCH_MEAN_REMOVED"
            ),
            "unit": "m",
            "time_difference_interval_s": interval if code in WAVELENGTHS else None,
        }
        # Phase 6's helper includes a provisional 0.05 m field; do not inherit an
        # irrelevant scientific threshold into Phase 7 reporting.
        summaries[code].pop("coverage_within_tolerance", None)
        summaries[code].pop("tolerance_m", None)
    return output, summaries


def validate(
    root: Path, definition: Definition, repo: Path, source: Path, *, dry_run: bool = False
) -> dict[str, Any]:
    planned = plan(root, definition, repo, source)
    out = experiment_dir(root, definition)
    read_verified_outputs(out, planned["fingerprint"])
    p5 = root / "processed/network-rtk/experiments" / definition.source_network_experiment
    station = definition.target_station
    session = next(
        s for s in read_json(p5 / "admission.json")["admitted"] if s["station_id"] == station
    )
    qcpath = (
        root
        / "processed/qc/profiles/network_rtk/sessions"
        / str(definition.year)
        / station
        / f"{definition.day_of_year:03d}"
        / "qc-result.json"
    )
    qc = read_json(qcpath)
    if qc.get("overall_classification") != "ACCEPT" or qc.get("result_fingerprint") != session.get(
        "phase4_result_fingerprint"
    ):
        raise Blocked("held-out validation target lacks current matching QC admission")
    target_path = Path(session["observation_path"])
    target_hash = checked_hash(target_path, session.get("converted_sha256"))
    if target_hash in planned["material"][
        "source_observation_sha256"
    ].values() or target_path.resolve() in {
        Path(p).resolve() for p in planned["observations"].values()
    }:
        raise Blocked("target observation file aliases a synthesis input")
    if dry_run:
        return {
            "status": "PLANNED",
            "target": station,
            "target_sha256": target_hash,
            "target_observation_path": str(target_path),
            "target_qc_path": str(qcpath),
            "outputs": str(out / "validation.json"),
        }
    with (out / "virtual-observations.csv").open() as handle:
        rows: list[dict[str, Any]] = list(csv.DictReader(handle))
    target = read_observations(target_path)
    output, metrics = residuals(rows, target, definition.sampling_interval)
    write_csv(
        out / "validation-residuals.csv",
        output,
        [
            "epoch_gpst",
            "previous_epoch_gpst",
            "satellite",
            "pivot_satellite",
            "code",
            "method",
            "residual_m",
            "removed_clock_code_datum_m",
        ],
    )
    material = {
        "generation_fingerprint": planned["fingerprint"],
        "target_sha256": target_hash,
        "target_observation_path": str(target_path),
        "target_qc_path": str(qcpath),
        "target_qc_sha256": sha256_file(qcpath),
        "virtual_observations_sha256": sha256_file(out / "virtual-observations.csv"),
    }
    if checked_hash(target_path, target_hash) != target_hash:
        raise Blocked("target changed during validation")
    result = {
        "status": "COMPLETE" if output else "BLOCKED",
        "target": station,
        "metrics": metrics,
        "provenance": material,
        "fingerprint": fingerprint(material),
        "execution_timestamp": utc_now_iso(),
        "held_out_observations_used_in_synthesis": False,
        "residuals_sha256": sha256_file(out / "validation-residuals.csv"),
        "positioning_validation": "NOT_PERFORMED; RINEX export deferred",
        "limitations": [
            "diagnostic residuals, not positioning errors",
            "code: one clock/code offset estimated per epoch and code; no absolute clock agreement",
            "phase: only time-differenced double differences, not undifferenced phase RMSE",
            "undetected cycle slips may remain; no integer ambiguity estimation",
            "target coordinate is a PRIDE daily solution, not independently surveyed truth",
            "no spatial correction gain claimed; no model promoted",
        ],
    }
    write_json(out / "validation.json", result)
    return result


def verified_validation(out: Path, generation_fingerprint: str) -> dict[str, Any]:
    """Read a validation result only when both held-out and synthesis inputs match."""
    result = read_json(out / "validation.json")
    material = result["provenance"]
    if material["generation_fingerprint"] != generation_fingerprint or fingerprint(
        material
    ) != result.get("fingerprint"):
        raise Blocked("stale validation fingerprint")
    checked_hash(Path(material["target_observation_path"]), material["target_sha256"])
    checked_hash(Path(material["target_qc_path"]), material["target_qc_sha256"])
    checked_hash(out / "virtual-observations.csv", material["virtual_observations_sha256"])
    checked_hash(out / "validation-residuals.csv", result["residuals_sha256"])
    return result
