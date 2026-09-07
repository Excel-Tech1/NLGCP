"""Phase 6 pipeline orchestration (derive -> fit -> validate).

Every stage enforces Phase 4/5 admission, records provenance, and supports
deterministic reuse: changing any input observation, ephemeris/product,
station coordinate, QC decision, model parameter, or code/config fingerprint
invalidates the stored result. Position-domain RMSE is never substituted for
satellite-derived atmospheric observables (fail-closed).
"""

from __future__ import annotations

import csv
import json
import os
import subprocess
from pathlib import Path
from typing import Any, cast

from . import PIPELINE_VERSION
from .interpolation import METHOD_NAMES, interpolate, prediction_to_row
from .ionosphere import pair_sd_proxies, spatial_gradient_proxy, station_gf_arcs
from .metrics import decorrelation_fit, rmse
from .models import (
    ModelBlocked,
    ModelExperimentDefinition,
    StageStatus,
    StationCoordinate,
    definition_from_dict,
)
from .observations import (
    StationDataset,
    common_epochs,
    common_satellite_summary,
    common_satellites,
    discover_observables,
    read_rinex2_observations,
)
from .provenance import (
    code_fingerprint,
    fingerprint,
    provenance_record,
    sha256_file,
)
from .reporting import write_csv, write_validation_reports
from .satellite_geometry import (
    Topocentric,
    geometry_table,
    parse_rinex3_gps_nav,
)
from .spatial import baseline_length_m, build_spatial_records, records_to_rows
from .troposphere import a_priori_slant
from .validation import loocv_folds, run_loocv

BLOCKED_MESSAGE = "SCIENTIFIC EXECUTION BLOCKED - PHASE 6 REQUIREMENTS NOT MET"
PROCESSED_SUBDIR = "processed/atmospheric-model"


def resolve_data_root(override: Path | None = None) -> Path:
    if override is not None:
        return override
    raw = os.environ.get("NLGCP_DATA_ROOT", "")
    if not raw:
        raise ModelBlocked(f"{BLOCKED_MESSAGE}: NLGCP_DATA_ROOT is not configured")
    root = Path(raw)
    if not root.is_dir():
        raise ModelBlocked(f"{BLOCKED_MESSAGE}: NLGCP_DATA_ROOT {root} is not a directory")
    return root


def git_commit(repo_root: Path) -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=repo_root, capture_output=True, text=True,
            timeout=10, check=False,
        )
        return out.stdout.strip() or "unknown"
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def experiment_dir(data_root: Path, experiment_id: str) -> Path:
    return data_root / PROCESSED_SUBDIR / "experiments" / experiment_id


def load_phase5_experiment(data_root: Path, phase5_id: str) -> dict[str, Any]:
    base = data_root / "processed" / "network-rtk" / "experiments" / phase5_id
    admission_path = base / "admission.json"
    if not base.is_dir() or not admission_path.is_file():
        raise ModelBlocked(
            f"{BLOCKED_MESSAGE}: Phase 5 experiment {phase5_id} admission not found "
            f"at {admission_path}"
        )
    admission = json.loads(admission_path.read_text(encoding="utf-8"))
    geometry_path = base / "geometry.json"
    geometry: dict[str, Any] = {}
    if geometry_path.is_file():
        geometry = json.loads(geometry_path.read_text(encoding="utf-8"))
    return {"dir": base, "admission": admission, "geometry": geometry}


def load_station_coordinates(data_root: Path) -> dict[str, StationCoordinate]:
    """Load verified IGS20 station coordinates (Phase 2/3 provenance)."""
    path = data_root / "processed" / "single-base" / "derived-coordinates.json"
    if not path.is_file():
        raise ModelBlocked(
            f"{BLOCKED_MESSAGE}: verified coordinates not found at {path}"
        )
    payload = json.loads(path.read_text(encoding="utf-8"))
    coords: dict[str, StationCoordinate] = {}
    stations = payload.get("stations", payload) if isinstance(payload, dict) else []
    items = stations.items() if isinstance(stations, dict) else []
    for station_id, entry in items:
        if not isinstance(entry, dict):
            continue
        raw_ecef = entry.get("ecef") or entry.get("xyz") or entry.get("coordinate_ecef")
        seq: Any = (
            (raw_ecef.get("x_m"), raw_ecef.get("y_m"), raw_ecef.get("z_m"))
            if isinstance(raw_ecef, dict)
            else raw_ecef
        )
        try:
            xyz = (float(seq[0]), float(seq[1]), float(seq[2]))
        except (TypeError, ValueError, IndexError):
            continue
        coords[str(station_id)] = StationCoordinate(
            station_id=str(station_id),
            x_m=xyz[0],
            y_m=xyz[1],
            z_m=xyz[2],
            frame=str(entry.get("reference_frame", entry.get("frame", "IGS20"))),
            epoch=str(entry.get("coordinate_epoch", entry.get("epoch", ""))),
        )
    return coords


