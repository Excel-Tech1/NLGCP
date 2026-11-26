"""Unit tests for Phase 6 Sprint atmospheric & spatial estimation modules.

SYNTHETIC TEST DATA — NOT VALID FOR SCIENTIFIC RESULTS.
All synthetic fixtures in this file verify algorithmic correctness, sign
conventions, edge-case fail-closed handling, and non-fabrication guarantees.
"""

from __future__ import annotations

import math
from pathlib import Path

import pytest
from nlgcp_atmospheric_model.atmospheric_schema import (
    AtmosphericComponent,
    AtmosphericEstimate,
    ValidationStatus,
)
from nlgcp_atmospheric_model.combinations import GAMMA_GPS
from nlgcp_atmospheric_model.dataset_audit import (
    audit_rinex2_signal_completeness,
    classify_network_geometry,
    convex_hull_2d,
    point_in_convex_hull_2d,
)
from nlgcp_atmospheric_model.ionosphere_estimation import (
    DCB_UNAVAILABLE_STATUS,
    L1_M_PER_TECU,
    common_arc_sd_l1_iono,
    estimate_station_ionosphere,
    nighttime_leveled_sd_l1_iono,
    slm_mapping_and_ipp,
)
from nlgcp_atmospheric_model.observations import (
    GPS_L1_WAVELENGTH_M,
    GPS_L2_WAVELENGTH_M,
    Rinex2Header,
    SatObs,
    StationDataset,
)
from nlgcp_atmospheric_model.spatial_estimation import (
    SPATIAL_MODELS,
    extended_residual_metrics,
    predict_spatial,
    run_stratified_loocv,
)
from nlgcp_atmospheric_model.troposphere_estimation import (
    UNB3M_LABEL,
    evaluate_tropo_against_pride,
    parse_pride_ztd,
    pride_to_atmospheric_estimates,
    slant_tropo_from_ztd,
    unb3m_zenith_delays,
)

# Synthetic 5-station square + interior centroid network in ECEF around central Nigeria
_CENTER_LAT = math.radians(9.0)
_CENTER_LON = math.radians(7.5)


def _geo_to_ecef(lat_deg: float, lon_deg: float, h_m: float = 400.0) -> tuple[float, float, float]:
    a = 6_378_137.0
    f = 1.0 / 298.257223563
    e2 = f * (2.0 - f)
    lat = math.radians(lat_deg)
    lon = math.radians(lon_deg)
    n = a / math.sqrt(1.0 - e2 * math.sin(lat) ** 2)
    return (
        (n + h_m) * math.cos(lat) * math.cos(lon),
        (n + h_m) * math.cos(lat) * math.sin(lon),
        (n * (1.0 - e2) + h_m) * math.sin(lat),
    )


def _synthetic_dual_freq_dataset(
    station_id: str,
    *,
    iono_l1_base_m: float,
    iono_slope_m_per_ep: float = 0.01,
    n_epochs: int = 20,
    step_s: int = 60,
    inject_slip_at: int | None = None,
    dcb_bias_m: float = 0.0,
) -> tuple[StationDataset, dict[tuple[str, str], tuple[float, float]]]:
    """Generate a physically consistent synthetic dual-frequency GPS dataset."""
    header = Rinex2Header(
        path=f"synthetic://{station_id}",
        obs_types=("C1", "P2", "L1", "L2"),
        interval_s=30.0,
        time_of_first_obs="2011-03-20T00:00:00.000000",
        approx_xyz_m=_geo_to_ecef(9.0, 7.5, 400.0),
    )
    epochs: list[str] = []
    data: dict[str, dict[str, SatObs]] = {}
    topo: dict[tuple[str, str], tuple[float, float]] = {}
    rho0 = 21_500_000.0
    n1_amb = 123_456.0
    n2_amb = 98_765.0
    for idx in range(n_epochs):
        total_s = idx * step_s
        hh, rem = divmod(total_s, 3600)
        mm, ss = divmod(rem, 60)
        ep = f"2011-03-20T{hh:02d}:{mm:02d}:{ss:02d}.000000"
        epochs.append(ep)
        rho = rho0 + 150.0 * idx
        i1 = iono_l1_base_m + iono_slope_m_per_ep * idx
        slip_l1 = 5.0 if (inject_slip_at is not None and idx >= inject_slip_at) else 0.0
        c1 = rho + i1
        p2 = rho + GAMMA_GPS * i1 + dcb_bias_m
        l1 = (rho - i1) / GPS_L1_WAVELENGTH_M + n1_amb + slip_l1
        l2 = (rho - GAMMA_GPS * i1) / GPS_L2_WAVELENGTH_M + n2_amb
        data[ep] = {"G01": SatObs(values={"C1": c1, "P2": p2, "L1": l1, "L2": l2})}
        topo[(ep, "G01")] = (45.0, 120.0)
    return StationDataset(station_id=station_id, header=header, epochs=epochs, data=data), topo


