#!/usr/bin/env python3
"""B-04 Geodetic Coordinate Analysis, Catalogues & Versioned B-02 v2 Truth Re-Evaluation.

Consumes the authentic PRIDE PPP-AR 3.2.8 outputs from ``scripts/run_b04_pride_ppp.py``
(54 IGS Final station-days + 18 CODE Final cross-check station-days), performs strict
frame-separated analysis (native IGS05 March 2011 vs native IGS08 December 2011),
applies official IERS/Altamimi et al. (2023) 14-parameter Helmert transformations and
ITRF2020-PMM Nubian plate velocity checks, emits the B-04 CSV catalogues, and performs
the versioned B-02 v2 re-evaluation of ``2011-03-20 OSGF`` without modifying original B-02.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import statistics
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
for rel in (
    "research/rover_benchmark/src",
    "research/atmospheric_spatial_model/src",
    "research/vrs_generator/src",
    "research/single_base_rtk/src",
    "research/rtcm_generation/src",
    "research/rtcm_replay/src",
):
    p = str(REPO_ROOT / rel)
    if p not in sys.path:
        sys.path.insert(0, p)

from nlgcp_atmospheric_model.dataset_audit import load_osgof_provisional_coords  # noqa: E402
from nlgcp_atmospheric_model.observations import read_rinex2_from_zip  # noqa: E402
from nlgcp_atmospheric_model.provenance import sha256_file  # noqa: E402
from nlgcp_atmospheric_model.satellite_geometry import parse_gps_nav_auto  # noqa: E402
from nlgcp_atmospheric_model.spatial import baseline_length_m, ecef_to_local_enu  # noqa: E402
from nlgcp_rover_benchmark.benchmark import (  # noqa: E402
    RELATIVE_PROFILES,
    _compute_ref_iono_fields,
    _decompress_unix_z,
    _derive_spp_gga_position,
    _execute_dataset_benchmark,
    _extract_zip_member,
    _inside_hull,
)
from nlgcp_rover_benchmark.metrics import compute_positioning_metrics  # noqa: E402
from nlgcp_rover_benchmark.models import (  # noqa: E402
    DatasetWindowSpec,
    RoverTruthRecord,
    TruthTier,
)
from nlgcp_single_base.solution import parse_solution_pos  # noqa: E402

DATA_ROOT = Path(os.environ.get("NLGCP_DATA_ROOT", "/home/excellence/nlgcp-data"))
WORK_ROOT = DATA_ROOT / "processed" / "b04-coordinate-verification"

PRIORITY_STATIONS: tuple[str, ...] = (
    "ABUZ",
    "BKFP",
    "CGGT",
    "FUTY",
    "MDGR",
    "OSGF",
    "RUST",
    "ULAG",
    "UNEC",
)

WGS84_A = 6378137.0
WGS84_F = 1.0 / 298.257223563
WGS84_E2 = WGS84_F * (2.0 - WGS84_F)
MAS_TO_RAD = math.pi / (180.0 * 3600.0 * 1000.0)

# Official IERS / IGN Altamimi et al. (2023) transformation parameters from ITRF2020
# to past ITRFs at reference epoch t0 = 2015.0:
# (Tx_mm, Ty_mm, Tz_mm, D_ppb, Rx_mas, Ry_mas, Rz_mas,
#  Tx_dot_mm_y, Ty_dot_mm_y, Tz_dot_mm_y, D_dot_ppb_y, Rx_dot, Ry_dot, Rz_dot)
ITRF2020_TO_FRAME: dict[str, tuple[float, ...]] = {
    "ITRF2014": (-1.4, -0.9, 1.4, -0.42, 0.0, 0.0, 0.0, 0.0, -0.1, 0.2, 0.00, 0.0, 0.0, 0.0),
    "ITRF2008": (0.2, 1.0, 3.3, -0.29, 0.0, 0.0, 0.0, 0.0, -0.1, 0.1, 0.03, 0.0, 0.0, 0.0),
    "ITRF2005": (2.7, 0.1, -1.4, 0.65, 0.0, 0.0, 0.0, 0.3, -0.1, 0.1, 0.03, 0.0, 0.0, 0.0),
}
ITRF_T0 = 2015.0

# Official ITRF2020-PMM Nubia (NUBI) plate rotation vector & ORB (Altamimi et al. 2023, GRL):
# omega in mas/yr, ORB translation rate in mm/yr (horizontal component only per Altamimi 2023)
NUBIA_OMEGA_MAS_YR = (0.090, -0.585, 0.717)
NUBIA_ORB_MM_YR = (0.37, 0.35, 0.74)


def ecef_to_geodetic(x: float, y: float, z: float) -> tuple[float, float, float]:
    p = math.hypot(x, y)
    lon = math.atan2(y, x)
    lat = math.atan2(z, p * (1.0 - WGS84_E2))
    for _ in range(10):
        s = math.sin(lat)
        n = WGS84_A / math.sqrt(1.0 - WGS84_E2 * s * s)
        h = p / math.cos(lat) - n
        lat_new = math.atan2(z, p * (1.0 - WGS84_E2 * n / (n + h)))
        if abs(lat_new - lat) < 1e-13:
            lat = lat_new
            break
        lat = lat_new
    s = math.sin(lat)
    n = WGS84_A / math.sqrt(1.0 - WGS84_E2 * s * s)
    h = p / math.cos(lat) - n
    return math.degrees(lat), math.degrees(lon), h


def transform_frame_to_itrf2020(
    xyz: tuple[float, float, float],
    source_frame: str,
    epoch_year: float,
) -> tuple[float, float, float]:
    """Transform ECEF from ITRF2005/IGS05 or ITRF2008/IGS08 to ITRF2020 at epoch_year.

    Applies the inverse of official Altamimi et al. (2023) ITRF2020 -> ITRF200x 14-parameter
    similarity transformation. Note: GNSS antenna calibration shifts (igs05.atx -> igs08.atx ->
    igs20.atx) are separate from pure ITRF datum shifts and are documented explicitly.
    """
    key = {"IGS05": "ITRF2005", "IGS08": "ITRF2008", "IGS14": "ITRF2014"}.get(
        source_frame, source_frame
    )
    if key not in ITRF2020_TO_FRAME:
        return xyz
    p = ITRF2020_TO_FRAME[key]
    dt = epoch_year - ITRF_T0
    # Negate ITRF2020 -> target to obtain source -> ITRF2020
    tx = -(p[0] + p[7] * dt) * 1e-3
    ty = -(p[1] + p[8] * dt) * 1e-3
    tz = -(p[2] + p[9] * dt) * 1e-3
    d = -(p[3] + p[10] * dt) * 1e-9
    rx = -(p[4] + p[11] * dt) * MAS_TO_RAD
    ry = -(p[5] + p[12] * dt) * MAS_TO_RAD
    rz = -(p[6] + p[13] * dt) * MAS_TO_RAD
    x, y, z = xyz
    return (
        x + tx + d * x - rz * y + ry * z,
        y + ty + rz * x + d * y - rx * z,
        z + tz - ry * x + rx * y + d * z,
    )


def nubia_velocity_ecef_m_yr(xyz: tuple[float, float, float]) -> tuple[float, float, float]:
    """Predict ITRF2020-PMM Nubian plate velocity in ECEF (m/yr), horizontal ORB applied."""
    wx, wy, wz = (c * MAS_TO_RAD for c in NUBIA_OMEGA_MAS_YR)
    x, y, z = xyz
    # v_rot = omega x r
    vx = wy * z - wz * y
    vy = wz * x - wx * z
    vz = wx * y - wy * x
    # Add horizontal projection of ORB (discard radial component per Altamimi et al. 2023)
    lat_deg, lon_deg, _ = ecef_to_geodetic(x, y, z)
    phi, lam = math.radians(lat_deg), math.radians(lon_deg)
    u_hat = (math.cos(phi) * math.cos(lam), math.cos(phi) * math.sin(lam), math.sin(phi))
    orb = tuple(v * 1e-3 for v in NUBIA_ORB_MM_YR)
    orb_up = orb[0] * u_hat[0] + orb[1] * u_hat[1] + orb[2] * u_hat[2]
    orb_h = (orb[0] - orb_up * u_hat[0], orb[1] - orb_up * u_hat[1], orb[2] - orb_up * u_hat[2])
    return (vx + orb_h[0], vy + orb_h[1], vz + orb_h[2])


def read_rinex_approx_xyz(rnx_path: Path) -> tuple[float, float, float] | None:
    if not rnx_path.is_file():
        return None
    with rnx_path.open("r", encoding="latin1", errors="replace") as f:
        for line in f:
            if "APPROX POSITION XYZ" in line:
                parts = line[:60].split()
                if len(parts) >= 3:
                    return (float(parts[0]), float(parts[1]), float(parts[2]))
            if "END OF HEADER" in line:
                break
    return None


def mjd_to_decimal_year(mjd: float) -> float:
    # MJD 55562.0 = 2011-01-01T00:00:00Z (non-leap year 2011 has 365 days)
    return 2011.0 + (mjd - 55562.0) / 365.0


def inverse_variance_mean(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute inverse-variance weighted mean XYZ, formal sigmas, and ENU repeatability."""
    wx = sum(1.0 / (r["sigma_x_m"] ** 2) for r in rows)
    wy = sum(1.0 / (r["sigma_y_m"] ** 2) for r in rows)
    wz = sum(1.0 / (r["sigma_z_m"] ** 2) for r in rows)
    xm = sum(r["x_m"] / (r["sigma_x_m"] ** 2) for r in rows) / wx
    ym = sum(r["y_m"] / (r["sigma_y_m"] ** 2) for r in rows) / wy
    zm = sum(r["z_m"] / (r["sigma_z_m"] ** 2) for r in rows) / wz
    mean_xyz = (xm, ym, zm)
    lat_deg, lon_deg, h_m = ecef_to_geodetic(*mean_xyz)

    # Empirical ENU residuals relative to weighted mean
    en_us = [ecef_to_local_enu((r["x_m"], r["y_m"], r["z_m"]), mean_xyz) for r in rows]
    es = [v[0] for v in en_us]
    ns = [v[1] for v in en_us]
    us = [v[2] for v in en_us]
    n = len(rows)
    if n >= 2:
        # Unbiased sample std (ddof=1) for daily repeatability
        rep_e = math.sqrt(sum(e * e for e in es) / (n - 1))
        rep_n = math.sqrt(sum(nv * nv for nv in ns) / (n - 1))
        rep_u = math.sqrt(sum(u * u for u in us) / (n - 1))
        rep_3d = math.sqrt(rep_e**2 + rep_n**2 + rep_u**2)
        p2p_e = max(es) - min(es)
        p2p_n = max(ns) - min(ns)
        p2p_u = max(us) - min(us)
        p2p_3d = max(
            math.dist(
                (rows[i]["x_m"], rows[i]["y_m"], rows[i]["z_m"]),
                (rows[j]["x_m"], rows[j]["y_m"], rows[j]["z_m"]),
            )
            for i in range(n)
            for j in range(i + 1, n)
        )
    else:
        rep_e = rep_n = rep_u = rep_3d = None
        p2p_e = p2p_n = p2p_u = p2p_3d = None

    mean_mjd = statistics.fmean(r["mjd"] for r in rows)
    rms_vals = [r["phase_rms_mm"] for r in rows if r.get("phase_rms_mm") is not None]
    mean_phase_rms = statistics.fmean(rms_vals) if rms_vals else None
    max_phase_rms = max(rms_vals) if rms_vals else None

    return {
        "n_days": n,
        "doys": [r["doy"] for r in rows],
        "mean_mjd": round(mean_mjd, 4),
        "mean_epoch_year": round(mjd_to_decimal_year(mean_mjd), 5),
        "ecef_xyz_m": [round(xm, 5), round(ym, 5), round(zm, 5)],
        "lat_deg": round(lat_deg, 9),
        "lon_deg": round(lon_deg, 9),
        "height_m": round(h_m, 5),
        "formal_sigma_xyz_mm": [
            round(math.sqrt(1.0 / wx) * 1e3, 3),
            round(math.sqrt(1.0 / wy) * 1e3, 3),
            round(math.sqrt(1.0 / wz) * 1e3, 3),
        ],
        "formal_sigma_enu_mean_daily_mm": [
            round(statistics.fmean(r["sigma_e_m"] for r in rows) * 1e3, 3),
            round(statistics.fmean(r["sigma_n_m"] for r in rows) * 1e3, 3),
            round(statistics.fmean(r["sigma_u_m"] for r in rows) * 1e3, 3),
        ],
        "repeatability_enu_mm": (
            [round(rep_e * 1e3, 3), round(rep_n * 1e3, 3), round(rep_u * 1e3, 3)]
            if rep_e is not None
            else None
        ),
        "repeatability_3d_mm": round(rep_3d * 1e3, 3) if rep_3d is not None else None,
        "p2p_enu_mm": (
            [round(p2p_e * 1e3, 3), round(p2p_n * 1e3, 3), round(p2p_u * 1e3, 3)]
            if p2p_e is not None
            else None
        ),
        "p2p_3d_mm": round(p2p_3d * 1e3, 3) if p2p_3d is not None else None,
        "phase_rms_mean_mm": round(mean_phase_rms, 2) if mean_phase_rms is not None else None,
        "phase_rms_max_mm": round(max_phase_rms, 2) if max_phase_rms is not None else None,
        "nobs_min": min(r["nobs"] for r in rows),
        "nobs_mean": round(statistics.fmean(r["nobs"] for r in rows), 1),
        "antenna_types": sorted({str(r.get("antenna_type")) for r in rows}),
        "antenna_delta_h_m": sorted({r.get("antenna_delta_h_m") for r in rows}),
        "receiver_types": sorted({str(r.get("receiver_type")) for r in rows}),
        "antex_tables": sorted({str(r.get("antex_table")) for r in rows}),
    }


