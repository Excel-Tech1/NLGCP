"""Orchestrator for B-02 Offline Rover Positioning Benchmark & Failure Suite.

Executes reproducible RTKLIB positioning benchmarks across:
- Dataset B (2024-01-26, DOY 026): Withheld rover PHRI00NGA with VERIFIED
  IGS20 PRIDE PPP-AR coordinate truth (3 references, 105.553 km anchor EKAK).
- Dataset A (2011-03-20, DOY 079): Withheld rover OSGF inside an 8-reference
  convex hull (216.320 km anchor CGGT) with PROVISIONAL OSGoF 2011-01-01
  coordinates explicitly classified LIMITED_PROVISIONAL_TRUTH.

Also runs all 12 required Phase H robustness and failure-mode checks without
ever substituting synthetic inputs for missing authentic observations.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import subprocess
import tempfile
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from nlgcp_atmospheric_model.dataset_audit import (
    convex_hull_2d,
    load_osgof_provisional_coords,
    point_in_convex_hull_2d,
)
from nlgcp_atmospheric_model.ionosphere_estimation import (
    IonosphericPointEstimate,
    common_arc_sd_l1_iono,
    estimate_station_ionosphere,
    nighttime_leveled_sd_l1_iono,
    slm_mapping_and_ipp,
)
from nlgcp_atmospheric_model.observations import (
    StationDataset,
    read_rinex2_from_zip,
    read_rinex2_observations,
)
from nlgcp_atmospheric_model.provenance import sha256_file, utc_now_iso
from nlgcp_atmospheric_model.satellite_geometry import (
    BroadcastEphemeris,
    geometry_table,
    parse_gps_nav_auto,
)
from nlgcp_atmospheric_model.spatial import baseline_length_m, ecef_to_local_enu
from nlgcp_atmospheric_model.troposphere_estimation import parse_pride_ztd
from nlgcp_single_base.coordinates import geodetic_to_ecef
from nlgcp_single_base.solution import (
    EpochResidual,
    SolutionQuality,
    parse_solution_pos,
    ttff_seconds,
)
from nlgcp_vrs.experimental_vrs import (
    VrsOutcome,
    generate_experimental_vrs,
)
from nlgcp_vrs.rtcm_bridge import encode_experimental_vrs_to_rtcm

from nlgcp_rover_benchmark import BENCHMARK_VERSION
from nlgcp_rover_benchmark.metrics import compute_positioning_metrics, paired_comparison
from nlgcp_rover_benchmark.models import (
    BenchmarkFailure,
    BenchmarkOutcome,
    DatasetWindowSpec,
    ProcessingProfile,
    RoverTruthRecord,
    TruthTier,
    VariantRunResult,
    assert_no_rover_leakage,
)
from nlgcp_rover_benchmark.rtklib_pipeline import (
    convert_rtcm_to_rinex,
    execute_rnx2rtkp,
    render_profile_config,
    rtklib_tool_provenance,
)

RELATIVE_PROFILES: tuple[ProcessingProfile, ...] = (
    ProcessingProfile.KINEMATIC_BRDC_SAAS,
    ProcessingProfile.STATIC_BRDC_SAAS,
    ProcessingProfile.KINEMATIC_VRS_IONO_OFF,
    ProcessingProfile.DGPS_CODE_DIFF,
)


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )


def _write_enu_residuals_csv(path: Path, residuals: list[EpochResidual]) -> None:
    """Persist per-epoch ENU errors for offline time-series and outlier inspection."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "epoch_utc",
                "quality_code",
                "quality",
                "satellites",
                "east_m",
                "north_m",
                "up_m",
                "horizontal_error_m",
                "vertical_abs_error_m",
                "error_3d_m",
            ]
        )
        for r in residuals:
            writer.writerow(
                [
                    r.epoch.isoformat().replace("+00:00", "Z"),
                    r.quality_code,
                    str(r.quality),
                    "" if r.satellites is None else r.satellites,
                    f"{r.east_m:.6f}",
                    f"{r.north_m:.6f}",
                    f"{r.up_m:.6f}",
                    f"{r.horizontal_error_m:.6f}",
                    f"{r.vertical_abs_error_m:.6f}",
                    f"{r.error_3d_m:.6f}",
                ]
            )


