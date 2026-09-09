"""Fail-closed admission, held-out synthesis and hash-checked resumability."""

from __future__ import annotations

import csv
import json
import math
import os
import platform
import subprocess
import tempfile
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from nlgcp_atmospheric_model.provenance import fingerprint, sha256_file, utc_now_iso
from nlgcp_single_base.coordinates import EcefCoordinate, ecef_to_geodetic

from . import VERSION, WATERMARK
from .geometry import build_adapter, geometry_batch, source_provenance
from .models import Blocked, Definition, anchor_selection, correction_gate
from .observations import SUPPORTED, WAVELENGTHS, Dataset, read_observations, transform


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise Blocked(f"expected JSON object: {path}")
    return value


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n")


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def checked_hash(path: Path, expected: Any) -> str:
    if not isinstance(expected, str) or len(expected) != 64 or not path.is_file():
        raise Blocked(f"missing input or recorded SHA-256: {path}")
    observed = sha256_file(path)
    if observed != expected:
        raise Blocked(f"input SHA-256 mismatch: {path}")
    return observed


def code_identity(repo: Path) -> dict[str, str]:
    paths = [repo / "pyproject.toml", repo / "scripts/run_vrs_generator.py"]
    for package in ("vrs_generator", "atmospheric_spatial_model", "single_base_rtk"):
        paths.extend((repo / "research" / package / "src").rglob("*.py"))
    paths.extend((repo / "research/vrs_generator/native").glob("*.c"))
    return {str(p.relative_to(repo)): sha256_file(p) for p in sorted(paths)}


def experiment_dir(root: Path, definition: Definition) -> Path:
    if not root.is_dir():
        raise Blocked("data root must be an existing directory")
    base = root / "processed/vrs/experiments"
    out = base / definition.experiment_id
    if not out.resolve().is_relative_to(root.resolve() / "processed/vrs/experiments"):
        raise Blocked("output path escapes the derived VRS directory")
    return out


