#!/usr/bin/env python3
"""B-03 Network Integer Ambiguity Resolution & Controlled Rover Validation Runner.

Executes three authentic, provenance-tracked experiments using B-04 verified 2011
coordinates (IGS05/IGS08) and 2024 verified IGS20 coordinates, while preserving all
original B-02 and B-02 v2 outputs untouched:

1. Authentic Network-Level Double-Difference IAR (Melbourne-Wubbena Wide-Lane +
   Ionosphere-Free Narrow-Lane LAMBDA/PAR + Triangle Loop Closure) across:
   - 2011-03-20 (IGS05, equinox): triangles (OSGF-CGGT-ABUZ) & (OSGF-ABUZ-UNEC)
   - 2011-12-05 (IGS08, Harmattan): triangle (OSGF-CGGT-ABUZ)
   - 2024-01-26 (IGS20): triangle (ABFC00NGA-EKAK00NGA-PHRI00NGA)
2. Forensic False-Fix Audit of B-02 v2's 7 wrong-integer Q=1 epochs using the
   conservative B-03 FalseFixGuard.
3. Controlled Rover Positioning Validation (pinned RTKLIB v2.4.2-p13) comparing
   physical anchor, offline atmospheric VRS, and strictly causal B-05 VRS under
   standard & long-baseline (est-stec + est-ztd, arthres=3.0 / 5.0) settings,
   plus a 5-minute outage/re-convergence stress test.

Outputs archived under ``${NLGCP_DATA_ROOT}/processed/rover-benchmark/b03-iar-validation/``.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_ROVER_SRC = Path(__file__).resolve().parents[1] / "research" / "rover_benchmark" / "src"
if str(_ROVER_SRC) not in sys.path:
    sys.path.insert(0, str(_ROVER_SRC))

from nlgcp_atmospheric_model.causal_iono import (  # noqa: E402
    CausalIonoEstimate,
    CausalIonoFilter,
    CausalNetworkDiffIonoTracker,
    combine_code_p1p2_p1c1_to_c1p2,
    parse_code_monthly_dcb,
    parse_ionex,
    parse_sinex_dsb,
    parse_sinex_osb_pair_diff,
)
from nlgcp_atmospheric_model.ionosphere_estimation import melbourne_wubbena_m  # noqa: E402
from nlgcp_atmospheric_model.observations import (  # noqa: E402
    GPS_L1_WAVELENGTH_M,
    GPS_L2_WAVELENGTH_M,
    StationDataset,
    read_rinex2_from_zip,
    read_rinex2_observations,
)
from nlgcp_atmospheric_model.provenance import sha256_file, utc_now_iso  # noqa: E402
from nlgcp_atmospheric_model.satellite_geometry import (  # noqa: E402
    BroadcastEphemeris,
    geometry_table,
    gps_datetime_to_tow,
    parse_gps_nav_auto,
    select_ephemeris,
)
from nlgcp_atmospheric_model.spatial import baseline_length_m  # noqa: E402
from nlgcp_atmospheric_model.troposphere import (  # noqa: E402
    ecef_to_geodetic,
    niell_hydrostatic_mapping,
    niell_wet_mapping,
)
from nlgcp_atmospheric_model.troposphere_estimation import unb3m_zenith_delays  # noqa: E402
from nlgcp_rover_benchmark.metrics import (  # noqa: E402
    compute_positioning_metrics,
    paired_comparison,
)
from nlgcp_rover_benchmark.models import (  # noqa: E402
    ProcessingProfile,
    RoverTruthRecord,
    TruthTier,
)
from nlgcp_rover_benchmark.rtklib_pipeline import (  # noqa: E402
    convert_rtcm_to_rinex,
    locate_rnx2rtkp,
    rtklib_tool_provenance,
)
from nlgcp_single_base.solution import ParsedSolution, parse_solution_pos  # noqa: E402
from nlgcp_vrs.experimental_vrs import (  # noqa: E402
    VrsMaturity,
    _sat_pos_and_range_at_rx,
    generate_experimental_vrs,
)
from nlgcp_vrs.network_iar import (  # noqa: E402
    IF_ALPHA1,
    IF_ALPHA2,
    LAMBDA_WL_M,
    AmbiguityStatus,
    FalseFixGuardConfig,
    audit_rover_fix_stream,
    check_network_loop_closure,
    resolve_dd_widelane,
    solve_if_narrowlane_with_zwd,
)
from nlgcp_vrs.rtcm_bridge import encode_experimental_vrs_to_rtcm  # noqa: E402


def _parse_pos_sd_3d_by_epoch(pos_path: Path) -> dict[datetime, float]:
    """Read formal 3D SD hypot(sdn, sde, sdu) per epoch directly from RTKLIB LLH .pos."""
    out: dict[datetime, float] = {}
    with pos_path.open(encoding="utf-8") as handle:
        for line in handle:
            s = line.strip()
            if not s or s.startswith("%"):
                continue
            fields = s.split()
            if len(fields) < 10:
                continue
            try:
                fmt = "%Y/%m/%d %H:%M:%S.%f" if "/" in fields[0] else "%Y-%m-%d %H:%M:%S.%f"
                ep = datetime.strptime(f"{fields[0]} {fields[1]}", fmt).replace(tzinfo=UTC)
                sdn, sde, sdu = float(fields[7]), float(fields[8]), float(fields[9])
                out[ep] = math.hypot(sdn, sde, sdu)
            except ValueError:
                continue
    return out


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )


def _baseline_dd_iar(
    *,
    sta_a: str,
    sta_b: str,
    ds_a: StationDataset,
    ds_b: StationDataset,
    coord_a: tuple[float, float, float],
    coord_b: tuple[float, float, float],
    nav_records: dict[str, list[BroadcastEphemeris]],
    doy: int,
    window_hours: int = 2,
    min_el_deg: float = 15.0,
) -> dict[str, Any]:
    """Run authentic MW Wide-Lane + IF Narrow-Lane LAMBDA/PAR across 2h windows on A->B."""
    bl_km = baseline_length_m(coord_a, coord_b) / 1000.0
    common_epochs = sorted(set(ds_a.epochs) & set(ds_b.epochs))
    unb_a = unb3m_zenith_delays(coord_a, doy, station_id=sta_a)
    unb_b = unb3m_zenith_delays(coord_b, doy, station_id=sta_b)
    lat_a, _, h_a = ecef_to_geodetic(coord_a)
    lat_b, _, h_b = ecef_to_geodetic(coord_b)

    # Group epochs into fixed UTC windows (e.g., 12 x 2h windows)
    windows: dict[int, list[str]] = {}
    for ep in common_epochs:
        hr = int(ep[11:13])
        w_idx = hr // window_hours
        windows.setdefault(w_idx, []).append(ep)

    window_reports: list[dict[str, Any]] = []
    wl_total_arcs = 0
    wl_fixed_arcs = 0
    nl_windows_attempted = 0
    nl_windows_fixed = 0
    nl_windows_partial = 0
    nl_windows_rejected_false = 0
    wl_by_window: dict[int, tuple[str, dict[str, int]]] = {}
    nl_by_window: dict[int, tuple[str, dict[str, int]]] = {}

    for w_idx, w_epochs in sorted(windows.items()):
        # Collect valid dual-freq GPS observations per epoch
        ep_sat_data: list[dict[str, dict[str, float]]] = []
        sat_el_sum: dict[str, float] = {}
        sat_ep_cnt: dict[str, int] = {}

        for ep in w_epochs:
            dt_obj = datetime.fromisoformat(ep)
            week, tow = gps_datetime_to_tow(dt_obj)
            map_a = ds_a.data.get(ep, {})
            map_b = ds_b.data.get(ep, {})
            common_sats = sorted(set(map_a) & set(map_b))
            row: dict[str, dict[str, float]] = {}
            for sat in common_sats:
                if not sat.startswith("G"):
                    continue
                oa, ob = map_a[sat], map_b[sat]
                if oa.epoch_flag != 0 or ob.epoch_flag != 0:
                    continue
                if any((oa.lli.get(c) or 0) & 3 for c in ("L1", "L2")) or any(
                    (ob.lli.get(c) or 0) & 3 for c in ("L1", "L2")
                ):
                    continue
                l1a, l2a = oa.values.get("L1"), oa.values.get("L2")
                l1b, l2b = ob.values.get("L1"), ob.values.get("L2")
                c1a = oa.values.get("P1") or oa.values.get("C1")
                c1b = ob.values.get("P1") or ob.values.get("C1")
                p2a, p2b = oa.values.get("P2"), ob.values.get("P2")
                if None in (l1a, l2a, l1b, l2b, c1a, c1b, p2a, p2b):
                    continue
                eph = select_ephemeris(nav_records.get(sat, []), week, tow)
                if eph is None:
                    continue
                assert l1a is not None and l2a is not None and c1a is not None and p2a is not None
                assert l1b is not None and l2b is not None and c1b is not None and p2b is not None
                ra, _, ela, _ = _sat_pos_and_range_at_rx(eph, week, tow, coord_a, c1a)
                rb, _, elb, _ = _sat_pos_and_range_at_rx(eph, week, tow, coord_b, c1b)
                if ela < min_el_deg or elb < min_el_deg:
                    continue
                mha = niell_hydrostatic_mapping(ela, lat_a, max(0.0, h_a), doy)
                mwa = niell_wet_mapping(ela, lat_a)
                mhb = niell_hydrostatic_mapping(elb, lat_b, max(0.0, h_b), doy)
                mwb = niell_wet_mapping(elb, lat_b)
                mw_a = melbourne_wubbena_m(l1a, l2a, c1a, p2a) / LAMBDA_WL_M
                mw_b = melbourne_wubbena_m(l1b, l2b, c1b, p2b) / LAMBDA_WL_M
                l_if_a = (
                    IF_ALPHA1 * l1a * GPS_L1_WAVELENGTH_M - IF_ALPHA2 * l2a * GPS_L2_WAVELENGTH_M
                )
                l_if_b = (
                    IF_ALPHA1 * l1b * GPS_L1_WAVELENGTH_M - IF_ALPHA2 * l2b * GPS_L2_WAVELENGTH_M
                )
                # Hydrostatic-corrected geometric residual (delta_ZWD estimated jointly!)
                sd_if_corr = (l_if_b - l_if_a) - (rb - ra) - (mhb * unb_b.zhd_m - mha * unb_a.zhd_m)
                row[sat] = {
                    "sd_mw_cyc": mw_b - mw_a,
                    "sd_if_corr_m": sd_if_corr,
                    "sd_wet_mf": mwb - mwa,
                    "min_el_deg": min(ela, elb),
                }
                sat_el_sum[sat] = sat_el_sum.get(sat, 0.0) + min(ela, elb)
                sat_ep_cnt[sat] = sat_ep_cnt.get(sat, 0) + 1
            ep_sat_data.append(row)

        # Pick reference satellite with highest coverage * mean elevation
        eligible_refs = [s for s, c in sat_ep_cnt.items() if c >= max(15, len(w_epochs) // 2)]
        if len(eligible_refs) < 4:
            continue
        ref_sat = max(eligible_refs, key=lambda s: sat_el_sum[s])

        # Gather per-satellite DD MW and DD IF observations (with simple cycle-slip screening)
        other_sats = sorted(s for s in sat_ep_cnt if s != ref_sat and sat_ep_cnt[s] >= 12)
        wl_fixed_map: dict[str, int] = {}
        wl_details: dict[str, dict[str, Any]] = {}
        clean_ep_if: list[dict[str, tuple[float, float, float]]] = [
            {} for _ in range(len(ep_sat_data))
        ]

        for sat in other_sats:
            dd_mw_series: list[float] = []
            dd_mw_w: list[float] = []
            dd_if_ep_idx: list[tuple[int, float, float, float]] = []
            prev_if: float | None = None
            slipped = False
            for idx, rmap in enumerate(ep_sat_data):
                if ref_sat not in rmap or sat not in rmap:
                    continue
                d_ref = rmap[ref_sat]
                d_sat = rmap[sat]
                dd_mw = d_sat["sd_mw_cyc"] - d_ref["sd_mw_cyc"]
                dd_if = d_sat["sd_if_corr_m"] - d_ref["sd_if_corr_m"]
                dd_mwf = d_sat["sd_wet_mf"] - d_ref["sd_wet_mf"]
                w_el = math.sin(math.radians(min(d_sat["min_el_deg"], d_ref["min_el_deg"]))) ** 2
                # Screen obvious cycle-slip jumps (>0.25 m step in DD IF phase)
                if prev_if is not None and abs(dd_if - prev_if) > 0.25:
                    slipped = True
                    break
                prev_if = dd_if
                dd_mw_series.append(dd_mw)
                dd_mw_w.append(w_el)
                dd_if_ep_idx.append((idx, dd_if, dd_mwf, w_el))

            if slipped or len(dd_mw_series) < 12:
                continue
            wl_total_arcs += 1
            wres = resolve_dd_widelane(
                ref_sat=ref_sat,
                sat=sat,
                dd_mw_cycles=dd_mw_series,
                weights=dd_mw_w,
                min_epochs=12,
                max_frac_cycles=0.20,
                max_sigma_cycles=0.15,
                min_prob=0.999,
            )
            wl_details[sat] = {
                "n_epochs": wres.n_epochs,
                "float_cycles": round(wres.float_cycles, 4),
                "frac": round(wres.fractional_offset, 4),
                "sigma": round(wres.sigma_cycles, 4),
                "fixed": wres.fixed,
                "int": wres.nearest_int if wres.fixed else None,
                "reason": wres.reason,
            }
            if wres.fixed:
                wl_fixed_arcs += 1
                wl_fixed_map[sat] = wres.nearest_int
                for ep_i, dd_if, dd_mwf, w_el in dd_if_ep_idx:
                    clean_ep_if[ep_i][sat] = (dd_if, dd_mwf, w_el)

        if wl_fixed_map:
            wl_by_window[w_idx] = (ref_sat, dict(wl_fixed_map))

        # Step 2: Narrow-lane LAMBDA + PAR + ZWD joint solve
        nl_res: dict[str, Any]
        if len(wl_fixed_map) >= 4:
            nl_windows_attempted += 1
            nl_res = solve_if_narrowlane_with_zwd(
                sat_ids=sorted(wl_fixed_map),
                epoch_obs=clean_ep_if,
                fixed_wl_by_sat=wl_fixed_map,
                prior_zwd_sigma_m=0.15,
                phase_if_sigma_m=0.015,
                ratio_threshold=3.0,
                min_success_rate=0.995,
                max_postfix_rms_m=0.025,
                min_par_sats=4,
            )
            st_str = nl_res["status"]
            if st_str == str(AmbiguityStatus.FIXED_VALIDATED):
                nl_windows_fixed += 1
                nl_by_window[w_idx] = (ref_sat, dict(nl_res["fixed_n1"]))
            elif st_str == str(AmbiguityStatus.PARTIAL_FIXED_VALIDATED):
                nl_windows_partial += 1
                nl_by_window[w_idx] = (ref_sat, dict(nl_res["fixed_n1"]))
            elif st_str == str(AmbiguityStatus.REJECTED_FALSE_FIX):
                nl_windows_rejected_false += 1
        else:
            nl_res = {
                "status": str(AmbiguityStatus.FLOAT_ONLY),
                "reason": f"fewer_than_4_wl_fixed({len(wl_fixed_map)})",
            }

        window_reports.append(
            {
                "window_idx": w_idx,
                "utc_hours": f"{w_idx * window_hours:02d}-{(w_idx + 1) * window_hours:02d}",
                "ref_sat": ref_sat,
                "wl_arcs_tested": len(wl_details),
                "wl_arcs_fixed": len(wl_fixed_map),
                "nl_result": nl_res,
            }
        )

    return {
        "baseline": f"{sta_a}->{sta_b}",
        "baseline_km": round(bl_km, 3),
        "wl_arcs_tested": wl_total_arcs,
        "wl_arcs_fixed": wl_fixed_arcs,
        "wl_fix_rate_pct": (
            round(100.0 * wl_fixed_arcs / wl_total_arcs, 2) if wl_total_arcs else 0.0
        ),
        "nl_windows_attempted": nl_windows_attempted,
        "nl_windows_full_fixed": nl_windows_fixed,
        "nl_windows_partial_fixed": nl_windows_partial,
        "nl_windows_rejected_false_fix": nl_windows_rejected_false,
        "nl_any_fix_rate_pct": (
            round(100.0 * (nl_windows_fixed + nl_windows_partial) / nl_windows_attempted, 2)
            if nl_windows_attempted
            else 0.0
        ),
        "windows": window_reports,
        "_wl_by_window": wl_by_window,
        "_nl_by_window": nl_by_window,
    }


def _triangle_loop_closures(
    ab: dict[str, Any], bc: dict[str, Any], ac: dict[str, Any]
) -> dict[str, Any]:
    """Check exact integer closure N_AB + N_BC - N_AC == 0 where all 3 baselines share ref_sat."""
    wl_checks: list[dict[str, Any]] = []
    nl_checks: list[dict[str, Any]] = []

    def _eval_map(key: str, out: list[dict[str, Any]]) -> None:
        m_ab = ab[key]
        m_bc = bc[key]
        m_ac = ac[key]
        for w_idx in sorted(set(m_ab) & set(m_bc) & set(m_ac)):
            r_ab, d_ab = m_ab[w_idx]
            r_bc, d_bc = m_bc[w_idx]
            r_ac, d_ac = m_ac[w_idx]
            # Re-reference to common pivot if ref_sat differs
            all_r = {r_ab, r_bc, r_ac}
            if len(all_r) == 1:
                chk = check_network_loop_closure(d_ab, d_bc, d_ac)
                if chk["common_satellites"] > 0:
                    out.append({"window_idx": w_idx, "ref_sat": r_ab, **chk})
            else:
                # Try re-referencing via common satellite present in all 3 maps
                def _ext(r: str, d: dict[str, int]) -> dict[str, int]:
                    return {**d, r: 0}

                e_ab, e_bc, e_ac = _ext(r_ab, d_ab), _ext(r_bc, d_bc), _ext(r_ac, d_ac)
                shared = sorted(set(e_ab) & set(e_bc) & set(e_ac))
                if len(shared) >= 2:
                    piv = shared[0]
                    n_ab = {s: e_ab[s] - e_ab[piv] for s in shared[1:]}
                    n_bc = {s: e_bc[s] - e_bc[piv] for s in shared[1:]}
                    n_ac = {s: e_ac[s] - e_ac[piv] for s in shared[1:]}
                    chk = check_network_loop_closure(n_ab, n_bc, n_ac)
                    if chk["common_satellites"] > 0:
                        out.append({"window_idx": w_idx, "ref_sat": piv, **chk})

    _eval_map("_wl_by_window", wl_checks)
    _eval_map("_nl_by_window", nl_checks)
    return {
        "wl_windows_checked": len(wl_checks),
        "wl_windows_passed": sum(1 for c in wl_checks if c["passed"]),
        "wl_total_sat_closures": sum(c["common_satellites"] for c in wl_checks),
        "wl_zero_closures": sum(
            c["common_satellites"] - len(c["nonzero_closures"]) for c in wl_checks
        ),
        "nl_windows_checked": len(nl_checks),
        "nl_windows_passed": sum(1 for c in nl_checks if c["passed"]),
        "wl_details": wl_checks,
        "nl_details": nl_checks,
    }


def _render_b03_rtklib_config(
    *,
    posmode: str,
    ionoopt: str,
    tropopt: str,
    armode: str,
    arthres: float,
    base_ecef_m: tuple[float, float, float],
    elevation_mask_deg: float = 15.0,
) -> str:
    return "\n".join(
        [
            "# NLGCP B-03 IAR Validation RTKLIB v2.4.2-p13 config",
            f"pos1-posmode       ={posmode}",
            "pos1-frequency     =l1+l2",
            "pos1-soltype       =forward",
            f"pos1-elmask        ={elevation_mask_deg:g}",
            f"pos1-ionoopt       ={ionoopt}",
            f"pos1-tropopt       ={tropopt}",
            "pos1-navsys        =1",
            f"pos2-armode        ={armode}",
            f"pos2-arthres       ={arthres:.1f}",
            "pos2-arlockcnt     =5",
            "pos2-arelmask      =20",
            "pos2-maxage        =30",
            "out-solformat      =llh",
            "out-outhead        =on",
            "out-outopt         =on",
            "out-timesys        =gpst",
            "out-timeform       =hms",
            "out-timendec       =3",
            "out-degform        =deg",
            "out-height         =ellipsoidal",
            "stats-eratio1      =100",
            "ant2-postype       =xyz",
            f"ant2-pos1          ={base_ecef_m[0]:.4f}",
            f"ant2-pos2          ={base_ecef_m[1]:.4f}",
            f"ant2-pos3          ={base_ecef_m[2]:.4f}",
            "",
        ]
    )


def _run_custom_rnx2rtkp(
    *,
    run_id: str,
    run_dir: Path,
    rover_obs: Path,
    base_obs: Path,
    nav_paths: list[Path],
    base_ecef_m: tuple[float, float, float],
    truth: RoverTruthRecord,
    start_ymd_hms: tuple[str, str],
    end_ymd_hms: tuple[str, str],
    posmode: str,
    ionoopt: str,
    tropopt: str,
    armode: str,
    arthres: float,
    baseline_km: float,
    ionosphere_corrected: bool,
) -> tuple[dict[str, Any], list[Any]]:
    """Execute pinned rnx2rtkp, score against verified truth, and run B-03 FalseFixGuard."""
    exe = locate_rnx2rtkp()
    run_dir.mkdir(parents=True, exist_ok=True)
    cfg_path = run_dir / "rtklib.conf"
    pos_path = run_dir / "solution.pos"
    cfg_text = _render_b03_rtklib_config(
        posmode=posmode,
        ionoopt=ionoopt,
        tropopt=tropopt,
        armode=armode,
        arthres=arthres,
        base_ecef_m=base_ecef_m,
    )
    def _complete_pos(p: Path) -> bool:
        if not p.is_file():
            return False
        n_rows = sum(
            1
            for ln in p.read_text(encoding="utf-8", errors="replace").splitlines()
            if ln.strip() and not ln.startswith("%")
        )
        return n_rows >= 2800

    reused = (
        cfg_path.is_file()
        and _complete_pos(pos_path)
        and cfg_path.read_text(encoding="utf-8") == cfg_text
    )
    if reused:
        dur_s = 0.0
    else:
        cfg_path.write_text(cfg_text, encoding="utf-8")
        cmd = [
            str(exe),
            "-k",
            str(cfg_path),
            "-ts",
            start_ymd_hms[0],
            start_ymd_hms[1],
            "-te",
            end_ymd_hms[0],
            end_ymd_hms[1],
            "-ti",
            "0",
            "-r",
            f"{base_ecef_m[0]:.4f}",
            f"{base_ecef_m[1]:.4f}",
            f"{base_ecef_m[2]:.4f}",
            "-o",
            str(pos_path),
            str(rover_obs),
            str(base_obs),
            *(str(p) for p in nav_paths),
        ]
        t0 = time.monotonic()
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=900)
        dur_s = round(time.monotonic() - t0, 3)
        if proc.returncode != 0 or not pos_path.is_file():
            return {
                "run_id": run_id,
                "status": "FAILED",
                "returncode": proc.returncode,
                "stderr_tail": proc.stderr[-400:],
            }, []

    parsed: ParsedSolution = parse_solution_pos(pos_path, strict=False)
    prof = (
        ProcessingProfile.STATIC_BRDC_SAAS
        if posmode == "static"
        else ProcessingProfile.KINEMATIC_BRDC_SAAS
    )
    metrics, residuals = compute_positioning_metrics(
        parsed.epochs,
        truth_ecef_m=truth.ecef_xyz_m,
        start_time_utc=f"{start_ymd_hms[0].replace('/', '-')}T{start_ymd_hms[1]}Z",
        end_time_utc=f"{end_ymd_hms[0].replace('/', '-')}T{end_ymd_hms[1]}Z",
        sampling_interval_s=30.0,
    )

    # Audit every Q=1 epoch with independent FalseFixGuard AND true ENU check
    enu_by_ep = {r.epoch: (r.east_m, r.north_m, r.up_m) for r in residuals}
    sd_3d_map = _parse_pos_sd_3d_by_epoch(pos_path)
    stream_for_guard: list[dict[str, Any]] = []
    raw_q1_true_false = 0
    raw_q1_true_good = 0
    raw_q1_h_errs: list[float] = []
    for ep in parsed.epochs:
        enu = enu_by_ep.get(ep.epoch)
        sd_3d = sd_3d_map.get(ep.epoch, 999.0)
        stream_for_guard.append(
            {
                "quality": ep.quality_code,
                "ratio": ep.ratio if ep.ratio is not None else 0.0,
                "ns": ep.satellites if ep.satellites is not None else 0,
                "age_s": ep.age_s if ep.age_s is not None else 999.0,
                "sd_3d_m": sd_3d,
                "pos_m": enu,
            }
        )
        if ep.quality_code == 1 and enu is not None:
            h_err = math.hypot(enu[0], enu[1])
            e3d = math.hypot(*enu)
            raw_q1_h_errs.append(h_err)
            if h_err > 0.25 or e3d > 0.40:
                raw_q1_true_false += 1
            else:
                raw_q1_true_good += 1

    guard = audit_rover_fix_stream(
        stream_for_guard,
        config=FalseFixGuardConfig(min_ratio=5.0, min_persistence_epochs=3),
        baseline_km=baseline_km,
        ionosphere_corrected=ionosphere_corrected,
    )
    # Count validated FIX epochs that are actually false fixes against truth
    guard_false_escapes = 0
    for a in guard["audits"]:
        if a.validated_status == AmbiguityStatus.FIXED_VALIDATED:
            enu = enu_by_ep.get(parsed.epochs[a.epoch_index].epoch)
            if enu is not None and (math.hypot(enu[0], enu[1]) > 0.25 or math.hypot(*enu) > 0.40):
                guard_false_escapes += 1

    return (
        {
            "run_id": run_id,
            "status": "COMPLETED",
            "duration_s": dur_s,
            "profile": str(prof),
            "posmode": posmode,
            "ionoopt": ionoopt,
            "tropopt": tropopt,
            "armode": armode,
            "arthres": arthres,
            "pos_path": str(pos_path),
            "pos_sha256": sha256_file(pos_path),
            "config_sha256": hashlib.sha256(cfg_text.encode("utf-8")).hexdigest(),
            "metrics": {
                "valid_epochs": metrics["valid_epochs"],
                "availability_pct": round(100.0 * metrics["availability_rate"], 2),
                "horizontal_rmse_m": round(metrics["horizontal_rmse_m"] or 0.0, 4),
                "vertical_rmse_m": round(metrics["vertical_rmse_m"] or 0.0, 4),
                "rmse_3d_m": round(metrics["three_d_rmse_m"] or 0.0, 4),
                "median_h_m": round(metrics["horizontal_median_m"] or 0.0, 4),
                "p95_h_m": round(metrics["horizontal_p95_m"] or 0.0, 4),
                "raw_fix_epochs": metrics["fix_epochs"],
                "raw_fix_rate_pct": round(100.0 * metrics["fix_rate"], 3),
                "float_rate_pct": round(100.0 * metrics["float_rate"], 2),
                "mean_satellites": metrics["satellites"]["mean"],
                "max_ratio": metrics["ratio_stats"]["max"],
                "ttff_s": metrics["ttff_s"],
                "ambiguity_resets": metrics["ambiguity_resets"],
            },
            "false_fix_audit": {
                "raw_q1_epochs": guard["raw_q1_epochs"],
                "raw_q1_true_good_lt25cm": raw_q1_true_good,
                "raw_q1_true_false_gt25cm": raw_q1_true_false,
                "raw_q1_max_h_err_m": round(max(raw_q1_h_errs), 4) if raw_q1_h_errs else None,
                "guard_validated_fix_epochs": guard["validated_fix_epochs"],
                "guard_rejected_q1_epochs": guard["rejected_q1_epochs"],
                "guard_false_fix_escapes": guard_false_escapes,
                "guard_rejection_reasons": guard["rejection_reasons_histogram"],
            },
        },
        residuals,
    )


def _generate_causal_vrs_rinex(
    *,
    experiment_id: str,
    target_station: str,
    target_ecef_m: tuple[float, float, float],
    ref_coords: dict[str, tuple[float, float, float]],
    ref_datasets: dict[str, StationDataset],
    nav_path: Path,
    sat_dsb_c1_p2_ns: dict[str, float],
    sat_dsb_p1_p2_ns: dict[str, float],
    ionex_path: Path,
    doy: int,
    ref_date_slash: str,
    reference_frame: str,
    coordinate_epoch: str,
    coordinate_provenance: str,
    spatial_model: str,
    require_interior_hull: bool,
    out_dir: Path,
) -> tuple[Path, dict[str, Any]]:
    """Synthesize strictly CAUSAL B-05 experimental VRS (epoch <= k only) -> RTCM -> RINEX."""
    out_dir.mkdir(parents=True, exist_ok=True)
    rtcm_path = out_dir / f"{experiment_id}.rtcm3"
    rnx_path = out_dir / f"{experiment_id}.rnx"
    if rtcm_path.is_file() and rnx_path.is_file() and rnx_path.stat().st_size > 1024:
        rnx_epochs = sum(
            1
            for ln in rnx_path.read_text(encoding="ascii", errors="replace").splitlines()
            if ln.startswith(">")
        )
        return rnx_path, {
            "reused_existing_causal_vrs": True,
            "rtcm_sha256": sha256_file(rtcm_path),
            "rinex_sha256": sha256_file(rnx_path),
            "rinex_epochs": rnx_epochs,
        }
    nav_records = parse_gps_nav_auto(nav_path)
    nav_hash = sha256_file(nav_path)
    ionex = parse_ionex(ionex_path)
    refs_sorted = sorted(ref_coords)
    anchor = min(refs_sorted, key=lambda r: baseline_length_m(ref_coords[r], target_ecef_m))

    all_epochs = sorted(set.union(*(set(ds.epochs) for ds in ref_datasets.values())))
    all_sats = sorted(
        {
            s
            for ds in ref_datasets.values()
            for m in ds.data.values()
            for s in m
            if s.startswith("G")
        }
    )
    all_coords_with_tgt = {**ref_coords, target_station: target_ecef_m}
    topo_rows, _ = geometry_table(
        epochs=all_epochs,
        satellites=all_sats,
        station_coords=all_coords_with_tgt,
        nav_records=nav_records,
        nav_hash=nav_hash,
    )
    topo_by_st: dict[str, dict[str, dict[str, tuple[float, float]]]] = {
        st: {} for st in all_coords_with_tgt
    }
    for row in topo_rows:
        topo_by_st[row.station_id].setdefault(row.epoch_iso, {})[row.satellite_id] = (
            row.elevation_deg,
            row.azimuth_deg,
        )

    filters = {
        st: CausalIonoFilter(
            station_id=st,
            station_ecef_m=ref_coords[st],
            nominal_step_s=30.0,
            min_elevation_deg=15.0,
            gf_slip_threshold_m=0.25,
            sat_dsb_c1_p2_ns=sat_dsb_c1_p2_ns,
            sat_dsb_p1_p2_ns=sat_dsb_p1_p2_ns,
            ionex_grid=ionex,
        )
        for st in refs_sorted
    }
    tracker = CausalNetworkDiffIonoTracker(datum_station=anchor, min_pair_epochs=3)
    causal_iono_field: dict[tuple[str, str, str], float] = {}
    ipp_by_key: dict[tuple[str, str, str], tuple[float, float]] = {}

    for ep in all_epochs:
        ep_ests: dict[str, list[CausalIonoEstimate]] = {}
        for st in refs_sorted:
            c_ests = filters[st].process_epoch(
                ep, ref_datasets[st].data.get(ep, {}), topo_by_st[st].get(ep, {})
            )
            ep_ests[st] = c_ests
            for ce in c_ests:
                ipp_by_key[(ce.epoch_iso, ce.satellite_id, st)] = (ce.ipp_lat_deg, ce.ipp_lon_deg)
        _, sd_pair = tracker.process_epoch(ep, ep_ests)
        causal_iono_field.update(sd_pair)

    from nlgcp_atmospheric_model.ionosphere_estimation import slm_mapping_and_ipp

    tgt_ipps: dict[tuple[str, str], tuple[float, float]] = {}
    for ep, smap in topo_by_st[target_station].items():
        for sat, (el_deg, az_deg) in smap.items():
            if el_deg >= 15.0:
                _, ilat, ilon = slm_mapping_and_ipp(target_ecef_m, el_deg, az_deg)
                tgt_ipps[(ep, sat)] = (ilat, ilon)

    vrs_res = generate_experimental_vrs(
        experiment_id=experiment_id,
        target_station_id=target_station,
        target_ecef_m=target_ecef_m,
        reference_coords=ref_coords,
        reference_datasets=ref_datasets,
        nav_records=nav_records,
        doy=doy,
        reference_frame=reference_frame,
        coordinate_epoch=coordinate_epoch,
        coordinate_provenance=coordinate_provenance,
        spatial_model=spatial_model,
        iono_field_by_key=causal_iono_field,
        ipp_by_key=ipp_by_key,
        target_ipp_by_epoch_sat=tgt_ipps,
        tropo_mode="unb3m",
        requested_maturity=VrsMaturity.EXPERIMENTAL_OBSERVATION_VRS,
        require_interior_hull=require_interior_hull,
    )
    bundle = encode_experimental_vrs_to_rtcm(vrs_res, rtcm_station_id=77)
    out_dir.mkdir(parents=True, exist_ok=True)
    rtcm_path = out_dir / f"{experiment_id}.rtcm3"
    rtcm_path.write_bytes(bundle.stream_bytes)
    rnx_path = out_dir / f"{experiment_id}.rnx"
    conv = convert_rtcm_to_rinex(rtcm_path, rnx_path, ref_date_slash=ref_date_slash)
    if not conv.ok or conv.rinex_path is None:
        raise RuntimeError(f"Causal VRS convbin failed for {experiment_id}: {conv.stderr}")
    return conv.rinex_path, {
        "vrs_summary": vrs_res.summary_dict(),
        "rtcm_sha256": conv.rtcm_sha256,
        "rinex_sha256": conv.rinex_sha256,
        "rinex_epochs": conv.summary.get("rinex_epoch_count"),
    }


_RINEX2_EPOCH_RE = re.compile(
    r"^ \d{2} [ \d]\d [ \d]\d ([ \d]\d) ([ \d]\d) [ \d]\d\.\d{7}  [01]"
)


def _mask_rinex2_outage(src: Path, dst: Path, *, start_hm: str, end_hm: str) -> Path:
    """Create a derived RINEX 2 observation file with a 5-minute data outage for re-fix tests."""
    lines = src.read_text(encoding="ascii", errors="replace").splitlines(keepends=True)
    out: list[str] = []
    in_header = True
    skip_epoch = False
    for ln in lines:
        if in_header:
            out.append(ln)
            if "END OF HEADER" in ln:
                in_header = False
            continue
        m = _RINEX2_EPOCH_RE.match(ln)
        if m is not None:
            hh = int(m.group(1))
            mm = int(m.group(2))
            hm = f"{hh:02d}:{mm:02d}"
            skip_epoch = start_hm <= hm < end_hm
        if not skip_epoch:
            out.append(ln)
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text("".join(out), encoding="ascii")
    return dst


def main() -> int:
    parser = argparse.ArgumentParser(description="Run B-03 Network IAR & Rover Validation Suite")
    parser.add_argument(
        "--data-root",
        type=Path,
        default=Path(os.environ.get("NLGCP_DATA_ROOT", "/home/excellence/nlgcp-data")),
    )
    args = parser.parse_args()
    data_root = args.data_root
    out_dir = data_root / "processed/rover-benchmark/b03-iar-validation"
    out_dir.mkdir(parents=True, exist_ok=True)

    tool_prov = rtklib_tool_provenance()
    b04_summary = json.loads(
        (data_root / "processed/b04-coordinate-verification/b04_analysis_summary.json").read_text()
    )
    zip_2011 = data_root / "incoming/southern-nignet/NIGNET2011.zip"
    audit_csv = data_root / "validation/southern-nignet/run-20261030T125136Z/rinex_header_audit.csv"
    nav_2011_dir = (
        data_root
        / "validation/southern-nignet/coordinate-navigation-recovery"
        / "run-20261030T132927Z/navigation-products"
    )

    def _load_2011_ds(date_iso: str, stations: list[str], stride: int) -> dict[str, StationDataset]:
        members: dict[str, str] = {}
        with audit_csv.open(encoding="utf-8") as h:
            for row in csv.DictReader(h):
                if row["observation_date_from_filename"] == date_iso:
                    st4 = row["canonical_station_id"][:4]
                    if st4 in stations:
                        members[st4] = row["relative_path"]
        return {
            st: read_rinex2_from_zip(zip_2011, members[st], st, stride=stride)
            for st in sorted(stations)
            if st in members
        }

    # =========================================================================
    # PART 1: AUTHENTIC NETWORK-LEVEL DD IAR (WL + LAMBDA NL + LOOP CLOSURE)
    # =========================================================================
    print("=== PART 1: Network-Level DD IAR (WL + IF NL LAMBDA + Triangle Closure) ===")
    mar_coords: dict[str, tuple[float, float, float]] = {
        st: (
            float(info["march_2011_igs05"]["ecef_xyz_m"][0]),
            float(info["march_2011_igs05"]["ecef_xyz_m"][1]),
            float(info["march_2011_igs05"]["ecef_xyz_m"][2]),
        )
        for st, info in sorted(b04_summary["stations"].items())
        if info["truth_acceptance_march_igs05"]["truth_ready"]
    }
    dec_coords: dict[str, tuple[float, float, float]] = {
        st: (
            float(info["december_2011_igs08"]["ecef_xyz_m"][0]),
            float(info["december_2011_igs08"]["ecef_xyz_m"][1]),
            float(info["december_2011_igs08"]["ecef_xyz_m"][2]),
        )
        for st, info in sorted(b04_summary["stations"].items())
        if info["truth_acceptance_december_igs08"]["truth_ready"]
    }

    ds_mar_sub = _load_2011_ds("2011-03-20", ["ABUZ", "CGGT", "OSGF", "UNEC"], stride=2)
    nav_079 = parse_gps_nav_auto(nav_2011_dir / "brdc0790.11n.Z")
    mar_baselines = {}
    for a, b in [
        ("OSGF", "CGGT"),
        ("CGGT", "ABUZ"),
        ("OSGF", "ABUZ"),
        ("ABUZ", "UNEC"),
        ("OSGF", "UNEC"),
    ]:
        mar_baselines[f"{a}->{b}"] = _baseline_dd_iar(
            sta_a=a,
            sta_b=b,
            ds_a=ds_mar_sub[a],
            ds_b=ds_mar_sub[b],
            coord_a=mar_coords[a],
            coord_b=mar_coords[b],
            nav_records=nav_079,
            doy=79,
        )
    tri_mar_1 = _triangle_loop_closures(
        mar_baselines["OSGF->CGGT"], mar_baselines["CGGT->ABUZ"], mar_baselines["OSGF->ABUZ"]
    )
    tri_mar_2 = _triangle_loop_closures(
        mar_baselines["OSGF->ABUZ"], mar_baselines["ABUZ->UNEC"], mar_baselines["OSGF->UNEC"]
    )

    ds_dec_sub = _load_2011_ds("2011-12-05", ["ABUZ", "CGGT", "OSGF"], stride=2)
    nav_339 = parse_gps_nav_auto(nav_2011_dir / "brdc3390.11n.Z")
    dec_baselines = {}
    for a, b in [("OSGF", "CGGT"), ("CGGT", "ABUZ"), ("OSGF", "ABUZ")]:
        dec_baselines[f"{a}->{b}"] = _baseline_dd_iar(
            sta_a=a,
            sta_b=b,
            ds_a=ds_dec_sub[a],
            ds_b=ds_dec_sub[b],
            coord_a=dec_coords[a],
            coord_b=dec_coords[b],
            nav_records=nav_339,
            doy=339,
        )
    tri_dec_1 = _triangle_loop_closures(
        dec_baselines["OSGF->CGGT"], dec_baselines["CGGT->ABUZ"], dec_baselines["OSGF->ABUZ"]
    )

    # 2024 verified IGS20 network triangle (ABFC - EKAK - PHRI)
    dc24 = json.loads((data_root / "processed/single-base/derived-coordinates.json").read_text())
    p5_adm = json.loads(
        (
            data_root / "processed/network-rtk/experiments/net-2024d026-phri-rover/admission.json"
        ).read_text()
    )
    coords_24: dict[str, tuple[float, float, float]] = {}
    obs_paths_24: dict[str, Path] = {}
    for s in p5_adm["admitted"]:
        sid = s["station_id"]
        if dc24["stations"].get(sid, {}).get("scientifically_valid") is True:
            e = dc24["stations"][sid]["ecef"]
            coords_24[sid] = (float(e["x_m"]), float(e["y_m"]), float(e["z_m"]))
            obs_paths_24[sid] = Path(s["observation_path"])
    ds_24_sub = {
        sid: read_rinex2_observations(obs_paths_24[sid], sid, stride=2)
        for sid in ("ABFC00NGA", "EKAK00NGA", "PHRI00NGA")
    }
    nav_24_path = (
        data_root
        / "processed/rover-benchmark/b02/inputs/2024_01_26/BRDC00IGS_R_20240260000_01D_MN.rnx"
    )
    nav_24 = parse_gps_nav_auto(nav_24_path)
    y24_baselines = {}
    for a, b in [
        ("EKAK00NGA", "PHRI00NGA"),
        ("ABFC00NGA", "EKAK00NGA"),
        ("ABFC00NGA", "PHRI00NGA"),
    ]:
        y24_baselines[f"{a}->{b}"] = _baseline_dd_iar(
            sta_a=a,
            sta_b=b,
            ds_a=ds_24_sub[a],
            ds_b=ds_24_sub[b],
            coord_a=coords_24[a],
            coord_b=coords_24[b],
            nav_records=nav_24,
            doy=26,
        )
    tri_24 = _triangle_loop_closures(
        y24_baselines["ABFC00NGA->EKAK00NGA"],
        y24_baselines["EKAK00NGA->PHRI00NGA"],
        y24_baselines["ABFC00NGA->PHRI00NGA"],
    )

    def _strip_internal(d: dict[str, Any]) -> dict[str, Any]:
        return {k: v for k, v in d.items() if not k.startswith("_")}

    part1_network_iar = {
        "2011_03_20_igs05": {
            "baselines": {k: _strip_internal(v) for k, v in mar_baselines.items()},
            "triangles": {"OSGF-CGGT-ABUZ": tri_mar_1, "OSGF-ABUZ-UNEC": tri_mar_2},
        },
        "2011_12_05_igs08": {
            "baselines": {k: _strip_internal(v) for k, v in dec_baselines.items()},
            "triangles": {"OSGF-CGGT-ABUZ": tri_dec_1},
        },
        "2024_01_26_igs20": {
            "baselines": {k: _strip_internal(v) for k, v in y24_baselines.items()},
            "triangles": {"ABFC-EKAK-PHRI": tri_24},
        },
    }
    for dlabel, dblock in part1_network_iar.items():
        print(f"  [{dlabel}]")
        for bname, binfo in dblock["baselines"].items():
            print(
                f"    {bname} ({binfo['baseline_km']} km): "
                f"WL {binfo['wl_arcs_fixed']}/{binfo['wl_arcs_tested']} "
                f"({binfo['wl_fix_rate_pct']}%) | "
                f"NL full={binfo['nl_windows_full_fixed']} "
                f"par={binfo['nl_windows_partial_fixed']}/{binfo['nl_windows_attempted']} "
                f"rej_false={binfo['nl_windows_rejected_false_fix']}"
            )
        for tname, tinfo in dblock["triangles"].items():
            print(
                f"    Triangle {tname}: WL closure "
                f"{tinfo['wl_zero_closures']}/{tinfo['wl_total_sat_closures']} sats "
                f"({tinfo['wl_windows_passed']}/{tinfo['wl_windows_checked']} wins) | "
                f"NL closure {tinfo['nl_windows_passed']}/{tinfo['nl_windows_checked']} wins"
            )

    # =========================================================================
    # PART 2: FORENSIC AUDIT OF B-02 v2's 7 FALSE Q=1 EPOCHS
    # =========================================================================
    print("=== PART 2: Forensic False-Fix Audit of B-02 v2 Preserved Runs ===")
    osgf_truth = RoverTruthRecord(
        station_id="OSGF",
        truth_tier=TruthTier.VERIFIED_ITRF,
        accuracy_claim_permitted=True,
        ecef_xyz_m=mar_coords["OSGF"],
        reference_frame="IGS05",
        coordinate_epoch="2011.21642",
        provenance_source=str(
            data_root / "processed/b04-coordinate-verification/b04_analysis_summary.json"
        ),
        provenance_sha256=sha256_file(
            data_root / "processed/b04-coordinate-verification/b04_analysis_summary.json"
        ),
        antenna_model="TRM59800.00     NONE",
        antenna_delta_hen_m=(0.1710, 0.0, 0.0),
        processing_method="B-04 PRIDE PPP-AR 3.2.8 IGS Final (DOY 079-080)",
    )
    b02_v2_root = (
        data_root
        / "processed/rover-benchmark/b02-v2-b04-verified-truth/2011_03_20_osgf_b04_verified_igs05"
    )
    part2_false_fix: dict[str, Any] = {}
    for variant in ("vrs_zero_geom_only", "vrs_tropo_unb3m_only"):
        pos_file = b02_v2_root / "runs" / variant / "kinematic_brdc_saas" / "solution.pos"
        parsed = parse_solution_pos(pos_file, strict=False)
        _, resids = compute_positioning_metrics(
            parsed.epochs,
            truth_ecef_m=osgf_truth.ecef_xyz_m,
            start_time_utc="2011-03-20T00:00:00Z",
            end_time_utc="2011-03-20T23:59:30Z",
            sampling_interval_s=30.0,
        )
        enu_map = {r.epoch: (r.east_m, r.north_m, r.up_m) for r in resids}
        sd_3d_map_p2 = _parse_pos_sd_3d_by_epoch(pos_file)
        ep_stream = [
            {
                "quality": ep.quality_code,
                "ratio": ep.ratio if ep.ratio is not None else 0.0,
                "ns": ep.satellites if ep.satellites is not None else 0,
                "age_s": ep.age_s if ep.age_s is not None else 999.0,
                "sd_3d_m": sd_3d_map_p2.get(ep.epoch, 999.0),
                "pos_m": enu_map.get(ep.epoch),
            }
            for ep in parsed.epochs
        ]
        # Audit under BOTH ionosphere_corrected=False (truth) AND True (to show ratio/jump alone!)
        guard_strict = audit_rover_fix_stream(
            ep_stream,
            config=FalseFixGuardConfig(min_ratio=5.0, min_persistence_epochs=3),
            baseline_km=216.32,
            ionosphere_corrected=False,
        )
        guard_blind = audit_rover_fix_stream(
            ep_stream,
            config=FalseFixGuardConfig(min_ratio=5.0, min_persistence_epochs=3),
            baseline_km=216.32,
            ionosphere_corrected=True,
        )
        q1_details = []
        for idx, ep in enumerate(parsed.epochs):
            if ep.quality_code == 1:
                enu = enu_map[ep.epoch]
                ga = guard_blind["audits"][idx]
                q1_details.append(
                    {
                        "epoch_utc": ep.epoch.isoformat(),
                        "ns": ep.satellites,
                        "ratio": ep.ratio,
                        "h_err_m": round(math.hypot(enu[0], enu[1]), 4),
                        "v_err_m": round(enu[2], 4),
                        "e3d_m": round(math.hypot(*enu), 4),
                        "guard_status_blind": str(ga.validated_status),
                        "guard_reasons_blind": list(ga.rejection_reasons),
                    }
                )
        part2_false_fix[variant] = {
            "source_pos_sha256": sha256_file(pos_file),
            "raw_q1_epochs": len(q1_details),
            "guard_strict_validated": guard_strict["validated_fix_epochs"],
            "guard_strict_rejected": guard_strict["rejected_q1_epochs"],
            "guard_blind_validated": guard_blind["validated_fix_epochs"],
            "guard_blind_rejected": guard_blind["rejected_q1_epochs"],
            "guard_blind_reasons": guard_blind["rejection_reasons_histogram"],
            "q1_epochs": q1_details,
        }
        print(
            f"  {variant}: raw Q=1={len(q1_details)} -> "
            f"guard_blind rejected {guard_blind['rejected_q1_epochs']}/{len(q1_details)} "
            f"(reasons={guard_blind['rejection_reasons_histogram']})"
        )

    # =========================================================================
    # PART 3: CONTROLLED ROVER POSITIONING VALIDATION (2024 PHRI + 2011 OSGF)
    # =========================================================================
    print("=== PART 3: Controlled Rover Positioning Validation (2024 + 2011 + Causal VRS) ===")
    # 3A. 2024-01-26 PHRI00NGA (Verified IGS20, 105.553 km anchor EKAK00NGA)
    phri_truth = RoverTruthRecord(
        station_id="PHRI00NGA",
        truth_tier=TruthTier.VERIFIED_IGS20_PPP_AR,
        accuracy_claim_permitted=True,
        ecef_xyz_m=coords_24["PHRI00NGA"],
        reference_frame="IGS20",
        coordinate_epoch="2024-01-26",
        provenance_source=str(data_root / "processed/single-base/derived-coordinates.json"),
        provenance_sha256=sha256_file(data_root / "processed/single-base/derived-coordinates.json"),
        antenna_model="TRM115000.00    NONE",
        antenna_delta_hen_m=(0.0, 0.0, 0.0),
        processing_method="Phase 3/B-02 verified IGS20 PRIDE PPP-AR",
    )
    b02_24_path = (
        data_root
        / "processed/rover-benchmark/b02/2024_01_26_phri_verified/benchmark_results.json"
    )
    b02_24_res = json.loads(b02_24_path.read_text())
    phri_vrs_arp = tuple(
        float(v) for v in b02_24_res["vrs_generation"]["vrs_idw2_unb3m"]["vrs_virtual_ecef_m"]
    )
    # Generate strictly CAUSAL B-05 VRS for 2024 PHRI (full 30s!)
    ref_24_full = {
        sid: read_rinex2_observations(obs_paths_24[sid], sid, stride=1)
        for sid in ("ABFC00NGA", "EKAK00NGA", "MGBO00NGA")
    }
    osb_24 = parse_sinex_osb_pair_diff(
        data_root / "external-products/igs/2024/biases/COD0OPSFIN_20240260000_01D_01D_OSB.BIA.gz",
        obs1="C1C",
        obs2="C2W",
    )
    dsb_24 = parse_sinex_dsb(
        data_root / "external-products/igs/2024/biases/CAS0OPSRAP_20240260000_01D_01D_DCB.BIA.gz",
        obs1="C1W",
        obs2="C2W",
    )
    causal_vrs_24_rnx, causal_vrs_24_meta = _generate_causal_vrs_rinex(
        experiment_id="b03_causal_2024_phri_idw2_unb3m",
        target_station="PHRI00NGA",
        target_ecef_m=phri_vrs_arp,  # type: ignore[arg-type]
        ref_coords={k: coords_24[k] for k in ("ABFC00NGA", "EKAK00NGA", "MGBO00NGA")},
        ref_datasets=ref_24_full,
        nav_path=nav_24_path,
        sat_dsb_c1_p2_ns=osb_24.sat_bias_ns,
        sat_dsb_p1_p2_ns=dsb_24.sat_bias_ns,
        ionex_path=data_root
        / "external-products/igs/2024/ionosphere/COD0OPSFIN_20240260000_01D_01H_GIM.INX.gz",
        doy=26,
        ref_date_slash="2024/01/26",
        reference_frame="IGS20",
        coordinate_epoch="2024-01-26",
        coordinate_provenance="VERIFIED_IGS20",
        spatial_model="idw2",
        require_interior_hull=False,
        out_dir=out_dir / "vrs_causal_2024",
    )

    vrs_24_idw2_rnx = (
        data_root
        / "processed/rover-benchmark/b02/2024_01_26_phri_verified/rinex/vrs_idw2_unb3m.obs"
    )
    runs_24: dict[str, Any] = {}
    enus_24: dict[str, list[Any]] = {}
    specs_24 = [
        (
            "anchor_kin_brdc_t3",
            obs_paths_24["EKAK00NGA"],
            coords_24["EKAK00NGA"],
            "kinematic",
            "brdc",
            "saas",
            "continuous",
            3.0,
            False,
        ),
        (
            "anchor_kin_est_stec_t3",
            obs_paths_24["EKAK00NGA"],
            coords_24["EKAK00NGA"],
            "kinematic",
            "est-stec",
            "est-ztd",
            "continuous",
            3.0,
            True,
        ),
        (
            "anchor_kin_est_stec_t5",
            obs_paths_24["EKAK00NGA"],
            coords_24["EKAK00NGA"],
            "kinematic",
            "est-stec",
            "est-ztd",
            "continuous",
            5.0,
            True,
        ),
        (
            "anchor_sta_est_stec_t5",
            obs_paths_24["EKAK00NGA"],
            coords_24["EKAK00NGA"],
            "static",
            "est-stec",
            "est-ztd",
            "continuous",
            5.0,
            True,
        ),
        (
            "vrs_off_idw2_kin_brdc_t3",
            vrs_24_idw2_rnx,
            phri_vrs_arp,
            "kinematic",
            "brdc",
            "saas",
            "continuous",
            3.0,
            True,
        ),
        (
            "vrs_off_idw2_kin_est_stec_t5",
            vrs_24_idw2_rnx,
            phri_vrs_arp,
            "kinematic",
            "est-stec",
            "est-ztd",
            "continuous",
            5.0,
            True,
        ),
        (
            "vrs_causal_idw2_kin_brdc_t3",
            causal_vrs_24_rnx,
            phri_vrs_arp,
            "kinematic",
            "brdc",
            "saas",
            "continuous",
            3.0,
            True,
        ),
        (
            "vrs_causal_idw2_kin_est_stec_t5",
            causal_vrs_24_rnx,
            phri_vrs_arp,
            "kinematic",
            "est-stec",
            "est-ztd",
            "continuous",
            5.0,
            True,
        ),
        (
            "vrs_causal_idw2_sta_brdc_t3",
            causal_vrs_24_rnx,
            phri_vrs_arp,
            "static",
            "brdc",
            "saas",
            "continuous",
            3.0,
            True,
        ),
    ]
    for rid, b_obs, b_xyz, pm, io, tr, ar, th, icorr in specs_24:
        res, emap = _run_custom_rnx2rtkp(
            run_id=rid,
            run_dir=out_dir / "2024_phri" / rid,
            rover_obs=obs_paths_24["PHRI00NGA"],
            base_obs=b_obs,
            nav_paths=[nav_24_path],
            base_ecef_m=b_xyz,  # type: ignore[arg-type]
            truth=phri_truth,
            start_ymd_hms=("2024/01/26", "00:00:00"),
            end_ymd_hms=("2024/01/26", "23:59:30"),
            posmode=pm,
            ionoopt=io,
            tropopt=tr,
            armode=ar,
            arthres=th,
            baseline_km=105.553,
            ionosphere_corrected=icorr,
        )
        runs_24[rid] = res
        enus_24[rid] = emap
        m = res["metrics"]
        ff = res["false_fix_audit"]
        print(
            f"  [2024 PHRI] {rid:32s} H={m['horizontal_rmse_m']:.4f}m "
            f"V={m['vertical_rmse_m']:.4f}m 3D={m['rmse_3d_m']:.4f}m "
            f"rawQ1={ff['raw_q1_epochs']} guardFix={ff['guard_validated_fix_epochs']} "
            f"escapes={ff['guard_false_fix_escapes']}"
        )

    # 3B. 2011-03-20 OSGF (B-04 Verified IGS05, interior 8-ref hull, 216.320 km anchor CGGT)
    b02_v2_summary = json.loads(
        (
            data_root
            / "processed/rover-benchmark/b02-v2-b04-verified-truth/b02_v2_b04_summary.json"
        ).read_text()
    )
    osgf_vrs_arp = tuple(
        float(v)
        for v in b02_v2_summary["part_b_full_dataset_result"]["vrs_generation"][
            "vrs_ipp_idw2_unb3m"
        ]["vrs_virtual_ecef_m"]
    )
    rnx_osgf_11 = data_root / "processed/b04-coordinate-verification/rinex_extracted/osgf0790.11o"
    rnx_cggt_11 = data_root / "processed/b04-coordinate-verification/rinex_extracted/cggt0790.11o"
    nav_079_plain = data_root / "processed/b04-coordinate-verification/rinex_extracted/brdm0790.11p"

    # Generate strictly CAUSAL B-05 VRS for 2011 OSGF (full 30s, 8 B-04 verified refs)
    ref_11_stations = sorted(st for st in mar_coords if st != "OSGF")
    ref_11_full = _load_2011_ds("2011-03-20", ref_11_stations, stride=1)
    p1p2_mar = parse_code_monthly_dcb(
        data_root / "external-products/igs/2011/biases/P1P21103.DCB.Z", "P1P2"
    )
    p1c1_mar = parse_code_monthly_dcb(
        data_root / "external-products/igs/2011/biases/P1C11103.DCB.Z", "P1C1"
    )
    c1p2_mar = combine_code_p1p2_p1c1_to_c1p2(p1p2_mar, p1c1_mar)
    causal_vrs_11_rnx, causal_vrs_11_meta = _generate_causal_vrs_rinex(
        experiment_id="b03_causal_2011_osgf_ipp_idw2_unb3m",
        target_station="OSGF",
        target_ecef_m=osgf_vrs_arp,  # type: ignore[arg-type]
        ref_coords={k: mar_coords[k] for k in ref_11_stations},
        ref_datasets=ref_11_full,
        nav_path=nav_2011_dir / "brdc0790.11n.Z",
        sat_dsb_c1_p2_ns=c1p2_mar,
        sat_dsb_p1_p2_ns=p1p2_mar.sat_bias_ns,
        ionex_path=data_root / "external-products/igs/2011/ionosphere/CODG0790.11I.Z",
        doy=79,
        ref_date_slash="2011/03/20",
        reference_frame="IGS05",
        coordinate_epoch="2011.21642",
        coordinate_provenance="VERIFIED_IGS05_PPP_FLOAT",
        spatial_model="ipp_idw2",
        require_interior_hull=True,
        out_dir=out_dir / "vrs_causal_2011",
    )

    vrs_11_ipp_rnx = b02_v2_root / "rinex/vrs_ipp_idw2_unb3m.obs"
    # Derived outage file (5-minute outage 12:00-12:05 UTC)
    osgf_outage_rnx = _mask_rinex2_outage(
        rnx_osgf_11,
        out_dir / "inputs/osgf0790_outage_1200_1205.11o",
        start_hm="12:00",
        end_hm="12:05",
    )

    runs_11: dict[str, Any] = {}
    enus_11: dict[str, list[Any]] = {}
    specs_11 = [
        (
            "anchor_kin_brdc_t3",
            rnx_cggt_11,
            mar_coords["CGGT"],
            rnx_osgf_11,
            "kinematic",
            "brdc",
            "saas",
            "continuous",
            3.0,
            False,
        ),
        (
            "anchor_kin_est_stec_t3",
            rnx_cggt_11,
            mar_coords["CGGT"],
            rnx_osgf_11,
            "kinematic",
            "est-stec",
            "est-ztd",
            "continuous",
            3.0,
            True,
        ),
        (
            "anchor_kin_est_stec_t5",
            rnx_cggt_11,
            mar_coords["CGGT"],
            rnx_osgf_11,
            "kinematic",
            "est-stec",
            "est-ztd",
            "continuous",
            5.0,
            True,
        ),
        (
            "vrs_off_ipp_kin_brdc_t3",
            vrs_11_ipp_rnx,
            osgf_vrs_arp,
            rnx_osgf_11,
            "kinematic",
            "brdc",
            "saas",
            "continuous",
            3.0,
            True,
        ),
        (
            "vrs_off_ipp_kin_est_stec_t3",
            vrs_11_ipp_rnx,
            osgf_vrs_arp,
            rnx_osgf_11,
            "kinematic",
            "est-stec",
            "est-ztd",
            "continuous",
            3.0,
            True,
        ),
        (
            "vrs_off_ipp_kin_est_stec_t5",
            vrs_11_ipp_rnx,
            osgf_vrs_arp,
            rnx_osgf_11,
            "kinematic",
            "est-stec",
            "est-ztd",
            "continuous",
            5.0,
            True,
        ),
        (
            "vrs_off_ipp_sta_est_stec_t5",
            vrs_11_ipp_rnx,
            osgf_vrs_arp,
            rnx_osgf_11,
            "static",
            "est-stec",
            "est-ztd",
            "continuous",
            5.0,
            True,
        ),
        (
            "vrs_causal_ipp_kin_brdc_t3",
            causal_vrs_11_rnx,
            osgf_vrs_arp,
            rnx_osgf_11,
            "kinematic",
            "brdc",
            "saas",
            "continuous",
            3.0,
            True,
        ),
        (
            "vrs_causal_ipp_kin_est_stec_t5",
            causal_vrs_11_rnx,
            osgf_vrs_arp,
            rnx_osgf_11,
            "kinematic",
            "est-stec",
            "est-ztd",
            "continuous",
            5.0,
            True,
        ),
        (
            "vrs_causal_ipp_sta_brdc_t3",
            causal_vrs_11_rnx,
            osgf_vrs_arp,
            rnx_osgf_11,
            "static",
            "brdc",
            "saas",
            "continuous",
            3.0,
            True,
        ),
        (
            "vrs_causal_ipp_outage_5min",
            causal_vrs_11_rnx,
            osgf_vrs_arp,
            osgf_outage_rnx,
            "kinematic",
            "brdc",
            "saas",
            "continuous",
            3.0,
            True,
        ),
    ]
    def _run_11_spec(spec: tuple[Any, ...]) -> tuple[str, dict[str, Any], list[Any]]:
        rid, b_obs, b_xyz, rov_obs, pm, io, tr, ar, th, icorr = spec
        res, emap = _run_custom_rnx2rtkp(
            run_id=rid,
            run_dir=out_dir / "2011_osgf" / rid,
            rover_obs=rov_obs,
            base_obs=b_obs,
            nav_paths=[nav_079_plain],
            base_ecef_m=b_xyz,
            truth=osgf_truth,
            start_ymd_hms=("2011/03/20", "00:00:00"),
            end_ymd_hms=("2011/03/20", "23:59:30"),
            posmode=pm,
            ionoopt=io,
            tropopt=tr,
            armode=ar,
            arthres=th,
            baseline_km=216.32,
            ionosphere_corrected=icorr,
        )
        return rid, res, emap

    with ThreadPoolExecutor(max_workers=4) as pool:
        for rid, res, emap in pool.map(_run_11_spec, specs_11):
            runs_11[rid] = res
            enus_11[rid] = emap
            m = res["metrics"]
            ff = res["false_fix_audit"]
            print(
                f"  [2011 OSGF] {rid:32s} H={m['horizontal_rmse_m']:.4f}m "
                f"V={m['vertical_rmse_m']:.4f}m 3D={m['rmse_3d_m']:.4f}m "
                f"rawQ1={ff['raw_q1_epochs']} guardFix={ff['guard_validated_fix_epochs']} "
                f"escapes={ff['guard_false_fix_escapes']}"
            )

    # Paired bootstrap CIs for key comparisons
    def _pair_ci(
        res_map: dict[str, list[Any]], cand: str, base: str
    ) -> dict[str, Any]:
        result: dict[str, Any] = paired_comparison(
            res_map[base],
            res_map[cand],
            baseline_label=base,
            candidate_label=cand,
        )
        return result

    paired_cis = {
        "2011_causal_ipp_vs_anchor_kin": _pair_ci(
            enus_11, "vrs_causal_ipp_kin_brdc_t3", "anchor_kin_brdc_t3"
        ),
        "2011_causal_ipp_vs_offline_ipp_kin": _pair_ci(
            enus_11, "vrs_causal_ipp_kin_brdc_t3", "vrs_off_ipp_kin_brdc_t3"
        ),
        "2011_anchor_est_stec_vs_brdc_kin": _pair_ci(
            enus_11, "anchor_kin_est_stec_t5", "anchor_kin_brdc_t3"
        ),
        "2011_vrs_off_ipp_est_stec_vs_anchor_est_stec": _pair_ci(
            enus_11, "vrs_off_ipp_kin_est_stec_t5", "anchor_kin_est_stec_t5"
        ),
        "2024_causal_idw2_vs_anchor_kin": _pair_ci(
            enus_24, "vrs_causal_idw2_kin_brdc_t3", "anchor_kin_brdc_t3"
        ),
        "2024_anchor_est_stec_vs_brdc_kin": _pair_ci(
            enus_24, "anchor_kin_est_stec_t5", "anchor_kin_brdc_t3"
        ),
    }

    summary = {
        "schema_version": "nlgcp.b03.network_iar_validation.v1",
        "generated_utc": utc_now_iso(),
        "tool_provenance": tool_prov,
        "part1_network_dd_iar": part1_network_iar,
        "part2_b02_false_fix_forensic_audit": part2_false_fix,
        "part3_rover_validation": {
            "2024_phri_igs20": {
                "causal_vrs_metadata": causal_vrs_24_meta,
                "runs": runs_24,
            },
            "2011_osgf_b04_igs05": {
                "causal_vrs_metadata": causal_vrs_11_meta,
                "runs": runs_11,
            },
            "paired_bootstrap_comparisons": paired_cis,
        },
    }
    out_summary = out_dir / "b03_iar_validation_summary.json"
    _write_json(out_summary, summary)
    print(f"\nWrote B-03 IAR validation summary: {out_summary}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