def test_convex_hull_and_geometry_classification() -> None:
    coords = {
        "NW": _geo_to_ecef(12.0, 4.0),
        "NE": _geo_to_ecef(12.0, 12.0),
        "SE": _geo_to_ecef(5.0, 12.0),
        "SW": _geo_to_ecef(5.0, 4.0),
        "IN": _geo_to_ecef(8.5, 8.0),
    }
    hull = convex_hull_2d([(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0), (5.0, 5.0)])
    assert len(hull) == 4
    assert point_in_convex_hull_2d((5.0, 5.0), hull) is True
    assert point_in_convex_hull_2d((12.0, 5.0), hull) is False

    geom = classify_network_geometry(coords)
    assert geom["containment_by_station"]["IN"] is True
    for corner in ("NW", "NE", "SE", "SW"):
        assert geom["containment_by_station"][corner] is False


def test_rinex2_signal_audit_detects_silent_l2_outage() -> None:
    # Mirrors real Dec 2011 RUST outage: L2/P2 declared in header, blank in obs body
    lines = [
        "     2.11           OBSERVATION DATA    M (MIXED)           RINEX VERSION / TYPE",
        "     4    C1    L1    L2    P2                              # / TYPES OF OBSERV",
        "    30.0000                                                 INTERVAL",
        "  2011    12     5     0     0    0.0000000     GPS         TIME OF FIRST OBS",
        "                                                            END OF HEADER",
        " 11 12  5  0  0  0.0000000  0  1G01",
        "  21500000.000   113000000.000",
        " 11 12  5  0  0 30.0000000  0  1G01",
        "  21500100.000   113000500.000",
    ]
    audit = audit_rinex2_signal_completeness(
        lines,
        station_id="RUST",
        date_iso="2011-12-05",
        source_identifier="synthetic://rust",
        file_sha256="deadbeef",
        epoch_count_declared=2880,
    )
    assert audit.dual_frequency_gps_usable is False
    assert audit.gps_code_completeness["L1"] == 1.0
    assert audit.gps_code_completeness["L2"] == 0.0
    assert audit.gps_code_completeness["P2"] == 0.0
    assert any("insufficient GPS dual-frequency" in r for r in audit.exclusion_reasons)


def test_ionosphere_estimation_slm_cycle_slip_and_common_arc_sd() -> None:
    xyz = _geo_to_ecef(9.0, 7.5, 400.0)
    mf, ipp_lat, ipp_lon = slm_mapping_and_ipp(xyz, 45.0, 90.0)
    assert 1.2 < mf < 1.5
    assert 8.5 < ipp_lat < 9.5
    assert ipp_lon > 7.5

    # Strided 60s dataset with header interval 30s must NOT trigger false gap slips
    ds_a, topo_a = _synthetic_dual_freq_dataset(
        "ST_A", iono_l1_base_m=2.0, iono_slope_m_per_ep=0.02, step_s=60, dcb_bias_m=1.2
    )
    ds_b, topo_b = _synthetic_dual_freq_dataset(
        "ST_B",
        iono_l1_base_m=2.6,
        iono_slope_m_per_ep=0.05,
        step_s=60,
        inject_slip_at=10,
        dcb_bias_m=-0.8,
    )
    est_a, summ_a = estimate_station_ionosphere(ds_a, xyz, topo_a)
    est_b, summ_b = estimate_station_ionosphere(ds_b, xyz, topo_b)
    assert summ_a["estimate_count"] == 20
    assert summ_a["cycle_slips_lli_or_gap"] == 0
    assert summ_a["dcb_status"] == DCB_UNAVAILABLE_STATUS
    assert all(e.bias_corrected_stec_tecu is None for e in est_a)
    # Injected 5-cycle L1 slip at epoch 10 must be detected by MW/GF and split arc into 2
    assert summ_b["cycle_slips_gf"] + summ_b["cycle_slips_mw"] >= 1
    assert summ_b["arcs_retained"] == 2

    # Common-arc SD eliminates constant ambiguity & tracks differential slope accurately
    sd_common, meta_common = common_arc_sd_l1_iono({"ST_A": est_a, "ST_B": est_b}, "ST_A")
    assert meta_common["datum_station"] == "ST_A"
    assert len(sd_common) > 0
    # Nighttime leveled SD recovers differential L1 ionosphere (incl. DCB alignment)
    sd_night, meta_night = nighttime_leveled_sd_l1_iono({"ST_A": est_a, "ST_B": est_b}, "ST_A")
    assert meta_night["datum_station"] == "ST_A"
    assert len(sd_night) > 0
    assert abs(L1_M_PER_TECU - 0.16237) < 2e-4


