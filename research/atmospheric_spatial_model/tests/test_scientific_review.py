"""SYNTHETIC TEST DATA — NOT VALID FOR SCIENTIFIC RESULTS."""

import json
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest
from nlgcp_atmospheric_model.combinations import GAMMA_GPS, gf_phase_m, gf_to_l1_iono_m
from nlgcp_atmospheric_model.interpolation import plane_diagnostics
from nlgcp_atmospheric_model.observations import GPS_L1_WAVELENGTH_M, GPS_L2_WAVELENGTH_M
from nlgcp_atmospheric_model.pipeline import admit_experiment
from nlgcp_atmospheric_model.satellite_geometry import gps_datetime_to_tow, select_ephemeris
from nlgcp_atmospheric_model.validation import run_loocv
from nlgcp_single_base.coordinates import EcefCoordinate, ecef_to_geodetic
from test_geometry_tropo import circular_equatorial_eph
from test_provenance_pipeline import REPO_ROOT, make_data_root, make_definition


def test_carrier_sign_from_observation_equation() -> None:
    rho, iono = 20_000_000.0, 3.0
    l1 = (rho - iono) / GPS_L1_WAVELENGTH_M
    l2 = (rho - GAMMA_GPS * iono) / GPS_L2_WAVELENGTH_M
    assert gf_to_l1_iono_m(gf_phase_m(l1, l2)) == pytest.approx(iono, abs=1e-8)


@pytest.mark.parametrize("z", [6356752.314245179, -6356752.314245179])
def test_geodetic_poles(z: float) -> None:
    point = ecef_to_geodetic(EcefCoordinate(0.0, 0.0, z))
    assert point.latitude_deg == (90.0 if z > 0 else -90.0)
    assert point.height_m == pytest.approx(0.0, abs=1e-8)


@pytest.mark.parametrize(
    "xyz", [(0.0, 0.0, 0.0), (float("nan"), 0.0, 1.0), (float("inf"), 1.0, 1.0)]
)
def test_invalid_ecef_rejected(xyz: tuple[float, float, float]) -> None:
    with pytest.raises(ValueError):
        ecef_to_geodetic(EcefCoordinate(*xyz))


def test_naive_gpst_is_timezone_independent() -> None:
    assert gps_datetime_to_tow(datetime(2024, 1, 26)) == (2298, 432000.0)


def test_stale_week_and_health_fail_closed() -> None:
    eph = circular_equatorial_eph()
    assert select_ephemeris([eph], 2299, 432000.0) is None
    assert select_ephemeris([eph], 2298, 440000.0) is None
    assert select_ephemeris([replace(eph, health=1)], 2298, 432000.0) is None
    assert select_ephemeris([replace(eph, toe_tow_s=604790.0)], 2299, 10.0) is not None


def test_planar_ill_conditioning_is_rejected() -> None:
    result = plane_diagnostics([(0.0, 0.0, 1.0), (1e6, 0.0, 2.0), (2e6, 1e-5, 3.0)])
    assert result["coefficients"] is None
    assert result["condition_number"] > 1e8


def test_each_fold_datum_excludes_target_and_target_perturbation_cannot_change_predictors() -> None:
    coords = {
        "A": (6378137.0, 0.0, 0.0),
        "B": (6378137.0, 1000.0, 0.0),
        "C": (6378137.0, 0.0, 1000.0),
        "D": (6378137.0, 2000.0, 3000.0),
    }
    observed = {("e", "G01", s): float(i + 1) for i, s in enumerate(coords)}

    def run(values: dict[tuple[str, str, str], float]) -> dict[str, Any]:
        return run_loocv(
            epochs=["e"], satellites=["G01"], coords=coords, observed=values, reference_datum=True
        )

    baseline = run(observed)
    assert baseline["comparison_keys"] == 4
    for target in coords:
        altered = dict(observed)
        altered[("e", "G01", target)] += 100
        changed = run(altered)
        old = [r for r in baseline["comparison_samples"] if r["target"] == target]
        new = [r for r in changed["comparison_samples"] if r["target"] == target]
        assert [r["predicted_m"] for r in old] == [r["predicted_m"] for r in new]
        assert all(
            b["residual_m"] - a["residual_m"] == pytest.approx(100)
            for a, b in zip(old, new, strict=True)
        )
        fold = next(f for f in baseline["folds"] if f["target"] == target)
        assert fold["datum"] != target


@pytest.mark.parametrize(
    "field,value",
    [
        ("scientifically_valid", False),
        ("reference_frame", "ITRF2000"),
        ("coordinate_epoch", "unknown"),
        ("pos_file_sha256", "0" * 64),
    ],
)
def test_coordinate_provenance_rejects_inconsistency(
    tmp_path: Path, field: str, value: object
) -> None:
    root = make_data_root(tmp_path)
    path = root / "processed/single-base/derived-coordinates.json"
    data = json.loads(path.read_text())
    data["stations"]["A00NGA"][field] = value
    path.write_text(json.dumps(data))
    assert admit_experiment(root, make_definition(), REPO_ROOT)["status"] == "BLOCKED"


def test_optional_nav_spares_preserve_record(tmp_path: Path) -> None:
    from nlgcp_atmospheric_model.satellite_geometry import parse_rinex3_gps_nav
    from phase6_fixtures import synthetic_nav_text

    path = tmp_path / "synthetic.nav"
    lines = synthetic_nav_text().splitlines()
    lines[-1] = lines[-1][:42]  # transmission time + fit; spare fields absent
    path.write_text("\n".join(lines) + "\n")
    assert len(parse_rinex3_gps_nav(path)["G01"]) == 1


def test_lli_band_changes_are_not_hidden_by_bitwise_or(tmp_path: Path) -> None:
    from nlgcp_atmospheric_model.combinations import compute_gf_series
    from nlgcp_atmospheric_model.observations import read_rinex2_observations
    from phase6_fixtures import write_rinex2

    dataset = read_rinex2_observations(write_rinex2(tmp_path / "s.24o"), "S")
    for i, epoch in enumerate(dataset.epochs):
        obs = dataset.data[epoch]["G01"]
        obs.lli["L1"], obs.lli["L2"] = (4, 0) if i < 2 else (0, 4)
    assert [r[2] for r in compute_gf_series(dataset, "G01")["G01"]] == [0, 0, 1, 1]


def test_derived_output_tampering_is_rejected(tmp_path: Path) -> None:
    from nlgcp_atmospheric_model.models import ModelBlocked
    from nlgcp_atmospheric_model.pipeline import derive_experiment, fit_experiment

    root = make_data_root(tmp_path)
    definition = make_definition()
    derive_experiment(root, definition, REPO_ROOT)
    path = (
        root
        / "processed/atmospheric-model/experiments"
        / definition.experiment_id
        / "residuals/station-fields.csv"
    )
    path.write_text("SYNTHETIC TEST DATA — NOT VALID FOR SCIENTIFIC RESULTS; tampered")
    with pytest.raises(ModelBlocked, match="checksum"):
        fit_experiment(root, definition, REPO_ROOT)
