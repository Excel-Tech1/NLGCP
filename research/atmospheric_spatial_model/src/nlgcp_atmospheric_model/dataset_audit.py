"""Reproducible GNSS observation dataset audit and selection (Workstream A).

Inspects immutable RINEX 2.11 archives (read-only ZIP or filesystem) at BOTH
header level and actual observation-block level so silent single-frequency
outages (e.g., L2/P2 declared in header but 0% populated in records) are caught
before atmospheric modelling or VRS generation.
"""

from __future__ import annotations

import csv
import json
import math
import zipfile
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .provenance import sha256_file
from .spatial import baseline_length_m, ecef_to_local_enu


@dataclass(frozen=True, slots=True)
class StationSignalAudit:
    """Actual signal completeness observed in one RINEX 2.11 file."""

    station_id: str
    date_iso: str
    source_identifier: str
    file_sha256: str
    rinex_version: str
    interval_s: float | None
    time_system: str
    epoch_count_declared: int
    epochs_sampled: int
    receiver_type: str
    antenna_type: str
    antenna_delta_hen_m: tuple[float, float, float] | None
    approx_xyz_m: tuple[float, float, float] | None
    gps_obs_per_epoch: float
    glonass_obs_per_epoch: float
    gps_code_completeness: dict[str, float]
    glonass_code_completeness: dict[str, float]
    dual_frequency_gps_usable: bool
    dual_frequency_glonass_usable: bool
    exclusion_reasons: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["exclusion_reasons"] = list(self.exclusion_reasons)
        return payload


@dataclass(frozen=True, slots=True)
class WindowSelectionCandidate:
    """One candidate multi-station simultaneous observation day."""

    date_iso: str
    year: int
    doy: int
    dual_freq_stations: tuple[str, ...]
    excluded_stations: dict[str, str]
    interior_stations: tuple[str, ...]
    perimeter_stations: tuple[str, ...]
    hull_area_km2: float
    min_baseline_km: float
    max_baseline_km: float
    navigation_gps_path: str | None
    navigation_glonass_path: str | None
    coordinate_provenance: str
    role: str
    rationale: str

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["dual_freq_stations"] = list(self.dual_freq_stations)
        payload["interior_stations"] = list(self.interior_stations)
        payload["perimeter_stations"] = list(self.perimeter_stations)
        return payload


@dataclass(frozen=True, slots=True)
class DatasetSelectionManifest:
    """Reproducible manifest for selected primary/secondary/reference datasets."""

    schema_version: str
    archive_path: str
    archive_sha256: str
    total_files_audited: int
    stations_discovered: tuple[str, ...]
    primary_windows: tuple[WindowSelectionCandidate, ...]
    secondary_windows: tuple[WindowSelectionCandidate, ...]
    verified_reference_windows: tuple[WindowSelectionCandidate, ...]
    station_file_entries: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    known_limitations: tuple[str, ...] = field(default_factory=tuple)

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "archive_path": self.archive_path,
            "archive_sha256": self.archive_sha256,
            "total_files_audited": self.total_files_audited,
            "stations_discovered": list(self.stations_discovered),
            "primary_windows": [w.as_dict() for w in self.primary_windows],
            "secondary_windows": [w.as_dict() for w in self.secondary_windows],
            "verified_reference_windows": [w.as_dict() for w in self.verified_reference_windows],
            "station_file_entries": list(self.station_file_entries),
            "known_limitations": list(self.known_limitations),
        }


