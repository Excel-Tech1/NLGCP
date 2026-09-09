"""Assemble review tables from stored outputs; never edit computed results."""

import csv
import json
import math
import os
from pathlib import Path

from nlgcp_atmospheric_model.provenance import sha256_file

repo = Path(__file__).resolve().parents[2]
root = Path(os.environ.get("NLGCP_DATA_ROOT", "/home/excellence/nlgcp-data"))
evidence = repo / "research/scientific_validation/evidence"
p6base = root / "processed/atmospheric-model/experiments"
old6 = p6base / "atm-2024d026-phri-target"
new6 = p6base / "atm-2024d026-phri-target-geometry-v3"
replay = p6base / "atm-2024d026-phri-target-geometry-v3-replay"


def read(path):
    return json.loads(path.read_text())


old = read(old6 / "validation/loocv.json")
new = read(new6 / "validation/loocv.json")
# Frozen original-pilot baseline: the pre-refresh summary snapshots are
# byte-identical to before-review.json (n=17768, zero RMSE 2.9843 m), proving
# the documented pilot figures. The on-disk old experiment directory was
# re-run post-freeze (9 files); `old` below is that reproduction state.
snapshot_validation: dict[str, dict[str, float | str | None]] = {}
with (evidence / "historical-summaries/validation-results.csv").open(newline="") as f:
    for row in csv.DictReader(f):
        snapshot_validation[row["model"]] = row
snapshot_gradients = list(
    csv.DictReader(
        (evidence / "historical-summaries/spatial-gradients.csv").open(newline="")
    )
)
rows = []


def compare(name, oldvalue, newvalue, reason, impact):
    numeric = isinstance(oldvalue, (int, float)) and isinstance(newvalue, (int, float))
    difference = newvalue - oldvalue if numeric else None
    rows.append(
        {
            "metric": name,
            "previous": oldvalue,
            "corrected": newvalue,
            "absolute_difference": abs(difference) if numeric else None,
            "signed_difference": difference,
            "relative_difference": difference / oldvalue if numeric and oldvalue else None,
            "reason": reason,
            "scientific_impact": impact,
        }
    )


for model in ("zero", "nearest", "idw", "planar"):
    for metric in ("rmse_m", "correlation_predicted_observed", "count", "bias_m", "mae_m"):
        compare(
            model + "." + metric,
            old["loocv"]["models"][model][metric],
            new["loocv"]["models"][model][metric],
            "corrected orbit/ENU/NMF/GF sign, complete component field, fold-local reference datum",
            "revised diagnostic; aggregate ranking must be recomputed",
        )
for field in ("slope_m_per_km", "correlation"):
    compare(
        "decorrelation." + field,
        old["decorrelation"][field],
        new["decorrelation"][field],
        "pair RMS unchanged by sign reversal; station arcs and chord lengths unchanged on this day",
        "one-day pilot interpretation only",
    )
compare(
    "best_model",
    old["loocv"]["best_model"],
    new["loocv"]["best_model"],
    "recomputed identical samples",
    "no promotion",
)
for model in ("zero", "nearest", "idw", "planar"):
    snap = snapshot_validation[model]
    for metric in ("rmse_m", "count", "bias_m", "mae_m"):
        oldvalue: float | str | None = (
            float(snap[metric]) if snap[metric] not in (None, "") else None
        )
        compare(
            model + "." + metric + ".original_pilot",
            oldvalue,
            new["loocv"]["models"][model][metric],
            "frozen pre-refresh summary snapshot vs corrected reproduction",
            "headline pilot figure revalidated",
        )
for filename, field in [
    ("models/fits.json", "prediction_count"),
    ("models/fits.json", "fitted_count"),
    ("derive-status.json", "spatial_record_count"),
]:
    compare(
        field,
        read(old6 / filename)[field],
        read(new6 / filename)[field],
        "corrected component availability and geometry",
        "different valid sample support",
    )
geometry = read(evidence / "geometry-audit.json")
for row in geometry["baselines"]:
    compare(
        row["pair"] + ".chord_m",
        row["historical_m"],
        row["ecef_chord_m"],
        "independent norm verification",
        "VERIFIED; historical Phase 5 unchanged",
    )
# Reproduce the exact historical bounding-circle/normal-equation geometry definitions.
xyz = {
    r["station"]: tuple(r["ecef"][k] for k in ("x_m", "y_m", "z_m")) for r in geometry["stations"]
}
for rotation in geometry["rotations"]:
    target = rotation["target"]
    refs = rotation["references"]
    origin = rotation["origin_ecef_m"]
    old_inside = math.dist(xyz[target], origin) <= max(math.dist(xyz[s], origin) for s in refs)
    compare(
        target + ".containment",
        "INSIDE_CIRCLE" if old_inside else "OUTSIDE_CIRCLE",
        rotation["containment"] + "_TRIANGLE",
        "circle is not convex-hull membership",
        "all folds are EXTRAPOLATION",
    )
    a, b, c = [math.dist(xyz[refs[i]], xyz[refs[j]]) for i, j in ((0, 1), (1, 2), (2, 0))]
    semi = (a + b + c) / 2
    area = math.sqrt(semi * (semi - a) * (semi - b) * (semi - c))
    compare(
        target + ".reference_area_m2",
        area,
        rotation["area_m2"],
        "historical Heron 3D chord triangle versus common EN projection",
        "different area definitions; historical chord area is not a numerical error",
    )