def plan(root: Path, definition: Definition, repo: Path, source: Path) -> dict[str, Any]:
    """Inspect reference inputs without reading held-out observations."""
    out = experiment_dir(root, definition)
    p5 = root / "processed/network-rtk/experiments" / definition.source_network_experiment
    p6 = root / "processed/atmospheric-model/experiments" / definition.source_phase6_experiment
    network = read_json(p5 / "experiment.json")
    read_json(p5 / "geometry.json")
    if read_json(p5 / "validation.json").get("verdict") != "COMPLETE":
        raise Blocked("Phase 5 network validation incomplete")
    if (
        network.get("experiment_id") != definition.source_network_experiment
        or network.get("coordinate_frame") != definition.coordinate_frame
        or network.get("coordinate_epoch") != definition.coordinate_epoch
        or network.get("year") != definition.year
        or network.get("day_of_year") != definition.day_of_year
        or set(network.get("reference_stations", []) + [network.get("test_station")])
        != {*definition.reference_stations, definition.target_station}
    ):
        raise Blocked("Phase 5 network context mismatch")
    admission = read_json(p5 / "admission.json")
    if admission.get("diagnostic") or admission.get("qc_profile") != "network_rtk":
        raise Blocked("Phase 5 must be ACCEPT-only network_rtk admission")
    if (admission.get("year"), admission.get("day_of_year")) != (
        definition.year,
        definition.day_of_year,
    ):
        raise Blocked("Phase 5 admission date mismatch")
    sessions = {s["station_id"]: s for s in admission["admitted"]}
    target_session = sessions.get(definition.target_station)
    if target_session is None:
        raise Blocked("held-out target coordinate context absent from Phase 5")
    target_path = Path(target_session["observation_path"]).resolve()
    reference_hashes = []
    for station in definition.reference_stations:
        session = sessions.get(station)
        if session is None:
            raise Blocked(f"reference not admitted: {station}")
        if Path(session["observation_path"]).resolve() == target_path or session.get(
            "converted_sha256"
        ) == target_session.get("converted_sha256"):
            raise Blocked("target observation aliases a reference; held-out leakage")
        reference_hashes.append(session.get("converted_sha256"))
    if len(set(reference_hashes)) != len(reference_hashes):
        raise Blocked("duplicate reference observation content")
    records = read_json(root / "processed/single-base/derived-coordinates.json")
    coordinates = records["stations"]
    needed = (*definition.reference_stations, definition.target_station)
    xyz: dict[str, tuple[float, float, float]] = {}
    coordinate_records = {}
    qc_hashes = {}
    input_hashes = {}
    navigation: Path | None = None
    nav_hash = ""
    for station in needed:
        if station not in sessions or station not in coordinates:
            raise Blocked(f"station lacks admission/coordinate: {station}")
        session, coord = sessions[station], coordinates[station]
        if (
            coord.get("scientifically_valid") is not True
            or coord.get("reference_frame") != definition.coordinate_frame
            or coord.get("coordinate_epoch") != definition.coordinate_epoch
        ):
            raise Blocked(f"unverified or incompatible coordinate frame/epoch: {station}")
        x = coord["ecef"]
        vector = (float(x["x_m"]), float(x["y_m"]), float(x["z_m"]))
        if not all(math.isfinite(v) for v in vector) or math.hypot(*vector) == 0:
            raise Blocked("invalid ECEF coordinate")
        # Verify the actual PRIDE coordinate source, not just a claimed boolean.
        checked_hash(Path(coord["pos_file_path"]), coord.get("pos_file_sha256"))
        xyz[station] = vector
        coordinate_records[station] = coord
        if station == definition.target_station:
            continue  # target observations/QC never control synthesis membership
        qcpath = (
            root
            / "processed/qc/profiles/network_rtk/sessions"
            / str(definition.year)
            / station
            / f"{definition.day_of_year:03d}"
            / "qc-result.json"
        )
        qc = read_json(qcpath)
        if (
            session.get("qc_status") != "ACCEPT"
            or qc.get("overall_classification") != "ACCEPT"
            or qc.get("result_fingerprint") != session.get("phase4_result_fingerprint")
            or qc.get("qc_profile", {}).get("name") != "network_rtk"
        ):
            raise Blocked(f"current Phase 4 admission mismatch: {station}")
        obs = Path(session["observation_path"])
        input_hashes[station] = checked_hash(obs, session.get("converted_sha256"))
        if qc.get("conversion", {}).get("converted_sha256") != input_hashes[station]:
            raise Blocked("QC conversion hash mismatch")
        qc_hashes[station] = {
            "file_sha256": sha256_file(qcpath),
            "result_fingerprint": session["phase4_result_fingerprint"],
        }
        candidate = root / session["navigation_path"]
        candidate_hash = checked_hash(candidate, session.get("navigation_sha256"))
        if navigation is not None and candidate_hash != nav_hash:
            raise Blocked("reference navigation products disagree")
        navigation, nav_hash = candidate, candidate_hash
    p6_definition = read_json(p6 / "definition.json")
    if (
        p6_definition.get("phase5_experiment_id") != definition.source_network_experiment
        or p6_definition.get("year") != definition.year
        or p6_definition.get("day_of_year") != definition.day_of_year
        or p6_definition.get("coordinate_frame") != definition.coordinate_frame
        or p6_definition.get("coordinate_epoch") != definition.coordinate_epoch
        or set(p6_definition.get("reference_stations", []) + [p6_definition.get("target_station")])
        != set(needed)
    ):
        raise Blocked("Phase 6 experiment context mismatch")
    derived = read_json(p6 / "derive-status.json")
    derivation_inputs = derived.get("provenance", {}).get("inputs", {})
    if derived.get("status") != "COMPLETE" or derivation_inputs.get("nav_sha256") != nav_hash:
        raise Blocked("Phase 6 derivation/navigation mismatch")
    for station in definition.reference_stations:
        if derivation_inputs.get("observation_sha256", {}).get(station) != input_hashes[station]:
            raise Blocked("Phase 6 observation source mismatch")
        old = derivation_inputs.get("station_coordinates", {}).get(station, {})
        if tuple(old.get(k) for k in ("x_m", "y_m", "z_m")) != xyz[station]:
            raise Blocked("Phase 6 coordinate mismatch")
    gate = correction_gate(
        read_json(p6 / "validation/loocv.json"), definition.correction_model, definition.diagnostic
    )
    phase_hashes = {
        "phase5/" + str(p.relative_to(p5)): sha256_file(p) for p in sorted(p5.glob("*.json"))
    }
    phase_hashes.update(
        {
            "phase6/" + name: sha256_file(p6 / name)
            for name in (
                "definition.json",
                "admission.json",
                "derive-status.json",
                "validation/loocv.json",
                "models/target-predictions.csv",
            )
        }
    )
    target = xyz[definition.target_station]
    llh = ecef_to_geodetic(EcefCoordinate(*target))
    target_record = {
        "station": definition.target_station,
        "target_ecef": target,
        "target_latitude": llh.latitude_deg,
        "target_longitude": llh.longitude_deg,
        "target_height": llh.height_m,
        "coordinate_frame": definition.coordinate_frame,
        "coordinate_epoch": definition.coordinate_epoch,
        "ellipsoid": "WGS84 ellipsoid for LLH representation; ECEF frame stays IGS20",
        "source": coordinate_records[definition.target_station],
    }
    material = {
        "definition": definition.model_dump(mode="json"),
        "target": target_record,
        "reference_coordinates": {s: coordinate_records[s] for s in definition.reference_stations},
        "source_observation_sha256": input_hashes,
        "navigation_sha256": nav_hash,
        "phase4_qc": qc_hashes,
        "source_experiments": phase_hashes,
        "software_sources": code_identity(repo),
        "rtklib": source_provenance(source),
        "algorithm_version": VERSION,
        "python": platform.python_version(),
        "correction_gate": gate,
    }
    return {
        "status": "PLANNED",
        "experiment_id": definition.experiment_id,
        "virtual_station_id": definition.virtual_id,
        "outputs": str(out),
        "definition": {
            **definition.model_dump(mode="json"),
            **{
                k: target_record[k]
                for k in ("target_latitude", "target_longitude", "target_height", "target_ecef")
            },
            "navigation_product": str(navigation),
            "correction_model_validation_status": gate["validation_status"],
            "software_provenance": material["rtklib"],
        },
        "target": target_record,
        "anchor": anchor_selection({s: xyz[s] for s in definition.reference_stations}, target),
        "admission": {
            "status": "ACCEPT",
            "references": definition.reference_stations,
            "phase4_thresholds": "PROVISIONAL",
            "qc": qc_hashes,
        },
        "correction_model": gate,
        "material": material,
        "fingerprint": fingerprint(material),
        "coordinates": xyz,
        "observations": {s: sessions[s]["observation_path"] for s in definition.reference_stations},
        "navigation": str(navigation),
    }