def convex_hull_2d(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Return counter-clockwise 2D convex hull vertices (Andrew's monotone chain)."""
    pts = sorted(set(points))
    if len(pts) <= 2:
        return pts

    def cross(o: tuple[float, float], a: tuple[float, float], b: tuple[float, float]) -> float:
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower: list[tuple[float, float]] = []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0.0:
            lower.pop()
        lower.append(p)
    upper: list[tuple[float, float]] = []
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0.0:
            upper.pop()
        upper.append(p)
    return lower[:-1] + upper[:-1]


def polygon_area_m2(polygon: list[tuple[float, float]]) -> float:
    """Shoelace area (m^2) for a simple 2D polygon in local ENU metres."""
    n = len(polygon)
    if n < 3:
        return 0.0
    acc = 0.0
    for i in range(n):
        x1, y1 = polygon[i]
        x2, y2 = polygon[(i + 1) % n]
        acc += x1 * y2 - x2 * y1
    return abs(acc) * 0.5


def point_in_convex_hull_2d(
    point: tuple[float, float],
    hull: list[tuple[float, float]],
    *,
    tol: float = 1e-6,
) -> bool:
    """Return True iff ``point`` lies inside or on the boundary of CCW convex ``hull``."""
    n = len(hull)
    if n < 3:
        return False
    for i in range(n):
        a = hull[i]
        b = hull[(i + 1) % n]
        cross = (b[0] - a[0]) * (point[1] - a[1]) - (b[1] - a[1]) * (point[0] - a[0])
        if cross < -tol:
            return False
    return True


def classify_network_geometry(
    station_coords: dict[str, tuple[float, float, float]],
) -> dict[str, Any]:
    """Compute ENU convex hull, hull area, baseline bounds, and LOOCV containment."""
    stations = sorted(station_coords)
    if len(stations) < 3:
        return {
            "stations": stations,
            "interior_stations": [],
            "perimeter_stations": stations,
            "hull_area_km2": 0.0,
            "min_baseline_km": 0.0,
            "max_baseline_km": 0.0,
            "containment_by_station": {s: False for s in stations},
        }
    centroid = (
        sum(station_coords[s][0] for s in stations) / len(stations),
        sum(station_coords[s][1] for s in stations) / len(stations),
        sum(station_coords[s][2] for s in stations) / len(stations),
    )
    enu = {s: ecef_to_local_enu(station_coords[s], centroid)[:2] for s in stations}
    full_hull = convex_hull_2d([enu[s] for s in stations])
    area_km2 = polygon_area_m2(full_hull) / 1e6

    containment: dict[str, bool] = {}
    for target in stations:
        refs = [s for s in stations if s != target]
        ref_hull = convex_hull_2d([enu[r] for r in refs])
        containment[target] = point_in_convex_hull_2d(enu[target], ref_hull)

    baselines: list[float] = []
    for i, a in enumerate(stations):
        for b in stations[i + 1 :]:
            baselines.append(baseline_length_m(station_coords[a], station_coords[b]) / 1000.0)

    interior = sorted(s for s, inside in containment.items() if inside)
    perimeter = sorted(s for s, inside in containment.items() if not inside)
    return {
        "stations": stations,
        "interior_stations": interior,
        "perimeter_stations": perimeter,
        "hull_area_km2": area_km2,
        "min_baseline_km": min(baselines) if baselines else 0.0,
        "max_baseline_km": max(baselines) if baselines else 0.0,
        "containment_by_station": containment,
    }


def audit_rinex2_signal_completeness(
    lines: list[str],
    *,
    station_id: str,
    date_iso: str,
    source_identifier: str,
    file_sha256: str,
    epoch_count_declared: int = 0,
    max_sample_epochs: int = 60,
    min_dual_freq_fraction: float = 0.75,
) -> StationSignalAudit:
    """Inspect RINEX 2.11 header and sample epochs to verify actual L1/L2/code presence."""
    obs_types: list[str] = []
    rinex_version = ""
    interval_s: float | None = None
    time_system = ""
    receiver_type = ""
    antenna_type = ""
    antenna_delta: tuple[float, float, float] | None = None
    approx_xyz: tuple[float, float, float] | None = None
    body_idx = 0

    for idx, line in enumerate(lines):
        label = line[60:].strip()
        if label == "RINEX VERSION / TYPE":
            rinex_version = line[:9].strip()
        elif label == "# / TYPES OF OBSERV":
            for k in range(6, 60, 6):
                tok = line[k : k + 6].strip()
                if tok:
                    obs_types.append(tok)
        elif label == "INTERVAL":
            try:
                interval_s = float(line[:10].strip())
            except ValueError:
                interval_s = None
        elif label == "TIME OF FIRST OBS":
            time_system = line[48:51].strip()
        elif label == "REC # / TYPE / VERS":
            receiver_type = line[20:40].strip()
        elif label == "ANT # / TYPE":
            antenna_type = line[20:40].strip()
        elif label == "ANTENNA: DELTA H/E/N":
            try:
                antenna_delta = (float(line[0:14]), float(line[14:28]), float(line[28:42]))
            except ValueError:
                antenna_delta = None
        elif label == "APPROX POSITION XYZ":
            try:
                approx_xyz = (float(line[0:14]), float(line[14:28]), float(line[28:42]))
            except ValueError:
                approx_xyz = None
        elif label == "END OF HEADER":
            body_idx = idx + 1
            break

    lps = max(1, (len(obs_types) + 4) // 5)
    sys_totals: Counter[str] = Counter()
    code_counts: Counter[tuple[str, str]] = Counter()
    epochs_sampled = 0
    pos = body_idx
    total_lines = len(lines)
    step_stride = max(1, (epoch_count_declared // max_sample_epochs) if epoch_count_declared else 1)
    epoch_ordinal = 0

    while pos < total_lines and epochs_sampled < max_sample_epochs:
        ln = lines[pos]
        pos += 1
        if not ln.strip():
            continue
        try:
            flag = int(ln[26:29])
            nsat = int(ln[29:32])
        except ValueError:
            continue
        if flag not in (0, 1):
            pos += max(0, nsat)
            continue
        sats_str = ln[32:].rstrip("\n")
        rem = max(0, nsat - 12)
        for _ in range((rem + 11) // 12):
            if pos >= total_lines:
                break
            sats_str += lines[pos][32:].rstrip("\n")
            pos += 1
        sats = [sats_str[k : k + 3].strip() for k in range(0, min(len(sats_str), nsat * 3), 3)]
        sample_this = (epoch_ordinal % step_stride) == 0
        epoch_ordinal += 1
        if not sample_this:
            pos += len(sats) * lps
            continue
        epochs_sampled += 1
        for sat in sats:
            blk = lines[pos : pos + lps]
            pos += lps
            if len(blk) < lps or not sat:
                continue
            const = sat[0]
            sys_totals[const] += 1
            for ci, code in enumerate(obs_types):
                row = blk[ci // 5]
                seg = row[(ci % 5) * 16 : (ci % 5) * 16 + 14].strip()
                if seg:
                    code_counts[(const, code)] += 1

    def completeness(const: str) -> dict[str, float]:
        denom = sys_totals[const]
        if denom == 0:
            return {c: 0.0 for c in obs_types}
        return {c: round(code_counts[(const, c)] / denom, 4) for c in obs_types}

    gps_comp = completeness("G")
    glo_comp = completeness("R")
    has_gps_dual = (
        gps_comp.get("L1", 0.0) >= min_dual_freq_fraction
        and gps_comp.get("L2", 0.0) >= min_dual_freq_fraction
        and max(gps_comp.get("C1", 0.0), gps_comp.get("P1", 0.0)) >= min_dual_freq_fraction
        and max(gps_comp.get("P2", 0.0), gps_comp.get("C2", 0.0)) >= min_dual_freq_fraction
    )
    has_glo_dual = (
        glo_comp.get("L1", 0.0) >= min_dual_freq_fraction
        and glo_comp.get("L2", 0.0) >= min_dual_freq_fraction
        and max(glo_comp.get("C1", 0.0), glo_comp.get("P1", 0.0)) >= min_dual_freq_fraction
        and max(glo_comp.get("P2", 0.0), glo_comp.get("C2", 0.0)) >= min_dual_freq_fraction
    )
    reasons: list[str] = []
    if not has_gps_dual:
        reasons.append(
            f"insufficient GPS dual-frequency data (L1={gps_comp.get('L1', 0.0):.2f}, "
            f"L2={gps_comp.get('L2', 0.0):.2f}, P2={gps_comp.get('P2', 0.0):.2f})"
        )
    if epoch_count_declared and epoch_count_declared < 2400:
        reasons.append(f"partial session ({epoch_count_declared} < 2400 epochs)")
    if time_system != "GPS":
        reasons.append(f"non-GPS time system: {time_system!r}")

    return StationSignalAudit(
        station_id=station_id,
        date_iso=date_iso,
        source_identifier=source_identifier,
        file_sha256=file_sha256,
        rinex_version=rinex_version,
        interval_s=interval_s,
        time_system=time_system,
        epoch_count_declared=epoch_count_declared or epochs_sampled,
        epochs_sampled=epochs_sampled,
        receiver_type=receiver_type,
        antenna_type=antenna_type,
        antenna_delta_hen_m=antenna_delta,
        approx_xyz_m=approx_xyz,
        gps_obs_per_epoch=round(sys_totals["G"] / max(1, epochs_sampled), 2),
        glonass_obs_per_epoch=round(sys_totals["R"] / max(1, epochs_sampled), 2),
        gps_code_completeness=gps_comp,
        glonass_code_completeness=glo_comp,
        dual_frequency_gps_usable=has_gps_dual,
        dual_frequency_glonass_usable=has_glo_dual,
        exclusion_reasons=tuple(reasons),
    )


def load_osgof_provisional_coords(
    provenance_csv: Path,
) -> dict[str, tuple[float, float, float]]:
    """Load the 11 OSGoF 2011-01-01 provisional coordinates (explicitly PROVISIONAL)."""
    coords: dict[str, tuple[float, float, float]] = {}
    with provenance_csv.open(encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            sid = row["station_id"].strip()[:4]
            parts = [float(v.strip()) for v in row["coordinate_xyz_m"].split(",")]
            if len(parts) == 3 and all(math.isfinite(x) for x in parts):
                coords[sid] = (parts[0], parts[1], parts[2])
    return coords


def build_2011_selection_manifest(
    *,
    zip_path: Path,
    header_audit_csv: Path,
    nav_inventories: tuple[Path, ...],
    osgof_coords_csv: Path,
    primary_dates: tuple[str, ...] = ("2011-03-20", "2011-03-21"),
    secondary_dates: tuple[str, ...] = ("2011-12-05", "2011-12-06", "2011-12-07", "2011-12-08"),
    verified_2024_coords_json: Path | None = None,
    verified_2024_nav_path: Path | None = None,
) -> DatasetSelectionManifest:
    """Build a reproducible manifest for 2011 NIGNET + 2024 DOY 026 datasets."""
    osgof_coords = load_osgof_provisional_coords(osgof_coords_csv)

    nav_by_date: dict[str, dict[str, str]] = defaultdict(dict)
    for inv_path in nav_inventories:
        if not inv_path.is_file():
            continue
        with inv_path.open(encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                if row.get("status") == "VALIDATED" and row.get("product_date"):
                    dt = row["product_date"]
                    nav_by_date[dt][row["system"]] = str(
                        inv_path.parent / "navigation-products" / row["filename"]
                    )
                elif row.get("recovery_status") == "VALIDATED" and row.get("target_date"):
                    dt = row["target_date"]
                    raw_path = Path(row["stored_path"])
                    resolved = raw_path if raw_path.is_absolute() else (inv_path.parent / raw_path)
                    nav_by_date[dt][row["product_system"]] = str(resolved)

    by_date: dict[str, list[dict[str, str]]] = defaultdict(list)
    stations_seen: set[str] = set()
    total_files = 0
    with header_audit_csv.open(encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            total_files += 1
            st4 = row["canonical_station_id"][:4]
            stations_seen.add(st4)
            by_date[row["observation_date_from_filename"]].append(row)

    selected_dates = (*primary_dates, *secondary_dates)
    file_entries: list[dict[str, Any]] = []
    windows: dict[str, WindowSelectionCandidate] = {}

    with zipfile.ZipFile(zip_path, "r") as zf:
        for dt in selected_dates:
            recs = sorted(by_date.get(dt, []), key=lambda r: r["canonical_station_id"])
            dual_stations: list[str] = []
            excluded: dict[str, str] = {}
            for rec in recs:
                st4 = rec["canonical_station_id"][:4]
                member = rec["relative_path"]
                ep_decl = int(float(rec["epoch_count_inspected"] or 0))
                lines = zf.read(member).decode("ascii", errors="replace").splitlines()
                sig = audit_rinex2_signal_completeness(
                    lines,
                    station_id=st4,
                    date_iso=dt,
                    source_identifier=f"{zip_path}::{member}",
                    file_sha256=rec["sha256"],
                    epoch_count_declared=ep_decl,
                    max_sample_epochs=30,
                )
                file_entries.append(sig.as_dict())
                if sig.dual_frequency_gps_usable and ep_decl >= 2400 and st4 in osgof_coords:
                    dual_stations.append(st4)
                else:
                    reason = "; ".join(sig.exclusion_reasons) or "missing provisional coordinate"
                    excluded[st4] = reason

            geom = classify_network_geometry({s: osgof_coords[s] for s in dual_stations})
            year_i, mon_i, day_i = (int(p) for p in dt.split("-"))
            from datetime import date

            doy_i = date(year_i, mon_i, day_i).timetuple().tm_yday
            is_primary = dt in primary_dates
            role = "PRIMARY_EQUINOX_INTERIOR_HULL" if is_primary else "SECONDARY_SOLSTICE_INTERIOR"
            rationale = (
                "9 simultaneous full-day dual-frequency GPS+GLONASS stations across Nigeria "
                "with 4 interior stations strictly inside convex hull and validated 2011 BKG nav; "
                "March equinox high-ionosphere regime."
                if is_primary
                else "9 simultaneous full-day dual-frequency stations (single-frequency RUST "
                "excluded by L2 content gate) with 4 interior hull stations and validated 2011 "
                "BKG nav; December solstice seasonal contrast."
            )
            windows[dt] = WindowSelectionCandidate(
                date_iso=dt,
                year=year_i,
                doy=doy_i,
                dual_freq_stations=tuple(sorted(dual_stations)),
                excluded_stations=excluded,
                interior_stations=tuple(geom["interior_stations"]),
                perimeter_stations=tuple(geom["perimeter_stations"]),
                hull_area_km2=round(float(geom["hull_area_km2"]), 2),
                min_baseline_km=round(float(geom["min_baseline_km"]), 2),
                max_baseline_km=round(float(geom["max_baseline_km"]), 2),
                navigation_gps_path=nav_by_date.get(dt, {}).get("GPS"),
                navigation_glonass_path=nav_by_date.get(dt, {}).get("GLONASS"),
                coordinate_provenance=(
                    "PROVISIONAL_OSGOF_2011_01_01 (frame/ARP/uncertainty undocumented; "
                    "experimental research only, not operationally verified)"
                ),
                role=role,
                rationale=rationale,
            )

    verified_windows: list[WindowSelectionCandidate] = []
    if verified_2024_coords_json is not None and verified_2024_coords_json.is_file():
        dc = json.loads(verified_2024_coords_json.read_text(encoding="utf-8"))
        v_coords: dict[str, tuple[float, float, float]] = {}
        for sid, info in sorted(dc.get("stations", {}).items()):
            if info.get("scientifically_valid") is True:
                e = info["ecef"]
                v_coords[sid] = (float(e["x_m"]), float(e["y_m"]), float(e["z_m"]))
        if len(v_coords) >= 3:
            vgeom = classify_network_geometry(v_coords)
            verified_windows.append(
                WindowSelectionCandidate(
                    date_iso="2024-01-26",
                    year=2024,
                    doy=26,
                    dual_freq_stations=tuple(sorted(v_coords)),
                    excluded_stations={"BKFP00NGA": "scientifically_valid=False in PRIDE QC"},
                    interior_stations=tuple(vgeom["interior_stations"]),
                    perimeter_stations=tuple(vgeom["perimeter_stations"]),
                    hull_area_km2=round(float(vgeom["hull_area_km2"]), 2),
                    min_baseline_km=round(float(vgeom["min_baseline_km"]), 2),
                    max_baseline_km=round(float(vgeom["max_baseline_km"]), 2),
                    navigation_gps_path=(
                        str(verified_2024_nav_path) if verified_2024_nav_path else None
                    ),
                    navigation_glonass_path=(
                        str(verified_2024_nav_path) if verified_2024_nav_path else None
                    ),
                    coordinate_provenance="VERIFIED_IGS20_PRIDE_PPP_AR (2024-01-26)",
                    role="VERIFIED_COORDINATE_AND_PRIDE_ZTD_REFERENCE",
                    rationale=(
                        "Authoritative 4-station verified IGS20 PRIDE PPP-AR coordinate and "
                        "independent PRIDE ZTD benchmark (all 4 LOOCV folds are extrapolative)."
                    ),
                )
            )

    limitations = (
        "2011 NIGNET coordinates are PROVISIONAL OSGoF 2011-01-01 published coordinates without "
        "documented ITRF frame, ARP continuity, or formal uncertainties.",
        "GPS P1 pseudorange is 0% populated across all 2011 NIGNET stations; dual-frequency GPS "
        "code combinations use C1/P2 (introducing uncalibrated C1-P1 + P1-P2 DCBs).",
        "RUST experiences 0% L2/P2 tracking across December 2011 despite header declaration and is "
        "excluded from December dual-frequency windows.",
        "No external IGS/CODE DCB or high-resolution regional IONEX files are present locally; "
        "raw STEC/VTEC estimates remain uncalibrated for hardware DCBs.",
        "2024 DOY 026 has verified IGS20 coordinates and PRIDE ZTD truth but only 4 stations "
        "(all LOOCV folds extrapolate over 105-1029 km).",
    )
    return DatasetSelectionManifest(
        schema_version="1.0",
        archive_path=str(zip_path),
        archive_sha256=sha256_file(zip_path) if zip_path.is_file() else "",
        total_files_audited=total_files,
        stations_discovered=tuple(sorted(stations_seen)),
        primary_windows=tuple(windows[d] for d in primary_dates if d in windows),
        secondary_windows=tuple(windows[d] for d in secondary_dates if d in windows),
        verified_reference_windows=tuple(verified_windows),
        station_file_entries=tuple(file_entries),
        known_limitations=limitations,
    )