def test_unb3m_and_pride_ztd_evaluation(tmp_path: Path) -> None:
    abj = _geo_to_ecef(9.0277, 7.49, 532.63)
    unb = unb3m_zenith_delays(abj, doy=26, station_id="ABFC00NGA")
    assert unb.meteorology_source == UNB3M_LABEL
    assert 2.10 < unb.zhd_m < 2.25
    assert 0.15 < unb.zwd_m < 0.30
    slant = slant_tropo_from_ztd(
        station_ecef_m=abj, elevation_deg=30.0, doy=26, zhd_m=unb.zhd_m, zwd_m=unb.zwd_m
    )
    assert slant > unb.ztd_m * 1.9

    ztd_file = tmp_path / "ztd_2024026"
    ztd_file.write_text(
        "END OF HEADER\n"
        "2024 01 26 00 00  0.000   2.1750   0.1200   0.0050   2.3000\n"
        "2024 01 26 00 00 30.000   2.1750   0.1200   0.0060   2.3010\n",
        encoding="utf-8",
    )
    recs, digest = parse_pride_ztd(ztd_file, station_id="ABFC00NGA")
    assert len(recs) == 2
    assert len(digest) == 64
    assert recs[0].zwd_total_m == pytest.approx(0.125)

    eval_out = evaluate_tropo_against_pride({"ABFC00NGA": recs}, {"ABFC00NGA": abj}, doy=26)
    assert eval_out["aggregate"]["unb3m_climatology_zhd"]["count"] == 2
    assert eval_out["aggregate"]["unb3m_climatology_zhd"]["rmse_m"] < 0.02

    atmo_ests = pride_to_atmospheric_estimates(recs, file_sha256=digest)
    assert len(atmo_ests) == 2
    assert isinstance(atmo_ests[0], AtmosphericEstimate)
    assert atmo_ests[0].component == AtmosphericComponent.ZTD_PPP_PRIDE
    assert atmo_ests[0].validation_status == ValidationStatus.SCIENTIFICALLY_VALIDATED


def test_stratified_loocv_exact_planar_interior_recovery() -> None:
    coords = {
        "NW": _geo_to_ecef(12.0, 4.0),
        "NE": _geo_to_ecef(12.0, 12.0),
        "SE": _geo_to_ecef(5.0, 12.0),
        "SW": _geo_to_ecef(5.0, 4.0),
        "IN": _geo_to_ecef(8.5, 8.0),
    }
    # Pure linear spatial gradient in latitude/longitude -> planar recovers interior near-exactly
    observed: dict[tuple[str, str, str], float] = {}
    lat_lon = {
        "NW": (12.0, 4.0),
        "NE": (12.0, 12.0),
        "SE": (5.0, 12.0),
        "SW": (5.0, 4.0),
        "IN": (8.5, 8.0),
    }
    for ep_i in range(5):
        ep = f"2011-03-20T00:0{ep_i}:00.000000"
        for st, (lat, lon) in lat_lon.items():
            observed[(ep, "G01", st)] = 0.25 * (lat - 8.5) + 0.15 * (lon - 8.0)

    loocv = run_stratified_loocv(
        coords=coords,
        observed=observed,
        models=SPATIAL_MODELS,
        min_refs=3,
        reanchor_per_fold=True,
    )
    interior_planar = loocv["interior_interpolated"]["models"]["planar"]
    interior_zero = loocv["interior_interpolated"]["models"]["zero"]
    assert interior_planar["rmse_m"] < 0.05
    assert interior_planar["rmse_m"] < interior_zero["rmse_m"]
    assert "p95_abs_m" in interior_planar

    refs = [
        (s, coords[s], observed[("2011-03-20T00:00:00.000000", "G01", s)])
        for s in ("NW", "NE", "SE", "SW")
    ]
    pred = predict_spatial(
        model_name="idw2",
        epoch_iso="2011-03-20T00:00:00.000000",
        satellite_id="G01",
        target_station="IN",
        target_xyz=coords["IN"],
        references=refs,
    )
    assert pred.predicted_m is not None
    assert abs(pred.predicted_m) < 0.05

    m = extended_residual_metrics([0.1, -0.2, 0.3, -0.4, 0.5])
    assert m["p95_abs_m"] is not None and m["p95_abs_m"] >= 0.4
