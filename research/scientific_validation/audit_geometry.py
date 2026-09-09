"""Reproduce real coordinate, orbit, baseline and triangle audits (no raw writes).

Requires existing PROJ geod command and pinned RTKLIB; no Python dependency added.
Run: .venv/bin/python research/scientific_validation/audit_geometry.py
"""

import gzip
import itertools
import json
import math
import os
import subprocess
import tempfile
from pathlib import Path

import numpy as np
from nlgcp_atmospheric_model.interpolation import (
    barycentric_coordinates,
    plane_diagnostics,
    reference_triangle_area_m2,
)
from nlgcp_atmospheric_model.pipeline import load_station_coordinates
from nlgcp_atmospheric_model.provenance import sha256_file
from nlgcp_atmospheric_model.satellite_geometry import (
    broadcast_position,
    parse_rinex3_gps_nav,
    select_ephemeris,
)
from nlgcp_atmospheric_model.spatial import ecef_to_local_enu
from nlgcp_atmospheric_model.troposphere import niell_hydrostatic_mapping, niell_wet_mapping
from nlgcp_single_base.coordinates import EcefCoordinate, ecef_to_geodetic
from nlgcp_single_base.coordinates_derive import parse_pride_pos
from reference import build_reference

repo = Path(__file__).resolve().parents[2]
root = Path(os.environ.get("NLGCP_DATA_ROOT", "/home/excellence/nlgcp-data"))
source = Path(os.environ.get("RTKLIB_SOURCE", "/home/excellence/RTKLIB"))
exe, provenance = build_reference(repo, source)
coordinates = load_station_coordinates(root)
assert len(coordinates) == 4
original = json.loads((root / "processed/single-base/derived-coordinates.json").read_text())
xyz = {s: (v.x_m, v.y_m, v.z_m) for s, v in coordinates.items()}
llh = {s: ecef_to_geodetic(EcefCoordinate(*v)) for s, v in xyz.items()}


def reference(lines, nav=None):
    result = subprocess.run(
        [str(exe), *([str(nav)] if nav else [])],
        input="\n".join(lines) + "\n",
        text=True,
        capture_output=True,
        check=True,
    )
    return [list(map(float, r.split())) for r in result.stdout.splitlines()]


reference_llh = reference(["G " + " ".join(map(str, v)) for v in xyz.values()])
stations = []
for (s, v), ref in zip(llh.items(), reference_llh, strict=True):
    pos = original["stations"][s]
    assert sha256_file(Path(pos["pos_file_path"])) == pos["pos_file_sha256"]
    parsed = parse_pride_pos(Path(pos["pos_file_path"]))
    assert (parsed.ecef.x_m, parsed.ecef.y_m, parsed.ecef.z_m) == xyz[s]
    assert parsed.coordinate_epoch == pos["coordinate_epoch"]
    assert parsed.reference_frame == pos["reference_frame"]
    delta = [v.latitude_deg - ref[0], v.longitude_deg - ref[1], v.height_m - ref[2]]
    assert max(abs(delta[0]), abs(delta[1])) < 1e-8 and abs(delta[2]) < 1e-3
    stations.append(
        {
            "station": s,
            **pos,
            "geodetic_deg_deg_m": [v.latitude_deg, v.longitude_deg, v.height_m],
            "difference_vs_rtklib_deg_deg_m": delta,
            "eligibility": "VERIFIED",
        }
    )
historical = json.loads(
    (root / "processed/network-rtk/experiments/net-2024d026-phri-rover/geometry.json").read_text()
)
baselines = []
for a, b in itertools.combinations(sorted(xyz), 2):
    va, vb = llh[a], llh[b]
    output = subprocess.run(
        ["geod", "+ellps=WGS84", "-I", "-f", "%.12f"],
        input=f"{va.latitude_deg} {va.longitude_deg} {vb.latitude_deg} {vb.longitude_deg}\n",
        text=True,
        capture_output=True,
        check=True,
    ).stdout.split()
    chord = math.dist(xyz[a], xyz[b])
    independent = float(np.linalg.norm(np.subtract(xyz[a], xyz[b])))
    assert abs(chord - independent) < 1e-8
    baselines.append(
        {
            "pair": a + "-" + b,
            "ecef_chord_m": chord,
            "numpy_chord_m": independent,
            "geodesic_surface_m": float(output[2]),
            "historical_m": historical["baseline_matrix_m"][a][b],
            "difference_m": chord - historical["baseline_matrix_m"][a][b],
        }
    )