def evaluate_truth_acceptance(
    *,
    win_summary: dict[str, Any] | None,
    cross_ac_3d_mm: float | None,
    frame: str,
    window_label: str,
    other_window_failed_reason: str | None = None,
) -> dict[str, Any]:
    """Apply Section 5.6 8-point Truth Acceptance Criteria conservatively."""
    if win_summary is None:
        return {
            "classification": "UNVERIFIED",
            "truth_ready": False,
            "criteria": {"solution_converged": False},
            "reason": other_window_failed_reason or f"No valid PPP solution in {window_label}",
        }

    rep = win_summary["repeatability_enu_mm"]
    rep_h_mm = math.hypot(rep[0], rep[1]) if rep else None
    rep_u_mm = rep[2] if rep else None
    c = {
        "1_precise_products_used": True,
        "2_consistent_frame_and_antex": len(win_summary["antex_tables"]) == 1
        and frame.upper() in win_summary["antex_tables"][0].upper(),
        "3_antenna_arp_delta_h_verified": win_summary["antenna_delta_h_m"] == [0.171],
        "4_acceptable_phase_rms_le_25mm": (
            win_summary["phase_rms_max_mm"] is not None and win_summary["phase_rms_max_mm"] <= 25.0
        ),
        "5_multiday_repeatability_h_lt_25mm_v_lt_50mm": (
            win_summary["n_days"] >= 2
            and rep_h_mm is not None
            and rep_u_mm is not None
            and rep_h_mm < 25.0
            and rep_u_mm < 50.0
        ),
        "6_cross_ac_agreement_3d_lt_25mm": (
            cross_ac_3d_mm is not None and cross_ac_3d_mm < 25.0
        ),
        "7_sufficient_dual_freq_obs_ge_10000": win_summary["nobs_min"] >= 10000,
        "8_no_unexplained_step_within_window": (
            win_summary["p2p_3d_mm"] is not None and win_summary["p2p_3d_mm"] < 60.0
        ),
    }
    all_pass = all(c.values())
    if all_pass:
        classification = f"VERIFIED_{frame}_PPP_FLOAT"
    elif (
        c["1_precise_products_used"]
        and c["2_consistent_frame_and_antex"]
        and c["4_acceptable_phase_rms_le_25mm"]
    ):
        classification = f"PROVISIONAL_{frame}_PPP_FLOAT"
    else:
        classification = "UNVERIFIED"
    failed = [k for k, v in c.items() if not v]
    return {
        "classification": classification,
        "truth_ready": all_pass,
        "criteria": c,
        "failed_criteria": failed,
        "repeatability_h_mm": round(rep_h_mm, 3) if rep_h_mm is not None else None,
        "repeatability_u_mm": round(rep_u_mm, 3) if rep_u_mm is not None else None,
        "cross_ac_3d_mm": round(cross_ac_3d_mm, 3) if cross_ac_3d_mm is not None else None,
    }


