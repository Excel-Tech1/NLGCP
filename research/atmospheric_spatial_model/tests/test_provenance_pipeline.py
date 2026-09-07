"""Tests for provenance, fingerprints, and pipeline admission (synthetic)."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from nlgcp_atmospheric_model.models import (  # noqa: E402
    ModelBlocked,  # noqa: E402
    ModelExperimentDefinition,
    definition_from_dict,
)
from nlgcp_atmospheric_model.pipeline import (  # noqa: E402
    admit_experiment,
    derive_experiment,
    fit_experiment,
    inspect_experiment,
    load_station_coordinates,
    plan_experiment,
    resolve_data_root,
    summarize_data_root,
    validate_experiment,
)
from nlgcp_atmospheric_model.provenance import (  # noqa: E402
    code_fingerprint,
    fingerprint,
    fingerprint_matches,
    provenance_record,
    sha256_file,
    utc_now_iso,
)
from phase6_fixtures import synthetic_nav_text, write_rinex2  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[3]


def make_definition(**overrides: Any) -> ModelExperimentDefinition:
    payload = {
        "experiment_id": "atm-synth",
        "research_question": "synthetic pipeline test",
        "phase5_experiment_id": "net-synth",
        "year": 2024,
        "day_of_year": 26,
        "reference_stations": ["A00NGA", "B00NGA", "C00NGA"],
        "target_station": "T00NGA",
        "coordinate_frame": "IGS20",
        "coordinate_epoch": "2024-01-26T00:00:00Z",
        "minimum_reference_station_count": 3,
        "epoch_stride": 1,
        "min_elevation_deg": 0.0,
        "gf_slip_threshold_m": 0.5,
    }
    payload.update(overrides)
    return definition_from_dict(payload)


def test_definition_validation_catches_problems() -> None:
    bad = make_definition(reference_stations=["A00NGA", "A00NGA"],
                          target_station="A00NGA",
                          minimum_reference_station_count=9)
    problems = bad.validate()
    assert any("duplicates" in p for p in problems)
    assert any("must not be listed" in p for p in problems)
    assert any("below network floor" in p or "declared minimum" in p for p in problems)


def test_fingerprint_determinism_and_invalidation() -> None:
    assert fingerprint({"b": 1, "a": 2}) == fingerprint({"a": 2, "b": 1})
    assert fingerprint({"a": 1}) != fingerprint({"a": 2})


def test_provenance_record_verifies() -> None:
    record = provenance_record(
        inputs={"x": "y"}, algorithm="algo", parameters={},
        code_fingerprint_value="cf", git_commit="abc",
    )
    assert fingerprint_matches(record) is True
    tampered = dict(record, inputs={"x": "z"})
    assert fingerprint_matches(tampered) is False
    assert fingerprint_matches({}) is False


def test_sha256_and_clock_helpers(tmp_path: Path) -> None:
    import hashlib

    path = tmp_path / "f.bin"
    path.write_bytes(b"abc")
    assert sha256_file(path) == hashlib.sha256(b"abc").hexdigest()
    assert utc_now_iso().endswith("+00:00")


def test_code_fingerprint_stable() -> None:
    assert code_fingerprint(REPO_ROOT) == code_fingerprint(REPO_ROOT)


def test_resolve_data_root_fail_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NLGCP_DATA_ROOT", raising=False)
    with pytest.raises(ModelBlocked):
        resolve_data_root(None)
    assert resolve_data_root(tmp_path) == tmp_path


def make_data_root(tmp_path: Path, *, with_nav: bool = False) -> Path:
    """Build a labelled-synthetic data root exercising the real pipeline."""
    root = tmp_path / "data"
    stations = ["A00NGA", "B00NGA", "C00NGA", "T00NGA"]
    admitted = []
    for index, station in enumerate(stations):
        obs = root / "obs" / f"{station}.24O"
        obs.parent.mkdir(parents=True, exist_ok=True)
        write_rinex2(obs, epochs=6, l1_base=1_000_000.0 + index * 100.0)
        admitted.append({
            "station_id": station,
            "qc_status": "ACCEPT",
            "observation_path": str(obs),
            "navigation_path": "external-products/brdc.nav"
            if with_nav
            else "external-products/missing.nav",
            "navigation_sha256": "synthetic" if with_nav else None,
        })
    exp = root / "processed" / "network-rtk" / "experiments" / "net-synth"
    exp.mkdir(parents=True, exist_ok=True)
    (exp / "admission.json").write_text(json.dumps({"admitted": admitted}), encoding="utf-8")
    (exp / "geometry.json").write_text(json.dumps({}), encoding="utf-8")
    coords = {
        "stations": {
            station: {
                "ecef": {"x_m": 6_378_137.0 + i * 50_000.0, "y_m": 100_000.0, "z_m": 200_000.0},
                "reference_frame": "IGS20",
                "coordinate_epoch": "2024-01-26T00:00:00Z",
            }
            for i, station in enumerate(stations)
        }
    }
    single = root / "processed" / "single-base"
    single.mkdir(parents=True, exist_ok=True)
    (single / "derived-coordinates.json").write_text(json.dumps(coords), encoding="utf-8")
    if with_nav:
        nav = root / "external-products" / "brdc.nav"
        nav.parent.mkdir(parents=True, exist_ok=True)
        nav.write_text(synthetic_nav_text(), encoding="utf-8")
    return root


def test_load_station_coordinates_dict_ecef(tmp_path: Path) -> None:
    root = make_data_root(tmp_path)
    coords = load_station_coordinates(root)
    assert coords["A00NGA"].frame == "IGS20"
    assert coords["A00NGA"].x_m == pytest.approx(6_378_137.0)


def test_admission_rejects_non_accept(tmp_path: Path) -> None:
    root = make_data_root(tmp_path)
    exp = root / "processed" / "network-rtk" / "experiments" / "net-synth"
    admission = json.loads((exp / "admission.json").read_text(encoding="utf-8"))
    admission["admitted"][0]["qc_status"] = "REJECT"
    (exp / "admission.json").write_text(json.dumps(admission), encoding="utf-8")
    result = admit_experiment(root, make_definition(), REPO_ROOT)
    assert result["status"] == "BLOCKED"
    assert result["problems"]


def test_admission_missing_phase5_blocked(tmp_path: Path) -> None:
    root = tmp_path / "empty"
    root.mkdir()
    with pytest.raises(ModelBlocked):
        admit_experiment(root, make_definition(), REPO_ROOT)


def test_plan_reports_folds(tmp_path: Path) -> None:
    root = make_data_root(tmp_path)
    plan = plan_experiment(root, make_definition(), REPO_ROOT)
    assert plan["status"] == "COMPLETE"
    assert len(plan["loocv_folds"]) == 4
    assert set(plan["models"]) == {"zero", "nearest", "idw", "planar"}


def test_inspect_reports_gps_compatibility(tmp_path: Path) -> None:
    root = make_data_root(tmp_path)
    report = inspect_experiment(root, make_definition(), REPO_ROOT)
    assert report["status"] == "COMPLETE"
    assert report["gps_l1_l2_compatible"] is True
    assert report["pos_satellite_fields_available"] is False


def test_full_synthetic_derive_fit_validate_without_nav(tmp_path: Path) -> None:
    root = make_data_root(tmp_path, with_nav=False)
    definition = make_definition(experiment_id="atm-synth-nonnav")
    derived = derive_experiment(root, definition, REPO_ROOT)
    # Ionosphere derivable from RINEX; troposphere BLOCKED without nav.
    assert derived["status"] == "PARTIAL"
    assert derived["troposphere"]["status"] == "BLOCKED"
    assert derived["spatial_record_count"] > 0
    # Deterministic reuse: second call must not recompute.
    again = derive_experiment(root, definition, REPO_ROOT)
    assert again.get("reused") is True
    fitted = fit_experiment(root, definition, REPO_ROOT)
    assert fitted["status"] == "COMPLETE"
    assert fitted["fitted_count"] > 0
    validated = validate_experiment(root, definition, REPO_ROOT)
    assert validated["status"] == "COMPLETE"
    assert validated["loocv"]["best_model"] in {"zero", "nearest", "idw", "planar"}
    assert "pilot" in validated["decorrelation"]["note"]


def test_full_synthetic_with_nav_troposphere(tmp_path: Path) -> None:
    root = make_data_root(tmp_path, with_nav=True)
    definition = make_definition(experiment_id="atm-synth-nav", min_elevation_deg=0.0)
    derived = derive_experiment(root, definition, REPO_ROOT)
    assert derived["troposphere"]["status"] in ("COMPLETE", "BLOCKED")
    # Synthetic nav covers only G01 at one Toe; either outcome is honest.
    assert "nav_hash" in derived["troposphere"] or derived["troposphere"]["reasons"]


def test_fit_blocked_without_derive(tmp_path: Path) -> None:
    root = make_data_root(tmp_path)
    result = fit_experiment(root, make_definition(experiment_id="atm-never-derived"), REPO_ROOT)
    assert result["status"] == "BLOCKED"
    assert "position RMSE" in result["reason"] or "proxies" in result["reason"]


def test_dry_run_marks_planned(tmp_path: Path) -> None:
    root = make_data_root(tmp_path)
    definition = make_definition(experiment_id="atm-dry")
    assert derive_experiment(root, definition, REPO_ROOT, dry_run=True)["status"] == "PLANNED"
    assert fit_experiment(root, definition, REPO_ROOT, dry_run=True)["status"] == "PLANNED"
    assert validate_experiment(root, definition, REPO_ROOT, dry_run=True)["status"] == "PLANNED"


def test_summarize_lists_experiments(tmp_path: Path) -> None:
    root = make_data_root(tmp_path)
    definition = make_definition(experiment_id="atm-sum")
    derive_experiment(root, definition, REPO_ROOT)
    summary = summarize_data_root(root)
    assert [e["experiment_id"] for e in summary["experiments"]] == ["atm-sum"]


def test_fingerprint_invalidated_by_parameter_change(tmp_path: Path) -> None:
    root = make_data_root(tmp_path)
    first = make_definition(experiment_id="atm-inv", epoch_stride=1)
    derive_experiment(root, first, REPO_ROOT)
    changed = make_definition(experiment_id="atm-inv", epoch_stride=2)
    second = derive_experiment(root, changed, REPO_ROOT)
    assert second.get("reused", False) is False
    assert second["derive_key"] != derive_experiment(root, first, REPO_ROOT)["derive_key"]


def make_spread_data_root(tmp_path: Path) -> Path:
    """Synthetic root with non-collinear station geometry (planar fittable)."""
    root = tmp_path / "spread"
    stations = ["A00NGA", "B00NGA", "C00NGA", "T00NGA"]
    offsets = {
        "A00NGA": (0.0, 0.0, 0.0),
        "B00NGA": (50_000.0, 20_000.0, 15_000.0),
        "C00NGA": (10_000.0, 60_000.0, -12_000.0),
        "T00NGA": (40_000.0, 40_000.0, 8_000.0),
    }
    admitted = []
    for index, station in enumerate(stations):
        obs = root / "obs" / f"{station}.24O"
        obs.parent.mkdir(parents=True, exist_ok=True)
        write_rinex2(obs, epochs=6, l1_base=1_000_000.0 + index * 100.0)
        admitted.append({
            "station_id": station,
            "qc_status": "ACCEPT",
            "observation_path": str(obs),
            "navigation_path": "external-products/missing.nav",
            "navigation_sha256": None,
        })
    exp = root / "processed" / "network-rtk" / "experiments" / "net-synth"
    exp.mkdir(parents=True, exist_ok=True)
    (exp / "admission.json").write_text(json.dumps({"admitted": admitted}), encoding="utf-8")
    (exp / "geometry.json").write_text(json.dumps({}), encoding="utf-8")
    coords: dict[str, Any] = {"stations": {}}
    for station in stations:
        dx, dy, dz = offsets[station]
        coords["stations"][station] = {
            "ecef": {"x_m": 6_378_137.0 + dx, "y_m": dy, "z_m": dz},
            "reference_frame": "IGS20",
            "coordinate_epoch": "2024-01-26T00:00:00Z",
        }
    single = root / "processed" / "single-base"
    single.mkdir(parents=True, exist_ok=True)
    (single / "derived-coordinates.json").write_text(json.dumps(coords), encoding="utf-8")
    return root


def test_datum_zero_records_anchor_loocv(tmp_path: Path) -> None:
    import csv as _csv
    import math

    root = make_spread_data_root(tmp_path)
    definition = make_definition(experiment_id="atm-spread")
    derived = derive_experiment(root, definition, REPO_ROOT)
    assert derived["status"] == "PARTIAL"  # no nav: troposphere BLOCKED

    records_path = (
        root / "processed" / "atmospheric-model" / "experiments"
        / "atm-spread" / "residuals" / "spatial-records.csv"
    )
    groups: dict[tuple[str, str], dict[str, float]] = {}
    with records_path.open(encoding="utf-8") as handle:
        for row in _csv.DictReader(handle):
            if row.get("combined_residual_m"):
                groups.setdefault((row["epoch"], row["satellite"]), {})[
                    row["reference_station"]
                ] = float(row["combined_residual_m"])
    assert groups
    # Datum self-difference records are identically zero and present.
    for key, values in groups.items():
        assert values.get("A00NGA") == 0.0, key

    fitted = fit_experiment(root, definition, REPO_ROOT)
    assert fitted["status"] == "COMPLETE"
    models_path = (
        root / "processed" / "atmospheric-model" / "experiments"
        / "atm-spread" / "models" / "target-predictions.csv"
    )
    coord_lookup = {
        "A00NGA": (6_378_137.0, 0.0, 0.0),
        "B00NGA": (6_428_137.0, 20_000.0, 15_000.0),
        "C00NGA": (6_388_137.0, 60_000.0, -12_000.0),
        "T00NGA": (6_418_137.0, 40_000.0, 8_000.0),
    }
    checked = 0
    with models_path.open(encoding="utf-8") as handle:
        for row in _csv.DictReader(handle):
            if row["model"] != "nearest" or row["predicted_m"] in (None, ""):
                continue
            observed_values = groups[(row["epoch"], row["satellite"])]
            target_xyz = coord_lookup["T00NGA"]
            nearest_ref = min(
                ("A00NGA", "B00NGA", "C00NGA"),
                key=lambda r: math.dist(coord_lookup[r], target_xyz),
            )
            # No leakage: nearest predicts the nearest *reference* value,
            # never the target station's own observed value.
            assert float(row["predicted_m"]) == pytest.approx(
                observed_values[nearest_ref]
            )
            checked += 1
    assert checked > 0

    validated = validate_experiment(root, definition, REPO_ROOT)
    assert validated["status"] == "COMPLETE"
    # Every rotation is evaluable, including the datum-target fold.
    assert len(validated["loocv"]["folds"]) == 4
    for fold in validated["loocv"]["folds"]:
        assert fold["admissible"] is True
        assert fold["evaluated"] > 0, fold
    assert validated["loocv"]["models"]["planar"]["count"] > 0
    assert validated["loocv"]["best_model"] in {"zero", "nearest", "idw", "planar"}