def _git_software_revision(repo_root: Path | None = None) -> dict[str, Any]:
    """Capture repository revision, branch, and dirty flag for reproducibility."""
    cwd = repo_root or Path(__file__).resolve().parents[4]

    def _run_git(*args: str) -> str | None:
        proc = subprocess.run(
            ["git", *args],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
        return proc.stdout.strip() if proc.returncode == 0 else None

    status_out = _run_git("status", "--porcelain")
    return {
        "git_branch": _run_git("rev-parse", "--abbrev-ref", "HEAD"),
        "git_head": _run_git("rev-parse", "HEAD"),
        "git_dirty": bool(status_out) if status_out is not None else None,
        "benchmark_version": BENCHMARK_VERSION,
    }


def _extract_zip_member(zip_path: Path, member: str, dest: Path) -> Path:
    """Read-only extraction of one member from an immutable ZIP to derived storage."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "r") as zf:
        dest.write_bytes(zf.read(member))
    return dest


def _decompress_unix_z(src_z: Path, dest: Path) -> Path:
    """Decompress a Unix .Z broadcast nav file to derived storage without touching source."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(["gzip", "-dc", str(src_z)], capture_output=True, check=False, timeout=30)
    if proc.returncode != 0 or not proc.stdout:
        raise BenchmarkFailure(f"failed to decompress {src_z}")
    dest.write_bytes(proc.stdout)
    return dest


def _parse_pride_formal_sigmas(pos_path: Path) -> tuple[float, float, float] | None:
    """Extract formal (sigma_x, sigma_y, sigma_z) in metres from a PRIDE pos_* file."""
    if not pos_path.is_file():
        return None
    lines = pos_path.read_text(encoding="utf-8", errors="replace").splitlines()
    for ln in reversed(lines):
        s = ln.strip()
        if not s or s.startswith("*") or "END OF HEADER" in s:
            continue
        parts = s.split()
        if len(parts) >= 12:
            try:
                sx_c = float(parts[5])
                sy_c = float(parts[6])
                sz_c = float(parts[7])
                sig0 = float(parts[11])
                return (
                    round(sig0 * math.sqrt(max(0.0, sx_c)), 6),
                    round(sig0 * math.sqrt(max(0.0, sy_c)), 6),
                    round(sig0 * math.sqrt(max(0.0, sz_c)), 6),
                )
            except ValueError:
                continue
    return None


def _compute_ref_iono_fields(
    *,
    ref_datasets: dict[str, StationDataset],
    ref_coords: dict[str, tuple[float, float, float]],
    target_station: str,
    target_ecef: tuple[float, float, float],
    nav_records: dict[str, list[BroadcastEphemeris]],
    nav_hash: str,
    datum_station: str,
    stride: int,
) -> tuple[
    dict[tuple[str, str, str], float],
    dict[tuple[str, str, str], float],
    dict[tuple[str, str, str], tuple[float, float]],
    dict[tuple[str, str], tuple[float, float]],
]:
    """Compute reference-only common-arc & nighttime iono fields (zero target leakage)."""
    all_epochs = sorted(set.union(*(set(ds.epochs) for ds in ref_datasets.values())))
    all_gps_sats = sorted(
        {
            sat
            for ds in ref_datasets.values()
            for ep_map in ds.data.values()
            for sat in ep_map
            if sat.startswith("G")
        }
    )
    coords_plus_target = {**ref_coords, target_station: target_ecef}
    topo_rows, _ = geometry_table(
        epochs=all_epochs,
        satellites=all_gps_sats,
        station_coords=coords_plus_target,
        nav_records=nav_records,
        nav_hash=nav_hash,
    )
    topo_by_st: dict[str, dict[tuple[str, str], tuple[float, float]]] = {
        st: {} for st in coords_plus_target
    }
    for topo in topo_rows:
        topo_by_st[topo.station_id][(topo.epoch_iso, topo.satellite_id)] = (
            topo.elevation_deg,
            topo.azimuth_deg,
        )

    iono_by_st: dict[str, list[IonosphericPointEstimate]] = {}
    ipp_by_key: dict[tuple[str, str, str], tuple[float, float]] = {}
    for st in sorted(ref_datasets):
        ests, _ = estimate_station_ionosphere(
            ref_datasets[st],
            ref_coords[st],
            topo_by_st[st],
            min_elevation_deg=15.0,
            gf_slip_threshold_m=0.35 if stride > 1 else 0.25,
        )
        iono_by_st[st] = ests
        for e in ests:
            ipp_by_key[(e.epoch_iso, e.satellite_id, st)] = (e.ipp_lat_deg, e.ipp_lon_deg)

    target_ipps: dict[tuple[str, str], tuple[float, float]] = {}
    for (ep, sat), (el_deg, az_deg) in topo_by_st[target_station].items():
        if el_deg >= 15.0:
            _mf, lat_i, lon_i = slm_mapping_and_ipp(target_ecef, el_deg, az_deg)
            target_ipps[(ep, sat)] = (lat_i, lon_i)

    common_field, _ = common_arc_sd_l1_iono(iono_by_st, datum_station)
    night_field, _ = nighttime_leveled_sd_l1_iono(iono_by_st, datum_station)
    return common_field, night_field, ipp_by_key, target_ipps


def _inside_hull(
    target_ecef: tuple[float, float, float], ref_coords: dict[str, tuple[float, float, float]]
) -> bool:
    if len(ref_coords) < 3:
        return False
    pts = list(ref_coords.values())
    centroid = (
        sum(p[0] for p in pts) / len(pts),
        sum(p[1] for p in pts) / len(pts),
        sum(p[2] for p in pts) / len(pts),
    )
    hull = convex_hull_2d([ecef_to_local_enu(p, centroid)[:2] for p in pts])
    return point_in_convex_hull_2d(ecef_to_local_enu(target_ecef, centroid)[:2], hull)


def _derive_spp_gga_position(
    *,
    spec: DatasetWindowSpec,
    out_dir: Path,
) -> tuple[
    tuple[float, float, float],
    dict[str, Any],
]:
    """Run standalone SPP once and derive an authentic GGA-style virtual station coordinate.

    Ensures the VRS generator never receives ``spec.rover_truth.ecef_xyz_m`` (zero truth
    coordinate leakage); instead the VRS is synthesized at the rover's own autonomous
    epoch-0 broadcast SPP position (~1-6 m from true position), matching real NTRIP GGA.
    """
    spp_dir = (
        out_dir / spec.dataset_id / "runs" / "spp_standalone" / str(ProcessingProfile.SPP_SINGLE)
    )
    spp_out, spp_sol, spp_exec = execute_rnx2rtkp(
        profile=ProcessingProfile.SPP_SINGLE,
        rover_obs_path=spec.rover_obs_path,
        base_obs_path=None,
        nav_paths=[spec.nav_path],
        base_ecef_m=None,
        start_time_utc=spec.start_time_utc,
        end_time_utc=spec.end_time_utc,
        run_dir=spp_dir,
    )
    if spp_out is not BenchmarkOutcome.COMPLETED or spp_sol is None or not spp_sol.epochs:
        raise BenchmarkFailure(f"standalone SPP failed for {spec.dataset_id}: {spp_out} {spp_exec}")
    ep0 = spp_sol.epochs[0]
    ecef0 = geodetic_to_ecef(ep0.coordinate)
    vrs_gga_ecef = (round(ecef0.x_m, 4), round(ecef0.y_m, 4), round(ecef0.z_m, 4))
    spp_metrics, _ = compute_positioning_metrics(
        spp_sol.epochs,
        truth_ecef_m=spec.rover_truth.ecef_xyz_m,
        start_time_utc=spec.start_time_utc,
        end_time_utc=spec.end_time_utc,
        sampling_interval_s=spec.sampling_interval_s,
    )
    return vrs_gga_ecef, {
        "outcome": str(spp_out),
        "metrics": spp_metrics,
        "execution": spp_exec,
        "epoch0_gga_ecef_m": list(vrs_gga_ecef),
        "epoch0_offset_from_truth_m": round(
            baseline_length_m(vrs_gga_ecef, spec.rover_truth.ecef_xyz_m), 4
        ),
    }


def _execute_dataset_benchmark(
    *,
    spec: DatasetWindowSpec,
    vrs_virtual_ecef_m: tuple[float, float, float],
    spp_payload: dict[str, Any],
    ref_coords: dict[str, tuple[float, float, float]],
    ref_datasets: dict[str, StationDataset],
    nav_records: dict[str, list[BroadcastEphemeris]],
    iono_common: dict[tuple[str, str, str], float],
    iono_night: dict[tuple[str, str, str], float],
    ipp_by_key: dict[tuple[str, str, str], tuple[float, float]],
    target_ipps: dict[tuple[str, str], tuple[float, float]],
    ref_ztd: dict[tuple[str, str], tuple[float, float]] | None,
    vrs_variants: tuple[tuple[str, str, str, str], ...],
    rtcm_station_id_base: int,
    out_dir: Path,
    require_interior_hull: bool,
    max_epochs: int | None,
) -> dict[str, Any]:
    """Execute Physical Anchor + SPP + all VRS variants identically across all profiles."""
    spec.rover_truth.validate()
    vrs_offset_m = round(baseline_length_m(vrs_virtual_ecef_m, spec.rover_truth.ecef_xyz_m), 4)
    leakage = assert_no_rover_leakage(
        rover_station_id=spec.rover_station_id,
        physical_anchor_id=spec.physical_anchor_id,
        reference_coord_ids=set(ref_coords),
        reference_dataset_ids=set(ref_datasets),
        iono_field_station_ids={k[2] for k in iono_common} | {k[2] for k in iono_night},
        ztd_station_ids={k[0] for k in (ref_ztd or {})},
        vrs_virtual_position_source="ROVER_EPOCH0_SPP_GGA",
        vrs_virtual_offset_from_truth_m=vrs_offset_m,
    )

    ds_dir = out_dir / spec.dataset_id
    rtcm_dir = ds_dir / "rtcm"
    rinex_dir = ds_dir / "rinex"
    runs_dir = ds_dir / "runs"
    rtcm_dir.mkdir(parents=True, exist_ok=True)
    rinex_dir.mkdir(parents=True, exist_ok=True)

    ref_date_slash = spec.date_iso.replace("-", "/")
    # Map variant_id -> (base_label, base_ecef, base_rinex_path, rtcm_path, rtcm_sha, conv_summary)
    variant_bases: dict[
        str,
        tuple[
            str,
            tuple[float, float, float],
            Path | None,
            Path | None,
            str | None,
            dict[str, Any],
        ],
    ] = {
        f"physical_anchor_{spec.physical_anchor_id.lower()}": (
            spec.physical_anchor_id,
            spec.physical_anchor_ecef_m,
            spec.physical_anchor_obs_path,
            None,
            None,
            {"mode": "PHYSICAL_RINEX_DIRECT"},
        )
    }

    vrs_generation_records: dict[str, Any] = {}
    for idx, (variant_id, sp_model, tr_mode, iono_source) in enumerate(vrs_variants):
        iono_map: dict[tuple[str, str, str], float] | None
        if sp_model == "zero":
            iono_map = None
        elif iono_source == "nighttime":
            iono_map = iono_night
        else:
            iono_map = iono_common

        vrs = generate_experimental_vrs(
            experiment_id=f"{spec.dataset_id}-{variant_id}",
            target_station_id=spec.rover_station_id,
            target_ecef_m=vrs_virtual_ecef_m,
            reference_coords=ref_coords,
            reference_datasets=ref_datasets,
            nav_records=nav_records,
            doy=spec.doy,
            reference_frame=spec.rover_truth.reference_frame,
            coordinate_epoch=spec.rover_truth.coordinate_epoch,
            coordinate_provenance=str(spec.rover_truth.truth_tier),
            spatial_model=sp_model,
            iono_field_by_key=iono_map,
            ipp_by_key=ipp_by_key if sp_model == "ipp_idw2" else None,
            target_ipp_by_epoch_sat=target_ipps if sp_model == "ipp_idw2" else None,
            ztd_by_station_epoch=ref_ztd if tr_mode == "network_ztd" else None,
            tropo_mode=tr_mode,
            require_interior_hull=require_interior_hull,
            max_epochs=max_epochs,
        )
        if vrs.outcome != VrsOutcome.EXPERIMENTAL_VRS_GENERATED:
            raise BenchmarkFailure(
                f"VRS variant {variant_id} blocked unexpectedly: {vrs.outcome} {vrs.reason_codes}"
            )
        bundle = encode_experimental_vrs_to_rtcm(
            vrs,
            rtcm_station_id=rtcm_station_id_base + idx,
            effective_interval_s=spec.sampling_interval_s,
            max_epochs=max_epochs,
        )
        rtcm_path = rtcm_dir / f"{variant_id}.rtcm3"
        rtcm_path.write_bytes(bundle.stream_bytes)
        rinex_path = rinex_dir / f"{variant_id}.obs"
        conv = convert_rtcm_to_rinex(rtcm_path, rinex_path, ref_date_slash=ref_date_slash)
        if not conv.ok or conv.rinex_path is None:
            raise BenchmarkFailure(
                f"convbin failed for {variant_id}: {conv.outcome} {conv.stderr}"
            )
        vrs_generation_records[variant_id] = {
            "vrs_virtual_ecef_m": list(vrs_virtual_ecef_m),
            "vrs_virtual_offset_from_truth_m": vrs_offset_m,
            "vrs_summary": vrs.summary_dict(),
            "rtcm_bundle_summary": bundle.summary_dict(),
            "convbin_summary": conv.summary,
        }
        variant_bases[variant_id] = (
            vrs.virtual_station_id,
            vrs_virtual_ecef_m,
            conv.rinex_path,
            rtcm_path,
            conv.rtcm_sha256,
            conv.summary,
        )

    # Execute every relative profile identically across Physical Anchor + all VRS variants
    runs_by_profile: dict[str, dict[str, VariantRunResult]] = {}
    residuals_by_profile: dict[str, dict[str, list[EpochResidual]]] = {}
    paired_by_profile: dict[str, dict[str, Any]] = {}

    anchor_key = f"physical_anchor_{spec.physical_anchor_id.lower()}"
    geom_key = "vrs_zero_geom_only"

    jobs: list[
        tuple[
            ProcessingProfile,
            str,
            str,
            tuple[float, float, float],
            Path | None,
            Path | None,
            str | None,
            dict[str, Any],
        ]
    ] = []
    for profile in RELATIVE_PROFILES:
        for variant_id, (
            base_lbl,
            base_xyz,
            base_rnx,
            rtcm_p,
            rtcm_sha,
            conv_sum,
        ) in variant_bases.items():
            jobs.append(
                (profile, variant_id, base_lbl, base_xyz, base_rnx, rtcm_p, rtcm_sha, conv_sum)
            )

    def _run_job(
        job: tuple[
            ProcessingProfile,
            str,
            str,
            tuple[float, float, float],
            Path | None,
            Path | None,
            str | None,
            dict[str, Any],
        ],
    ) -> tuple[str, str, VariantRunResult, list[EpochResidual]]:
        profile, variant_id, base_lbl, base_xyz, base_rnx, rtcm_p, rtcm_sha, conv_sum = job
        pkey = str(profile)
        rdir = runs_dir / variant_id / pkey
        outcome, sol, exec_info = execute_rnx2rtkp(
            profile=profile,
            rover_obs_path=spec.rover_obs_path,
            base_obs_path=base_rnx,
            nav_paths=[spec.nav_path],
            base_ecef_m=base_xyz,
            start_time_utc=spec.start_time_utc,
            end_time_utc=spec.end_time_utc,
            run_dir=rdir,
        )
        if outcome is BenchmarkOutcome.COMPLETED and sol is not None:
            metrics, resids = compute_positioning_metrics(
                sol.epochs,
                truth_ecef_m=spec.rover_truth.ecef_xyz_m,
                start_time_utc=spec.start_time_utc,
                end_time_utc=spec.end_time_utc,
                sampling_interval_s=spec.sampling_interval_s,
            )
            _write_enu_residuals_csv(rdir / "enu_residuals.csv", resids)
        else:
            metrics, resids = {}, []
        v_res = VariantRunResult(
            dataset_id=spec.dataset_id,
            variant_id=variant_id,
            profile=profile,
            outcome=outcome,
            truth_tier=spec.rover_truth.truth_tier,
            base_station_label=base_lbl,
            base_ecef_m=base_xyz,
            rtcm_source_path=str(rtcm_p) if rtcm_p else None,
            rtcm_source_sha256=rtcm_sha,
            base_rinex_path=str(base_rnx) if base_rnx else None,
            base_rinex_sha256=(
                sha256_file(base_rnx) if base_rnx and base_rnx.is_file() else None
            ),
            rtklib_config_path=exec_info.get("config_path"),
            rtklib_config_sha256=exec_info.get("config_sha256"),
            solution_pos_path=exec_info.get("solution_pos_path"),
            solution_pos_sha256=exec_info.get("solution_pos_sha256"),
            metrics=metrics,
            conversion_summary=conv_sum,
            execution_summary=exec_info,
            error_detail=exec_info.get("error"),
        )
        return pkey, variant_id, v_res, resids

    for profile in RELATIVE_PROFILES:
        pkey = str(profile)
        runs_by_profile[pkey] = {}
        residuals_by_profile[pkey] = {}

    with ThreadPoolExecutor(max_workers=4) as pool:
        for pkey, variant_id, v_res, resids in pool.map(_run_job, jobs):
            runs_by_profile[pkey][variant_id] = v_res
            residuals_by_profile[pkey][variant_id] = resids

    for profile in RELATIVE_PROFILES:
        pkey = str(profile)
        # Paired statistical comparisons against Physical Anchor AND Geometry-Only VRS
        p_comps: dict[str, Any] = {}
        anchor_res = residuals_by_profile[pkey].get(anchor_key, [])
        geom_res = residuals_by_profile[pkey].get(geom_key, [])
        for variant_id, cand_res in residuals_by_profile[pkey].items():
            if variant_id != anchor_key:
                p_comps[f"{variant_id}_vs_{anchor_key}"] = paired_comparison(
                    anchor_res,
                    cand_res,
                    baseline_label=anchor_key,
                    candidate_label=variant_id,
                )
            if variant_id not in (anchor_key, geom_key):
                p_comps[f"{variant_id}_vs_{geom_key}"] = paired_comparison(
                    geom_res,
                    cand_res,
                    baseline_label=geom_key,
                    candidate_label=variant_id,
                )
        paired_by_profile[pkey] = p_comps

    result_payload = {
        "dataset_spec": spec.as_dict(),
        "leakage_audit": leakage.as_dict(),
        "vrs_generation": vrs_generation_records,
        "spp_standalone": spp_payload,
        "profiles": {
            pkey: {vid: vres.as_dict() for vid, vres in vmap.items()}
            for pkey, vmap in runs_by_profile.items()
        },
        "paired_comparisons": paired_by_profile,
    }
    _write_json(ds_dir / "benchmark_results.json", result_payload)
    return result_payload


def run_failure_and_robustness_suite(
    *,
    spec_2024: DatasetWindowSpec,
    ref_coords_2024: dict[str, tuple[float, float, float]],
    ref_ds_2024: dict[str, StationDataset],
    nav_2024: dict[str, list[BroadcastEphemeris]],
    valid_rtcm_2024: Path,
    sample_float_pos_2024: Path,
) -> dict[str, Any]:
    """Execute all 12 required Phase H robustness and fail-closed verification tests."""
    scenarios: dict[str, Any] = {}
    with tempfile.TemporaryDirectory(prefix="nlgcp-b02-fail-") as tmp_str:
        tmp = Path(tmp_str)

        # 1. Missing rover observations
        o1, _, e1 = execute_rnx2rtkp(
            profile=ProcessingProfile.KINEMATIC_BRDC_SAAS,
            rover_obs_path=tmp / "missing_rover.24O",
            base_obs_path=spec_2024.physical_anchor_obs_path,
            nav_paths=[spec_2024.nav_path],
            base_ecef_m=spec_2024.physical_anchor_ecef_m,
            start_time_utc=spec_2024.start_time_utc,
            end_time_utc=spec_2024.end_time_utc,
            run_dir=tmp / "f1",
        )
        scenarios["1_missing_rover_observations"] = {
            "outcome": str(o1),
            "passed": o1 is BenchmarkOutcome.FAILED_MISSING_ROVER_OBS,
            "detail": e1.get("error"),
        }

        # 2. Missing reference observations
        o2, _, e2 = execute_rnx2rtkp(
            profile=ProcessingProfile.KINEMATIC_BRDC_SAAS,
            rover_obs_path=spec_2024.rover_obs_path,
            base_obs_path=tmp / "missing_base.obs",
            nav_paths=[spec_2024.nav_path],
            base_ecef_m=spec_2024.physical_anchor_ecef_m,
            start_time_utc=spec_2024.start_time_utc,
            end_time_utc=spec_2024.end_time_utc,
            run_dir=tmp / "f2",
        )
        scenarios["2_missing_reference_observations"] = {
            "outcome": str(o2),
            "passed": o2 is BenchmarkOutcome.FAILED_MISSING_REFERENCE_OBS,
            "detail": e2.get("error"),
        }

        # 3. Missing navigation product
        o3, _, e3 = execute_rnx2rtkp(
            profile=ProcessingProfile.KINEMATIC_BRDC_SAAS,
            rover_obs_path=spec_2024.rover_obs_path,
            base_obs_path=spec_2024.physical_anchor_obs_path,
            nav_paths=[tmp / "missing.rnx"],
            base_ecef_m=spec_2024.physical_anchor_ecef_m,
            start_time_utc=spec_2024.start_time_utc,
            end_time_utc=spec_2024.end_time_utc,
            run_dir=tmp / "f3",
        )
        scenarios["3_navigation_product_gap"] = {
            "outcome": str(o3),
            "passed": o3 is BenchmarkOutcome.FAILED_MISSING_NAVIGATION,
            "detail": e3.get("error"),
        }

        # 4. Invalid RTCM frame (flipped CRC byte)
        raw_rtcm = bytearray(valid_rtcm_2024.read_bytes())
        raw_rtcm[10] ^= 0xFF
        bad_rtcm = tmp / "corrupt_crc.rtcm3"
        bad_rtcm.write_bytes(bytes(raw_rtcm))
        c4 = convert_rtcm_to_rinex(bad_rtcm, tmp / "f4.obs", ref_date_slash="2024/01/26")
        scenarios["4_invalid_rtcm_crc_frame"] = {
            "outcome": str(c4.outcome),
            "passed": not c4.ok and c4.outcome is BenchmarkOutcome.FAILED_INVALID_RTCM,
            "crc_fail_count": c4.summary.get("crc_fail_count"),
        }

        # 5. Truncated RTCM stream
        trunc_rtcm = tmp / "truncated.rtcm3"
        trunc_rtcm.write_bytes(valid_rtcm_2024.read_bytes()[:40])
        c5 = convert_rtcm_to_rinex(trunc_rtcm, tmp / "f5.obs", ref_date_slash="2024/01/26")
        scenarios["5_truncated_rtcm_stream"] = {
            "outcome": str(c5.outcome),
            "passed": not c5.ok and c5.outcome is BenchmarkOutcome.FAILED_TRUNCATED_RTCM,
            "findings": c5.summary.get("findings"),
        }

        # 6. Insufficient satellite visibility (1-satellite minimal RINEX -> 0 epochs)
        one_sat_obs = tmp / "one_sat.24O"
        one_sat_obs.write_text(
            "     2.11           OBSERVATION DATA    G (GPS)             RINEX VERSION / TYPE\n"
            "     4    C1    P2    L1    L2                              # / TYPES OF OBSERV\n"
            "  2024     1    26     0     0    0.0000000     GPS         TIME OF FIRST OBS\n"
            "                                                            END OF HEADER\n"
            " 24  1 26  0  0  0.0000000  0  1G01\n"
            "  21500000.000  21500002.000 113000000.000  88000000.000\n",
            encoding="ascii",
        )
        o6, _, e6 = execute_rnx2rtkp(
            profile=ProcessingProfile.KINEMATIC_BRDC_SAAS,
            rover_obs_path=one_sat_obs,
            base_obs_path=spec_2024.physical_anchor_obs_path,
            nav_paths=[spec_2024.nav_path],
            base_ecef_m=spec_2024.physical_anchor_ecef_m,
            start_time_utc="2024-01-26T00:00:00Z",
            end_time_utc="2024-01-26T00:01:00Z",
            run_dir=tmp / "f6",
        )
        scenarios["6_insufficient_satellite_visibility"] = {
            "outcome": str(o6),
            "passed": o6 is BenchmarkOutcome.FAILED_INSUFFICIENT_SATELLITES,
            "detail": e6.get("error"),
        }

        # 7. Inconsistent observation epochs (wrong date window -> zero overlap epochs)
        o7, _, e7 = execute_rnx2rtkp(
            profile=ProcessingProfile.KINEMATIC_BRDC_SAAS,
            rover_obs_path=spec_2024.rover_obs_path,
            base_obs_path=spec_2024.physical_anchor_obs_path,
            nav_paths=[spec_2024.nav_path],
            base_ecef_m=spec_2024.physical_anchor_ecef_m,
            start_time_utc="2024-01-27T00:00:00Z",
            end_time_utc="2024-01-27T00:05:00Z",
            run_dir=tmp / "f7",
        )
        scenarios["7_inconsistent_observation_epochs"] = {
            "outcome": str(o7),
            "passed": o7 is BenchmarkOutcome.FAILED_EPOCH_MISMATCH,
            "detail": e7.get("error"),
        }

        # 8. Incorrect coordinate provenance (provisional truth claiming verified accuracy)
        prov_blocked = False
        prov_err = ""
        try:
            RoverTruthRecord(
                station_id="OSGF",
                truth_tier=TruthTier.PROVISIONAL_OSGOF_LIMITED,
                accuracy_claim_permitted=True,
                ecef_xyz_m=(6246471.2, 820848.74, 994267.93),
                reference_frame="UNKNOWN",
                coordinate_epoch="2011-01-01",
                provenance_source="OSGoF",
                provenance_sha256=None,
                antenna_model="TRM59800.00",
                antenna_delta_hen_m=(0.171, 0.0, 0.0),
            ).validate()
        except BenchmarkFailure as exc:
            prov_blocked = True
            prov_err = str(exc)
        scenarios["8_incorrect_coordinate_provenance"] = {
            "passed": prov_blocked,
            "detail": prov_err,
        }

        # 9. Unavailable atmospheric model
        r9 = generate_experimental_vrs(
            experiment_id="b02-fail-atmo",
            target_station_id="PHRI00NGA",
            target_ecef_m=spec_2024.rover_truth.ecef_xyz_m,
            reference_coords=ref_coords_2024,
            reference_datasets=ref_ds_2024,
            nav_records=nav_2024,
            doy=26,
            reference_frame="IGS20",
            coordinate_epoch="2024-01-26",
            coordinate_provenance="VERIFIED_IGS20",
            spatial_model="idw2",
            iono_field_by_key=None,
            require_interior_hull=False,
        )
        scenarios["9_unavailable_atmospheric_model"] = {
            "outcome": str(r9.outcome),
            "passed": r9.outcome == VrsOutcome.ATMOSPHERIC_MODEL_UNAVAILABLE,
        }

        # 10. Rover outside convex hull (strict interior hull gate)
        r10 = generate_experimental_vrs(
            experiment_id="b02-fail-hull",
            target_station_id="PHRI00NGA",
            target_ecef_m=spec_2024.rover_truth.ecef_xyz_m,
            reference_coords=ref_coords_2024,
            reference_datasets=ref_ds_2024,
            nav_records=nav_2024,
            doy=26,
            reference_frame="IGS20",
            coordinate_epoch="2024-01-26",
            coordinate_provenance="VERIFIED_IGS20",
            spatial_model="zero",
            require_interior_hull=True,
        )
        scenarios["10_rover_outside_convex_hull"] = {
            "outcome": str(r10.outcome),
            "passed": r10.outcome == VrsOutcome.INSUFFICIENT_NETWORK_GEOMETRY,
        }

        # 11. Failed ambiguity resolution detection (explicitly reports FIX=0, FLOAT>0, TTFF=None)
        parsed_float = parse_solution_pos(sample_float_pos_2024, strict=False)
        fix_cnt = sum(1 for ep in parsed_float.epochs if ep.quality is SolutionQuality.FIX)
        flt_cnt = sum(1 for ep in parsed_float.epochs if ep.quality is SolutionQuality.FLOAT)
        ttff_val = ttff_seconds(parsed_float.epochs)
        scenarios["11_failed_ambiguity_resolution_honest_reporting"] = {
            "source_pos": str(sample_float_pos_2024),
            "total_epochs": len(parsed_float.epochs),
            "fix_epochs": fix_cnt,
            "float_epochs": flt_cnt,
            "ttff_s": ttff_val,
            "passed": (
                len(parsed_float.epochs) > 0
                and fix_cnt == 0
                and flt_cnt > 0
                and ttff_val is None
            ),
        }

        # 12. RTKLIB timeout & non-zero exit handling
        o12, _, e12 = execute_rnx2rtkp(
            profile=ProcessingProfile.KINEMATIC_BRDC_SAAS,
            rover_obs_path=spec_2024.rover_obs_path,
            base_obs_path=spec_2024.physical_anchor_obs_path,
            nav_paths=[spec_2024.nav_path],
            base_ecef_m=spec_2024.physical_anchor_ecef_m,
            start_time_utc=spec_2024.start_time_utc,
            end_time_utc=spec_2024.end_time_utc,
            run_dir=tmp / "f12",
            timeout_s=0.001,
        )
        scenarios["12_rtklib_timeout_or_nonzero_exit"] = {
            "outcome": str(o12),
            "passed": o12 is BenchmarkOutcome.FAILED_RTKLIB_EXECUTION,
            "detail": e12.get("error"),
        }

    return {
        "total_scenarios": len(scenarios),
        "all_passed": all(v["passed"] for v in scenarios.values()),
        "scenarios": scenarios,
    }


def _probe_preserved_phase7_streams(
    *,
    data_root: Path,
    spec_2024: DatasetWindowSpec,
    spec_2011: DatasetWindowSpec,
    out_dir: Path,
) -> dict[str, Any]:
    """Read-only positioning probe of preserved Phase 7 sprint-phase67 120s RTCM files.

    Demonstrates direct traceability from the pre-existing Phase 7 artifacts and
    empirically quantifies the 120 s cadence vs RTKLIB maxage=30 s limitation.
    """
    probes: dict[str, Any] = {}
    targets = (
        (
            "phase7_2024_phri_120s",
            data_root / "processed/vrs/sprint-phase67/vrs_2024_01_26_phri_exp.rtcm3",
            spec_2024,
            "2024-01-26T00:00:00Z",
            "2024-01-26T00:58:00Z",
        ),
        (
            "phase7_2011_osgf_120s",
            data_root / "processed/vrs/sprint-phase67/vrs_2011_03_20_osgf_exp.rtcm3",
            spec_2011,
            "2011-03-20T00:00:00Z",
            "2011-03-20T00:58:00Z",
        ),
    )
    probe_root = out_dir / "phase7_preserved_rtcm_probes"
    for key, rtcm_path, spec, start_u, end_u in targets:
        if not rtcm_path.is_file():
            probes[key] = {"present": False, "path": str(rtcm_path)}
            continue
        rnx_out = probe_root / f"{key}.obs"
        conv = convert_rtcm_to_rinex(
            rtcm_path, rnx_out, ref_date_slash=spec.date_iso.replace("-", "/")
        )
        if not conv.ok or conv.rinex_path is None:
            probes[key] = {
                "present": True,
                "path": str(rtcm_path),
                "sha256": conv.rtcm_sha256,
                "convbin_ok": False,
                "outcome": str(conv.outcome),
            }
            continue
        approx = conv.summary.get("rinex_approx_xyz_m")
        base_xyz = (
            (float(approx[0]), float(approx[1]), float(approx[2]))
            if isinstance(approx, list) and len(approx) == 3
            else spec.rover_truth.ecef_xyz_m
        )
        out_k, sol_k, exec_k = execute_rnx2rtkp(
            profile=ProcessingProfile.KINEMATIC_BRDC_SAAS,
            rover_obs_path=spec.rover_obs_path,
            base_obs_path=conv.rinex_path,
            nav_paths=[spec.nav_path],
            base_ecef_m=base_xyz,
            start_time_utc=start_u,
            end_time_utc=end_u,
            run_dir=probe_root / key,
        )
        metrics: dict[str, Any] = {}
        if out_k is BenchmarkOutcome.COMPLETED and sol_k is not None:
            metrics, _ = compute_positioning_metrics(
                sol_k.epochs,
                truth_ecef_m=spec.rover_truth.ecef_xyz_m,
                start_time_utc=start_u,
                end_time_utc=end_u,
                sampling_interval_s=30.0,
            )
        probes[key] = {
            "present": True,
            "path": str(rtcm_path),
            "sha256": conv.rtcm_sha256,
            "convbin_summary": conv.summary,
            "rnx2rtkp_outcome": str(out_k),
            "metrics": metrics,
            "execution": exec_k,
            "note": (
                "Preserved Phase 7 120 s (stride=4) artifact probed read-only; "
                "drops to SINGLE on intermediate 30 s epochs where age > maxage=30 s. "
                "Note: Phase 7 sprint-phase67 encoded RTCM 1005 at the station target coordinate "
                "(observation-residual test); B-02 full runs instead synthesize at autonomous "
                "epoch-0 SPP GGA to eliminate coordinate leakage."
            ),
        }
    return probes


def run_b02_benchmark(
    *,
    data_root: Path,
    out_dir: Path | None = None,
    stride: int = 1,
    max_epochs: int | None = None,
) -> dict[str, Any]:
    """Run the complete B-02 Offline Rover Positioning Benchmark on authentic data."""
    t_start = time.monotonic()
    started_utc = utc_now_iso()
    target_out = out_dir or (data_root / "processed/rover-benchmark/b02")
    target_out.mkdir(parents=True, exist_ok=True)
    tool_prov = rtklib_tool_provenance()
    sw_rev = _git_software_revision()

    # =========================================================================
    # DATASET B: 2024-01-26 (DOY 026) — VERIFIED IGS20 TRUTH (PHRI00NGA)
    # =========================================================================
    dc = json.loads((data_root / "processed/single-base/derived-coordinates.json").read_text())
    p5_adm = json.loads(
        (data_root / "processed/network-rtk/experiments/net-2024d026-phri-rover/admission.json")
        .read_text()
    )
    coords_2024: dict[str, tuple[float, float, float]] = {}
    obs_paths_2024: dict[str, Path] = {}
    nav_2024_path: Path | None = None
    for s in p5_adm["admitted"]:
        sid = s["station_id"]
        if dc["stations"].get(sid, {}).get("scientifically_valid") is not True:
            continue
        e = dc["stations"][sid]["ecef"]
        coords_2024[sid] = (float(e["x_m"]), float(e["y_m"]), float(e["z_m"]))
        obs_paths_2024[sid] = Path(s["observation_path"])
        if nav_2024_path is None:
            nav_2024_path = data_root / s["navigation_path"]
    assert nav_2024_path is not None

    rover_2024 = "PHRI00NGA"
    anchor_2024 = "EKAK00NGA"
    ref_coords_2024 = {k: v for k, v in coords_2024.items() if k != rover_2024}
    ref_ds_2024 = {
        k: read_rinex2_observations(obs_paths_2024[k], k, stride=stride)
        for k in sorted(ref_coords_2024)
    }
    nav_2024_gz_sha = sha256_file(nav_2024_path)
    derived_in_2024 = target_out / "inputs/2024_01_26"
    if nav_2024_path.suffix == ".gz":
        nav_2024_plain = _decompress_unix_z(
            nav_2024_path, derived_in_2024 / nav_2024_path.with_suffix("").name
        )
    else:
        nav_2024_plain = nav_2024_path
    nav_2024_records = parse_gps_nav_auto(nav_2024_plain)
    nav_2024_sha = sha256_file(nav_2024_plain)

    # Strictly 3-reference PRIDE ZTD (zero PHRI00NGA leakage!)
    pride_ref_paths_2024 = {
        "ABFC00NGA": data_root / "working/pride-test/2024/026/ztd_2024026",
        "EKAK00NGA": data_root / "working/pride/run-EKAK00NGA/2024/026/ztd_2024026_ekak",
        "MGBO00NGA": data_root / "working/pride/run-MGBO00NGA/2024/026/ztd_2024026_mgbo",
    }
    ref_ztd_2024: dict[tuple[str, str], tuple[float, float]] = {}
    for sid, zp in pride_ref_paths_2024.items():
        if zp.is_file():
            recs, _ = parse_pride_ztd(zp, station_id=sid)
            for rec in recs:
                ref_ztd_2024[(sid, rec.epoch_iso)] = (rec.zhd_m, rec.zwd_total_m)

    phri_pos_path = Path(dc["stations"][rover_2024]["pos_file_path"])
    truth_2024 = RoverTruthRecord(
        station_id=rover_2024,
        truth_tier=TruthTier.VERIFIED_IGS20_PPP_AR,
        accuracy_claim_permitted=True,
        ecef_xyz_m=coords_2024[rover_2024],
        reference_frame="IGS20",
        coordinate_epoch=str(dc["stations"][rover_2024]["coordinate_epoch"]),
        provenance_source=str(phri_pos_path),
        provenance_sha256=str(dc["stations"][rover_2024]["pos_file_sha256"]),
        antenna_model="TRM59900.00 NONE",
        antenna_delta_hen_m=(0.1710, 0.0, 0.0),
        formal_sigma_xyz_m=_parse_pride_formal_sigmas(phri_pos_path),
        processing_method="PRIDE PPP-AR 3.2.8 static daily solution (45 fixed GPS amb, 26,065 obs)",
        precise_products=(
            "WUM0MGXRAP_20240260000_01D_05M_ORB.SP3",
            "WUM0MGXRAP_20240260000_01D_30S_CLK.CLK",
            "WUM0MGXRAP_20240260000_01D_30S_ATT.OBX",
            "WUM0MGXRAP_20240260000_01D_01D_OSB.BIA",
            "WUM0MGXRAP_20240260000_01D_01D_ERP.ERP",
        ),
        bias_products_available=True,
        notes="Verified IGS20 ARP coordinate; EKAK vs PHRI antenna PCO Up differs ~1.4-1.7 cm.",
    )
    end_2024 = (
        ref_ds_2024[anchor_2024].epochs[max_epochs - 1] + "Z"
        if max_epochs is not None and max_epochs < len(ref_ds_2024[anchor_2024].epochs)
        else "2024-01-26T23:59:30Z"
    )
    spec_2024 = DatasetWindowSpec(
        dataset_id="2024_01_26_phri_verified",
        date_iso="2024-01-26",
        year=2024,
        doy=26,
        start_time_utc="2024-01-26T00:00:00Z",
        end_time_utc=end_2024,
        sampling_interval_s=30.0 * stride,
        rover_station_id=rover_2024,
        rover_obs_path=obs_paths_2024[rover_2024],
        rover_obs_sha256=sha256_file(obs_paths_2024[rover_2024]),
        physical_anchor_id=anchor_2024,
        physical_anchor_obs_path=obs_paths_2024[anchor_2024],
        physical_anchor_obs_sha256=sha256_file(obs_paths_2024[anchor_2024]),
        physical_anchor_ecef_m=coords_2024[anchor_2024],
        reference_stations=tuple(sorted(ref_coords_2024)),
        nav_path=nav_2024_plain,
        nav_sha256=nav_2024_sha,
        rover_inside_convex_hull=_inside_hull(coords_2024[rover_2024], ref_coords_2024),
        anchor_baseline_km=baseline_length_m(coords_2024[anchor_2024], coords_2024[rover_2024])
        / 1000.0,
        rover_truth=truth_2024,
        notes=(
            "Primary verified-truth benchmark (3 refs, 105.553 km anchor, outside convex hull; "
            f"source nav .rnx.gz sha256={nav_2024_gz_sha})."
        ),
    )

    vrs_gga_2024, spp_2024 = _derive_spp_gga_position(spec=spec_2024, out_dir=target_out)
    iono_c_2024, iono_n_2024, ipp_2024, tgt_ipp_2024 = _compute_ref_iono_fields(
        ref_datasets=ref_ds_2024,
        ref_coords=ref_coords_2024,
        target_station=rover_2024,
        target_ecef=vrs_gga_2024,
        nav_records=nav_2024_records,
        nav_hash=nav_2024_sha,
        datum_station=anchor_2024,
        stride=stride,
    )

    res_2024 = _execute_dataset_benchmark(
        spec=spec_2024,
        vrs_virtual_ecef_m=vrs_gga_2024,
        spp_payload=spp_2024,
        ref_coords=ref_coords_2024,
        ref_datasets=ref_ds_2024,
        nav_records=nav_2024_records,
        iono_common=iono_c_2024,
        iono_night=iono_n_2024,
        ipp_by_key=ipp_2024,
        target_ipps=tgt_ipp_2024,
        ref_ztd=ref_ztd_2024,
        vrs_variants=(
            ("vrs_zero_geom_only", "zero", "zero", "none"),
            ("vrs_tropo_unb3m_only", "zero", "unb3m", "none"),
            ("vrs_tropo_pride_ztd_only", "zero", "network_ztd", "none"),
            ("vrs_idw2_unb3m", "idw2", "unb3m", "common_arc"),
            ("vrs_idw2_pride_ztd", "idw2", "network_ztd", "common_arc"),
            ("vrs_nighttime_idw2_pride_ztd", "idw2", "network_ztd", "nighttime"),
        ),
        rtcm_station_id_base=2400,
        out_dir=target_out,
        require_interior_hull=False,
        max_epochs=max_epochs,
    )

    # =========================================================================
    # DATASET A: 2011-03-20 (DOY 079) — INTERIOR HULL (OSGF, PROVISIONAL TRUTH)
    # =========================================================================
    zip_2011 = data_root / "incoming/southern-nignet/NIGNET2011.zip"
    audit_csv = data_root / "validation/southern-nignet/run-20261030T125136Z/rinex_header_audit.csv"
    osgof_csv = (
        data_root
        / "validation/southern-nignet/coordinate-navigation-recovery"
        / "run-20261030T132927Z/coordinate_provenance.csv"
    )
    nav_2011_z = (
        data_root
        / "validation/southern-nignet/coordinate-navigation-recovery"
        / "run-20261123T163056Z/navigation-products/attempts/bkg/brdc0790.11n.Z"
    )
    osgof_coords = load_osgof_provisional_coords(osgof_csv)
    stations_2011 = ("ABUZ", "BKFP", "CGGT", "FUTY", "MDGR", "OSGF", "RUST", "ULAG", "UNEC")
    members_2011: dict[str, str] = {}
    with audit_csv.open(encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row["observation_date_from_filename"] == "2011-03-20":
                st4 = row["canonical_station_id"][:4]
                if st4 in stations_2011:
                    members_2011[st4] = row["relative_path"]

    rover_2011 = "OSGF"
    anchor_2011 = "CGGT"
    derived_in_2011 = target_out / "inputs/2011_03_20"
    rover_obs_2011 = _extract_zip_member(
        zip_2011, members_2011[rover_2011], derived_in_2011 / "OSGF0790.11O"
    )
    anchor_obs_2011 = _extract_zip_member(
        zip_2011, members_2011[anchor_2011], derived_in_2011 / "CGGT0790.11O"
    )
    nav_2011_plain = _decompress_unix_z(nav_2011_z, derived_in_2011 / "brdc0790.11n")

    ref_coords_2011 = {st: osgof_coords[st] for st in stations_2011 if st != rover_2011}
    ref_ds_2011 = {
        st: read_rinex2_from_zip(zip_2011, members_2011[st], st, stride=stride)
        for st in sorted(ref_coords_2011)
    }
    nav_2011_records = parse_gps_nav_auto(nav_2011_plain)
    nav_2011_sha = sha256_file(nav_2011_plain)

    truth_2011 = RoverTruthRecord(
        station_id=rover_2011,
        truth_tier=TruthTier.PROVISIONAL_OSGOF_LIMITED,
        accuracy_claim_permitted=False,
        ecef_xyz_m=osgof_coords[rover_2011],
        reference_frame="ITRF_UNDOCUMENTED_OSGOF_2011",
        coordinate_epoch="2011-01-01",
        provenance_source=str(osgof_csv),
        provenance_sha256=sha256_file(osgof_csv),
        antenna_model="TRM59800.00",
        antenna_delta_hen_m=(0.1710, 0.0, 0.0),
        formal_sigma_xyz_m=None,
        processing_method="OSGoF 2011-01-01 published table (PROVISIONAL; no 2011 SP3/PPP on disk)",
        precise_products=(),
        bias_products_available=False,
        notes=(
            "LIMITED PROVISIONAL TRUTH: frame/ARP/uncertainty undocumented. "
            "Accuracy vs OSGoF is exploratory; evaluate alongside truth-independent repeatability."
        ),
    )
    end_2011 = (
        ref_ds_2011[anchor_2011].epochs[max_epochs - 1] + "Z"
        if max_epochs is not None and max_epochs < len(ref_ds_2011[anchor_2011].epochs)
        else "2011-03-20T23:59:30Z"
    )
    spec_2011 = DatasetWindowSpec(
        dataset_id="2011_03_20_osgf_interior",
        date_iso="2011-03-20",
        year=2011,
        doy=79,
        start_time_utc="2011-03-20T00:00:00Z",
        end_time_utc=end_2011,
        sampling_interval_s=30.0 * stride,
        rover_station_id=rover_2011,
        rover_obs_path=rover_obs_2011,
        rover_obs_sha256=sha256_file(rover_obs_2011),
        physical_anchor_id=anchor_2011,
        physical_anchor_obs_path=anchor_obs_2011,
        physical_anchor_obs_sha256=sha256_file(anchor_obs_2011),
        physical_anchor_ecef_m=osgof_coords[anchor_2011],
        reference_stations=tuple(sorted(ref_coords_2011)),
        nav_path=nav_2011_plain,
        nav_sha256=nav_2011_sha,
        rover_inside_convex_hull=_inside_hull(osgof_coords[rover_2011], ref_coords_2011),
        anchor_baseline_km=baseline_length_m(osgof_coords[anchor_2011], osgof_coords[rover_2011])
        / 1000.0,
        rover_truth=truth_2011,
        notes="Interior convex-hull benchmark (8 refs, 216.32 km anchor, provisional truth only).",
    )

    vrs_gga_2011, spp_2011 = _derive_spp_gga_position(spec=spec_2011, out_dir=target_out)
    iono_c_2011, iono_n_2011, ipp_2011, tgt_ipp_2011 = _compute_ref_iono_fields(
        ref_datasets=ref_ds_2011,
        ref_coords=ref_coords_2011,
        target_station=rover_2011,
        target_ecef=vrs_gga_2011,
        nav_records=nav_2011_records,
        nav_hash=nav_2011_sha,
        datum_station=anchor_2011,
        stride=stride,
    )

    res_2011 = _execute_dataset_benchmark(
        spec=spec_2011,
        vrs_virtual_ecef_m=vrs_gga_2011,
        spp_payload=spp_2011,
        ref_coords=ref_coords_2011,
        ref_datasets=ref_ds_2011,
        nav_records=nav_2011_records,
        iono_common=iono_c_2011,
        iono_night=iono_n_2011,
        ipp_by_key=ipp_2011,
        target_ipps=tgt_ipp_2011,
        ref_ztd=None,
        vrs_variants=(
            ("vrs_zero_geom_only", "zero", "zero", "none"),
            ("vrs_tropo_unb3m_only", "zero", "unb3m", "none"),
            ("vrs_idw2_unb3m", "idw2", "unb3m", "common_arc"),
            ("vrs_ipp_idw2_unb3m", "ipp_idw2", "unb3m", "common_arc"),
            ("vrs_nighttime_ipp_idw2_unb3m", "ipp_idw2", "unb3m", "nighttime"),
        ),
        rtcm_station_id_base=2100,
        out_dir=target_out,
        require_interior_hull=True,
        max_epochs=max_epochs,
    )

    # =========================================================================
    # READ-ONLY PROBE OF PRESERVED PHASE 7 120 s RTCM ARTIFACTS
    # =========================================================================
    phase7_probes = _probe_preserved_phase7_streams(
        data_root=data_root,
        spec_2024=spec_2024,
        spec_2011=spec_2011,
        out_dir=target_out,
    )

    # =========================================================================
    # PHASE H: 12 FAILURE & ROBUSTNESS SCENARIOS
    # =========================================================================
    sample_rtcm = target_out / spec_2024.dataset_id / "rtcm/vrs_idw2_pride_ztd.rtcm3"
    sample_pos_raw = res_2024["profiles"][str(ProcessingProfile.STATIC_BRDC_SAAS)][
        "physical_anchor_ekak00nga"
    ]["solution_pos_path"]
    if not isinstance(sample_pos_raw, str):
        raise BenchmarkFailure(
            "expected completed 2024 static physical_anchor_ekak00nga solution for failure suite"
        )
    sample_pos = Path(sample_pos_raw)
    failure_suite = run_failure_and_robustness_suite(
        spec_2024=spec_2024,
        ref_coords_2024=ref_coords_2024,
        ref_ds_2024=ref_ds_2024,
        nav_2024=nav_2024_records,
        valid_rtcm_2024=sample_rtcm,
        sample_float_pos_2024=sample_pos,
    )

    completed_utc = utc_now_iso()
    duration_s = round(time.monotonic() - t_start, 3)

    manifest = {
        "schema_version": "nlgcp.b02.dataset_manifest.v1",
        "benchmark_version": BENCHMARK_VERSION,
        "generated_utc": completed_utc,
        "operational_approved": False,
        "datasets": [spec_2024.as_dict(), spec_2011.as_dict()],
    }
    _write_json(target_out / "dataset_manifest.json", manifest)

    profile_templates = {
        str(p): {
            "config_text": render_profile_config(p, base_ecef_m=None),
            "template_sha256": hashlib.sha256(
                render_profile_config(p, base_ecef_m=None).encode("utf-8")
            ).hexdigest(),
        }
        for p in (ProcessingProfile.SPP_SINGLE, *RELATIVE_PROFILES)
    }
    experiment_config = {
        "schema_version": "nlgcp.b02.experiment_config.v1",
        "benchmark_version": BENCHMARK_VERSION,
        "generated_utc": completed_utc,
        "operational_approved": False,
        "stride": stride,
        "max_epochs": max_epochs,
        "elevation_mask_deg": 15.0,
        "constellations": "GPS_ONLY (pos1-navsys=1)",
        "frequencies": "l1+l2",
        "vrs_virtual_position_policy": "ROVER_EPOCH0_SPP_GGA (zero truth leakage)",
        "bootstrap_policy": {
            "method": "moving_block_bootstrap",
            "block_size_epochs": 40,
            "iterations": 500,
            "seed": 20261125,
        },
        "profiles": profile_templates,
    }
    _write_json(target_out / "experiment_config.json", experiment_config)

    comparison_summary = {
        "schema_version": "nlgcp.b02.comparison_summary.v1",
        "benchmark_version": BENCHMARK_VERSION,
        "generated_utc": completed_utc,
        "operational_approved": False,
        "dataset_2024_phri_verified": {
            "truth_tier": str(spec_2024.rover_truth.truth_tier),
            "inside_convex_hull": spec_2024.rover_inside_convex_hull,
            "leakage_audit": res_2024["leakage_audit"],
            "spp_metrics": res_2024["spp_standalone"]["metrics"],
            "paired_comparisons": res_2024["paired_comparisons"],
        },
        "dataset_2011_osgf_interior": {
            "truth_tier": str(spec_2011.rover_truth.truth_tier),
            "inside_convex_hull": spec_2011.rover_inside_convex_hull,
            "leakage_audit": res_2011["leakage_audit"],
            "spp_metrics": res_2011["spp_standalone"]["metrics"],
            "paired_comparisons": res_2011["paired_comparisons"],
        },
    }
    _write_json(target_out / "comparison_summary.json", comparison_summary)

    exec_metadata = {
        "schema_version": "nlgcp.b02.execution_metadata.v1",
        "benchmark_version": BENCHMARK_VERSION,
        "started_utc": started_utc,
        "completed_utc": completed_utc,
        "duration_s": duration_s,
        "operational_approved": False,
        "software_revision": sw_rev,
        "tool_provenance": tool_prov,
    }
    _write_json(target_out / "execution_metadata.json", exec_metadata)

    summary = {
        "schema_version": "nlgcp.b02.summary.v1",
        "benchmark_version": BENCHMARK_VERSION,
        "generated_utc": completed_utc,
        "duration_s": duration_s,
        "operational_approved": False,
        "stride": stride,
        "max_epochs": max_epochs,
        "software_revision": sw_rev,
        "tool_provenance": tool_prov,
        "phase7_preserved_rtcm_probes": phase7_probes,
        "dataset_2024_phri_verified": res_2024,
        "dataset_2011_osgf_interior": res_2011,
        "failure_and_robustness_suite": failure_suite,
    }
    _write_json(target_out / "b02_benchmark_summary.json", summary)

    # Record input and output artifact SHA-256 manifest
    output_hashes: dict[str, str] = {}
    for rel in sorted(target_out.rglob("*")):
        if rel.is_file() and rel.name != "hashes_manifest.json":
            output_hashes[str(rel.relative_to(target_out))] = sha256_file(rel)
    _write_json(
        target_out / "hashes_manifest.json",
        {
            "schema_version": "nlgcp.b02.hashes_manifest.v1",
            "generated_utc": completed_utc,
            "inputs": {
                "2024_rover_obs": spec_2024.rover_obs_sha256,
                "2024_anchor_obs": spec_2024.physical_anchor_obs_sha256,
                "2024_nav_gz_source": nav_2024_gz_sha,
                "2024_nav_plain": spec_2024.nav_sha256,
                "2024_truth_pos": spec_2024.rover_truth.provenance_sha256,
                "2011_rover_obs": spec_2011.rover_obs_sha256,
                "2011_anchor_obs": spec_2011.physical_anchor_obs_sha256,
                "2011_nav": spec_2011.nav_sha256,
                "2011_osgof_csv": spec_2011.rover_truth.provenance_sha256,
            },
            "outputs": output_hashes,
        },
    )
    return summary