def admit_experiment(
    data_root: Path,
    definition: ModelExperimentDefinition,
    repo_root: Path,
) -> dict[str, Any]:
    """Fail-closed admission: Phase 5 ACCEPT + verified coordinates + files."""
    problems = definition.validate()
    phase5 = load_phase5_experiment(data_root, definition.phase5_experiment_id)
    admitted = {
        str(item.get("station_id")): item
        for item in phase5["admission"].get("admitted", [])
        if isinstance(item, dict)
    }
    needed = [*definition.reference_stations, definition.target_station]
    for station in needed:
        item = admitted.get(station)
        if item is None:
            problems.append(f"station {station} not admitted in Phase 5 experiment")
            continue
        if item.get("qc_status") != "ACCEPT":
            problems.append(f"station {station} Phase 5 QC status {item.get('qc_status')}")
        obs = item.get("observation_path") or item.get("observation_sha256") or ""
        if obs and not Path(str(item.get("observation_path", ""))).is_file():
            problems.append(f"station {station} RINEX observation file missing")
    coords = load_station_coordinates(data_root)
    for station in needed:
        if station not in coords:
            problems.append(f"station {station} lacks verified coordinates")
    status = StageStatus.BLOCKED if problems else StageStatus.COMPLETE
    body = {
        "experiment_id": definition.experiment_id,
        "phase5_experiment_id": definition.phase5_experiment_id,
        "status": str(status),
        "problems": problems,
        "admitted_stations": sorted(set(needed) & set(admitted)),
        "phase5_admission_fingerprint": fingerprint(phase5["admission"]),
        "coordinate_frame": definition.coordinate_frame,
    }
    return body


def _station_rinex_paths(data_root: Path, definition: ModelExperimentDefinition) -> dict[str, Path]:
    phase5 = load_phase5_experiment(data_root, definition.phase5_experiment_id)
    paths: dict[str, Path] = {}
    for item in phase5["admission"].get("admitted", []):
        sid = str(item.get("station_id", ""))
        if sid in {*definition.reference_stations, definition.target_station}:
            paths[sid] = Path(str(item.get("observation_path", "")))
    return paths


def _nav_path(
    data_root: Path, definition: ModelExperimentDefinition
) -> tuple[Path | None, str | None]:
    phase5 = load_phase5_experiment(data_root, definition.phase5_experiment_id)
    for item in phase5["admission"].get("admitted", []):
        nav = item.get("navigation_path")
        sha = item.get("navigation_sha256")
        if nav:
            candidate = Path(str(nav))
            if not candidate.is_absolute():
                candidate = data_root / candidate
            return candidate, (str(sha) if sha else None)
    return None, None


def inspect_experiment(
    data_root: Path, definition: ModelExperimentDefinition, repo_root: Path
) -> dict[str, Any]:
    """Header-level observable audit (fast; parses RINEX headers only)."""
    admission = admit_experiment(data_root, definition, repo_root)
    if admission["status"] != str(StageStatus.COMPLETE):
        return {"admission": admission, "status": str(StageStatus.BLOCKED)}
    from .observations import parse_rinex2_header

    paths = _station_rinex_paths(data_root, definition)
    headers: dict[str, Any] = {}
    for station, path in paths.items():
        if not path.is_file():
            headers[station] = {"available": False, "reason": "RINEX file missing"}
            continue
        header = parse_rinex2_header(path)
        headers[station] = {
            "available": True,
            "observation_codes": list(header.obs_types),
            "interval_s": header.interval_s,
            "time_of_first_obs": header.time_of_first_obs,
            "sha256": sha256_file(path),
        }
    common_codes = None
    for info in headers.values():
        if not info.get("available"):
            continue
        codes = set(info["observation_codes"])
        common_codes = codes if common_codes is None else (common_codes & codes)
    return {
        "admission": admission,
        "status": str(StageStatus.COMPLETE),
        "headers": headers,
        "common_observation_codes": sorted(common_codes or []),
        "gps_l1_l2_compatible": bool(common_codes and {"L1", "L2"} <= common_codes),
        "pos_satellite_fields_available": False,
        "pos_limitation": (
            "RTKLIB .pos outputs provide position-domain residuals only; "
            "satellite-level observables come from RINEX extraction"
        ),
    }


