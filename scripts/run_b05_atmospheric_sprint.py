#!/usr/bin/env python3
"""B-05 Atmospheric Model Enhancement Validation Runner (Causal + DCB/IONEX + Tropo + Spatial).

Executes authentic real-data experiments across:
- 2011-03-20 (DOY 079, equinox disturbed, 9 B-04 verified IGS05 stations)
- 2011-03-21 (DOY 080, equinox disturbed, 9 B-04 verified IGS05 stations)
- 2011-12-05 (DOY 339, Harmattan quiet/dry, 8 B-04 verified IGS08 stations; RUST excluded L2=0%)
- 2024-01-26 (DOY 026, 4 verified IGS20 stations)
- Plus 50 2011 station-days & 4 2024 station-days of PRIDE PPP-AR 3.2.8 ZTD evaluation (54 total).

Outputs machine-readable JSON & provenance under
``${NLGCP_DATA_ROOT}/processed/atmospheric-model/b05/``.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import random
import statistics
from pathlib import Path
from typing import Any

from nlgcp_atmospheric_model.causal_iono import (
    CausalIonoEstimate,
    CausalIonoFilter,
    CausalNetworkDiffIonoTracker,
    IonexGrid,
    combine_code_p1p2_p1c1_to_c1p2,
    parse_code_monthly_dcb,
    parse_ionex,
    parse_sinex_dsb,
    parse_sinex_osb_pair_diff,
)
from nlgcp_atmospheric_model.causal_tropo import CausalTropoZwdFilter
from nlgcp_atmospheric_model.ionosphere_estimation import (
    IonosphericPointEstimate,
    common_arc_sd_l1_iono,
    estimate_station_ionosphere,
    nighttime_leveled_sd_l1_iono,
)
from nlgcp_atmospheric_model.observations import (
    StationDataset,
    read_rinex2_from_zip,
    read_rinex2_observations,
)
from nlgcp_atmospheric_model.provenance import sha256_file, utc_now_iso
from nlgcp_atmospheric_model.satellite_geometry import geometry_table, parse_gps_nav_auto
from nlgcp_atmospheric_model.spatial import baseline_length_m
from nlgcp_atmospheric_model.spatial_estimation import (
    SPATIAL_MODELS,
    predict_spatial,
    run_stratified_loocv,
)
from nlgcp_atmospheric_model.troposphere_estimation import (
    PrideZtdEpoch,
    evaluate_tropo_against_pride,
    parse_pride_ztd,
    unb3m_zenith_delays,
)

IONO_MODELS = (*SPATIAL_MODELS, "ipp_idw2")
COASTAL_STATIONS = frozenset({"ULAG", "RUST", "PHRI00NGA", "EKAK00NGA"})
INTERIOR_2011_STATIONS = frozenset({"ABUZ", "CGGT", "OSGF", "UNEC"})
SPARSE_2011_SUBSET = ("ABUZ", "CGGT", "OSGF", "ULAG")


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )


def _rmse(vals: list[float]) -> float | None:
    if not vals:
        return None
    return math.sqrt(sum(v * v for v in vals) / len(vals))


def _epoch_hour_utc(epoch_iso: str) -> int:
    return int(epoch_iso[11:13])


def _block_bootstrap_gain_ci(
    zero_resids_by_ep: dict[str, list[float]],
    cand_resids_by_ep: dict[str, list[float]],
    *,
    block_epochs: int = 20,
    n_boot: int = 400,
    seed: int = 20261126,
) -> dict[str, Any] | None:
    """Compute paired epoch-block bootstrap 95% CI on RMSE reduction (zero - cand)."""
    epochs = sorted(set(zero_resids_by_ep) & set(cand_resids_by_ep))
    if len(epochs) < max(5, block_epochs):
        return None
    blocks: list[list[str]] = [
        epochs[i : i + block_epochs] for i in range(0, len(epochs), block_epochs)
    ]
    rng = random.Random(seed)
    gains_m: list[float] = []
    gains_pct: list[float] = []
    n_blocks = len(blocks)
    for _ in range(n_boot):
        z_sq = 0.0
        c_sq = 0.0
        cnt = 0
        for _ in range(n_blocks):
            blk = blocks[rng.randrange(n_blocks)]
            for ep in blk:
                zv = zero_resids_by_ep[ep]
                cv = cand_resids_by_ep[ep]
                z_sq += sum(x * x for x in zv)
                c_sq += sum(x * x for x in cv)
                cnt += len(zv)
        if cnt > 0 and z_sq > 0.0:
            z_r = math.sqrt(z_sq / cnt)
            c_r = math.sqrt(c_sq / cnt)
            gains_m.append(z_r - c_r)
            gains_pct.append((1.0 - c_r / z_r) * 100.0)
    if not gains_m:
        return None
    gains_m.sort()
    gains_pct.sort()
    lo_idx = int(0.025 * len(gains_m))
    hi_idx = min(len(gains_m) - 1, int(0.975 * len(gains_m)))
    win_frac = sum(1 for g in gains_m if g > 0.0) / len(gains_m)
    return {
        "block_epochs": block_epochs,
        "n_boot": n_boot,
        "seed": seed,
        "rmse_reduction_m_ci95": [round(gains_m[lo_idx], 4), round(gains_m[hi_idx], 4)],
        "rmse_reduction_pct_ci95": [round(gains_pct[lo_idx], 2), round(gains_pct[hi_idx], 2)],
        "bootstrap_win_prob": round(win_frac, 4),
    }


def _compute_loocv_bootstrap_cis(
    *,
    coords: dict[str, tuple[float, float, float]],
    observed: dict[tuple[str, str, str], float],
    ipp_by_key: dict[tuple[str, str, str], tuple[float, float]],
    interior_set: frozenset[str],
    candidate_models: tuple[str, ...] = ("idw2", "ipp_idw2"),
    min_refs: int = 3,
) -> dict[str, Any]:
    """Compute paired epoch-block bootstrap 95% CIs on interior & perimeter LOOCV gains."""
    stations = sorted(coords)
    keys_by_ep_sat: dict[tuple[str, str], set[str]] = {}
    for ep, sat, sid in observed:
        if sid in coords:
            keys_by_ep_sat.setdefault((ep, sat), set()).add(sid)

    buckets: dict[str, dict[str, dict[str, list[float]]]] = {
        "interior": {m: {} for m in ("zero", *candidate_models)},
        "perimeter": {m: {} for m in ("zero", *candidate_models)},
        "overall": {m: {} for m in ("zero", *candidate_models)},
    }
    for target in stations:
        refs_all = [s for s in stations if s != target]
        if len(refs_all) < min_refs:
            continue
        stratum = "interior" if target in interior_set else "perimeter"
        for (ep, sat), present in sorted(keys_by_ep_sat.items()):
            if target not in present:
                continue
            avail_refs = [r for r in refs_all if r in present]
            if len(avail_refs) < min_refs:
                continue
            fold_anchor = min(
                avail_refs, key=lambda r: baseline_length_m(coords[r], coords[target])
            )
            offset = observed[(ep, sat, fold_anchor)]
            obs_t = observed[(ep, sat, target)] - offset
            ref_triples = [(r, coords[r], observed[(ep, sat, r)] - offset) for r in avail_refs]
            tgt_ipp = ipp_by_key.get((ep, sat, target))
            ref_ipps = {
                r: ipp_by_key[(ep, sat, r)]
                for r in avail_refs
                if (ep, sat, r) in ipp_by_key
            }
            res_map: dict[str, float] = {}
            for m in ("zero", *candidate_models):
                pred = predict_spatial(
                    model_name=m,
                    epoch_iso=ep,
                    satellite_id=sat,
                    target_station=target,
                    target_xyz=coords[target],
                    references=ref_triples,
                    observed_m=obs_t,
                    target_ipp=tgt_ipp,
                    reference_ipps=ref_ipps,
                    inside_override=(stratum == "interior"),
                )
                if pred.residual_m is None:
                    break
                res_map[m] = float(pred.residual_m)
            if len(res_map) == 1 + len(candidate_models):
                for m, rv in res_map.items():
                    buckets[stratum][m].setdefault(ep, []).append(rv)
                    buckets["overall"][m].setdefault(ep, []).append(rv)

    out: dict[str, Any] = {}
    for stratum in ("overall", "interior", "perimeter"):
        out[stratum] = {
            m: _block_bootstrap_gain_ci(buckets[stratum]["zero"], buckets[stratum][m])
            for m in candidate_models
        }
    return out


def _stratified_spatial_summary(
    loocv: dict[str, Any],
    *,
    coastal_set: frozenset[str],
    interior_set: frozenset[str],
) -> dict[str, Any]:
    """Summarize LOOCV across overall, interior, perimeter, coastal, and inland strata."""
    folds_by_tgt = {f["target"]: f for f in loocv["folds"]}
    out: dict[str, Any] = {}
    for split in ("overall", "interior_interpolated", "perimeter_extrapolated"):
        s = loocv[split]
        out[split] = {
            "keys": s["comparison_keys"],
            "best": s["best_model"],
            "rmse_m": {
                m: round(s["models"][m]["rmse_m"], 4)
                if s["models"][m]["rmse_m"] is not None
                else None
                for m in s["models"]
            },
            "gain_vs_zero_pct": s["rmse_reduction_vs_zero_pct"],
        }

    def _agg_folds(targets: list[str]) -> dict[str, Any]:
        sub = [
            folds_by_tgt[t]
            for t in targets
            if t in folds_by_tgt and folds_by_tgt[t]["comparison_keys"] > 0
        ]
        if not sub:
            return {"targets": [], "keys": 0}
        total_keys = sum(f["comparison_keys"] for f in sub)
        rmse_by_m: dict[str, float | None] = {}
        for m in loocv["models_evaluated"]:
            sq_sum = 0.0
            k_sum = 0
            for f in sub:
                r = f["models"][m]["rmse_m"]
                k = f["comparison_keys"]
                if r is not None and k > 0:
                    sq_sum += (r * r) * k
                    k_sum += k
            rmse_by_m[m] = round(math.sqrt(sq_sum / k_sum), 4) if k_sum > 0 else None
        z_r = rmse_by_m.get("zero")
        best = min(
            (m for m, r in rmse_by_m.items() if r is not None),
            key=lambda m: float(rmse_by_m[m]),  # type: ignore[arg-type]
        )
        gain = {
            m: round((1.0 - r / z_r) * 100.0, 2) if (z_r and r is not None and z_r > 0) else None
            for m, r in rmse_by_m.items()
        }
        return {
            "targets": [f["target"] for f in sub],
            "keys": total_keys,
            "best": best,
            "rmse_m": rmse_by_m,
            "gain_vs_zero_pct": gain,
        }

    all_tgts = sorted(folds_by_tgt)
    out["coastal_folds"] = _agg_folds([t for t in all_tgts if t in coastal_set])
    out["inland_folds"] = _agg_folds([t for t in all_tgts if t not in coastal_set])
    out["interior_targets"] = sorted(t for t in all_tgts if t in interior_set)
    out["per_fold_best"] = {
        t: {
            "geometry": folds_by_tgt[t]["geometry_class"],
            "nearest_km": folds_by_tgt[t]["nearest_ref_km"],
            "best": folds_by_tgt[t]["best_model"],
            "zero_rmse": round(folds_by_tgt[t]["models"]["zero"]["rmse_m"], 4)
            if folds_by_tgt[t]["models"]["zero"]["rmse_m"] is not None
            else None,
            "best_rmse": round(
                folds_by_tgt[t]["models"][folds_by_tgt[t]["best_model"]]["rmse_m"], 4
            )
            if folds_by_tgt[t]["best_model"]
            else None,
            "gain_vs_zero_pct": folds_by_tgt[t]["rmse_reduction_vs_zero_pct"],
        }
        for t in all_tgts
    }
    return out


def _eval_causal_day(
    *,
    label: str,
    date_iso: str,
    doy: int,
    datasets: dict[str, StationDataset],
    coords: dict[str, tuple[float, float, float]],
    nav_path: Path,
    sat_dsb_c1_p2_ns: dict[str, float],
    sat_dsb_p1_p2_ns: dict[str, float],
    ionex: IonexGrid,
    datum_station: str,
    stride: int,
    coastal_set: frozenset[str],
    interior_set: frozenset[str],
) -> dict[str, Any]:
    used_stations = sorted(datasets)
    nav_records = parse_gps_nav_auto(nav_path)
    if not nav_records:
        raise RuntimeError(f"Fail-closed: parsed 0 GPS ephemerides from {nav_path}")
    nav_hash = sha256_file(nav_path)
    all_epochs = sorted(set.union(*(set(ds.epochs) for ds in datasets.values())))
    all_gps_sats = sorted(
        {
            sat
            for ds in datasets.values()
            for ep_map in ds.data.values()
            for sat in ep_map
            if sat.startswith("G")
        }
    )
    topo_rows, _ = geometry_table(
        epochs=all_epochs,
        satellites=all_gps_sats,
        station_coords=coords,
        nav_records=nav_records,
        nav_hash=nav_hash,
    )
    topo_by_st: dict[str, dict[str, dict[str, tuple[float, float]]]] = {
        st: {} for st in used_stations
    }
    topo_flat_by_st: dict[str, dict[tuple[str, str], tuple[float, float]]] = {
        st: {} for st in used_stations
    }
    for row in topo_rows:
        topo_by_st[row.station_id].setdefault(row.epoch_iso, {})[row.satellite_id] = (
            row.elevation_deg,
            row.azimuth_deg,
        )
        topo_flat_by_st[row.station_id][(row.epoch_iso, row.satellite_id)] = (
            row.elevation_deg,
            row.azimuth_deg,
        )

    # 1. Offline Phase 6 reference baseline (with B-04 verified coordinates)
    offline_by_st: dict[str, list[IonosphericPointEstimate]] = {}
    ipp_by_key: dict[tuple[str, str, str], tuple[float, float]] = {}
    for st in used_stations:
        ests, _ = estimate_station_ionosphere(
            datasets[st],
            coords[st],
            topo_flat_by_st[st],
            min_elevation_deg=15.0,
            gf_slip_threshold_m=0.35 if stride > 1 else 0.25,
        )
        offline_by_st[st] = ests
        for e in ests:
            ipp_by_key[(e.epoch_iso, e.satellite_id, st)] = (e.ipp_lat_deg, e.ipp_lon_deg)
    off_pair_arc, _ = common_arc_sd_l1_iono(offline_by_st, datum_station)
    off_night, _ = nighttime_leveled_sd_l1_iono(offline_by_st, datum_station)

    # 2. Strictly Causal Epoch-by-Epoch Filter + Network Differential Tracker
    step_s = 30.0 * stride
    filters = {
        st: CausalIonoFilter(
            station_id=st,
            station_ecef_m=coords[st],
            nominal_step_s=step_s,
            min_elevation_deg=15.0,
            gf_slip_threshold_m=0.35 if stride > 1 else 0.25,
            sat_dsb_c1_p2_ns=sat_dsb_c1_p2_ns,
            sat_dsb_p1_p2_ns=sat_dsb_p1_p2_ns,
            ionex_grid=ionex,
        )
        for st in used_stations
    }
    net_tracker = CausalNetworkDiffIonoTracker(datum_station=datum_station, min_pair_epochs=3)

    causal_leveled_sd: dict[tuple[str, str, str], float] = {}
    causal_pair_arc_sd: dict[tuple[str, str, str], float] = {}
    causal_ests_by_st: dict[str, list[CausalIonoEstimate]] = {st: [] for st in used_stations}
    gim_resids_by_st: dict[str, list[float]] = {st: [] for st in used_stations}
    uncal_vs_gim_by_st: dict[str, list[float]] = {st: [] for st in used_stations}
    roti_stats: dict[str, list[float]] = {st: [] for st in used_stations}
    roti_quiet_stats: dict[str, list[float]] = {st: [] for st in used_stations}
    roti_dist_stats: dict[str, list[float]] = {st: [] for st in used_stations}

    for ep in all_epochs:
        hr = _epoch_hour_utc(ep)
        ep_ests: dict[str, list[CausalIonoEstimate]] = {}
        for st in used_stations:
            obs_map = datasets[st].data.get(ep, {})
            t_map = topo_by_st[st].get(ep, {})
            c_ests = filters[st].process_epoch(ep, obs_map, t_map)
            ep_ests[st] = c_ests
            causal_ests_by_st[st].extend(c_ests)
            for ce in c_ests:
                if ce.roti_tecu_per_min is not None:
                    roti_stats[st].append(ce.roti_tecu_per_min)
                    if 6 <= hr < 12:
                        roti_quiet_stats[st].append(ce.roti_tecu_per_min)
                    elif 18 <= hr <= 23:
                        roti_dist_stats[st].append(ce.roti_tecu_per_min)
                v_gim, _ = ionex.interpolate_vtec(ce.ipp_lat_deg, ce.ipp_lon_deg, ep)
                if v_gim is not None:
                    uncal_vs_gim_by_st[st].append((ce.causal_raw_stec_tecu / ce.slm_mf) - v_gim)
                    if ce.causal_calibrated_vtec_tecu is not None:
                        gim_resids_by_st[st].append(ce.causal_calibrated_vtec_tecu - v_gim)
        sd_l, sd_p = net_tracker.process_epoch(ep, ep_ests)
        causal_leveled_sd.update(sd_l)
        causal_pair_arc_sd.update(sd_p)

    # 3. Quantify Causal vs Offline Performance Gap
    common_pa_keys = sorted(set(causal_pair_arc_sd) & set(off_pair_arc))
    pa_diffs_all: list[float] = []
    pa_diffs_early: list[float] = []
    pa_diffs_steady: list[float] = []
    est_lookup = {
        (e.epoch_iso, e.satellite_id, e.station_id): e
        for st, lst in causal_ests_by_st.items()
        for e in lst
    }
    for k in common_pa_keys:
        if k[2] == datum_station:
            continue
        diff = causal_pair_arc_sd[k] - off_pair_arc[k]
        pa_diffs_all.append(diff)
        e_obj = est_lookup.get(k)
        if e_obj is not None and e_obj.arc_epoch_count <= 15:
            pa_diffs_early.append(diff)
        else:
            pa_diffs_steady.append(diff)

    common_lev_keys = sorted(set(causal_leveled_sd) & set(off_night))
    lev_diffs = [
        causal_leveled_sd[k] - off_night[k] for k in common_lev_keys if k[2] != datum_station
    ]

    # 4. Stratified LOOCV: Offline baseline vs Causal (pair-arc & calibrated leveled)
    loocv_off_pa = run_stratified_loocv(
        coords=coords,
        observed=off_pair_arc,
        models=IONO_MODELS,
        ipp_by_key=ipp_by_key,
        min_refs=3,
        datum_station=datum_station,
        reanchor_per_fold=True,
    )
    loocv_causal_pa = run_stratified_loocv(
        coords=coords,
        observed=causal_pair_arc_sd,
        models=IONO_MODELS,
        ipp_by_key=ipp_by_key,
        min_refs=3,
        datum_station=datum_station,
        reanchor_per_fold=True,
    )
    loocv_causal_lev = run_stratified_loocv(
        coords=coords,
        observed=causal_leveled_sd,
        models=IONO_MODELS,
        ipp_by_key=ipp_by_key,
        min_refs=3,
        datum_station=datum_station,
        reanchor_per_fold=True,
    )

    # Quiet (06-12 UTC) vs Disturbed (18-24 UTC) stratification on causal pair-arc
    pa_quiet = {
        k: v for k, v in causal_pair_arc_sd.items() if 6 <= _epoch_hour_utc(k[0]) < 12
    }
    pa_disturbed = {
        k: v for k, v in causal_pair_arc_sd.items() if 18 <= _epoch_hour_utc(k[0]) <= 23
    }
    loocv_quiet = run_stratified_loocv(
        coords=coords,
        observed=pa_quiet,
        models=IONO_MODELS,
        ipp_by_key=ipp_by_key,
        min_refs=3,
        datum_station=datum_station,
        reanchor_per_fold=True,
    )
    loocv_disturbed = run_stratified_loocv(
        coords=coords,
        observed=pa_disturbed,
        models=IONO_MODELS,
        ipp_by_key=ipp_by_key,
        min_refs=3,
        datum_station=datum_station,
        reanchor_per_fold=True,
    )

    # Paired epoch-block bootstrap 95% CIs for causal pair-arc & causal leveled
    bootstrap_causal_pa = _compute_loocv_bootstrap_cis(
        coords=coords,
        observed=causal_pair_arc_sd,
        ipp_by_key=ipp_by_key,
        interior_set=interior_set,
    )
    bootstrap_causal_lev = _compute_loocv_bootstrap_cis(
        coords=coords,
        observed=causal_leveled_sd,
        ipp_by_key=ipp_by_key,
        interior_set=interior_set,
    )

    # Sparse-geometry (4-station) comparison if >= 6 stations available
    sparse_summary = None
    if all(st in datasets for st in SPARSE_2011_SUBSET):
        sp_coords = {st: coords[st] for st in SPARSE_2011_SUBSET}
        sp_obs = {k: v for k, v in causal_pair_arc_sd.items() if k[2] in sp_coords}
        loocv_sparse = run_stratified_loocv(
            coords=sp_coords,
            observed=sp_obs,
            models=IONO_MODELS,
            ipp_by_key=ipp_by_key,
            min_refs=3,
            datum_station="OSGF",
            reanchor_per_fold=True,
        )
        sparse_summary = _stratified_spatial_summary(
            loocv_sparse, coastal_set=coastal_set, interior_set=interior_set
        )

    # Station-level DCB & GIM validation + ROTI disturbance summary
    station_iono_cal: dict[str, Any] = {}
    for st in used_stations:
        last_rx = next(
            (
                e.rx_dcb_est_tecu
                for e in reversed(causal_ests_by_st[st])
                if e.rx_dcb_est_tecu is not None
            ),
            None,
        )
        roti_vals = roti_stats[st]
        q_vals = roti_quiet_stats[st]
        d_vals = roti_dist_stats[st]
        station_iono_cal[st] = {
            "samples": len(causal_ests_by_st[st]),
            "slip_counts": dict(filters[st].slip_counts),
            "final_causal_rx_dcb_vs_gim_tecu": round(last_rx, 3) if last_rx is not None else None,
            "uncalibrated_vtec_vs_gim_rmse_tecu": (
                round(r, 3) if (r := _rmse(uncal_vs_gim_by_st[st])) is not None else None
            ),
            "calibrated_vtec_vs_gim_rmse_tecu": (
                round(r, 3) if (r := _rmse(gim_resids_by_st[st])) is not None else None
            ),
            "calibrated_vtec_vs_gim_bias_tecu": (
                round(statistics.fmean(gim_resids_by_st[st]), 3)
                if gim_resids_by_st[st]
                else None
            ),
            "roti_mean_tecu_min": (
                round(statistics.fmean(roti_vals), 4) if roti_vals else None
            ),
            "roti_quiet_06_12_mean": (
                round(statistics.fmean(q_vals), 4) if q_vals else None
            ),
            "roti_disturbed_18_24_mean": (
                round(statistics.fmean(d_vals), 4) if d_vals else None
            ),
            "roti_max_tecu_min": round(max(roti_vals), 4) if roti_vals else None,
            "roti_gt_05_frac": (
                round(sum(1 for x in roti_vals if x > 0.5) / len(roti_vals), 4)
                if roti_vals
                else None
            ),
            "roti_disturbed_gt_05_frac": (
                round(sum(1 for x in d_vals if x > 0.5) / len(d_vals), 4)
                if d_vals
                else None
            ),
        }

    return {
        "label": label,
        "date_iso": date_iso,
        "doy": doy,
        "stride": stride,
        "stations": used_stations,
        "nav_path": str(nav_path),
        "nav_sha256": nav_hash,
        "sat_dsb_applied_count": len(sat_dsb_c1_p2_ns) or len(sat_dsb_p1_p2_ns),
        "ionex_sha256": ionex.sha256,
        "causal_vs_offline_comparison": {
            "pair_arc_common_samples": len(pa_diffs_all),
            "pair_arc_all_rmse_diff_m": round(_rmse(pa_diffs_all) or 0.0, 4),
            "pair_arc_early_le15ep_rmse_diff_m": round(_rmse(pa_diffs_early) or 0.0, 4),
            "pair_arc_steady_gt15ep_rmse_diff_m": round(_rmse(pa_diffs_steady) or 0.0, 4),
            "leveled_common_samples": len(lev_diffs),
            "leveled_vs_nighttime_rmse_diff_m": round(_rmse(lev_diffs) or 0.0, 4),
        },
        "station_calibration_and_roti": station_iono_cal,
        "spatial_offline_pair_arc": _stratified_spatial_summary(
            loocv_off_pa, coastal_set=coastal_set, interior_set=interior_set
        ),
        "spatial_causal_pair_arc": _stratified_spatial_summary(
            loocv_causal_pa, coastal_set=coastal_set, interior_set=interior_set
        ),
        "spatial_causal_leveled": _stratified_spatial_summary(
            loocv_causal_lev, coastal_set=coastal_set, interior_set=interior_set
        ),
        "spatial_causal_quiet_06_12": _stratified_spatial_summary(
            loocv_quiet, coastal_set=coastal_set, interior_set=interior_set
        ),
        "spatial_causal_disturbed_18_24": _stratified_spatial_summary(
            loocv_disturbed, coastal_set=coastal_set, interior_set=interior_set
        ),
        "bootstrap_ci95_causal_pair_arc": bootstrap_causal_pa,
        "bootstrap_ci95_causal_leveled": bootstrap_causal_lev,
        "spatial_causal_sparse_4st": sparse_summary,
    }


def _run_tropo_validation(
    data_root: Path,
    b04_summary: dict[str, Any],
    coords_24: dict[str, tuple[float, float, float]],
    stride: int,
) -> dict[str, Any]:
    """Evaluate UNB3m + CausalTropoZwdFilter + Spatial LOOCV across 50 2011 + 4 2024 ZTD runs."""
    b04_runs = data_root / "processed/b04-coordinate-verification/runs/igs"
    windows_meta = [
        ("2011_MAR", 79, "2011-03-20", "march_2011_igs05"),
        ("2011_MAR", 80, "2011-03-21", "march_2011_igs05"),
        ("2011_DEC", 339, "2011-12-05", "december_2011_igs08"),
        ("2011_DEC", 340, "2011-12-06", "december_2011_igs08"),
        ("2011_DEC", 341, "2011-12-07", "december_2011_igs08"),
        ("2011_DEC", 342, "2011-12-08", "december_2011_igs08"),
    ]

    window_summaries: dict[str, Any] = {}
    coastal_zwd_res: list[float] = []
    inland_zwd_res: list[float] = []
    causal_1step_res: list[float] = []
    unb3m_static_res: list[float] = []
    spatial_zwd_days: dict[str, Any] = {}

    def _eval_day_ztd(
        win_lbl: str,
        doy: int,
        date_iso: str,
        pride_by_st: dict[str, list[PrideZtdEpoch]],
        coords: dict[str, tuple[float, float, float]],
        run_spatial: bool,
    ) -> dict[str, Any]:
        eval_res = evaluate_tropo_against_pride(pride_by_st, coords, doy=doy)
        causal_by_st: dict[str, float] = {}
        for st, recs in sorted(pride_by_st.items()):
            flt = CausalTropoZwdFilter(station_id=st, station_ecef_m=coords[st])
            u = unb3m_zenith_delays(coords[st], doy, station_id=st)
            st_c_res: list[float] = []
            for idx, r in enumerate(recs):
                if idx % stride != 0:
                    continue
                pred = flt.predict_at(r.epoch_iso, doy=doy)
                if idx > 0:
                    err_c = pred.causal_zwd_m - r.zwd_total_m
                    err_u = u.zwd_m - r.zwd_total_m
                    st_c_res.append(err_c)
                    causal_1step_res.append(err_c)
                    unb3m_static_res.append(err_u)
                    if st in COASTAL_STATIONS:
                        coastal_zwd_res.append(err_u)
                    else:
                        inland_zwd_res.append(err_u)
                flt.update(r.epoch_iso, doy=doy, observed_zwd_m=r.zwd_total_m)
            causal_by_st[st] = round(_rmse(st_c_res) or 0.0, 5)

        day_payload: dict[str, Any] = {
            "window": win_lbl,
            "date_iso": date_iso,
            "stations_count": len(pride_by_st),
            "unb3m_zhd_rmse_m": eval_res["aggregate"]["unb3m_climatology_zhd"]["rmse_m"],
            "unb3m_zwd_rmse_m": eval_res["aggregate"]["unb3m_climatology_zwd"]["rmse_m"],
            "unb3m_ztd_rmse_m": eval_res["aggregate"]["unb3m_climatology_ztd"]["rmse_m"],
            "legacy_ztd_rmse_m": eval_res["aggregate"]["legacy_012m_prior_ztd"]["rmse_m"],
            "causal_zwd_1step_rmse_by_station_m": causal_by_st,
            "per_station": eval_res["per_station"],
        }
        if run_spatial:
            zwd_obs: dict[tuple[str, str, str], float] = {}
            for sid, recs in pride_by_st.items():
                for idx, rec in enumerate(recs):
                    if idx % (stride * 2) == 0:
                        zwd_obs[(rec.epoch_iso, "ZENITH", sid)] = rec.zwd_total_m
            loocv_zwd = run_stratified_loocv(
                coords=coords,
                observed=zwd_obs,
                models=SPATIAL_MODELS,
                min_refs=3,
                reanchor_per_fold=True,
            )
            spatial_zwd_days[date_iso] = _stratified_spatial_summary(
                loocv_zwd,
                coastal_set=COASTAL_STATIONS,
                interior_set=INTERIOR_2011_STATIONS if win_lbl.startswith("2011") else frozenset(),
            )
        return day_payload

    for win_lbl, doy, date_iso, coord_key in windows_meta:
        doy_s = f"{doy:03d}"
        coords: dict[str, tuple[float, float, float]] = {}
        pride_by_st: dict[str, list[PrideZtdEpoch]] = {}
        for st, sinfo in b04_summary["stations"].items():
            cblock = sinfo.get(coord_key)
            if not cblock:
                continue
            ztd_file = b04_runs / doy_s / st / "2011" / doy_s / f"ztd_2011{doy_s}_{st.lower()}"
            if not ztd_file.is_file():
                continue
            recs, _ = parse_pride_ztd(ztd_file, station_id=st)
            if recs:
                raw_c = cblock["ecef_xyz_m"]
                coords[st] = (float(raw_c[0]), float(raw_c[1]), float(raw_c[2]))
                pride_by_st[st] = recs
        window_summaries[date_iso] = _eval_day_ztd(
            win_lbl, doy, date_iso, pride_by_st, coords, run_spatial=(doy in (79, 339))
        )

    # 2024-01-26 (4 verified IGS20 stations)
    ztd_2024_paths = {
        "ABFC00NGA": data_root / "working/pride-test/2024/026/ztd_2024026",
        "EKAK00NGA": data_root / "working/pride/run-EKAK00NGA/2024/026/ztd_2024026_ekak",
        "MGBO00NGA": data_root / "working/pride/run-MGBO00NGA/2024/026/ztd_2024026_mgbo",
        "PHRI00NGA": data_root / "working/pride/run-PHRI00NGA/2024/026/ztd_2024026_phri",
    }
    pride_24: dict[str, list[PrideZtdEpoch]] = {}
    for sid, zp in ztd_2024_paths.items():
        if zp.is_file() and sid in coords_24:
            recs, _ = parse_pride_ztd(zp, station_id=sid)
            if recs:
                pride_24[sid] = recs
    if pride_24:
        window_summaries["2024-01-26"] = _eval_day_ztd(
            "2024_JAN", 26, "2024-01-26", pride_24, coords_24, run_spatial=True
        )

    return {
        "total_station_days": sum(v["stations_count"] for v in window_summaries.values()),
        "total_2011_station_days": sum(
            v["stations_count"]
            for k, v in window_summaries.items()
            if k.startswith("2011")
        ),
        "total_2024_station_days": sum(
            v["stations_count"]
            for k, v in window_summaries.items()
            if k.startswith("2024")
        ),
        "windows": window_summaries,
        "coastal_unb3m_zwd_rmse_m": round(_rmse(coastal_zwd_res) or 0.0, 4),
        "inland_unb3m_zwd_rmse_m": round(_rmse(inland_zwd_res) or 0.0, 4),
        "unb3m_zwd_overall_rmse_m": round(_rmse(unb3m_static_res) or 0.0, 4),
        "causal_zwd_1step_overall_rmse_m": round(_rmse(causal_1step_res) or 0.0, 5),
        "spatial_pride_zwd_loocv": spatial_zwd_days,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run B-05 atmospheric model validation suite")
    parser.add_argument(
        "--data-root",
        type=Path,
        default=Path(os.environ.get("NLGCP_DATA_ROOT", "/home/excellence/nlgcp-data")),
    )
    parser.add_argument(
        "--stride",
        type=int,
        default=4,
        help="Epoch stride (default=4 -> 120s, 720 ep/day)",
    )
    args = parser.parse_args()

    data_root = args.data_root
    out_dir = data_root / "processed/atmospheric-model/b05"
    out_dir.mkdir(parents=True, exist_ok=True)

    b04_summary = json.loads(
        (data_root / "processed/b04-coordinate-verification/b04_analysis_summary.json").read_text(
            encoding="utf-8"
        )
    )
    zip_2011 = data_root / "incoming/southern-nignet/NIGNET2011.zip"
    audit_csv = (
        data_root / "validation/southern-nignet/run-20261030T125136Z/rinex_header_audit.csv"
    )
    nav_2011_dir = (
        data_root
        / "validation/southern-nignet/coordinate-navigation-recovery"
        / "run-20261030T132927Z/navigation-products"
    )

    def _load_2011_datasets(
        date_iso: str, stations: list[str]
    ) -> dict[str, StationDataset]:
        members: dict[str, str] = {}
        with audit_csv.open(encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                if row["observation_date_from_filename"] == date_iso:
                    st4 = row["canonical_station_id"][:4]
                    if st4 in stations:
                        members[st4] = row["relative_path"]
        return {
            st: read_rinex2_from_zip(zip_2011, members[st], st, stride=args.stride)
            for st in sorted(stations)
            if st in members
        }

    # --- 1. 2011-03-20 & 2011-03-21 (Equinox disturbed, 9 B-04 verified IGS05 stations) ---
    mar_stations = [
        st
        for st, info in sorted(b04_summary["stations"].items())
        if info["truth_acceptance_march_igs05"]["truth_ready"]
    ]
    mar_coords: dict[str, tuple[float, float, float]] = {
        st: (
            float(b04_summary["stations"][st]["march_2011_igs05"]["ecef_xyz_m"][0]),
            float(b04_summary["stations"][st]["march_2011_igs05"]["ecef_xyz_m"][1]),
            float(b04_summary["stations"][st]["march_2011_igs05"]["ecef_xyz_m"][2]),
        )
        for st in mar_stations
    }
    p1p2_mar = parse_code_monthly_dcb(
        data_root / "external-products/igs/2011/biases/P1P21103.DCB.Z", "P1P2"
    )
    p1c1_mar = parse_code_monthly_dcb(
        data_root / "external-products/igs/2011/biases/P1C11103.DCB.Z", "P1C1"
    )
    c1p2_mar = combine_code_p1p2_p1c1_to_c1p2(p1p2_mar, p1c1_mar)
    ionex_079 = parse_ionex(data_root / "external-products/igs/2011/ionosphere/CODG0790.11I.Z")
    ionex_080 = parse_ionex(data_root / "external-products/igs/2011/ionosphere/CODG0800.11I.Z")

    res_mar079 = _eval_causal_day(
        label="2011-03-20_equinox_igs05_9st",
        date_iso="2011-03-20",
        doy=79,
        datasets=_load_2011_datasets("2011-03-20", mar_stations),
        coords=mar_coords,
        nav_path=nav_2011_dir / "brdc0790.11n.Z",
        sat_dsb_c1_p2_ns=c1p2_mar,
        sat_dsb_p1_p2_ns=p1p2_mar.sat_bias_ns,
        ionex=ionex_079,
        datum_station="OSGF",
        stride=args.stride,
        coastal_set=COASTAL_STATIONS,
        interior_set=INTERIOR_2011_STATIONS,
    )
    res_mar080 = _eval_causal_day(
        label="2011-03-21_equinox_igs05_9st",
        date_iso="2011-03-21",
        doy=80,
        datasets=_load_2011_datasets("2011-03-21", mar_stations),
        coords=mar_coords,
        nav_path=nav_2011_dir / "brdc0800.11n.Z",
        sat_dsb_c1_p2_ns=c1p2_mar,
        sat_dsb_p1_p2_ns=p1p2_mar.sat_bias_ns,
        ionex=ionex_080,
        datum_station="OSGF",
        stride=args.stride,
        coastal_set=COASTAL_STATIONS,
        interior_set=INTERIOR_2011_STATIONS,
    )

    # --- 2. 2011-12-05 (Harmattan quiet/dry, 8 B-04 verified IGS08 stations; RUST excluded) ---
    dec_stations = [
        st
        for st, info in sorted(b04_summary["stations"].items())
        if info["truth_acceptance_december_igs08"]["truth_ready"]
    ]
    dec_coords: dict[str, tuple[float, float, float]] = {
        st: (
            float(b04_summary["stations"][st]["december_2011_igs08"]["ecef_xyz_m"][0]),
            float(b04_summary["stations"][st]["december_2011_igs08"]["ecef_xyz_m"][1]),
            float(b04_summary["stations"][st]["december_2011_igs08"]["ecef_xyz_m"][2]),
        )
        for st in dec_stations
    }
    p1p2_dec = parse_code_monthly_dcb(
        data_root / "external-products/igs/2011/biases/P1P21112.DCB.Z", "P1P2"
    )
    p1c1_dec = parse_code_monthly_dcb(
        data_root / "external-products/igs/2011/biases/P1C11112.DCB.Z", "P1C1"
    )
    c1p2_dec = combine_code_p1p2_p1c1_to_c1p2(p1p2_dec, p1c1_dec)
    ionex_339 = parse_ionex(data_root / "external-products/igs/2011/ionosphere/CODG3390.11I.Z")

    res_dec339 = _eval_causal_day(
        label="2011-12-05_harmattan_igs08_8st",
        date_iso="2011-12-05",
        doy=339,
        datasets=_load_2011_datasets("2011-12-05", dec_stations),
        coords=dec_coords,
        nav_path=nav_2011_dir / "brdc3390.11n.Z",
        sat_dsb_c1_p2_ns=c1p2_dec,
        sat_dsb_p1_p2_ns=p1p2_dec.sat_bias_ns,
        ionex=ionex_339,
        datum_station="OSGF",
        stride=args.stride,
        coastal_set=COASTAL_STATIONS,
        interior_set=INTERIOR_2011_STATIONS,
    )

    # --- 3. 2024-01-26 (Verified IGS20 4-station sparse network) ---
    dc24 = json.loads((data_root / "processed/single-base/derived-coordinates.json").read_text())
    p5_adm_path = (
        data_root / "processed/network-rtk/experiments/net-2024d026-phri-rover/admission.json"
    )
    p5_adm = json.loads(p5_adm_path.read_text())
    coords_24: dict[str, tuple[float, float, float]] = {}
    ds_24: dict[str, StationDataset] = {}
    for s in p5_adm["admitted"]:
        sid = s["station_id"]
        if dc24["stations"].get(sid, {}).get("scientifically_valid") is not True:
            continue
        e = dc24["stations"][sid]["ecef"]
        coords_24[sid] = (float(e["x_m"]), float(e["y_m"]), float(e["z_m"]))
        ds_24[sid] = read_rinex2_observations(Path(s["observation_path"]), sid, stride=args.stride)
    nav_24 = (
        data_root
        / "processed/rover-benchmark/b02/inputs/2024_01_26/BRDC00IGS_R_20240260000_01D_MN.rnx"
    )
    if not nav_24.is_file():
        nav_24 = data_root / "external-products/brdc/2024/BRDC00IGS_R_20240260000_01D_MN.rnx.gz"
    osb_24 = parse_sinex_osb_pair_diff(
        data_root / "external-products/igs/2024/biases/COD0OPSFIN_20240260000_01D_01D_OSB.BIA.gz",
        obs1="C1C",
        obs2="C2W",
    )
    dsb_p1p2_24 = parse_sinex_dsb(
        data_root / "external-products/igs/2024/biases/CAS0OPSRAP_20240260000_01D_01D_DCB.BIA.gz",
        obs1="C1W",
        obs2="C2W",
    )
    ionex_24 = parse_ionex(
        data_root
        / "external-products/igs/2024/ionosphere/COD0OPSFIN_20240260000_01D_01H_GIM.INX.gz"
    )
    res_2024 = _eval_causal_day(
        label="2024-01-26_igs20_4st_sparse",
        date_iso="2024-01-26",
        doy=26,
        datasets=ds_24,
        coords=coords_24,
        nav_path=nav_24,
        sat_dsb_c1_p2_ns=osb_24.sat_bias_ns,
        sat_dsb_p1_p2_ns=dsb_p1p2_24.sat_bias_ns,
        ionex=ionex_24,
        datum_station="ABFC00NGA",
        stride=args.stride,
        coastal_set=COASTAL_STATIONS,
        interior_set=frozenset(),
    )

    # --- 4. Troposphere Validation across all 50 B-04 2011 + 4 2024 PRIDE ZTD runs ---
    tropo_res = _run_tropo_validation(data_root, b04_summary, coords_24, stride=args.stride)

    summary = {
        "schema_version": "nlgcp.b05.atmospheric_validation.v1",
        "generated_utc": utc_now_iso(),
        "stride": args.stride,
        "datasets": {
            "2011-03-20": res_mar079,
            "2011-03-21": res_mar080,
            "2011-12-05": res_dec339,
            "2024-01-26": res_2024,
        },
        "troposphere_54_station_days": tropo_res,
    }
    out_path = out_dir / "b05_validation_summary.json"
    _write_json(out_path, summary)
    print(f"Wrote B-05 validation summary: {out_path}")
    for key, d in summary["datasets"].items():
        cmp = d["causal_vs_offline_comparison"]
        print(
            f"\n[{key}] stations={len(d['stations'])} "
            f"causal_vs_off_pa_rmse={cmp['pair_arc_all_rmse_diff_m']}m "
            f"(early={cmp['pair_arc_early_le15ep_rmse_diff_m']}m, "
            f"steady={cmp['pair_arc_steady_gt15ep_rmse_diff_m']}m)"
        )
        print("  offline_pa interior:", d["spatial_offline_pair_arc"]["interior_interpolated"])
        print("  causal_pa  interior:", d["spatial_causal_pair_arc"]["interior_interpolated"])
        print("  causal_pa perimeter:", d["spatial_causal_pair_arc"]["perimeter_extrapolated"])
        print("  causal_lev interior:", d["spatial_causal_leveled"]["interior_interpolated"])
        print("  causal_pa  quiet   :", d["spatial_causal_quiet_06_12"]["overall"])
        print("  causal_pa  disturb :", d["spatial_causal_disturbed_18_24"]["overall"])
        print("  bootstrap CI95 pa  :", d["bootstrap_ci95_causal_pair_arc"])
    print(
        f"\n[TROPO {tropo_res['total_station_days']} station-days] "
        f"UNB3m ZWD RMSE={tropo_res['unb3m_zwd_overall_rmse_m']}m "
        f"(coastal={tropo_res['coastal_unb3m_zwd_rmse_m']}m, "
        f"inland={tropo_res['inland_unb3m_zwd_rmse_m']}m) | "
        f"Causal 1-step ZWD RMSE={tropo_res['causal_zwd_1step_overall_rmse_m']}m"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
