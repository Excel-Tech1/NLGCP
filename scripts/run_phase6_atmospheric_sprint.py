#!/usr/bin/env python3
"""Reproducible Phase 6 Atmospheric & Spatial Modelling Sprint Experiment Runner.

Executes Experiments 1–4 against immutable external GNSS observation archives
under ``NLGCP_DATA_ROOT`` without modifying raw data and writes derived evidence
outside Git under ``${NLGCP_DATA_ROOT}/processed/atmospheric-model/sprint-phase67/``.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from pathlib import Path
from typing import Any

from nlgcp_atmospheric_model.dataset_audit import (
    build_2011_selection_manifest,
    load_osgof_provisional_coords,
)
from nlgcp_atmospheric_model.ionosphere import pair_sd_proxies
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
from nlgcp_atmospheric_model.satellite_geometry import (
    geometry_table,
    parse_gps_nav_auto,
)
from nlgcp_atmospheric_model.spatial_estimation import (
    SPATIAL_MODELS,
    run_stratified_loocv,
)
from nlgcp_atmospheric_model.troposphere_estimation import (
    PrideZtdEpoch,
    evaluate_tropo_against_pride,
    parse_pride_ztd,
    slant_tropo_from_ztd,
    unb3m_zenith_delays,
)

IONO_SPATIAL_MODELS = (*SPATIAL_MODELS, "ipp_idw2")


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )


def _run_2011_day(
    *,
    date_iso: str,
    doy: int,
    stations: tuple[str, ...],
    zip_path: Path,
    header_audit_csv: Path,
    nav_gps_path: Path,
    coords: dict[str, tuple[float, float, float]],
    stride: int,
) -> dict[str, Any]:
    members: dict[str, str] = {}
    with header_audit_csv.open(encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row["observation_date_from_filename"] == date_iso:
                st4 = row["canonical_station_id"][:4]
                if st4 in stations:
                    members[st4] = row["relative_path"]

    datasets: dict[str, StationDataset] = {
        st: read_rinex2_from_zip(zip_path, members[st], st, stride=stride)
        for st in sorted(stations)
        if st in members
    }
    used_stations = sorted(datasets)
    used_coords = {st: coords[st] for st in used_stations}

    nav_records = parse_gps_nav_auto(nav_gps_path)
    nav_hash = sha256_file(nav_gps_path)

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
    topo_rows, _exclusions = geometry_table(
        epochs=all_epochs,
        satellites=all_gps_sats,
        station_coords=used_coords,
        nav_records=nav_records,
        nav_hash=nav_hash,
    )
    topo_by_station: dict[str, dict[tuple[str, str], tuple[float, float]]] = {
        st: {} for st in used_stations
    }
    for topo in topo_rows:
        topo_by_station[topo.station_id][(topo.epoch_iso, topo.satellite_id)] = (
            topo.elevation_deg,
            topo.azimuth_deg,
        )

    iono_by_station: dict[str, list[IonosphericPointEstimate]] = {}
    iono_summaries: dict[str, Any] = {}
    ipp_by_key: dict[tuple[str, str, str], tuple[float, float]] = {}
    roti_summary: dict[str, Any] = {}
    unb3m_summary: dict[str, Any] = {}

    for st in used_stations:
        ests, summ = estimate_station_ionosphere(
            datasets[st],
            used_coords[st],
            topo_by_station[st],
            min_elevation_deg=15.0,
            gf_slip_threshold_m=0.35 if stride > 1 else 0.25,
        )
        iono_by_station[st] = ests
        iono_summaries[st] = summ
        for e in ests:
            ipp_by_key[(e.epoch_iso, e.satellite_id, st)] = (e.ipp_lat_deg, e.ipp_lon_deg)
        rotis = [e.roti_tecu_per_min for e in ests if e.roti_tecu_per_min is not None]
        raw_vtecs = [e.vtec_uncalibrated_tecu for e in ests]
        roti_summary[st] = {
            "roti_samples": len(rotis),
            "roti_mean_tecu_per_min": round(sum(rotis) / len(rotis), 4) if rotis else None,
            "roti_max_tecu_per_min": round(max(rotis), 4) if rotis else None,
            "roti_gt_05_fraction": (
                round(sum(1 for v in rotis if v > 0.5) / len(rotis), 4) if rotis else None
            ),
            "uncalibrated_vtec_min_tecu": round(min(raw_vtecs), 2) if raw_vtecs else None,
            "uncalibrated_vtec_max_tecu": round(max(raw_vtecs), 2) if raw_vtecs else None,
        }
        u = unb3m_zenith_delays(used_coords[st], doy, station_id=st)
        unb3m_summary[st] = {
            "height_m": round(u.height_m, 2),
            "lat_deg": round(u.lat_deg, 4),
            "unb3m_zhd_m": round(u.zhd_m, 4),
            "unb3m_zwd_m": round(u.zwd_m, 4),
            "unb3m_ztd_m": round(u.ztd_m, 4),
        }

    # Datum station for field assembly (reanchor_per_fold=True removes datum dependence in LOOCV)
    datum = "OSGF" if "OSGF" in used_stations else used_stations[0]

    # Method 1: Common-overlap pair-arc differential L1 ionosphere (fixes mismatched-arc median bug)
    obs_common_arc, meta_common_arc = common_arc_sd_l1_iono(iono_by_station, datum)
    loocv_common_arc = run_stratified_loocv(
        coords=used_coords,
        observed=obs_common_arc,
        models=IONO_SPATIAL_MODELS,
        ipp_by_key=ipp_by_key,
        min_refs=3,
        datum_station=datum,
        reanchor_per_fold=True,
    )

    # Method 2: Nighttime receiver-DCB-aligned phase-leveled STEC differential L1 ionosphere
    obs_night, meta_night = nighttime_leveled_sd_l1_iono(iono_by_station, datum)
    loocv_night = run_stratified_loocv(
        coords=used_coords,
        observed=obs_night,
        models=IONO_SPATIAL_MODELS,
        ipp_by_key=ipp_by_key,
        min_refs=3,
        datum_station=datum,
        reanchor_per_fold=True,
    )

    # Method 3: Legacy independent per-station arc-detrended GF SD (for apples-to-apples comparison)
    obs_legacy: dict[tuple[str, str, str], float] = {}
    step_s = 30.0 * stride
    for sat in all_gps_sats:
        for st in used_stations:
            if st == datum:
                for ep in datasets[datum].epochs:
                    if sat in datasets[datum].data.get(ep, {}):
                        obs_legacy[(ep, sat, datum)] = 0.0
                continue
            for sample in pair_sd_proxies(
                datasets[st], datasets[datum], sat, slip_threshold_m=0.5, step_s=step_s
            ):
                obs_legacy[(sample.epoch_iso, sample.satellite_id, st)] = sample.value_m
    loocv_legacy = run_stratified_loocv(
        coords=used_coords,
        observed=obs_legacy,
        models=SPATIAL_MODELS,
        min_refs=3,
        datum_station=datum,
        reanchor_per_fold=True,
    )

    return {
        "date_iso": date_iso,
        "doy": doy,
        "stride": stride,
        "effective_interval_s": 30.0 * stride,
        "stations": used_stations,
        "nav_gps_path": str(nav_gps_path),
        "nav_gps_sha256": nav_hash,
        "coordinate_provenance": "PROVISIONAL_OSGOF_2011_01_01",
        "iono_summaries": iono_summaries,
        "roti_and_vtec_summary": roti_summary,
        "unb3m_tropo_summary": unb3m_summary,
        "spatial_loocv_common_pair_arc_l1": {
            "observable_meta": meta_common_arc,
            **loocv_common_arc,
        },
        "spatial_loocv_nighttime_leveled_stec_l1": {
            "observable_meta": meta_night,
            **loocv_night,
        },
        "spatial_loocv_legacy_independent_arc_detrend": loocv_legacy,
    }


def _run_2024_doy026_benchmark(data_root: Path, *, stride: int) -> dict[str, Any]:
    dc = json.loads((data_root / "processed/single-base/derived-coordinates.json").read_text())
    p5_adm = json.loads(
        (data_root / "processed/network-rtk/experiments/net-2024d026-phri-rover/admission.json")
        .read_text()
    )
    coords: dict[str, tuple[float, float, float]] = {}
    datasets: dict[str, StationDataset] = {}
    nav_path: Path | None = None
    for s in p5_adm["admitted"]:
        sid = s["station_id"]
        if dc["stations"].get(sid, {}).get("scientifically_valid") is not True:
            continue
        e = dc["stations"][sid]["ecef"]
        coords[sid] = (float(e["x_m"]), float(e["y_m"]), float(e["z_m"]))
        datasets[sid] = read_rinex2_observations(
            Path(s["observation_path"]), sid, stride=stride
        )
        if nav_path is None:
            nav_path = data_root / s["navigation_path"]

    assert nav_path is not None
    used_stations = sorted(datasets)
    nav_records = parse_gps_nav_auto(nav_path)
    nav_hash = sha256_file(nav_path)

    # 1. PRIDE PPP-AR ZTD benchmark (all 4 verified stations)
    pride_paths = {
        "ABFC00NGA": data_root / "working/pride-test/2024/026/ztd_2024026",
        "EKAK00NGA": data_root / "working/pride/run-EKAK00NGA/2024/026/ztd_2024026_ekak",
        "MGBO00NGA": data_root / "working/pride/run-MGBO00NGA/2024/026/ztd_2024026_mgbo",
        "PHRI00NGA": data_root / "working/pride/run-PHRI00NGA/2024/026/ztd_2024026_phri",
    }
    pride_by_st: dict[str, list[PrideZtdEpoch]] = {}
    pride_hashes: dict[str, str] = {}
    for sid, p in pride_paths.items():
        if p.is_file():
            recs, digest = parse_pride_ztd(p, station_id=sid)
            pride_by_st[sid] = recs
            pride_hashes[sid] = digest

    tropo_pride_eval = evaluate_tropo_against_pride(pride_by_st, coords, doy=26)

    # 2. PRIDE ZTD spatial LOOCV (zenith wet delay & slant tropospheric delay)
    pride_zwd_obs: dict[tuple[str, str, str], float] = {}
    for sid, recs in pride_by_st.items():
        for idx, rec in enumerate(recs):
            if idx % stride == 0:
                pride_zwd_obs[(rec.epoch_iso, "ZENITH", sid)] = rec.zwd_total_m
    loocv_pride_zwd = run_stratified_loocv(
        coords=coords,
        observed=pride_zwd_obs,
        models=SPATIAL_MODELS,
        min_refs=3,
        reanchor_per_fold=True,
    )

    # 3. 2024 DOY 026 ionospheric estimation + LOOCV (comparing common-arc & nighttime vs legacy)
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
    topo_by_st: dict[str, dict[tuple[str, str], tuple[float, float]]] = {
        st: {} for st in used_stations
    }
    for row in topo_rows:
        topo_by_st[row.station_id][(row.epoch_iso, row.satellite_id)] = (
            row.elevation_deg,
            row.azimuth_deg,
        )

    iono_by_st: dict[str, list[IonosphericPointEstimate]] = {}
    ipp_by_key: dict[tuple[str, str, str], tuple[float, float]] = {}
    for st in used_stations:
        ests, _ = estimate_station_ionosphere(
            datasets[st],
            coords[st],
            topo_by_st[st],
            min_elevation_deg=15.0,
            gf_slip_threshold_m=0.35 if stride > 1 else 0.25,
        )
        iono_by_st[st] = ests
        for e in ests:
            ipp_by_key[(e.epoch_iso, e.satellite_id, st)] = (e.ipp_lat_deg, e.ipp_lon_deg)

    datum = used_stations[0]
    obs_ca, meta_ca = common_arc_sd_l1_iono(iono_by_st, datum)
    loocv_ca = run_stratified_loocv(
        coords=coords,
        observed=obs_ca,
        models=IONO_SPATIAL_MODELS,
        ipp_by_key=ipp_by_key,
        min_refs=3,
        datum_station=datum,
        reanchor_per_fold=True,
    )
    obs_nl, meta_nl = nighttime_leveled_sd_l1_iono(iono_by_st, datum)
    loocv_nl = run_stratified_loocv(
        coords=coords,
        observed=obs_nl,
        models=IONO_SPATIAL_MODELS,
        ipp_by_key=ipp_by_key,
        min_refs=3,
        datum_station=datum,
        reanchor_per_fold=True,
    )

    # Slant tropospheric residual LOOCV (PRIDE ZTD mapped via Niell)
    pride_map = {
        (sid, rec.epoch_iso): rec for sid, recs in pride_by_st.items() for rec in recs
    }
    slant_tropo_obs: dict[tuple[str, str, str], float] = {}
    for row in topo_rows:
        if row.elevation_deg < 15.0:
            continue
        p_rec = pride_map.get((row.station_id, row.epoch_iso))
        if p_rec is None:
            continue
        slant_tropo_obs[(row.epoch_iso, row.satellite_id, row.station_id)] = slant_tropo_from_ztd(
            station_ecef_m=coords[row.station_id],
            elevation_deg=row.elevation_deg,
            doy=26,
            zhd_m=p_rec.zhd_m,
            zwd_m=p_rec.zwd_total_m,
        )
    loocv_slant_tropo = run_stratified_loocv(
        coords=coords,
        observed=slant_tropo_obs,
        models=SPATIAL_MODELS,
        min_refs=3,
        reanchor_per_fold=True,
    )

    return {
        "date_iso": "2024-01-26",
        "doy": 26,
        "stride": stride,
        "stations": used_stations,
        "coordinate_provenance": "VERIFIED_IGS20_PRIDE_PPP_AR",
        "pride_ztd_sha256": pride_hashes,
        "tropo_validation_vs_pride": tropo_pride_eval,
        "pride_zwd_spatial_loocv": loocv_pride_zwd,
        "pride_slant_tropo_spatial_loocv": loocv_slant_tropo,
        "iono_spatial_loocv_common_pair_arc_l1": {"observable_meta": meta_ca, **loocv_ca},
        "iono_spatial_loocv_nighttime_leveled_stec_l1": {"observable_meta": meta_nl, **loocv_nl},
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run reproducible Phase 6 atmospheric & spatial experiments (2011 + 2024)."
    )
    parser.add_argument(
        "--data-root",
        default=os.environ.get("NLGCP_DATA_ROOT", "/home/excellence/nlgcp-data"),
        help="External NLGCP_DATA_ROOT directory (immutable raw inputs).",
    )
    parser.add_argument(
        "--stride",
        type=int,
        default=2,
        help="Epoch stride (1=30s full rate, 2=60s, default=2 for 1440 epochs/day).",
    )
    args = parser.parse_args()

    data_root = Path(args.data_root)
    out_dir = data_root / "processed/atmospheric-model/sprint-phase67"
    out_dir.mkdir(parents=True, exist_ok=True)

    zip_path = data_root / "incoming/southern-nignet/NIGNET2011.zip"
    audit_csv = data_root / "validation/southern-nignet/run-20261030T125136Z/rinex_header_audit.csv"
    rec_base = data_root / "validation/southern-nignet/coordinate-navigation-recovery"
    rec1_dir = rec_base / "run-20261030T132927Z"
    rec2_dir = rec_base / "run-20261123T163056Z"
    osgof_csv = rec1_dir / "coordinate_provenance.csv"
    coords_2024 = data_root / "processed/single-base/derived-coordinates.json"
    nav_2024 = data_root / "external-products/brdc/2024/BRDC00IGS_R_20240260000_01D_MN.rnx.gz"

    # Experiment 1: Reproducible Dataset Audit & Manifest
    manifest = build_2011_selection_manifest(
        zip_path=zip_path,
        header_audit_csv=audit_csv,
        nav_inventories=(
            rec1_dir / "navigation_product_inventory.csv",
            rec2_dir / "navigation_product_inventory.csv",
        ),
        osgof_coords_csv=osgof_csv,
        verified_2024_coords_json=coords_2024,
        verified_2024_nav_path=nav_2024,
    )
    _write_json(out_dir / "dataset_selection_manifest.json", manifest.as_dict())

    osgof_coords = load_osgof_provisional_coords(osgof_csv)

    # Experiments 2-4 on Primary Equinox (2011-03-20, 2011-03-21) & Secondary Solstice (2011-12-05)
    windows_to_run = (
        manifest.primary_windows[0],  # 2011-03-20 (Equinox, 9 full dual-freq, 4 interior)
        manifest.primary_windows[1],  # 2011-03-21 (Equinox repeat, 9 full dual-freq, 4 interior)
        manifest.secondary_windows[0],  # 2011-12-05 (Solstice, 9 full dual-freq, 4 interior)
    )
    results_2011: dict[str, Any] = {}
    for w in windows_to_run:
        assert w.navigation_gps_path is not None
        res = _run_2011_day(
            date_iso=w.date_iso,
            doy=w.doy,
            stations=w.dual_freq_stations,
            zip_path=zip_path,
            header_audit_csv=audit_csv,
            nav_gps_path=Path(w.navigation_gps_path),
            coords=osgof_coords,
            stride=args.stride,
        )
        results_2011[w.date_iso] = res
        _write_json(out_dir / f"phase6_{w.date_iso}.json", res)

    # Experiment 3 & 4D on 2024 DOY 026 (verified IGS20 coords + independent PRIDE PPP-AR ZTD)
    res_2024 = _run_2024_doy026_benchmark(data_root, stride=args.stride)
    _write_json(out_dir / "phase6_2024-01-26_benchmark.json", res_2024)

    # Compact executive summary for quick inspection & reporting
    def compact_loocv(block: dict[str, Any]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for split in ("overall", "interior_interpolated", "perimeter_extrapolated"):
            s = block[split]
            out[split] = {
                "keys": s["comparison_keys"],
                "best": s["best_model"],
                "rmse_m": {
                    m: round(s["models"][m]["rmse_m"], 4)
                    if s["models"][m]["rmse_m"] is not None
                    else None
                    for m in s["models"]
                },
                "p95_abs_m": {
                    m: round(s["models"][m]["p95_abs_m"], 4)
                    if s["models"][m]["p95_abs_m"] is not None
                    else None
                    for m in s["models"]
                },
                "gain_vs_zero_pct": s["rmse_reduction_vs_zero_pct"],
            }
        return out

    summary = {
        "generated_utc": utc_now_iso(),
        "stride": args.stride,
        "output_dir": str(out_dir),
        "manifest_summary": {
            "total_files_audited": manifest.total_files_audited,
            "stations_discovered": list(manifest.stations_discovered),
            "primary_dates": [w.date_iso for w in manifest.primary_windows],
            "secondary_dates": [w.date_iso for w in manifest.secondary_windows],
        },
        "tropo_vs_pride_2024d026": res_2024["tropo_validation_vs_pride"],
        "pride_zwd_loocv_2024d026": compact_loocv(res_2024["pride_zwd_spatial_loocv"]),
        "pride_slant_tropo_loocv_2024d026": compact_loocv(
            res_2024["pride_slant_tropo_spatial_loocv"]
        ),
        "iono_2024d026_common_arc": compact_loocv(
            res_2024["iono_spatial_loocv_common_pair_arc_l1"]
        ),
        "iono_2024d026_nighttime": compact_loocv(
            res_2024["iono_spatial_loocv_nighttime_leveled_stec_l1"]
        ),
        "days_2011": {
            dt: {
                "stations": r["stations"],
                "roti_and_vtec": r["roti_and_vtec_summary"],
                "common_pair_arc_l1": compact_loocv(r["spatial_loocv_common_pair_arc_l1"]),
                "nighttime_leveled_stec_l1": compact_loocv(
                    r["spatial_loocv_nighttime_leveled_stec_l1"]
                ),
                "legacy_independent_detrend": compact_loocv(
                    r["spatial_loocv_legacy_independent_arc_detrend"]
                ),
            }
            for dt, r in results_2011.items()
        },
    }
    _write_json(out_dir / "phase6_sprint_summary.json", summary)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