rotations = []
for target in sorted(xyz):
    refs = [s for s in sorted(xyz) if s != target]
    origin = tuple(float(x) for x in np.mean([xyz[s] for s in refs], axis=0))
    enu = {s: ecef_to_local_enu(xyz[s], origin) for s in xyz}
    tri = [enu[s][:2] for s in refs]
    bary = barycentric_coordinates(*tri, enu[target][:2])
    area = reference_triangle_area_m2([xyz[s] for s in refs], origin)
    independent = abs(float(np.linalg.det(np.array(tri[1:]) - tri[0]))) / 2
    assert abs(area - independent) < 1e-3
    condition = plane_diagnostics([(p[0], p[1], 0.0) for p in tri])
    distances = {s: math.dist(xyz[target], xyz[s]) for s in refs}
    edges = [math.dist(tri[i], tri[j]) for i, j in itertools.combinations(range(3), 2)]
    rotations.append(
        {
            "target": target,
            "references": refs,
            "origin_ecef_m": origin,
            "enu_m": enu,
            "area_m2": area,
            "area_km2": area / 1e6,
            "area_crosscheck_m2": independent,
            "longest_edge_to_altitude_ratio": max(edges) ** 2 / (2 * area),
            "barycentric": bary[:3],
            "containment": "BOUNDARY"
            if bary[3] and min(bary[:3]) <= 1e-9
            else ("INSIDE" if bary[3] else "OUTSIDE"),
            "classification": "INTERPOLATION" if bary[3] else "EXTRAPOLATION",
            "planar_diagnostics": condition,
            "anchor": min(distances, key=lambda s: (distances[s], s)),
            "candidate_distances_m": distances,
        }
    )
nav = root / "external-products/brdc/2024/BRDC00IGS_R_20240260000_01D_MN.rnx.gz"
nav_records = parse_rinex3_gps_nav(nav)
orbits = []
with tempfile.TemporaryDirectory(dir=repo / "build/scientific-validation") as tmp:
    path = Path(tmp) / "brdc.rnx"
    path.write_bytes(gzip.decompress(nav.read_bytes()))
    for tow in (432000.0, 438123.0, 475200.0, 518220.0):
        for sat in ("G01", "G03", "G10", "G22", "G32"):
            eph = select_ephemeris(nav_records.get(sat, []), 2298, tow)
            if eph is None:
                continue
            ref = reference([f"S 2298 {tow} {int(sat[1:])}"], path)[0]
            pos = broadcast_position(eph, 2298, tow)
            difference = math.dist(ref, pos)
            orbits.append(
                {
                    "satellite": sat,
                    "gps_week": 2298,
                    "tow_s": tow,
                    "ecef_m": pos,
                    "rtklib_ecef_m": ref,
                    "difference_m": difference,
                }
            )
            assert difference < 0.001, (sat, tow, difference)
nmf = []
for lat, h, elev, doy in itertools.product(
    (9.0, 22.5, 45.0, -52.5), (0.0, 500.0), (10.0, 45.0, 90.0), (26.0, 180.5)
):
    ref = reference([f"N {lat} {h} {elev} {doy}"])[0]
    calc = [
        niell_hydrostatic_mapping(elev, math.radians(lat), h, doy),
        niell_wet_mapping(elev, math.radians(lat)),
    ]
    err = max(abs(a - b) for a, b in zip(ref, calc, strict=True))
    assert err < 1e-12
    nmf.append(err)
result = {
    "status": "VERIFIED",
    "reference_provenance": provenance,
    "navigation_sha256": sha256_file(nav),
    "stations": stations,
    "baselines": baselines,
    "rotations": rotations,
    "satellite_checks": orbits,
    "nmf_checks": len(nmf),
    "nmf_max_difference": max(nmf),
    "notes": [
        "IGS20 coordinates retained; WGS84 ellipsoid does not transform reference frame.",
        "Geodesic is ellipsoid surface distance; chord is 3D marker separation including height.",
        "Phase 5 area is a 3D chord triangle (Heron); reviewed area is a common EN projection.",
        "Satellite comparison uses the same GPST epoch. Phase 6 mapping uses reception time.",
    ],
}
out = repo / "research/scientific_validation/evidence/geometry-audit.json"
out.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
print(
    json.dumps(
        {"stations": len(stations), "pairs": len(baselines), "orbits": len(orbits), "nmf": len(nmf)}
    )
)