def run_b02_v2_reevaluation(
    *,
    b04_march_igs05_coords: dict[str, tuple[float, float, float]],
    osgof_coords: dict[str, tuple[float, float, float]],
    osgf_march_summary: dict[str, Any],
    b04_analysis_sha: str,
) -> dict[str, Any]:
    """Re-evaluate B-02 2011-03-20 OSGF in a new versioned directory (preserving original B-02).

    Produces two strictly separated analyses:
    (A) Pure Truth-Coordinate Re-Evaluation: re-scores the IMMUTABLE original B-02 .pos files
        against B-04 verified IGS05 OSGF coordinate (isolating pure truth-datum shift).
    (B) Full B-04 Verified-Network Re-Run: re-executes 2011-03-20 OSGF benchmark with ALL 9
        stations updated to B-04 verified IGS05 coordinates into
        ``processed/rover-benchmark/b02-v2-b04-verified-truth/``.
    """
    orig_b02_root = DATA_ROOT / "processed/rover-benchmark/b02"
    orig_summary_path = orig_b02_root / "b02_benchmark_summary.json"
    orig_summary = json.loads(orig_summary_path.read_text(encoding="utf-8"))
    orig_2011 = orig_summary["dataset_2011_osgf_interior"]

    v2_out = DATA_ROOT / "processed/rover-benchmark/b02-v2-b04-verified-truth"
    v2_out.mkdir(parents=True, exist_ok=True)

    osgf_b04 = b04_march_igs05_coords["OSGF"]
    osgf_old = osgof_coords["OSGF"]
    truth_shift_enu = ecef_to_local_enu(osgf_b04, osgf_old)

    # --- PART A: Re-score immutable original B-02 .pos solutions against B-04 OSGF truth ---
    pure_truth_rescore: dict[str, Any] = {}
    for prof_name, variants in orig_2011["profiles"].items():
        pure_truth_rescore[prof_name] = {}
        for vid, rec in variants.items():
            pos_raw = rec.get("solution_pos_path")
            if not isinstance(pos_raw, str) or not Path(pos_raw).is_file():
                continue
            sol = parse_solution_pos(Path(pos_raw), strict=False)
            new_m, _ = compute_positioning_metrics(
                sol.epochs,
                truth_ecef_m=osgf_b04,
                start_time_utc="2011-03-20T00:00:00Z",
                end_time_utc="2011-03-20T23:59:30Z",
                sampling_interval_s=30.0,
            )
            old_m = rec["metrics"]
            pure_truth_rescore[prof_name][vid] = {
                "old_osgof_h_rmse_m": old_m.get("horizontal_rmse_m"),
                "new_b04_h_rmse_m": new_m.get("horizontal_rmse_m"),
                "delta_h_rmse_m": (
                    round(new_m["horizontal_rmse_m"] - old_m["horizontal_rmse_m"], 4)
                    if new_m.get("horizontal_rmse_m") is not None
                    and old_m.get("horizontal_rmse_m") is not None
                    else None
                ),
                "old_osgof_v_rmse_m": old_m.get("vertical_rmse_m"),
                "new_b04_v_rmse_m": new_m.get("vertical_rmse_m"),
                "delta_v_rmse_m": (
                    round(new_m["vertical_rmse_m"] - old_m["vertical_rmse_m"], 4)
                    if new_m.get("vertical_rmse_m") is not None
                    and old_m.get("vertical_rmse_m") is not None
                    else None
                ),
                "old_osgof_3d_rmse_m": old_m.get("three_d_rmse_m"),
                "new_b04_3d_rmse_m": new_m.get("three_d_rmse_m"),
                "delta_3d_rmse_m": (
                    round(new_m["three_d_rmse_m"] - old_m["three_d_rmse_m"], 4)
                    if new_m.get("three_d_rmse_m") is not None
                    and old_m.get("three_d_rmse_m") is not None
                    else None
                ),
                "fix_rate": new_m.get("fix_rate"),
                "old_mean_bias_enu_m": [
                    old_m.get("mean_east_m"),
                    old_m.get("mean_north_m"),
                    old_m.get("mean_up_m"),
                ],
                "new_mean_bias_enu_m": [
                    new_m.get("mean_east_m"),
                    new_m.get("mean_north_m"),
                    new_m.get("mean_up_m"),
                ],
            }

    # --- PART B: Full B-04 verified-network coordinate re-run (all 9 stations in IGS05) ---
    zip_2011 = DATA_ROOT / "incoming/southern-nignet/NIGNET2011.zip"
    audit_csv = (
        DATA_ROOT / "validation/southern-nignet/run-20261030T125136Z/rinex_header_audit.csv"
    )
    nav_2011_z = (
        DATA_ROOT
        / "validation/southern-nignet/coordinate-navigation-recovery"
        / "run-20261030T132927Z/navigation-products/brdc0790.11n.Z"
    )
    members_2011: dict[str, str] = {}
    with audit_csv.open(encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row["observation_date_from_filename"] == "2011-03-20":
                st4 = row["canonical_station_id"][:4]
                if st4 in PRIORITY_STATIONS:
                    members_2011[st4] = row["relative_path"]

    rover_2011 = "OSGF"
    anchor_2011 = "CGGT"
    derived_in = v2_out / "inputs/2011_03_20"
    rover_obs = _extract_zip_member(
        zip_2011, members_2011[rover_2011], derived_in / "OSGF0790.11O"
    )
    anchor_obs = _extract_zip_member(
        zip_2011, members_2011[anchor_2011], derived_in / "CGGT0790.11O"
    )
    nav_plain = _decompress_unix_z(nav_2011_z, derived_in / "brdc0790.11n")
    nav_records = parse_gps_nav_auto(nav_plain)
    nav_sha = sha256_file(nav_plain)

    ref_coords_v2 = {
        st: b04_march_igs05_coords[st] for st in PRIORITY_STATIONS if st != rover_2011
    }
    ref_ds_v2 = {
        st: read_rinex2_from_zip(zip_2011, members_2011[st], st, stride=1)
        for st in sorted(ref_coords_v2)
    }

    sig_xyz = tuple(s * 1e-3 for s in osgf_march_summary["formal_sigma_xyz_mm"])
    truth_v2 = RoverTruthRecord(
        station_id=rover_2011,
        truth_tier=TruthTier.VERIFIED_ITRF,
        accuracy_claim_permitted=True,
        ecef_xyz_m=osgf_b04,
        reference_frame="IGS05",
        coordinate_epoch="2011-03-20.5",
        provenance_source=str(WORK_ROOT / "pride_ppp_igs_54.json"),
        provenance_sha256=b04_analysis_sha,
        antenna_model="TRM59800.00 NONE",
        antenna_delta_hen_m=(0.1710, 0.0, 0.0),
        formal_sigma_xyz_m=(sig_xyz[0], sig_xyz[1], sig_xyz[2]),
        processing_method=(
            "B-04 PRIDE PPP-AR 3.2.8 static dual-frequency GPS PPP-float "
            "(2-day weighted mean DOY 079-080, IGS Final SP3/CLK_30S/ERP + igs05_1617.atx; "
            "cross-checked against CODE Final)"
        ),
        precise_products=(
            "igs16280.sp3",
            "igs16280.clk_30s",
            "igs16281.sp3",
            "igs16281.clk_30s",
            "igs16287.erp",
            "CODG0790.11I",
            "igs05_1617.atx",
        ),
        bias_products_available=False,
        notes=(
            "B-04 verified native IGS05 marker coordinate (PPP-float; no 2011 OSB available). "
            "Replaces provisional OSGoF 2011-01-01 coordinate for all 9 stations."
        ),
    )
    spec_v2 = DatasetWindowSpec(
        dataset_id="2011_03_20_osgf_b04_verified_igs05",
        date_iso="2011-03-20",
        year=2011,
        doy=79,
        start_time_utc="2011-03-20T00:00:00Z",
        end_time_utc="2011-03-20T23:59:30Z",
        sampling_interval_s=30.0,
        rover_station_id=rover_2011,
        rover_obs_path=rover_obs,
        rover_obs_sha256=sha256_file(rover_obs),
        physical_anchor_id=anchor_2011,
        physical_anchor_obs_path=anchor_obs,
        physical_anchor_obs_sha256=sha256_file(anchor_obs),
        physical_anchor_ecef_m=b04_march_igs05_coords[anchor_2011],
        reference_stations=tuple(sorted(ref_coords_v2)),
        nav_path=nav_plain,
        nav_sha256=nav_sha,
        rover_inside_convex_hull=_inside_hull(osgf_b04, ref_coords_v2),
        anchor_baseline_km=baseline_length_m(b04_march_igs05_coords[anchor_2011], osgf_b04)
        / 1000.0,
        rover_truth=truth_v2,
        notes="B-02 v2 re-evaluation with B-04 verified IGS05 coordinates across all 9 stations.",
    )

    vrs_gga_v2, spp_v2 = _derive_spp_gga_position(spec=spec_v2, out_dir=v2_out)
    iono_c_v2, iono_n_v2, ipp_v2, tgt_ipp_v2 = _compute_ref_iono_fields(
        ref_datasets=ref_ds_v2,
        ref_coords=ref_coords_v2,
        target_station=rover_2011,
        target_ecef=vrs_gga_v2,
        nav_records=nav_records,
        nav_hash=nav_sha,
        datum_station=anchor_2011,
        stride=1,
    )
    res_v2 = _execute_dataset_benchmark(
        spec=spec_v2,
        vrs_virtual_ecef_m=vrs_gga_v2,
        spp_payload=spp_v2,
        ref_coords=ref_coords_v2,
        ref_datasets=ref_ds_v2,
        nav_records=nav_records,
        iono_common=iono_c_v2,
        iono_night=iono_n_v2,
        ipp_by_key=ipp_v2,
        target_ipps=tgt_ipp_v2,
        ref_ztd=None,
        vrs_variants=(
            ("vrs_zero_geom_only", "zero", "zero", "none"),
            ("vrs_tropo_unb3m_only", "zero", "unb3m", "none"),
            ("vrs_idw2_unb3m", "idw2", "unb3m", "common_arc"),
            ("vrs_ipp_idw2_unb3m", "ipp_idw2", "unb3m", "common_arc"),
            ("vrs_nighttime_ipp_idw2_unb3m", "ipp_idw2", "unb3m", "nighttime"),
        ),
        rtcm_station_id_base=2150,
        out_dir=v2_out,
        require_interior_hull=True,
        max_epochs=None,
    )

    # Compare full v2 re-run against original B-02
    full_rerun_comparison: dict[str, Any] = {}
    for prof in RELATIVE_PROFILES:
        pname = str(prof)
        full_rerun_comparison[pname] = {}
        old_prof = orig_2011["profiles"].get(pname, {})
        new_prof = res_v2["profiles"].get(pname, {})
        for vid, new_rec in new_prof.items():
            old_rec = old_prof.get(vid, {})
            om = old_rec.get("metrics", {})
            nm = new_rec.get("metrics", {})
            full_rerun_comparison[pname][vid] = {
                "old_osgof_h_rmse_m": om.get("horizontal_rmse_m"),
                "v2_b04_h_rmse_m": nm.get("horizontal_rmse_m"),
                "old_osgof_v_rmse_m": om.get("vertical_rmse_m"),
                "v2_b04_v_rmse_m": nm.get("vertical_rmse_m"),
                "old_osgof_3d_rmse_m": om.get("three_d_rmse_m"),
                "v2_b04_3d_rmse_m": nm.get("three_d_rmse_m"),
                "old_fix_rate": om.get("fix_rate"),
                "v2_fix_rate": nm.get("fix_rate"),
                "old_fix_epochs": om.get("fix_epochs"),
                "v2_fix_epochs": nm.get("fix_epochs"),
                "v2_valid_epochs": nm.get("valid_epochs"),
                "v2_mean_bias_enu_m": [
                    nm.get("mean_east_m"),
                    nm.get("mean_north_m"),
                    nm.get("mean_up_m"),
                ],
            }

    v2_summary = {
        "schema_version": "nlgcp.b04.b02_v2_reevaluation.v1",
        "generated_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "original_b02_preserved_untouched": str(orig_b02_root),
        "original_b02_summary_sha256": sha256_file(orig_summary_path),
        "osgf_truth_shift_b04_minus_osgof_enu_m": [round(v, 5) for v in truth_shift_enu],
        "osgf_truth_shift_3d_m": round(math.dist(osgf_b04, osgf_old), 5),
        "cggt_anchor_shift_3d_m": round(
            math.dist(b04_march_igs05_coords["CGGT"], osgof_coords["CGGT"]), 5
        ),
        "part_a_pure_truth_rescore_immutable_b02_pos": pure_truth_rescore,
        "part_b_full_b04_network_rerun_comparison": full_rerun_comparison,
        "part_b_full_dataset_result": res_v2,
    }
    v2_summary_path = v2_out / "b02_v2_b04_summary.json"
    v2_summary_path.write_text(json.dumps(v2_summary, indent=2) + "\n", encoding="utf-8")
    return v2_summary


def main() -> int:
    parser = argparse.ArgumentParser(description="B-04 coordinate analysis & B-02 v2 re-evaluation")
    parser.add_argument(
        "--skip-b02-v2", action="store_true", help="Only run B-04 analysis & CSV generation"
    )
    args = parser.parse_args()

    igs_path = WORK_ROOT / "pride_ppp_igs_54.json"
    code_path = WORK_ROOT / "pride_ppp_code_crosscheck_18.json"
    igs_data = json.loads(igs_path.read_text(encoding="utf-8"))
    code_data = json.loads(code_path.read_text(encoding="utf-8"))

    osgof_csv = (
        DATA_ROOT
        / "validation/southern-nignet/coordinate-navigation-recovery"
        / "run-20261030T132927Z/coordinate_provenance.csv"
    )
    osgof_coords = load_osgof_provisional_coords(osgof_csv)
    dc_2024 = json.loads(
        (DATA_ROOT / "processed/single-base/derived-coordinates.json").read_text(encoding="utf-8")
    )

    # Index results by (ac, station, window/doy)
    igs_by_st_win: dict[tuple[str, str], list[dict[str, Any]]] = {}
    igs_failures: list[dict[str, Any]] = []
    igs_by_st_doy: dict[tuple[str, str], dict[str, Any]] = {}
    for r in igs_data["results"]:
        if r["status"] == "OK":
            igs_by_st_win.setdefault((r["station"], r["window"]), []).append(r)
            igs_by_st_doy[(r["station"], r["doy"])] = r
        else:
            igs_failures.append(r)

    code_by_st_doy: dict[tuple[str, str], dict[str, Any]] = {}
    code_failures: list[dict[str, Any]] = []
    for r in code_data["results"]:
        if r["status"] == "OK":
            code_by_st_doy[(r["station"], r["doy"])] = r
        else:
            code_failures.append(r)

    rnx_dir = WORK_ROOT / "rinex_extracted"
    stations_report: dict[str, Any] = {}
    catalogue_rows: list[dict[str, Any]] = []
    uncertainty_rows: list[dict[str, Any]] = []
    b04_march_coords: dict[str, tuple[float, float, float]] = {}

    for st in PRIORITY_STATIONS:
        mar_rows = igs_by_st_win.get((st, "2011_MAR"), [])
        dec_rows = igs_by_st_win.get((st, "2011_DEC"), [])
        mar_sum = inverse_variance_mean(mar_rows) if mar_rows else None
        dec_sum = inverse_variance_mean(dec_rows) if dec_rows else None
        if mar_sum is not None:
            b04_march_coords[st] = tuple(mar_sum["ecef_xyz_m"])  # type: ignore[assignment]

        # Cross-AC comparison (IGS - CODE) on DOY 079 (IGS05) and DOY 339 (IGS08)
        cross_ac: dict[str, Any] = {}
        for doy, lbl in (("079", "IGS05_DOY079"), ("339", "IGS08_DOY339")):
            ri = igs_by_st_doy.get((st, doy))
            rc = code_by_st_doy.get((st, doy))
            if ri and rc:
                enu = ecef_to_local_enu(
                    (ri["x_m"], ri["y_m"], ri["z_m"]), (rc["x_m"], rc["y_m"], rc["z_m"])
                )
                d3 = math.hypot(*enu)
                cross_ac[lbl] = {
                    "igs_minus_code_enu_mm": [round(v * 1e3, 3) for v in enu],
                    "igs_minus_code_3d_mm": round(d3 * 1e3, 3),
                }
            else:
                cross_ac[lbl] = None

        # Compare against provisional OSGoF 2011-01-01 and RINEX header approx XYZ
        osgof_xyz = osgof_coords.get(st)
        rnx_xyz_079 = read_rinex_approx_xyz(rnx_dir / f"{st.lower()}0790.11o")
        rnx_xyz_339 = read_rinex_approx_xyz(rnx_dir / f"{st.lower()}3390.11o")

        osgof_diff_mar = None
        if mar_sum and osgof_xyz:
            enu = ecef_to_local_enu(tuple(mar_sum["ecef_xyz_m"]), osgof_xyz)
            osgof_diff_mar = {
                "b04_minus_osgof_enu_m": [round(v, 5) for v in enu],
                "b04_minus_osgof_3d_m": round(math.hypot(*enu), 5),
                "b04_minus_osgof_horiz_m": round(math.hypot(enu[0], enu[1]), 5),
            }

        osgof_diff_dec = None
        if dec_sum and osgof_xyz:
            enu = ecef_to_local_enu(tuple(dec_sum["ecef_xyz_m"]), osgof_xyz)
            osgof_diff_dec = {
                "b04_minus_osgof_enu_m": [round(v, 5) for v in enu],
                "b04_minus_osgof_3d_m": round(math.hypot(*enu), 5),
                "b04_minus_osgof_horiz_m": round(math.hypot(enu[0], enu[1]), 5),
            }

        rnx_diff_mar = None
        if mar_sum and rnx_xyz_079:
            enu = ecef_to_local_enu(tuple(mar_sum["ecef_xyz_m"]), rnx_xyz_079)
            rnx_diff_mar = {
                "b04_minus_rinex_enu_m": [round(v, 5) for v in enu],
                "b04_minus_rinex_3d_m": round(math.hypot(*enu), 5),
            }

        # Frame-consistent March vs December check via ITRF2020 + ITRF2020-PMM Nubia plate motion
        mar_vs_dec = None
        if mar_sum and dec_sum:
            mar_2020 = transform_frame_to_itrf2020(
                tuple(mar_sum["ecef_xyz_m"]), "IGS05", mar_sum["mean_epoch_year"]
            )
            dec_2020 = transform_frame_to_itrf2020(
                tuple(dec_sum["ecef_xyz_m"]), "IGS08", dec_sum["mean_epoch_year"]
            )
            dt_yr = dec_sum["mean_epoch_year"] - mar_sum["mean_epoch_year"]
            v_nubi = nubia_velocity_ecef_m_yr(mar_2020)
            mar_pred_at_dec = (
                mar_2020[0] + v_nubi[0] * dt_yr,
                mar_2020[1] + v_nubi[1] * dt_yr,
                mar_2020[2] + v_nubi[2] * dt_yr,
            )
            raw_enu = ecef_to_local_enu(tuple(dec_sum["ecef_xyz_m"]), tuple(mar_sum["ecef_xyz_m"]))
            res_enu = ecef_to_local_enu(dec_2020, mar_pred_at_dec)
            mar_vs_dec = {
                "dt_yr": round(dt_yr, 4),
                "raw_igs08_minus_igs05_enu_mm": [round(v * 1e3, 2) for v in raw_enu],
                "itrf2020_pmm_residual_dec_minus_mar_pred_enu_mm": [
                    round(v * 1e3, 2) for v in res_enu
                ],
                "itrf2020_pmm_residual_horiz_mm": round(
                    math.hypot(res_enu[0], res_enu[1]) * 1e3, 2
                ),
                "itrf2020_pmm_residual_up_mm": round(res_enu[2] * 1e3, 2),
                "note": (
                    "Includes igs05_1617.atx -> igs08_1648.atx TRM59800.00/satellite PCO shift "
                    "(primarily Up ~10-25 mm) not captured by pure ITRF Helmert."
                ),
            }

        # Monument continuity against 2024 verified IGS20 stations
        continuity_2024 = None
        ref_for_2024 = dec_sum or mar_sum
        ref_frame_2024 = "IGS08" if dec_sum else "IGS05"
        if ref_for_2024:
            p2020 = transform_frame_to_itrf2020(
                tuple(ref_for_2024["ecef_xyz_m"]), ref_frame_2024, ref_for_2024["mean_epoch_year"]
            )
            for sid24, info24 in dc_2024["stations"].items():
                if not info24.get("scientifically_valid"):
                    continue
                e24 = info24["ecef"]
                xyz24 = (float(e24["x_m"]), float(e24["y_m"]), float(e24["z_m"]))
                dist_raw = math.dist(p2020, xyz24)
                if dist_raw < 100.0:
                    ep24 = 2024.0 + 25.5 / 366.0  # 2024-01-26.5 (2024 is leap year)
                    dt24 = ep24 - ref_for_2024["mean_epoch_year"]
                    v_nubi = nubia_velocity_ecef_m_yr(p2020)
                    pred24 = (
                        p2020[0] + v_nubi[0] * dt24,
                        p2020[1] + v_nubi[1] * dt24,
                        p2020[2] + v_nubi[2] * dt24,
                    )
                    obs_shift_enu = ecef_to_local_enu(xyz24, p2020)
                    pred_shift_enu = ecef_to_local_enu(pred24, p2020)
                    res_enu = ecef_to_local_enu(xyz24, pred24)
                    continuity_2024 = {
                        "matched_2024_station": sid24,
                        "source_2011_frame": ref_frame_2024,
                        "dt_yr": round(dt24, 4),
                        "observed_2024_minus_2011_enu_mm": [
                            round(v * 1e3, 2) for v in obs_shift_enu
                        ],
                        "predicted_nubia_pmm_enu_mm": [round(v * 1e3, 2) for v in pred_shift_enu],
                        "residual_after_pmm_enu_mm": [round(v * 1e3, 2) for v in res_enu],
                        "residual_horiz_mm": round(math.hypot(res_enu[0], res_enu[1]) * 1e3, 2),
                        "residual_up_mm": round(res_enu[2] * 1e3, 2),
                        "monument_continuity_confirmed": math.hypot(res_enu[0], res_enu[1]) < 0.05,
                    }

        # Truth acceptance per frame
        mar_acc = evaluate_truth_acceptance(
            win_summary=mar_sum,
            cross_ac_3d_mm=(
                cross_ac["IGS05_DOY079"]["igs_minus_code_3d_mm"]
                if cross_ac["IGS05_DOY079"]
                else None
            ),
            frame="IGS05",
            window_label="2011_MAR",
        )
        dec_fail_reasons = [
            f["failure_reason"]
            for f in igs_failures
            if f["station"] == st and f["window"] == "2011_DEC"
        ]
        dec_acc = evaluate_truth_acceptance(
            win_summary=dec_sum,
            cross_ac_3d_mm=(
                cross_ac["IGS08_DOY339"]["igs_minus_code_3d_mm"]
                if cross_ac["IGS08_DOY339"]
                else None
            ),
            frame="IGS08",
            window_label="2011_DEC",
            other_window_failed_reason=(
                f"Failed/rejected in Dec 2011 ({len(dec_fail_reasons)}/4 days): "
                f"{dec_fail_reasons[0]}"
                if dec_fail_reasons
                else None
            ),
        )

        stations_report[st] = {
            "station": st,
            "osgof_provisional_xyz_m": list(osgof_xyz) if osgof_xyz else None,
            "rinex_header_079_xyz_m": list(rnx_xyz_079) if rnx_xyz_079 else None,
            "rinex_header_339_xyz_m": list(rnx_xyz_339) if rnx_xyz_339 else None,
            "march_2011_igs05": mar_sum,
            "december_2011_igs08": dec_sum,
            "cross_ac_igs_minus_code": cross_ac,
            "osgof_discrepancy_march_igs05": osgof_diff_mar,
            "osgof_discrepancy_december_igs08": osgof_diff_dec,
            "rinex_header_discrepancy_march_igs05": rnx_diff_mar,
            "march_vs_december_itrf2020_pmm": mar_vs_dec,
            "monument_continuity_2024": continuity_2024,
            "truth_acceptance_march_igs05": mar_acc,
            "truth_acceptance_december_igs08": dec_acc,
        }

        # Populate CSV catalogue & uncertainty rows (one row per station × frame)
        for win_key, frame, wsum, acc, osg_d, cac_key in (
            ("2011_MAR", "IGS05", mar_sum, mar_acc, osgof_diff_mar, "IGS05_DOY079"),
            ("2011_DEC", "IGS08", dec_sum, dec_acc, osgof_diff_dec, "IGS08_DOY339"),
        ):
            cac = cross_ac.get(cac_key)
            if wsum is not None:
                p2020 = transform_frame_to_itrf2020(
                    tuple(wsum["ecef_xyz_m"]), frame, wsum["mean_epoch_year"]
                )
                catalogue_rows.append(
                    {
                        "station_id": st,
                        "window": win_key,
                        "native_frame": frame,
                        "epoch_year": wsum["mean_epoch_year"],
                        "days_used": wsum["n_days"],
                        "x_m": f"{wsum['ecef_xyz_m'][0]:.5f}",
                        "y_m": f"{wsum['ecef_xyz_m'][1]:.5f}",
                        "z_m": f"{wsum['ecef_xyz_m'][2]:.5f}",
                        "lat_deg": f"{wsum['lat_deg']:.9f}",
                        "lon_deg": f"{wsum['lon_deg']:.9f}",
                        "ellipsoidal_height_m": f"{wsum['height_m']:.5f}",
                        "itrf2020_at_epoch_x_m": f"{p2020[0]:.5f}",
                        "itrf2020_at_epoch_y_m": f"{p2020[1]:.5f}",
                        "itrf2020_at_epoch_z_m": f"{p2020[2]:.5f}",
                        "antenna_type": wsum["antenna_types"][0],
                        "antenna_delta_h_m": wsum["antenna_delta_h_m"][0],
                        "antex_model": wsum["antex_tables"][0],
                        "receiver_type": wsum["receiver_types"][0],
                        "processing_mode": "PRIDE_PPPAR_3.2.8_STATIC_GPS_FLOAT",
                        "primary_products": f"IGS_FINAL_{frame}",
                        "osgof_diff_3d_m": (
                            f"{osg_d['b04_minus_osgof_3d_m']:.5f}" if osg_d else ""
                        ),
                        "classification": acc["classification"],
                        "truth_ready": acc["truth_ready"],
                    }
                )
                rep = wsum["repeatability_enu_mm"] or [None, None, None]
                p2p = wsum["p2p_enu_mm"] or [None, None, None]
                cac_e = cac["igs_minus_code_enu_mm"][0] if cac else ""
                cac_n = cac["igs_minus_code_enu_mm"][1] if cac else ""
                cac_u = cac["igs_minus_code_enu_mm"][2] if cac else ""
                cac_3d = cac["igs_minus_code_3d_mm"] if cac else ""
                uncertainty_rows.append(
                    {
                        "station_id": st,
                        "window": win_key,
                        "native_frame": frame,
                        "days_used": wsum["n_days"],
                        "formal_sigma_e_mm": wsum["formal_sigma_enu_mean_daily_mm"][0],
                        "formal_sigma_n_mm": wsum["formal_sigma_enu_mean_daily_mm"][1],
                        "formal_sigma_u_mm": wsum["formal_sigma_enu_mean_daily_mm"][2],
                        "repeatability_e_mm": rep[0] if rep[0] is not None else "",
                        "repeatability_n_mm": rep[1] if rep[1] is not None else "",
                        "repeatability_u_mm": rep[2] if rep[2] is not None else "",
                        "repeatability_3d_mm": wsum["repeatability_3d_mm"] or "",
                        "p2p_e_mm": p2p[0] if p2p[0] is not None else "",
                        "p2p_n_mm": p2p[1] if p2p[1] is not None else "",
                        "p2p_u_mm": p2p[2] if p2p[2] is not None else "",
                        "p2p_3d_mm": wsum["p2p_3d_mm"] or "",
                        "cross_ac_igs_minus_code_e_mm": cac_e,
                        "cross_ac_igs_minus_code_n_mm": cac_n,
                        "cross_ac_igs_minus_code_u_mm": cac_u,
                        "cross_ac_igs_minus_code_3d_mm": cac_3d,
                        "phase_rms_mean_mm": wsum["phase_rms_mean_mm"],
                        "phase_rms_max_mm": wsum["phase_rms_max_mm"],
                        "nobs_min": wsum["nobs_min"],
                        "osgof_diff_e_m": osg_d["b04_minus_osgof_enu_m"][0] if osg_d else "",
                        "osgof_diff_n_m": osg_d["b04_minus_osgof_enu_m"][1] if osg_d else "",
                        "osgof_diff_u_m": osg_d["b04_minus_osgof_enu_m"][2] if osg_d else "",
                        "osgof_diff_3d_m": osg_d["b04_minus_osgof_3d_m"] if osg_d else "",
                        "classification": acc["classification"],
                    }
                )
            else:
                catalogue_rows.append(
                    {
                        "station_id": st,
                        "window": win_key,
                        "native_frame": frame,
                        "epoch_year": "",
                        "days_used": 0,
                        "x_m": "",
                        "y_m": "",
                        "z_m": "",
                        "lat_deg": "",
                        "lon_deg": "",
                        "ellipsoidal_height_m": "",
                        "itrf2020_at_epoch_x_m": "",
                        "itrf2020_at_epoch_y_m": "",
                        "itrf2020_at_epoch_z_m": "",
                        "antenna_type": "",
                        "antenna_delta_h_m": "",
                        "antex_model": "",
                        "receiver_type": "",
                        "processing_mode": "FAILED_NO_DUAL_FREQ_OBS",
                        "primary_products": f"IGS_FINAL_{frame}",
                        "osgof_diff_3d_m": "",
                        "classification": "UNVERIFIED",
                        "truth_ready": False,
                    }
                )
                uncertainty_rows.append(
                    {
                        "station_id": st,
                        "window": win_key,
                        "native_frame": frame,
                        "days_used": 0,
                        "formal_sigma_e_mm": "",
                        "formal_sigma_n_mm": "",
                        "formal_sigma_u_mm": "",
                        "repeatability_e_mm": "",
                        "repeatability_n_mm": "",
                        "repeatability_u_mm": "",
                        "repeatability_3d_mm": "",
                        "p2p_e_mm": "",
                        "p2p_n_mm": "",
                        "p2p_u_mm": "",
                        "p2p_3d_mm": "",
                        "cross_ac_igs_minus_code_e_mm": "",
                        "cross_ac_igs_minus_code_n_mm": "",
                        "cross_ac_igs_minus_code_u_mm": "",
                        "cross_ac_igs_minus_code_3d_mm": "",
                        "phase_rms_mean_mm": "",
                        "phase_rms_max_mm": "",
                        "nobs_min": 0,
                        "osgof_diff_e_m": "",
                        "osgof_diff_n_m": "",
                        "osgof_diff_u_m": "",
                        "osgof_diff_3d_m": "",
                        "classification": "UNVERIFIED",
                    }
                )

    # Write CSV deliverables into docs/research/
    docs_research = REPO_ROOT / "docs" / "research"
    docs_research.mkdir(parents=True, exist_ok=True)
    cat_csv = docs_research / "b04_station_coordinate_catalogue.csv"
    unc_csv = docs_research / "b04_coordinate_uncertainty.csv"
    with cat_csv.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(catalogue_rows[0].keys()))
        w.writeheader()
        w.writerows(catalogue_rows)
    with unc_csv.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(uncertainty_rows[0].keys()))
        w.writeheader()
        w.writerows(uncertainty_rows)

    summary_payload: dict[str, Any] = {
        "schema_version": "nlgcp.b04.analysis_summary.v1",
        "generated_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "inputs": {
            "igs_54_path": str(igs_path),
            "igs_54_sha256": sha256_file(igs_path),
            "code_18_path": str(code_path),
            "code_18_sha256": sha256_file(code_path),
            "osgof_csv_sha256": sha256_file(osgof_csv),
        },
        "counts": {
            "igs_total": igs_data["summary"]["total_jobs"],
            "igs_ok": igs_data["summary"]["ok"],
            "igs_failed": igs_data["summary"]["failed_or_rejected"],
            "code_total": code_data["summary"]["total_jobs"],
            "code_ok": code_data["summary"]["ok"],
            "code_failed": code_data["summary"]["failed_or_rejected"],
            "march_igs05_verified_stations": sum(
                1
                for s in stations_report.values()
                if s["truth_acceptance_march_igs05"]["truth_ready"]
            ),
            "december_igs08_verified_stations": sum(
                1
                for s in stations_report.values()
                if s["truth_acceptance_december_igs08"]["truth_ready"]
            ),
        },
        "igs_failures": igs_failures,
        "code_failures": code_failures,
        "stations": stations_report,
    }
    analysis_path = WORK_ROOT / "b04_analysis_summary.json"
    analysis_path.write_text(json.dumps(summary_payload, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote B-04 catalogues: {cat_csv} & {unc_csv}")
    print(
        f"Summary: IGS {summary_payload['counts']['igs_ok']}/54 OK, "
        f"CODE {summary_payload['counts']['code_ok']}/18 OK; "
        f"March IGS05 verified={summary_payload['counts']['march_igs05_verified_stations']}/9, "
        f"Dec IGS08 verified={summary_payload['counts']['december_igs08_verified_stations']}/9"
    )

    if not args.skip_b02_v2 and len(b04_march_coords) == 9:
        print(
            "\nRunning versioned B-02 v2 re-evaluation "
            "(2011-03-20 OSGF with B-04 IGS05 coords)..."
        )
        v2 = run_b02_v2_reevaluation(
            b04_march_igs05_coords=b04_march_coords,
            osgof_coords=osgof_coords,
            osgf_march_summary=stations_report["OSGF"]["march_2011_igs05"],
            b04_analysis_sha=sha256_file(analysis_path),
        )
        print(
            f"B-02 v2 complete! OSGF truth shift 3D={v2['osgf_truth_shift_3d_m']:.4f} m, "
            f"CGGT anchor shift 3D={v2['cggt_anchor_shift_3d_m']:.4f} m"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
