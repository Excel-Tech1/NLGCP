"""Tests for measurement combinations and ionospheric proxies (synthetic)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from nlgcp_atmospheric_model.combinations import (  # noqa: E402
    arc_detrend,
    compute_gf_series,
    gf_iono_to_tecu,
    gf_phase_m,
    gf_to_l1_iono_m,
    single_difference,
)
from nlgcp_atmospheric_model.ionosphere import (  # noqa: E402
    pair_sd_proxies,
)
from nlgcp_atmospheric_model.observations import read_rinex2_observations  # noqa: E402
from phase6_fixtures import write_rinex2  # noqa: E402


def test_gf_reference_values() -> None:
    # Wavelengths from IS-GPS-200 frequencies and exact light speed.
    assert gf_phase_m(1.0, 0.0) == pytest.approx(0.1902936728, rel=1e-9)
    assert gf_phase_m(0.0, 1.0) == pytest.approx(-0.2442102134, rel=1e-9)
    assert gf_phase_m(1e6, 1e6) == pytest.approx(-53916.540626, rel=1e-9)


def test_gf_to_l1_factor() -> None:
    assert gf_to_l1_iono_m(1.0) == pytest.approx(1.5457277802, rel=1e-9)
    # 1 TECU produces ~0.162 m of L1 delay (first-order, documented).
    assert gf_iono_to_tecu(0.16237) == pytest.approx(1.0, rel=1e-3)


def test_gf_series_arc_segmentation_on_gap(tmp_path: Path) -> None:
    path = write_rinex2(tmp_path / "G.24O", epochs=5, gap_at=2)
    dataset = read_rinex2_observations(path, "G")
    series = compute_gf_series(dataset, "G01")["G01"]
    arcs = sorted({arc for _, _, arc in series})
    assert arcs == [0, 1]


def test_gf_series_new_arc_on_lli(tmp_path: Path) -> None:
    path = write_rinex2(tmp_path / "L.24O", epochs=4, lli_at=2)
    dataset = read_rinex2_observations(path, "L")
    series = compute_gf_series(dataset, "G01")["G01"]
    # LLI 0 -> 1 at epoch 2 opens a new arc; the return to 0 at epoch 3 is
    # likewise a flag change, so it opens another arc.
    assert [arc for _, _, arc in series] == [0, 0, 1, 2]


def test_gf_series_constant_nonzero_lli_keeps_arc(tmp_path: Path) -> None:
    # A static flag (e.g. the PHRI L2 LLI=4 converter annotation) carries
    # no per-epoch slip information and must not shred the series.
    path = write_rinex2(tmp_path / "LS.24O", epochs=4)
    dataset = read_rinex2_observations(path, "LS")
    for sats in dataset.data.values():
        for obs in sats.values():
            obs.lli["L1"] = 0
            obs.lli["L2"] = 4
    series = compute_gf_series(dataset, "G01")["G01"]
    assert {arc for _, _, arc in series} == {0}


def test_gf_series_gap_opens_new_arc(tmp_path: Path) -> None:
    path = write_rinex2(tmp_path / "LG.24O", epochs=5, gap_at=2)
    dataset = read_rinex2_observations(path, "LG")
    series = compute_gf_series(dataset, "G01")["G01"]
    # Missing epoch ends the arc; the return starts a new one (never rejoins).
    assert [arc for _, _, arc in series] == [0, 0, 1, 1]


def test_gf_series_stride_aware_step(tmp_path: Path) -> None:
    # 30 s data decimated by stride 6 has 180 s effective spacing: the
    # header-interval gap test would shred it, the effective step keeps
    # the smooth series in one arc.
    path = write_rinex2(tmp_path / "LD.24O", epochs=13)
    dataset = read_rinex2_observations(path, "LD", stride=6)
    assert len(dataset.epochs) == 3
    split = compute_gf_series(dataset, "G01")["G01"]
    assert [arc for _, _, arc in split] == [0, 1, 2]
    kept = compute_gf_series(dataset, "G01", step_s=180.0)["G01"]
    assert {arc for _, _, arc in kept} == {0}


def test_gf_series_new_arc_on_jump(tmp_path: Path) -> None:
    path = write_rinex2(tmp_path / "J.24O", epochs=3)
    dataset = read_rinex2_observations(path, "J")
    # Inject a 2 m-class jump by editing the last epoch L1 value.
    last = dataset.epochs[-1]
    current_l1 = dataset.data[last]["G01"].values["L1"]
    assert current_l1 is not None
    dataset.data[last]["G01"].values["L1"] = current_l1 + 20.0
    series = compute_gf_series(dataset, "G01", slip_threshold_m=0.5)["G01"]
    assert [arc for _, _, arc in series] == [0, 0, 1]


def test_non_gps_has_no_gf_series(tmp_path: Path) -> None:
    path = write_rinex2(tmp_path / "R.24O", epochs=2, sats=["R07"])
    dataset = read_rinex2_observations(path, "R")
    assert compute_gf_series(dataset, "R07")["R07"] == []


def test_arc_detrend_removes_median() -> None:
    series = [("a", 10.0, 0), ("b", 12.0, 0), ("c", 5.0, 1)]
    detrended = arc_detrend(series)
    assert [d for _, _, _, d in detrended] == pytest.approx([-1.0, 1.0, 0.0])


def test_single_difference_common_epochs_only() -> None:
    a = [("e1", 1.0, 0), ("e2", 2.0, 0)]
    b = [("e2", 0.5, 0), ("e3", 9.0, 0)]
    result = single_difference(a, b)
    assert len(result) == 1
    assert result[0][0] == "e2"
    assert result[0][1] == pytest.approx(1.5)


def test_pair_sd_proxies_units_and_codes(tmp_path: Path) -> None:
    a = read_rinex2_observations(write_rinex2(tmp_path / "PA.24O", epochs=3), "PA")
    b = read_rinex2_observations(write_rinex2(tmp_path / "PB.24O", epochs=3), "PB")
    samples = pair_sd_proxies(a, b, "G01")
    assert len(samples) == 3
    assert samples[0].input_obs_codes == ("L1", "L2")
    assert samples[0].kind == "GF_SD_ARC_DETRENDED"
    assert "m (slant L1 variation)" in samples[0].unit


def test_gradient_proxy_scales_with_baseline() -> None:
    from nlgcp_atmospheric_model.ionosphere import IonosphericSample
    from nlgcp_atmospheric_model.ionosphere import spatial_gradient_proxy as grad

    sample = IonosphericSample(
        epoch_iso="e",
        satellite_id="G01",
        constellation="G",
        reference_pair=("A", "B"),
        baseline_distance_m=None,
        value_m=2.0,
        value_tecu=1.0,
        kind="GF_SD_ARC_DETRENDED",
    )

    out = grad([sample], 1_000_000.0)
    assert out[0]["gradient_m_per_km"] == pytest.approx(0.002)
    with pytest.raises(ValueError):
        grad([sample], 0.0)