def synthesis_rows(
    definition: Definition,
    datasets: dict[str, Dataset],
    anchor: str,
    geometry: dict[tuple[str, str], dict[str, Any]],
    provenance_id: str,
) -> tuple[list[dict[str, Any]], Counter[str]]:
    if set(datasets) != set(definition.reference_stations) or definition.target_station in datasets:
        raise Blocked("synthesis dataset membership must match references exactly; target leakage")
    start, end = definition.window()
    epochs = sorted(set.intersection(*(set(d.data) for d in datasets.values())))
    rows: list[dict[str, Any]] = []
    exclusions: Counter[str] = Counter()
    all_epochs = set.union(*(set(d.data) for d in datasets.values()))
    exclusions["epoch absent from at least one reference"] = len(all_epochs - set(epochs))
    common_codes = set.intersection(*(set(d.codes) for d in datasets.values()))
    for code in sorted(set.union(*(set(d.codes) for d in datasets.values())) - set(SUPPORTED)):
        exclusions[f"unsupported observation code {code}"] += 1
    for epoch in epochs:
        moment = datetime.fromisoformat(epoch)
        if (
            not start <= moment <= end
            or (moment - start).total_seconds() % definition.sampling_interval
        ):
            continue
        satellites = set.intersection(*(set(d.data[epoch]) for d in datasets.values()))
        all_sats = set.union(*(set(d.data[epoch]) for d in datasets.values()))
        exclusions["satellite absent from at least one reference"] += len(all_sats - satellites)
        for satellite in sorted(satellites):
            if not satellite.startswith("G"):
                exclusions["non-GPS constellation unsupported"] += 1
                continue
            geo = geometry.get((epoch, satellite), {"reason": "no compatible anchor pseudorange"})
            if geo.get("reason"):
                exclusions[str(geo["reason"])] += 1
                continue
            for code in SUPPORTED:
                if code not in common_codes or any(
                    code not in d.data[epoch][satellite] for d in datasets.values()
                ):
                    exclusions[f"missing compatible {code} reference observation"] += 1
                    continue
                observation = datasets[anchor].data[epoch][satellite][code]
                # RINEX bit 1 denotes half-cycle ambiguity. Preserve in source,
                # exclude from relative full-cycle output; bit 0 starts an arc.
                if code.startswith("L") and (observation.lli or 0) & 2:
                    exclusions["anchor phase half-cycle ambiguity"] += 1
                    continue
                value = transform(
                    code,
                    observation.value,
                    geo["geometric_transformation_m"],
                    geo["satellite_clock_translation_m"],
                )
                rows.append(
                    {
                        "epoch_gpst": epoch,
                        "satellite": satellite,
                        "observation_code": code,
                        "virtual_station_id": definition.virtual_id,
                        "anchor_station": anchor,
                        "source_observation": observation.value,
                        "source_observation_sha256": "",
                        "provenance_id": provenance_id,
                        "virtual_observation": value,
                        "unit": "cycle" if code in WAVELENGTHS else "m",
                        "wavelength_m": WAVELENGTHS.get(code),
                        "source_lli": observation.lli,
                        "source_ssi": observation.ssi,
                        "epoch_flag": observation.epoch_flag,
                        "ionosphere_correction_m": 0.0,
                        "troposphere_correction_m": 0.0,
                        "ambiguity_policy": "ANCHOR_RELATIVE_FLOAT"
                        if code in WAVELENGTHS
                        else "N/A",
                        "quality_flags": WATERMARK + ";ANCHOR_CLOCK_AND_HARDWARE_INHERITED",
                        **geo,
                    }
                )
    return rows, exclusions