def plan_experiment(
    data_root: Path, definition: ModelExperimentDefinition, repo_root: Path
) -> dict[str, Any]:
    admission = admit_experiment(data_root, definition, repo_root)
    coords = load_station_coordinates(data_root) if admission["status"] == str(
        StageStatus.COMPLETE
    ) else {}
    needed = [*definition.reference_stations, definition.target_station]
    geometry: dict[str, Any] = {"baselines_m": {}, "centroid_m": None}
    points = [coords[s] for s in needed if s in coords]
    if len(points) >= 2:
        for ref in definition.reference_stations:
            if ref in coords and definition.target_station in coords:
                a = coords[ref]
                b = coords[definition.target_station]
                geometry["baselines_m"][f"{ref}->{definition.target_station}"] = (
                    baseline_length_m((a.x_m, a.y_m, a.z_m), (b.x_m, b.y_m, b.z_m))
                )
    folds = loocv_folds(needed)
    return {
        "experiment_id": definition.experiment_id,
        "definition": definition.as_dict(),
        "admission": admission,
        "status": admission["status"],
        "geometry": geometry,
        "loocv_folds": folds,
        "models": list(METHOD_NAMES),
        "outputs": str(experiment_dir(data_root, definition.experiment_id)),
        "code_fingerprint": code_fingerprint(repo_root),
    }


def _definition_fingerprint(
    definition: ModelExperimentDefinition, repo_root: Path, extra: dict[str, Any]
) -> str:
    return fingerprint({
        "definition": definition.as_dict(),
        "code_fingerprint": code_fingerprint(repo_root),
        "pipeline_version": PIPELINE_VERSION,
        "extra": extra,
    })