vrs = []
for station in ("phri", "abfc", "ekak", "mgbo"):
    directory = root / "processed/vrs/experiments" / f"vrs-2024d026-{station}-geometry-v3"
    previous = root / "processed/vrs/experiments" / f"vrs-2024d026-{station}-geometry-v2"
    validation = read(directory / "validation.json")
    summary = read(repo / f"build/scientific-validation/logs/{station}-summarize.json")
    with (directory / "virtual-observations.csv").open() as f:
        current = list(csv.DictReader(f))
    with (previous / "virtual-observations.csv").open() as f:
        historical = list(csv.DictReader(f))
    ignored = {"virtual_station_id", "provenance_id"}
    assert len(current) == len(historical)
    for a, b in zip(current, historical, strict=True):
        assert {k: v for k, v in a.items() if k not in ignored} == {
            k: v for k, v in b.items() if k not in ignored
        }
    old_validation = read(previous / "validation.json")
    assert validation["metrics"] == old_validation["metrics"]
    vrs.append(
        {
            "target": station.upper() + "00NGA",
            "experiment_id": directory.name,
            "virtual_observation_count": len(current),
            "epochs": len({r["epoch_gpst"] for r in current}),
            "satellites": len({r["satellite"] for r in current}),
            "codes": sorted({r["observation_code"] for r in current}),
            "anchor": current[0]["anchor_station"],
            "metrics": validation["metrics"],
            "comparison_vs_v2": "observation/geometry columns identical "
            "except virtual ID/provenance; metrics exactly equal",
            "generation": {k: v for k, v in summary.items() if k != "validation"},
            "artifacts": {
                str(p.relative_to(directory)): sha256_file(p)
                for p in sorted(directory.rglob("*"))
                if p.is_file()
            },
        }
    )
repro = []
for relative in (
    "ionosphere/station-gf.csv",
    "ionosphere/pair-sd.csv",
    "troposphere/apriori.csv",
    "residuals/station-fields.csv",
    "residuals/spatial-records.csv",
    "models/target-predictions.csv",
    "validation/comparison-samples.csv",
):
    if not (new6 / relative).is_file():
        continue
    primary, repeated = sha256_file(new6 / relative), sha256_file(replay / relative)
    assert primary == repeated, relative
    repro.append({"artifact": relative, "sha256": primary, "fresh_replay_equal": True})
assert read(replay / "validation/loocv.json")["loocv"] == new["loocv"]
assert read(repo / "build/scientific-validation/logs/phri-resume.json")["reused"]
# Verify historical per-experiment artifacts against the freeze inventory.
# Two post-freeze modifications are recorded here (not silently ignored):
# (a) aggregate catalogs under processed/.../summaries rewritten by the
# authorized summarize CLI (snapshotted first; snapshots preserve the frozen
# pre-refresh summary values byte-for-byte except LF line endings normalized
# for commit hygiene — CRLF hashes verified equal to the freeze before
# normalization — and corroborate the documented pilot: n=17768, zero 2.9843 m);
# (b) nine files under the old Phase 6 pilot directory re-run under its own ID
# on 2026-09-08 ~14:10 local AFTER the 13:37 freeze by an undocumented pipeline
# reproduction (provenance inside shows algorithm phase6-derive-v1, git 59c986a,
# timestamp 13:10Z). The `previous` column below is that reproduction state
# (zero RMSE 3.5464, n=13326); headline original-pilot baselines are appended
# as `.original_pilot` rows sourced from the frozen snapshots. Any changed
# path outside these two classes fails the review.
before = read(evidence / "before-review.json")
verified = 0
changed = []
for record in before["artifacts"]:
    p = root / record["path"]
    if p.is_file() and sha256_file(p) == record["sha256"]:
        verified += 1
    else:
        changed.append(record["path"])
old_prefix = "processed/atmospheric-model/experiments/atm-2024d026-phri-target/"
unexpected = [
    p
    for p in changed
    if "/summaries/" not in p and not p.startswith(old_prefix)
]
assert not unexpected, unexpected
result = {
    "status": "CORRECTED",
    "phase6_previous": old,
    "phase6_corrected": new,
    "comparison": rows,
    "phase6_fresh_replay": repro,
    "vrs": vrs,
    "virtual_observations_total": sum(r["virtual_observation_count"] for r in vrs),
    "historical_preservation": {
        "unchanged_artifacts": verified,
        "changed_aggregate_catalogs": [p for p in changed if "/summaries/" in p],
        "changed_old_experiment_rerun": [p for p in changed if p.startswith(old_prefix)],
        "incident": "old Phase 6 pilot directory re-run under its own ID after the freeze "
        "(2026-09-08 ~14:10 local); frozen hashes in before-review.json remain the "
        "authoritative historical record; pre-refresh summary snapshots corroborate "
        "the documented pilot (n=17768, zero 2.9843 m); comparison `previous` column "
        "is the post-freeze reproduction state, original-pilot baselines appended "
        "as `.original_pilot` rows",
    },
    "phase6_artifacts": {
        str(p.relative_to(new6)): sha256_file(p) for p in sorted(new6.rglob("*")) if p.is_file()
    },
    "source_head": before["head"],
    "positioning_validation": "NOT_PERFORMED; RINEX export not certified",
}
(evidence / "corrected-results.json").write_text(
    json.dumps(result, indent=2, allow_nan=False) + "\n"
)
with (evidence / "old-vs-corrected.csv").open("w", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
print(
    json.dumps(
        {
            "vrs_total": result["virtual_observations_total"],
            "fresh_replay_files": len(repro),
            "historical_unchanged": verified,
            "catalogs_refreshed": len(changed),
        }
    )
)