def read_verified_outputs(out: Path, expected: str) -> dict[str, Any]:
    manifest = read_json(out / "completion.json")
    if manifest.get("fingerprint") != expected:
        raise Blocked("material fingerprint changed; use a new experiment_id")
    for name, digest in manifest.get("output_sha256", {}).items():
        if Path(name).name != name:
            raise Blocked("unsafe output manifest")
        checked_hash(out / name, digest)
    required = {
        "virtual-observations.csv",
        "provenance.json",
        "metrics.json",
        "definition.json",
        "admission.json",
        "target.json",
        "anchor.json",
        "correction-model.json",
        "exclusions.json",
    }
    if not required <= set(manifest.get("output_sha256", {})):
        raise Blocked("incomplete output manifest")
    return read_json(out / "metrics.json")


def generate(
    root: Path, definition: Definition, repo: Path, source: Path, *, dry_run: bool = False
) -> dict[str, Any]:
    planned = plan(root, definition, repo, source)
    if dry_run:
        return planned
    out = Path(planned["outputs"])
    if out.exists():
        return {
            **read_verified_outputs(out, planned["fingerprint"]),
            "reused": True,
            "outputs": str(out),
        }
    executable, build = build_adapter(repo, source)
    datasets = {s: read_observations(Path(p)) for s, p in planned["observations"].items()}
    for dataset in datasets.values():
        if definition.sampling_interval % dataset.interval:
            raise Blocked(
                "sampling interval must be an integer multiple of every reference interval"
            )
    anchor = planned["anchor"]["station"]
    epochs = sorted(set.intersection(*(set(d.data) for d in datasets.values())))
    requests = []
    start, end = definition.window()
    for epoch in epochs:
        moment = datetime.fromisoformat(epoch)
        if (
            not start <= moment <= end
            or (moment - start).total_seconds() % definition.sampling_interval
        ):
            continue
        for sat, observations in sorted(datasets[anchor].data[epoch].items()):
            if not sat.startswith("G") or not all(sat in d.data[epoch] for d in datasets.values()):
                continue
            code = next(
                (c for c in ("C1", "P1", "P2") if c in observations and observations[c].value > 0),
                None,
            )
            if code:
                requests.append((epoch, sat, observations[code].value))
    if not requests:
        raise Blocked("no common GPS epochs/satellites with anchor pseudorange")
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".vrs-", dir=out.parent) as temporary:
        temp = Path(temporary)
        geometries = geometry_batch(
            executable,
            Path(planned["navigation"]),
            planned["coordinates"][anchor],
            planned["coordinates"][definition.target_station],
            requests,
            temp,
        )
        geometry = {
            (e, s): {**g, "transmit_time_source_pseudorange_m": p}
            for (e, s, p), g in zip(requests, geometries, strict=True)
        }
        rows, exclusions = synthesis_rows(
            definition, datasets, anchor, geometry, planned["fingerprint"]
        )
        if not rows:
            raise Blocked("no virtual observations passed scientific gates")
        for row in rows:
            row["source_observation_sha256"] = planned["material"]["source_observation_sha256"][
                anchor
            ]
        write_csv(temp / "virtual-observations.csv", rows, list(rows[0]))
        epochs_out = sorted({r["epoch_gpst"] for r in rows})
        counts = Counter(r["epoch_gpst"] for r in rows if r["observation_code"] == "C1")
        expected = math.floor((end - start).total_seconds() / definition.sampling_interval) + 1
        metrics = {
            "status": "COMPLETE",
            "scope": "TECHNICAL_GEOMETRY_ONLY",
            "observation_nature": "VIRTUAL / SYNTHETIC DERIVED OBSERVATION",
            "watermark": WATERMARK,
            "experiment_id": definition.experiment_id,
            "virtual_observation_count": len(rows),
            "observation_codes": dict(sorted(Counter(r["observation_code"] for r in rows).items())),
            "epoch_count": len(epochs_out),
            "expected_epoch_count": expected,
            "epoch_coverage": len(epochs_out) / expected,
            "first_epoch_gpst": epochs_out[0],
            "last_epoch_gpst": epochs_out[-1],
            "satellite_count": len({r["satellite"] for r in rows}),
            "satellites": sorted({r["satellite"] for r in rows}),
            "code_satellites_per_epoch_min": min(counts.get(e, 0) for e in epochs_out),
            "code_satellites_per_epoch_max": max(counts.values(), default=0),
            "correction_mode": "ZERO",
            "rinex_generated": False,
            "anchor": planned["anchor"],
            "fingerprint": planned["fingerprint"],
        }
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
        dirty = bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=repo, text=True))
        provenance = {
            **planned["material"],
            "fingerprint": planned["fingerprint"],
            "execution_timestamp": utc_now_iso(),
            "git_commit": commit,
            "git_dirty": dirty,
            "build": build,
            "held_out_observations_used": False,
            "source_phase6_role": "validation veto only; no numeric field applied",
            "navigation_frame": "GPS broadcast WGS84; no IGS20 frame transform applied",
            "frame_limitation": (
                "broadcast/IGS20 realization mismatch unresolved; technical control only"
            ),
        }
        for name, value in (
            ("definition", planned["definition"]),
            ("admission", planned["admission"]),
            ("target", planned["target"]),
            ("anchor", planned["anchor"]),
            ("correction-model", planned["correction_model"]),
            ("provenance", provenance),
            ("metrics", metrics),
            ("exclusions", dict(sorted(exclusions.items()))),
        ):
            write_json(temp / f"{name}.json", value)
        # Detect source changes while processing before publishing a completed directory.
        if plan(root, definition, repo, source)["fingerprint"] != planned["fingerprint"]:
            raise Blocked("inputs changed during generation")
        write_json(
            temp / "completion.json",
            {
                "fingerprint": planned["fingerprint"],
                "output_sha256": {
                    p.name: sha256_file(p) for p in sorted(temp.iterdir()) if p.is_file()
                },
            },
        )
        os.rename(temp, out)
    return {**metrics, "outputs": str(out), "reused": False}