def derive_experiment(
    data_root: Path,
    definition: ModelExperimentDefinition,
    repo_root: Path,
    *,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Extract satellite observables, combinations, and spatial records."""
    out = experiment_dir(data_root, definition.experiment_id)
    admission = admit_experiment(data_root, definition, repo_root)
    if admission["status"] != str(StageStatus.COMPLETE):
        return {"admission": admission, "status": str(StageStatus.BLOCKED)}
    if dry_run:
        return {"admission": admission, "status": "PLANNED", "outputs": str(out)}
    out.mkdir(parents=True, exist_ok=True)
    (out / "definition.json").write_text(
        json.dumps(definition.as_dict(), indent=2, sort_keys=True), encoding="utf-8"
    )
    (out / "admission.json").write_text(
        json.dumps(admission, indent=2, sort_keys=True), encoding="utf-8"
    )
    coords = load_station_coordinates(data_root)
    needed = [*definition.reference_stations, definition.target_station]
    coord_xyz = {
        s: (coords[s].x_m, coords[s].y_m, coords[s].z_m) for s in needed
    }
    paths = _station_rinex_paths(data_root, definition)
    input_hashes = {s: sha256_file(p) for s, p in paths.items()}
    nav_path, nav_recorded_sha = _nav_path(data_root, definition)
    nav_hash: str | None = None
    if nav_path is not None and nav_path.is_file():
        nav_hash = sha256_file(nav_path)

    key = _definition_fingerprint(definition, repo_root, {
        "inputs": input_hashes, "nav": nav_hash, "stage": "derive",
    })
    status_path = out / "derive-status.json"
    if status_path.is_file():
        stored = json.loads(status_path.read_text(encoding="utf-8"))
        derive_key = stored.get("derive_key")
        records_ready = (out / "residuals" / "spatial-records.csv").is_file()
        if derive_key == key and records_ready:
            return {**stored, "reused": True}

    datasets: dict[str, StationDataset] = {}
    for station in needed:
        datasets[station] = read_rinex2_observations(
            paths[station], station, stride=definition.epoch_stride
        )
    discovery = discover_observables(datasets)
    epochs = [e for e in common_epochs(datasets)]
    common_dir = out / "common-observations"
    common_dir.mkdir(parents=True, exist_ok=True)
    summary = common_satellite_summary(datasets, epochs, stations=needed)
    (common_dir / "summary.json").write_text(
        json.dumps({"discovery": discovery, "common": summary,
                    "common_epoch_count": len(epochs)}, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    with (common_dir / "per-epoch-common.csv").open("w", newline="", encoding="utf-8") as handle:
        epoch_writer = csv.writer(handle)
        epoch_writer.writerow(["epoch", "common_satellites", "gps_l1l2_common"])
        for epoch, total, gps in zip(
            epochs, summary["common_satellites_per_epoch"],
            summary["gps_l1l2_common_per_epoch"], strict=True,
        ):
            epoch_writer.writerow([epoch, total, gps])

    # Effective sampling step per station (header interval x stride): the
    # arc-segmentation gap test must use the decimated spacing, otherwise
    # every kept epoch would open a spurious new arc.
    step_by_station = {
        station: (datasets[station].header.interval_s or 30.0) * definition.epoch_stride
        for station in needed
    }
    iono_dir = out / "ionosphere"
    iono_dir.mkdir(parents=True, exist_ok=True)

    # Station-level arc-detrended GF series (diagnostic + audit trail of the
    # segmentation: every value carries its arc id).
    station_rows: list[dict[str, Any]] = []
    for station in needed:
        sats = sorted(
            {s for e in epochs for s in datasets[station].data.get(e, {}) if s.startswith("G")}
        )
        for sat in sats:
            for epoch, gf, arc, detr in station_gf_arcs(
                datasets[station], sat,
                slip_threshold_m=definition.gf_slip_threshold_m,
                step_s=step_by_station[station],
            ):
                station_rows.append({
                    "epoch": epoch, "station": station, "satellite": sat,
                    "gf_m": gf, "gf_detrended_m": detr, "arc_id": arc,
                    "codes": "L1,L2",
                })
    with (iono_dir / "station-gf.csv").open("w", newline="", encoding="utf-8") as handle:
        station_writer = csv.DictWriter(handle, fieldnames=[
            "epoch", "station", "satellite", "gf_m", "gf_detrended_m",
            "arc_id", "codes",
        ])
        station_writer.writeheader()
        station_writer.writerows(station_rows)

    # Ionospheric single-differenced proxies for every station pair.
    pairs = [(needed[i], needed[j]) for i in range(len(needed)) for j in range(i + 1, len(needed))]
    pair_rows: list[dict[str, Any]] = []
    pair_status: dict[str, Any] = {}
    for sta_a, sta_b in pairs:
        dist = baseline_length_m(coord_xyz[sta_a], coord_xyz[sta_b])
        sats = sorted({s for e in epochs for s in common_satellites(
            datasets, e, stations=[sta_a, sta_b], require_l1_l2=True)})
        count = 0
        step_pair = max(step_by_station[sta_a], step_by_station[sta_b])
        for sat in sats:
            samples = pair_sd_proxies(
                datasets[sta_a], datasets[sta_b], sat,
                slip_threshold_m=definition.gf_slip_threshold_m,
                step_s=step_pair,
            )
            for row in spatial_gradient_proxy(samples, dist):
                pair_rows.append({
                    "epoch": row["epoch_iso"], "satellite": row["satellite_id"],
                    "pair": f"{sta_a}-{sta_b}", "baseline_m": dist,
                    "value_m": row["value_m"], "value_tecu": row["value_tecu"],
                    "gradient_m_per_km": row["gradient_m_per_km"],
                    "kind": row["kind"], "method": row["derivation_method"],
                    "codes": ",".join(row["input_obs_codes"]),
                })
                count += 1
        pair_status[f"{sta_a}-{sta_b}"] = {
            "baseline_m": dist, "sample_count": count,
            "satellites": sats,
            "status": str(StageStatus.COMPLETE if count else StageStatus.BLOCKED),
        }
    with (iono_dir / "pair-sd.csv").open("w", newline="", encoding="utf-8") as handle:
        pair_writer = csv.DictWriter(handle, fieldnames=[
            "epoch", "satellite", "pair", "baseline_m", "value_m", "value_tecu",
            "gradient_m_per_km", "kind", "method", "codes",
        ])
        pair_writer.writeheader()
        pair_writer.writerows(pair_rows)
    (iono_dir / "summary.json").write_text(
        json.dumps(pair_status, indent=2, sort_keys=True), encoding="utf-8"
    )

    # Tropospheric a priori terms (needs broadcast ephemeris + geometry).
    tropo_dir = out / "troposphere"
    tropo_dir.mkdir(parents=True, exist_ok=True)
    tropo_status: dict[str, Any] = {"status": str(StageStatus.BLOCKED), "reasons": []}
    tropo_by_epoch_sat_station: dict[tuple[str, str, str], float] = {}
    elev_by_epoch_sat_station: dict[tuple[str, str, str], float] = {}
    azim_by_epoch_sat_station: dict[tuple[str, str, str], float] = {}
    if nav_path is None or not nav_path.is_file():
        tropo_status["reasons"].append("broadcast navigation file unavailable")
    elif nav_hash is None:
        tropo_status["reasons"].append("navigation hash could not be established")
    else:
        nav_records = parse_rinex3_gps_nav(nav_path)
        if not nav_records:
            tropo_status["reasons"].append("no GPS broadcast records parsed from nav file")
        else:
            gps_sats = sorted({s for e in epochs for s in common_satellites(
                datasets, e, stations=needed, require_l1_l2=True)})
            rows_geo, exclusions = geometry_table(
                epochs=epochs, satellites=gps_sats,
                station_coords=coord_xyz, nav_records=nav_records, nav_hash=nav_hash,
            )
            geo_by_key: dict[tuple[str, str, str], Topocentric] = {
                (r.epoch_iso, r.satellite_id, r.station_id): r for r in rows_geo
            }
            tropo_rows: list[dict[str, Any]] = []
            for (epoch, sat, station), geo in geo_by_key.items():
                if geo.elevation_deg < definition.min_elevation_deg:
                    continue
                term = a_priori_slant(
                    station_id=station, satellite_id=sat, epoch_iso=epoch,
                    elevation_deg=geo.elevation_deg,
                    station_ecef_m=coord_xyz[station], doy=definition.day_of_year,
                )
                tropo_by_epoch_sat_station[(epoch, sat, station)] = term.slant_total_m
                elev_by_epoch_sat_station[(epoch, sat, station)] = geo.elevation_deg
                azim_by_epoch_sat_station[(epoch, sat, station)] = geo.azimuth_deg
                tropo_rows.append({
                    "epoch": epoch, "satellite": sat, "station": station,
                    "elevation_deg": geo.elevation_deg, "azimuth_deg": geo.azimuth_deg,
                    "zhd_m": term.zenith_hydrostatic_m, "zwd_m": term.zenith_wet_m,
                    "slant_m": term.slant_total_m,
                    "meteorology": term.meteorology_source,
                })
            with (tropo_dir / "apriori.csv").open("w", newline="", encoding="utf-8") as handle:
                tropo_writer = csv.DictWriter(handle, fieldnames=[
                    "epoch", "satellite", "station", "elevation_deg", "azimuth_deg",
                    "zhd_m", "zwd_m", "slant_m", "meteorology",
                ])
                tropo_writer.writeheader()
                tropo_writer.writerows(tropo_rows)
            (tropo_dir / "geometry-exclusions.json").write_text(
                json.dumps(exclusions[:5000], indent=2), encoding="utf-8"
            )
            tropo_status = {
                "status": str(StageStatus.COMPLETE if tropo_rows else StageStatus.BLOCKED),
                "reasons": [] if tropo_rows else ["no geometries above elevation mask"],
                "nav_hash": nav_hash,
                "nav_recorded_sha256": nav_recorded_sha,
                "nav_hash_match": (nav_recorded_sha in (None, nav_hash)),
                "term_count": len(tropo_rows),
                "exclusion_count": len(exclusions),
            }
    (tropo_dir / "summary.json").write_text(
        json.dumps(tropo_status, indent=2, sort_keys=True), encoding="utf-8"
    )

    # Spatial records: iono SD vs datum reference + trop SD vs datum.
    # The datum station's single difference against itself is identically
    # zero, so one explicit zero record per (epoch, satellite) anchors the
    # differential field at the datum. Without it the datum fold of the
    # leave-one-out validation would have no observed target values and the
    # planar fit at the target would never see three references.
    res_dir = out / "residuals"
    res_dir.mkdir(parents=True, exist_ok=True)
    datum = definition.reference_stations[0]
    records: list[Any] = []
    datum_emitted: set[tuple[str, str]] = set()
    for row in pair_rows:
        epoch, sat = row["epoch"], row["satellite"]
        if (epoch, sat) not in datum_emitted:
            datum_emitted.add((epoch, sat))
            records.extend(build_spatial_records(
                epoch_iso=epoch, satellite_id=sat, constellation=sat[0] if sat else "?",
                target=coords[definition.target_station],
                references=[coords[datum]],
                iono_by_station={datum: 0.0}, tropo_by_station={datum: 0.0},
                elevation_by_station={datum: elev_by_epoch_sat_station.get((epoch, sat, datum))},
                azimuth_by_station={datum: azim_by_epoch_sat_station.get((epoch, sat, datum))},
                provenance=(
                    f"phase6 derive {definition.experiment_id}; "
                    f"datum {datum} self-difference identically zero"
                ),
            ))
        a, b = row["pair"].split("-", 1)
        for ref_station, other in ((a, b), (b, a)):
            # Only the non-datum side of a datum pair carries a measured
            # single difference; the datum side is identically zero and is
            # emitted once per (epoch, satellite) above.
            if ref_station == datum or other != datum:
                continue
            value = row["value_m"] if ref_station == a else -row["value_m"]
            iono_map = {ref_station: value}
            tropo_map: dict[str, float | None] = {}
            t_key = (epoch, sat, ref_station)
            d_key = (epoch, sat, datum)
            if t_key in tropo_by_epoch_sat_station and d_key in tropo_by_epoch_sat_station:
                tropo_map[ref_station] = (
                    tropo_by_epoch_sat_station[t_key] - tropo_by_epoch_sat_station[d_key]
                )
            elev_map = {ref_station: elev_by_epoch_sat_station.get(t_key)}
            azim_map = {ref_station: azim_by_epoch_sat_station.get(t_key)}
            records.extend(build_spatial_records(
                epoch_iso=epoch, satellite_id=sat, constellation=sat[0] if sat else "?",
                target=coords[definition.target_station],
                references=[coords[ref_station]],
                iono_by_station=iono_map, tropo_by_station=tropo_map,
                elevation_by_station=elev_map, azimuth_by_station=azim_map,
                provenance=(
                    f"phase6 derive {definition.experiment_id}; "
                    f"datum {datum}; iono {row['kind']}"
                ),
            ))
    rows = records_to_rows(records)
    with (res_dir / "spatial-records.csv").open("w", newline="", encoding="utf-8") as handle:
        record_writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()) if rows else [
            "epoch", "satellite", "constellation", "reference_station", "target_station",
            "station_x_m", "station_y_m", "station_z_m", "baseline_length_m",
            "azimuth_deg", "elevation_deg", "ionosphere_proxy_m", "troposphere_proxy_m",
            "combined_residual_m", "quality_flags", "provenance",
        ])
        record_writer.writeheader()
        record_writer.writerows(rows)
    iono_complete = any(v["status"] == str(StageStatus.COMPLETE) for v in pair_status.values())
    if iono_complete:
        derive_status = StageStatus.COMPLETE if tropo_status["status"] == str(
            StageStatus.COMPLETE) else StageStatus.PARTIAL
    else:
        derive_status = StageStatus.BLOCKED
    result = {
        "experiment_id": definition.experiment_id,
        "status": str(derive_status),
        "derive_key": key,
        "admission": admission,
        "common_epoch_count": len(epochs),
        "ionosphere_pairs": pair_status,
        "troposphere": tropo_status,
        "spatial_record_count": len(rows),
        "provenance": provenance_record(
            inputs={"observation_sha256": input_hashes, "nav_sha256": nav_hash,
                    "phase5_admission_fingerprint": admission["phase5_admission_fingerprint"],
                    "station_coordinates": {
                        s: {"x_m": coords[s].x_m, "y_m": coords[s].y_m,
                            "z_m": coords[s].z_m, "frame": coords[s].frame,
                            "epoch": coords[s].epoch} for s in needed}},
            algorithm="phase6-derive-v1",
            parameters={"epoch_stride": definition.epoch_stride,
                        "min_elevation_deg": definition.min_elevation_deg,
                        "gf_slip_threshold_m": definition.gf_slip_threshold_m},
            code_fingerprint_value=code_fingerprint(repo_root),
            git_commit=git_commit(repo_root),
        ),
    }
    (out / "derive-status.json").write_text(
        json.dumps(result, indent=2, sort_keys=True, default=str), encoding="utf-8"
    )
    return {**result, "reused": False}


def fit_experiment(
    data_root: Path,
    definition: ModelExperimentDefinition,
    repo_root: Path,
    *,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Fit spatial models on satellite-derived proxies (never position RMSE)."""
    out = experiment_dir(data_root, definition.experiment_id)
    if dry_run:
        return {"status": "PLANNED", "outputs": str(out / "models")}
    derive_path = out / "derive-status.json"
    if not derive_path.is_file():
        return {"status": str(StageStatus.BLOCKED),
                "reason": "derive stage has not produced satellite-derived proxies"}
    derived = json.loads(derive_path.read_text(encoding="utf-8"))
    if derived.get("status") == str(StageStatus.BLOCKED):
        return {"status": str(StageStatus.BLOCKED),
                "reason": "no satellite-derived proxies; position RMSE is not a substitute"}
    import csv as _csv

    records: list[dict[str, Any]] = []
    with (out / "residuals" / "spatial-records.csv").open(encoding="utf-8") as handle:
        for row in _csv.DictReader(handle):
            # The target's own record (its observed differential proxy) must
            # never enter the reference set: predicting a station from its
            # own observed value (distance zero) would be leakage, not a
            # spatial model.
            if row["reference_station"] == definition.target_station:
                continue
            if row["reference_station"] not in definition.reference_stations:
                continue
            records.append(row)
    coords = load_station_coordinates(data_root)
    target_xyz = (coords[definition.target_station].x_m,
                  coords[definition.target_station].y_m,
                  coords[definition.target_station].z_m)
    # Group values per (epoch, satellite) across reference stations.
    from collections import defaultdict
    groups: dict[tuple[str, str], dict[str, float | None]] = defaultdict(dict)
    ref_xyz: dict[str, tuple[float, float, float]] = {}
    for row in records:
        ref = row["reference_station"]
        ref_xyz[ref] = (
            float(row["station_x_m"]), float(row["station_y_m"]), float(row["station_z_m"])
        )
        raw = row.get("combined_residual_m") or row.get("ionosphere_proxy_m")
        try:
            key = (row["epoch"], row["satellite"])
            if raw is None or raw == "":
                groups[key][ref] = None
            else:
                groups[key][ref] = float(cast(Any, raw))
        except (TypeError, ValueError):
            groups[(row["epoch"], row["satellite"])][ref] = None
    models_dir = out / "models"
    models_dir.mkdir(parents=True, exist_ok=True)
    predictions: list[dict[str, Any]] = []
    fitted = 0
    for (epoch, sat), values in sorted(groups.items()):
        refs = [(r, ref_xyz[r], values.get(r)) for r in sorted(values)]
        for model in METHOD_NAMES:
            pred = interpolate(
                model_name=model, epoch_iso=epoch, satellite_id=sat,
                target_station=definition.target_station, target_xyz=target_xyz,
                references=refs,
            )
            if pred.predicted_m is not None:
                fitted += 1
            predictions.append(prediction_to_row(pred))
    with (models_dir / "target-predictions.csv").open("w", newline="", encoding="utf-8") as handle:
        fields = ["epoch", "satellite", "target_station", "model", "predicted_m",
                  "observed_m", "residual_m", "extrapolated", "model_parameters", "reason"]
        pred_writer = csv.DictWriter(handle, fieldnames=fields)
        pred_writer.writeheader()
        pred_writer.writerows(predictions)
    status = StageStatus.COMPLETE if fitted else StageStatus.BLOCKED
    result = {
        "experiment_id": definition.experiment_id,
        "status": str(status),
        "prediction_count": len(predictions),
        "fitted_count": fitted,
        "models": list(METHOD_NAMES),
        "note": ("predictions of satellite-derived differential proxies at target; "
                 "not VRS corrections") if fitted else "no predictions could be fitted",
    }
    (models_dir / "fits.json").write_text(
        json.dumps(result, indent=2, sort_keys=True), encoding="utf-8"
    )
    return result


def validate_experiment(
    data_root: Path,
    definition: ModelExperimentDefinition,
    repo_root: Path,
    *,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Leave-one-out cross-validation + decorrelation + model comparison."""
    out = experiment_dir(data_root, definition.experiment_id)
    if dry_run:
        return {"status": "PLANNED", "outputs": str(out / "validation")}
    derive_path = out / "derive-status.json"
    if not derive_path.is_file():
        return {"status": str(StageStatus.BLOCKED), "reason": "derive stage missing"}
    derived = json.loads(derive_path.read_text(encoding="utf-8"))
    if derived.get("status") == str(StageStatus.BLOCKED):
        return {"status": str(StageStatus.BLOCKED),
                "reason": "no satellite-derived proxies to validate"}
    import csv as _csv
    from collections import defaultdict

    coords = load_station_coordinates(data_root)
    stations = [*definition.reference_stations, definition.target_station]
    coord_map = {s: (coords[s].x_m, coords[s].y_m, coords[s].z_m) for s in stations}
    # Observed term per (epoch, satellite, station): the datum-anchored
    # differential proxy from the spatial records (combined residual where
    # both components exist, else the ionospheric proxy). The datum
    # station's self-difference records (identically zero) are included so
    # that the datum-target fold is evaluable like every other rotation.
    records_path = out / "residuals" / "spatial-records.csv"
    obs_store: dict[tuple[str, str, str], float] = {}
    with records_path.open(encoding="utf-8") as handle:
        for row in _csv.DictReader(handle):
            raw = row.get("combined_residual_m") or row.get("ionosphere_proxy_m")
            if raw is None or raw == "":
                continue
            try:
                obs_store[(row["epoch"], row["satellite"], row["reference_station"])] = float(raw)
            except (TypeError, ValueError):
                continue
    epochs = sorted({e for e, _, _ in obs_store})
    satellites = sorted({s for _, s, _ in obs_store})
    loocv = run_loocv(epochs=epochs, satellites=satellites, coords=coord_map,
                      observed=obs_store)
    # Decorrelation: RMS SD proxy per pair vs baseline distance.
    iono_path = out / "ionosphere" / "pair-sd.csv"
    pair_values: dict[str, list[float]] = defaultdict(list)
    with iono_path.open(encoding="utf-8") as handle:
        for row in _csv.DictReader(handle):
            try:
                pair_values[row["pair"]].append(float(row["value_m"]))
            except (TypeError, ValueError):
                continue
    distances: list[float] = []
    rms_list: list[float] = []
    pair_rows: list[dict[str, Any]] = []
    for pair, values in sorted(pair_values.items()):
        a, b = pair.split("-", 1)
        dist = baseline_length_m(coord_map[a], coord_map[b])
        rms_value = rmse(values) if values else None
        if rms_value is None:
            continue
        distances.append(dist)
        rms_list.append(rms_value)
        pair_rows.append({"pair": pair, "baseline_m": dist, "rms_m": rms_value,
                          "count": len(values)})
    decorr = decorrelation_fit(distances, rms_list)
    validation_dir = out / "validation"
    validation_dir.mkdir(parents=True, exist_ok=True)
    evaluated = sum(f.get("evaluated", 0) for f in loocv["folds"])
    status = StageStatus.COMPLETE if evaluated else StageStatus.BLOCKED
    result = {
        "experiment_id": definition.experiment_id,
        "status": str(status),
        "loocv": loocv,
        "decorrelation": {**decorr, "pairs": pair_rows},
        "metrics_note": "bias/MAE/RMSE/std/correlation/coverage on satellite-derived proxies",
    }
    (validation_dir / "loocv.json").write_text(
        json.dumps(result, indent=2, sort_keys=True, default=str), encoding="utf-8"
    )
    reports = write_validation_reports(
        out,
        coord_map=coord_map,
        loocv=loocv,
        decorr={**decorr, "pairs": pair_rows},
        common_epoch_csv=out / "common-observations" / "per-epoch-common.csv",
    )
    result["reports"] = reports
    metrics_path = out / "metrics.json"
    metrics: dict[str, Any] = {}
    if metrics_path.is_file():
        metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
    metrics["validation"] = {
        "status": str(status), "best_model": loocv["best_model"],
        "models": loocv["models"], "decorrelation": decorr,
    }
    metrics_path.write_text(json.dumps(metrics, indent=2, sort_keys=True, default=str),
                            encoding="utf-8")
    return result


def summarize_data_root(data_root: Path) -> dict[str, Any]:
    base = data_root / PROCESSED_SUBDIR
    experiments: list[dict[str, Any]] = []
    if base.is_dir():
        experiments_dir = base / "experiments"
        children = sorted(experiments_dir.glob("*")) if experiments_dir.is_dir() else []
        for child in children:
            row: dict[str, Any] = {"experiment_id": child.name}
            for name in ("derive-status.json", "metrics.json", "validation/loocv.json",
                         "models/fits.json"):
                path = child / name
                if path.is_file():
                    try:
                        payload = json.loads(path.read_text(encoding="utf-8"))
                        row[name] = {
                            "status": payload.get("status"),
                            "best_model": payload.get("best_model")
                            or (payload.get("loocv") or {}).get("best_model"),
                        }
                    except (ValueError, OSError):
                        row[name] = {"status": "UNREADABLE"}
            experiments.append(row)
    payload = {"experiments": experiments, "processed_subdir": str(base)}
    # Machine-readable summary CSVs (regenerated deterministically).
    summaries_dir = base / "summaries"
    experiment_rows: list[dict[str, Any]] = []
    validation_rows: list[dict[str, Any]] = []
    gradient_rows: list[dict[str, Any]] = []
    for child in ([base / "experiments" / e["experiment_id"] for e in experiments]
                  if experiments else []):
        derive_path = child / "derive-status.json"
        derive: dict[str, Any] = {}
        if derive_path.is_file():
            try:
                derive = json.loads(derive_path.read_text(encoding="utf-8"))
            except (ValueError, OSError):
                derive = {}
        loocv_path = child / "validation" / "loocv.json"
        loocv_doc: dict[str, Any] = {}
        if loocv_path.is_file():
            try:
                loocv_doc = json.loads(loocv_path.read_text(encoding="utf-8"))
            except (ValueError, OSError):
                loocv_doc = {}
        loocv = loocv_doc.get("loocv", {}) if isinstance(loocv_doc, dict) else {}
        experiment_rows.append({
            "experiment_id": child.name,
            "derive_status": derive.get("status"),
            "common_epoch_count": derive.get("common_epoch_count"),
            "spatial_record_count": derive.get("spatial_record_count"),
            "best_model": loocv.get("best_model"),
            "comparison_keys": loocv.get("comparison_keys"),
        })
        for model in sorted(loocv.get("models") or {}):
            metrics = loocv["models"][model]
            validation_rows.append({
                "experiment_id": child.name,
                "model": model,
                "count": metrics.get("count"),
                "bias_m": metrics.get("bias_m"),
                "mae_m": metrics.get("mae_m"),
                "rmse_m": metrics.get("rmse_m"),
                "std_m": metrics.get("std_m"),
                "correlation_predicted_observed": metrics.get(
                    "correlation_predicted_observed"),
                "coverage_within_tolerance": metrics.get(
                    "coverage_within_tolerance"),
            })
        decorr = loocv_doc.get("decorrelation", {}) if isinstance(
            loocv_doc, dict) else {}
        for pair in decorr.get("pairs", []) or []:
            gradient_rows.append({
                "experiment_id": child.name,
                "pair": pair.get("pair"),
                "baseline_m": pair.get("baseline_m"),
                "rms_m": pair.get("rms_m"),
                "count": pair.get("count"),
            })
    if experiments:
        write_csv(summaries_dir / "model-experiments.csv", experiment_rows,
                  ["experiment_id", "derive_status", "common_epoch_count",
                   "spatial_record_count", "best_model", "comparison_keys"])
        write_csv(summaries_dir / "validation-results.csv", validation_rows,
                  ["experiment_id", "model", "count", "bias_m", "mae_m",
                   "rmse_m", "std_m", "correlation_predicted_observed",
                   "coverage_within_tolerance"])
        write_csv(summaries_dir / "spatial-gradients.csv", gradient_rows,
                  ["experiment_id", "pair", "baseline_m", "rms_m", "count"])
        payload["summaries"] = [str(summaries_dir / "model-experiments.csv"),
                                str(summaries_dir / "validation-results.csv"),
                                str(summaries_dir / "spatial-gradients.csv")]
    return payload


def load_definition_from_path(path: Path) -> ModelExperimentDefinition:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ModelBlocked(f"{BLOCKED_MESSAGE}: definition {path} is not a JSON object")
    return definition_from_dict(payload)
