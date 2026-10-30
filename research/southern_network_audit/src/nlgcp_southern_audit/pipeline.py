"""Deterministic ZIP-first Southern Nigeria NIGNET audit pipeline."""

from __future__ import annotations

import bz2
import concurrent.futures
import csv
import gzip
import hashlib
import io
import itertools
import json
import math
import os
import re
import shutil
import zipfile
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, BinaryIO, cast

from nlgcp_single_base.stations import (
    CANONICAL_STATIONS,
    MARKER_TO_CANONICAL,
)

from .core import (
    RinexHeader,
    classify_file,
    combinations,
    convex_hull,
    coordinate_provenance_status,
    ecef_to_enu,
    ecef_to_geodetic,
    enu_to_ecef,
    intersect_windows,
    parse_header_time,
    parse_rinex_header,
    station_code,
)

CANONICAL_PREFIX_TO_ID = {station[:4]: station for station in CANONICAL_STATIONS}


def _canonical_id(code: str) -> str:
    return CANONICAL_PREFIX_TO_ID.get(code, MARKER_TO_CANONICAL.get(code, code))


RINEX2_EPOCH = re.compile(
    rb"(?m)^[ \t]*(\d{1,2})[ \t]+(\d{1,2})[ \t]+(\d{1,2})[ \t]+"
    rb"(\d{1,2})[ \t]+(\d{1,2})[ \t]+(\d{1,2}\.\d+)[ \t]+([0-6])[ \t]+\d+"
)


def _jsonable(value: Any) -> Any:
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    return value


def _csv(path: Path, rows: list[dict[str, Any]]) -> None:
    keys: list[str] = []
    for row in rows:
        for key in row:
            if key not in keys:
                keys.append(key)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=keys or ["status"], extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    k: json.dumps(_jsonable(v), ensure_ascii=False)
                    if isinstance(v, (list, tuple, dict))
                    else v
                    for k, v in row.items()
                }
            )


def _archive_sha256(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def _header_from_zip(zf: zipfile.ZipFile, info: zipfile.ZipInfo) -> RinexHeader | None:
    try:
        with zf.open(info) as stream:
            name = info.filename.lower()
            if name.endswith(".gz"):
                payload = cast(BinaryIO, gzip.GzipFile(fileobj=stream))
            elif name.endswith(".bz2"):
                payload = cast(BinaryIO, bz2.BZ2File(stream))
            else:
                payload = cast(BinaryIO, stream)
            prefix = payload.read(128 * 1024)
        if b"RINEX VERSION / TYPE" not in prefix[:8192]:
            return None
        return parse_rinex_header(io.BytesIO(prefix))
    except (OSError, EOFError, zipfile.BadZipFile, RuntimeError):
        return None


def _time_window(header: RinexHeader) -> tuple[datetime, datetime, str] | None:
    start, scale1 = parse_header_time(header.first_obs, header.time_system)
    end, scale2 = parse_header_time(header.last_obs, header.time_system)
    scale = scale1 or scale2 or header.time_system
    if start is None or end is None or (scale1 and scale2 and scale1 != scale2):
        return None
    return start, end, scale


def _filename_date(filename: str) -> str:
    """Extract a RINEX day label without treating it as an observation window."""
    legacy = re.search(
        r"^[A-Za-z0-9]{4}(\d{3})\d\.(\d{2})[odnglhijc]$",
        Path(filename).name,
        re.IGNORECASE,
    )
    if legacy:
        doy, yy = int(legacy.group(1)), int(legacy.group(2))
        year = 2000 + yy if yy < 80 else 1900 + yy
        try:
            return datetime.strptime(f"{year} {doy}", "%Y %j").date().isoformat()
        except ValueError:
            return ""
    modern = re.search(r"_(\d{4})(\d{3})\d{4}_", filename)
    if modern:
        try:
            return (
                datetime.strptime(f"{modern.group(1)} {modern.group(2)}", "%Y %j")
                .date()
                .isoformat()
            )
        except ValueError:
            return ""
    return ""


def _date_range(start: datetime, end: datetime) -> list[datetime]:
    return [
        datetime.fromordinal(start.toordinal() + offset)
        for offset in range((end.date() - start.date()).days + 1)
    ]


def _external_navigation_products(root: Path) -> list[dict[str, Any]]:
    """Inventory already available BKG/IGS navigation products by filename day."""
    rows: list[dict[str, Any]] = []
    if not root.exists():
        return rows
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        lower = path.name.lower()
        if not any(token in lower for token in ("brdc", "nav", "mn.rnx", "n.rnx")):
            continue
        day = _filename_date(path.name)
        if not day:
            match = re.search(r"_(\d{4})(\d{3})\d{4}_", path.name)
            if match:
                try:
                    day = (
                        datetime.strptime(f"{match.group(1)} {match.group(2)}", "%Y %j")
                        .date()
                        .isoformat()
                    )
                except ValueError:
                    day = ""
        rows.append(
            {
                "path": str(path),
                "filename": path.name,
                "size_bytes": path.stat().st_size,
                "date_from_name": day,
                "product_family": "BKG/IGS BROADCAST NAVIGATION CANDIDATE",
                "sha256": "NOT_REHASHED_EXISTING_VAULT_PRODUCT",
            }
        )
    return rows


def _discover_incoming(root: Path) -> dict[str, Any]:
    """Discover local archives and extracted RINEX within the named input root only."""
    archives: list[dict[str, Any]] = []
    rinex_files: list[dict[str, Any]] = []
    other_files: list[dict[str, Any]] = []
    directories: list[str] = []
    if not root.exists():
        return {
            "root": str(root),
            "exists": False,
            "archives": [],
            "rinex_files": [],
            "other_files": [],
        }
    for current, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames[:] = sorted(d for d in dirnames if not (Path(current) / d).is_symlink())
        directories.extend(str((Path(current) / dirname).relative_to(root)) for dirname in dirnames)
        for filename in sorted(filenames):
            path = Path(current) / filename
            if path.is_symlink():
                other_files.append(
                    {"path": str(path.relative_to(root)), "status": "SYMLINK_REJECTED"}
                )
                continue
            lower = filename.lower()
            suffix = (
                "zip"
                if lower.endswith(".zip")
                else "tar"
                if ".tar" in lower or lower.endswith(".tgz")
                else ""
            )
            record = {"path": str(path.relative_to(root)), "size_bytes": path.stat().st_size}
            if suffix:
                archives.append({**record, "archive_format": suffix})
            elif classify_file(filename)[0] != "unsupported":
                rinex_files.append({**record, "file_type": classify_file(filename)[0]})
            else:
                other_files.append(record)
    return {
        "root": str(root),
        "exists": True,
        "directories": directories,
        "archives": archives,
        "standalone_rinex_files": rinex_files,
        "other_files": other_files,
    }


def _record_hash(
    zf: zipfile.ZipFile, info: zipfile.ZipInfo, scan_rinex2: bool = False
) -> tuple[str, int, str, datetime | None, datetime | None, int]:
    earliest: datetime | None = None
    latest: datetime | None = None
    epoch_count = 0
    carry = b""
    try:
        with zf.open(info) as stream:
            digest = hashlib.sha256()
            size = 0
            while chunk := stream.read(1024 * 1024):
                digest.update(chunk)
                size += len(chunk)
                if scan_rinex2:
                    data = carry + chunk
                    complete_end = data.rfind(b"\n") + 1
                    complete_lines = data[:complete_end]
                    for match in RINEX2_EPOCH.finditer(complete_lines):
                        stamp = _rinex2_epoch_time(match)
                        if stamp is not None:
                            earliest = stamp if earliest is None else min(earliest, stamp)
                            latest = stamp if latest is None else max(latest, stamp)
                            epoch_count += 1
                    carry = data[complete_end:]
            if scan_rinex2:
                for match in RINEX2_EPOCH.finditer(carry):
                    stamp = _rinex2_epoch_time(match)
                    if stamp is not None:
                        earliest = stamp if earliest is None else min(earliest, stamp)
                        latest = stamp if latest is None else max(latest, stamp)
                        epoch_count += 1
        return digest.hexdigest(), size, "OK", earliest, latest, epoch_count
    except (OSError, EOFError, zipfile.BadZipFile, RuntimeError) as exc:
        return "", 0, f"CORRUPT: {type(exc).__name__}: {exc}", None, None, 0


def _rinex2_epoch_time(match: re.Match[bytes]) -> datetime | None:
    try:
        yy, month, day, hour, minute = map(int, match.groups()[:5])
        year = 2000 + yy if yy < 80 else 1900 + yy
        seconds = float(match.group(6))
        whole = int(seconds)
        return datetime(
            year,
            month,
            day,
            hour,
            minute,
            whole,
            round((seconds - whole) * 1_000_000),
        )
    except (ValueError, OverflowError):
        return None


def _network_windows(
    windows_by_station_day: dict[tuple[str, str], list[tuple[datetime, datetime, str, str]]],
    station_ids: tuple[str, ...],
) -> list[dict[str, Any]]:
    """Return actual common header/record windows, preserving their time scale."""
    if not station_ids:
        return []
    days_by_station = [
        {day for station, day in windows_by_station_day if station == station_id}
        for station_id in station_ids
    ]
    common_days = sorted(set.intersection(*days_by_station)) if days_by_station else []
    rows: list[dict[str, Any]] = []
    for day in common_days:
        best: tuple[datetime, datetime, str, tuple[str, ...]] | None = None
        scales: set[str] = set()
        for windows in itertools.product(
            *(windows_by_station_day[(station_id, day)] for station_id in station_ids)
        ):
            scales.update(window[2] for window in windows)
            result = intersect_windows(windows)
            if result and (best is None or (result[1] - result[0]) > (best[1] - best[0])):
                best = (result[0], result[1], windows[0][2], tuple(w[3] for w in windows))
        if best:
            rows.append(
                {
                    "date": day,
                    "start": best[0].isoformat(),
                    "end": best[1].isoformat(),
                    "time_system": best[2],
                    "duration_s": (best[1] - best[0]).total_seconds(),
                    "source_files": best[3],
                    "overlap_status": "COMMON_WINDOW_NOT_EPOCH_COUNT",
                }
            )
        elif len(scales) > 1:
            rows.append(
                {
                    "date": day,
                    "start": "",
                    "end": "",
                    "time_system": "|".join(sorted(scales)),
                    "duration_s": "",
                    "source_files": (),
                    "overlap_status": "TIME_SCALE_MISMATCH_UNRESOLVED",
                }
            )
    return rows


def _metadata_row(
    path: str, size: int, sha: str, header: RinexHeader | None, archive_name: str, integrity: str
) -> dict[str, Any]:
    kind, compression = classify_file(path)
    code = station_code(
        Path(path).name,
        header.marker_name if header else "",
        header.marker_number if header else "",
    )
    window = _time_window(header) if header else None
    row: dict[str, Any] = {
        "relative_path": path,
        "filename": Path(path).name,
        "file_size": size,
        "extension": "".join(Path(path).suffixes),
        "file_type": kind,
        "compression": compression,
        "sha256": sha,
        "archive_source": archive_name,
        "integrity_status": integrity,
        "duplicate_status": "PENDING",
        "parsing_status": "NOT_RINEX",
        "rejection_warning": "",
        "original_station_code": code,
        "observation_date_from_filename": _filename_date(Path(path).name),
    }
    if header is not None:
        header_code = station_code("", header.marker_name, header.marker_number)
        canonical_code = _canonical_id(code)
        canonical_header_code = _canonical_id(header_code)
        row.update(
            {
                "file_type": header.file_type,
                "parsing_status": header.parse_status,
                "marker_name": header.marker_name,
                "marker_number": header.marker_number,
                "marker_station_code": header_code,
                "canonical_station_id": canonical_code,
                "identity_resolution": "MATCH"
                if canonical_code == canonical_header_code
                else "IDENTITY_MISMATCH",
                "rinex_version": header.version,
                "approx_xyz_m": header.approx_xyz,
                "time_system": window[2] if window else header.time_system,
                "first_obs": window[0].isoformat() if window else header.first_obs,
                "last_obs": window[1].isoformat() if window else header.last_obs,
                "interval_s": header.interval_s,
                "systems": header.systems,
                "observables": header.observables,
                "missing_fields": header.missing_fields,
                "receiver_serial": header.receiver_serial,
                "receiver_type": header.receiver_type,
                "receiver_version": header.receiver_version,
                "antenna_serial": header.antenna_serial,
                "antenna_type": header.antenna_type,
                "antenna_delta_hen_m": header.antenna_delta_hen,
            }
        )
        if header.parse_status != "parsed":
            row["rejection_warning"] = "INCOMPLETE_HEADER"
        if row.get("identity_resolution") == "IDENTITY_MISMATCH":
            row["rejection_warning"] = "FILENAME_MARKER_IDENTITY_MISMATCH"
        if not code:
            row["rejection_warning"] = "STATION_ID_MISSING"
    return row


def _geometry(
    stations: dict[str, dict[str, Any]],
    candidate_sizes: tuple[int, ...] = (3, 4, 5),
    southern_max_latitude_deg: float = 8.5,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    usable = {
        key: rec
        for key, rec in stations.items()
        if rec.get("xyz")
        and rec.get("coordinate_status") in {"PROVISIONAL", "VERIFIED"}
        and ecef_to_geodetic(*rec["xyz"])[0] <= southern_max_latitude_deg
    }
    ids = sorted(usable)
    geometries: list[dict[str, Any]] = []
    held: list[dict[str, Any]] = []
    features: dict[str, dict[str, Any]] = {}
    for size in candidate_sizes:
        for refs in combinations(ids, (size,)):
            xyz = [usable[i]["xyz"] for i in refs]
            origin = tuple(sum(point[k] for point in xyz) / size for k in range(3))
            pts = {i: ecef_to_enu(usable[i]["xyz"], origin)[:2] for i in refs}
            hull = convex_hull(list(pts.values()))
            area = (
                abs(
                    sum(
                        hull[i][0] * hull[(i + 1) % len(hull)][1]
                        - hull[(i + 1) % len(hull)][0] * hull[i][1]
                        for i in range(len(hull))
                    )
                )
                / 2
                if len(hull) >= 3
                else 0.0
            )
            distances = [
                math.dist(pts[a], pts[b]) for n, a in enumerate(refs) for b in refs[n + 1 :]
            ]
            collinear = len(hull) < 3 or area < 1e-6
            lengths = (
                [math.dist(hull[i], hull[(i + 1) % len(hull)]) for i in range(len(hull))]
                if len(hull) >= 2
                else []
            )
            triangle_angles: list[float] = []
            for triangle in itertools.combinations(refs, 3):
                side = [
                    math.dist(pts[triangle[i]], pts[triangle[j]])
                    for i, j in ((0, 1), (1, 2), (2, 0))
                ]
                if min(side) > 0:
                    for edge, other_a, other_b in (
                        (side[0], side[1], side[2]),
                        (side[1], side[0], side[2]),
                        (side[2], side[0], side[1]),
                    ):
                        cosine = max(
                            -1.0,
                            min(1.0, (other_a**2 + other_b**2 - edge**2) / (2 * other_a * other_b)),
                        )
                        triangle_angles.append(math.degrees(math.acos(cosine)))
            gid = "+".join(refs)
            geometries.append(
                {
                    "reference_stations": gid,
                    "reference_count": size,
                    "coordinate_provenance": ";".join(
                        sorted({usable[i]["coordinate_status"] for i in refs})
                    ),
                    "geographic_scope_max_latitude_deg": southern_max_latitude_deg,
                    "minimum_baseline_m": min(distances) if distances else "",
                    "maximum_baseline_m": max(distances) if distances else "",
                    "mean_baseline_m": sum(distances) / len(distances) if distances else "",
                    "centroid_ecef_m": origin,
                    "convex_hull_enu_m": hull,
                    "polygon_area_km2": area / 1e6,
                    "edge_lengths_m": lengths,
                    "minimum_triangle_angle_deg": min(triangle_angles) if triangle_angles else "",
                    "shape_condition_indicator": (min(triangle_angles) / 60.0)
                    if triangle_angles
                    else (area / max(max(distances, default=0.0) ** 2, 1.0)),
                    "collinearity_warning": collinear,
                }
            )
            features[gid] = {
                "refs": refs,
                "origin": origin,
                "hull": hull,
                "area": area,
                "min": min(distances) if distances else 0.0,
                "max": max(distances) if distances else 0.0,
                "mean": sum(distances) / len(distances) if distances else 0.0,
                "collinear": collinear,
            }
            for target in ids:
                if target in refs:
                    continue
                local = ecef_to_enu(usable[target]["xyz"], origin)[:2]
                status = _point_status(local, hull)
                dists = [math.dist(usable[target]["xyz"], usable[ref]["xyz"]) for ref in refs]
                held.append(
                    {
                        "reference_stations": gid,
                        "target_station": target,
                        "target_provenance": usable[target]["coordinate_status"],
                        "containment": status,
                        "target_to_reference_m": dict(zip(refs, dists, strict=True)),
                        "minimum_target_baseline_m": min(dists),
                        "maximum_target_baseline_m": max(dists),
                        "relative_east_m": local[0],
                        "relative_north_m": local[1],
                    }
                )
    rankings: list[dict[str, Any]] = []
    for row in held:
        item = features[row["reference_stations"]]
        all_verified = row["target_provenance"] == "VERIFIED" and all(
            usable[r]["coordinate_status"] == "VERIFIED" for r in item["refs"]
        )
        days = usable[row["target_station"]].get("common_days", 0)
        ranks = usable[row["target_station"]].get("navigation_match", 0)
        state = (
            "GEOMETRY_FEASIBLE"
            if all_verified and not item["collinear"] and row["containment"] == "INSIDE"
            else "GEOMETRY_PROVISIONAL"
            if not item["collinear"] and row["containment"] == "INSIDE"
            else "COORDINATE_PROVENANCE_INSUFFICIENT"
        )
        score = (
            int(all_verified),
            int(row["containment"] == "INSIDE"),
            days,
            ranks,
            -row["maximum_target_baseline_m"],
        )
        rankings.append(
            {
                "reference_stations": row["reference_stations"],
                "target_station": row["target_station"],
                "state": state,
                "containment": row["containment"],
                "common_observation_days": days,
                "navigation_matching_days": ranks,
                "polygon_area_km2": item["area"] / 1e6,
                "maximum_reference_baseline_m": item["max"],
                "maximum_target_baseline_m": row["maximum_target_baseline_m"],
                "coordinate_provenance_priority": score[0],
                "containment_priority": score[1],
                "common_observation_day_priority": score[2],
                "navigation_day_priority": score[3],
                "shorter_target_baseline_tiebreak_m": -score[4],
                "rank_basis": (
                    "Lexicographic provenance, containment, common header-overlap days, "
                    "navigation days, target baseline; not positioning accuracy"
                ),
            }
        )
    geojson: dict[str, Any] = {"type": "FeatureCollection", "features": []}
    for gid, item in features.items():
        if len(item["hull"]) < 3:
            continue
        local_ring = [*item["hull"], item["hull"][0]]
        ring = []
        for east, north in local_ring:
            xyz_point = enu_to_ecef((east, north, 0.0), item["origin"])
            lat, lon, _ = ecef_to_geodetic(*xyz_point)
            ring.append([lon, lat])
        geojson["features"].append(
            {
                "type": "Feature",
                "properties": {
                    "reference_stations": gid,
                    "coordinate_provenance": ";".join(
                        sorted({usable[i]["coordinate_status"] for i in item["refs"]})
                    ),
                    "polygon_area_km2": item["area"] / 1e6,
                    "geometry_calculated_in": "local ENU metres",
                    "coordinate_system": (
                        "WGS84 longitude/latitude output; source coordinates retain "
                        "their declared/unknown frame"
                    ),
                },
                "geometry": {"type": "Polygon", "coordinates": [ring]},
            }
        )
    return geometries, held, rankings, geojson


def _point_status(point: tuple[float, float], hull: list[tuple[float, float]]) -> str:
    from .core import point_in_polygon

    result = point_in_polygon(point, hull)
    return (
        "INSIDE"
        if result in {"INSIDE", "BOUNDARY"}
        else "OUTSIDE"
        if result == "OUTSIDE"
        else "COLLINEAR_OR_DEGENERATE"
    )


def run_audit(
    archive: Path,
    output: Path,
    station_registry: Path | None = None,
    southern_max_latitude_deg: float = 8.5,
    workers: int = 4,
) -> dict[str, Any]:
    """Audit an existing ZIP in place; derived outputs go only to a new directory."""
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"output directory is not empty: {output}")
    output.mkdir(parents=True, exist_ok=True)
    archive_hash, archive_size = _archive_sha256(archive)
    incoming_discovery = _discover_incoming(archive.parent)
    vault_root = (
        archive.parents[2]
        if len(archive.parents) > 2 and archive.parents[2].name == "nlgcp-data"
        else archive.parent
    )
    records: list[dict[str, Any]] = []
    header_by_path: dict[str, RinexHeader] = {}
    bad_paths: list[str] = []
    with zipfile.ZipFile(archive) as zf:
        infos = zf.infolist()
        member_specs: list[tuple[zipfile.ZipInfo, str, str, RinexHeader | None, bool]] = []
        for info in infos:
            if info.is_dir():
                continue
            name = info.filename
            head = b""
            try:
                with zf.open(info) as stream:
                    head = stream.read(8192)
                rough_type, _ = classify_file(name, head)
                header = (
                    _header_from_zip(zf, info)
                    if rough_type
                    in {"observation", "navigation", "rinex_unknown", "hatanaka_observation"}
                    else None
                )
                if header is not None:
                    header_by_path[name] = header
                scan_rinex2 = bool(
                    header is not None
                    and header.file_type == "observation"
                    and header.version.startswith("2")
                    and not header.last_obs
                    and classify_file(name)[1] == "none"
                )
                member_specs.append((info, name, rough_type, header, scan_rinex2))
            except (OSError, EOFError, zipfile.BadZipFile, RuntimeError):
                member_specs.append((info, name, "corrupt", None, False))
        with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, workers)) as executor:
            hash_futures = [
                executor.submit(_record_hash, zf, info, scan_rinex2)
                for info, _, _, _, scan_rinex2 in member_specs
            ]
            for spec, future in zip(member_specs, hash_futures, strict=True):
                info, name, rough_type, header, scan_rinex2 = spec
                sha, actual_size, integrity, first_epoch, last_epoch, epoch_count = future.result()
                if integrity != "OK" or actual_size != info.file_size:
                    integrity = integrity if integrity != "OK" else "SIZE_MISMATCH"
                    bad_paths.append(name)
                record = _metadata_row(
                    name, actual_size or info.file_size, sha, header, archive.name, integrity
                )
                if scan_rinex2 and header is not None:
                    record["epoch_count_inspected"] = epoch_count
                    record["epoch_scan_status"] = "SCANNED" if epoch_count else "NO_EPOCHS_FOUND"
                    if first_epoch is not None and last_epoch is not None:
                        record["first_obs"] = first_epoch.isoformat()
                        record["last_obs"] = last_epoch.isoformat()
                        record["time_system"] = header.time_system
                    else:
                        record["rejection_warning"] = "NO_EPOCH_RECORDS_FOUND"
                if rough_type == "unsupported" and not header:
                    record["rejection_warning"] = "UNSUPPORTED_FORMAT"
                elif rough_type == "hatanaka_observation" and not header:
                    record["rejection_warning"] = (
                        "CRINEX_CONVERTER_UNAVAILABLE"
                        if shutil.which("crx2rnx") is None
                        else "CRINEX_CONVERSION_NOT_ENABLED_FOR_ARCHIVE_MEMBER"
                    )
                elif classify_file(name)[1] == "unix_compress" and not header:
                    record["rejection_warning"] = "UNIX_COMPRESS_DECODING_NOT_IMPLEMENTED"
                elif (
                    header is not None
                    and header.file_type == "observation"
                    and not header.last_obs
                    and not scan_rinex2
                ):
                    record["rejection_warning"] = "END_EPOCH_NOT_AVAILABLE_OR_NOT_SCANNED"
                elif (
                    header is not None
                    and header.file_type == "observation"
                    and scan_rinex2
                    and epoch_count == 0
                ):
                    record["rejection_warning"] = "NO_EPOCH_RECORDS_FOUND"
                try:
                    start_time = datetime.fromisoformat(record["first_obs"])
                    end_time = datetime.fromisoformat(record["last_obs"])
                    record["session_duration_s"] = (end_time - start_time).total_seconds()
                except (KeyError, TypeError, ValueError):
                    record["session_duration_s"] = ""
                records.append(record)
    # Exact duplicate and basename conflicts are retained and explicitly classified.
    by_sha: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_name: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in records:
        if row["sha256"]:
            by_sha[row["sha256"]].append(row)
        by_name[row["filename"].lower()].append(row)
    dup_rows: list[dict[str, Any]] = []
    for digest, group in by_sha.items():
        if len(group) > 1:
            for row in group:
                row["duplicate_status"] = "EXACT_DUPLICATE"
            dup_rows.append(
                {
                    "duplicate_type": "EXACT_CONTENT",
                    "sha256": digest,
                    "paths": [r["relative_path"] for r in group],
                    "treatment": "PRESERVED_ALL",
                }
            )
    for filename, group in by_name.items():
        if len(group) > 1 and len({r["sha256"] for r in group}) > 1:
            for row in group:
                row["duplicate_status"] = "CONFLICTING_BASENAME"
            dup_rows.append(
                {
                    "duplicate_type": "CONFLICTING_BASENAME",
                    "filename": filename,
                    "hashes": [r["sha256"] for r in group],
                    "paths": [r["relative_path"] for r in group],
                    "treatment": "PRESERVED_ALL",
                }
            )
    by_station_session: dict[tuple[str, str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in records:
        filename = row["filename"]
        if row.get("original_station_code") and row.get("observation_date_from_filename"):
            session = filename[7:8].upper() if len(filename) > 7 else ""
            key = (
                row["original_station_code"],
                row["observation_date_from_filename"],
                session,
                row["file_type"],
            )
            by_station_session[key].append(row)
    for key, group in by_station_session.items():
        if len(group) > 1:
            for row in group:
                if row["duplicate_status"] == "PENDING":
                    row["duplicate_status"] = "DUPLICATE_STATION_DAY_SESSION"
            dup_rows.append(
                {
                    "duplicate_type": "DUPLICATE_STATION_DAY_SESSION",
                    "station_code": key[0],
                    "date": key[1],
                    "session": key[2],
                    "file_type": key[3],
                    "paths": [r["relative_path"] for r in group],
                    "hashes": [r["sha256"] for r in group],
                    "treatment": "PRESERVED_ALL_REVIEW_REQUIRED",
                }
            )
    for row in records:
        if row["duplicate_status"] == "PENDING":
            row["duplicate_status"] = "UNIQUE"
    obs = [r for r in records if r["file_type"] == "observation"]
    nav = [r for r in records if r["file_type"] == "navigation"]
    stations: dict[str, dict[str, Any]] = {}
    for row in obs:
        code = row.get("original_station_code", "")
        if not code:
            continue
        station = stations.setdefault(
            code, {"files": [], "xyz_votes": [], "windows": [], "days": set(), "nav_days": set()}
        )
        station["files"].append(row)
        if row.get("observation_date_from_filename"):
            station["days"].add(row["observation_date_from_filename"])
        header = header_by_path.get(row["relative_path"])
        if header and header.approx_xyz:
            station["xyz_votes"].append((header.approx_xyz, row["relative_path"]))
        if row.get("first_obs") and row.get("last_obs"):
            start = datetime.fromisoformat(row["first_obs"])
            end = datetime.fromisoformat(row["last_obs"])
            scale = row.get("time_system", "")
            station["windows"].append((start, end, scale, row["relative_path"]))
            station["days"].add(start.date().isoformat())
    for row in nav:
        if row.get("first_obs"):
            code = row.get("original_station_code") or "NAV"
            if code in stations:
                stations[code]["nav_days"].add(row["first_obs"][:10])
    registry_rows: dict[str, dict[str, str]] = {}
    if station_registry and station_registry.exists():
        with station_registry.open(newline="", encoding="utf-8-sig") as stream:
            registry_rows = {r.get("station_id", "").upper(): r for r in csv.DictReader(stream)}
    metadata_rows: list[dict[str, Any]] = []
    provenance_rows: list[dict[str, Any]] = []
    for code, record in sorted(stations.items()):
        # The first header coordinate is retained deterministically, not as surveyed truth.
        votes = record["xyz_votes"]
        xyz = votes[0][0] if votes else None
        reg = registry_rows.get(code, {})
        status = coordinate_provenance_status(
            xyz,
            reg.get("coordinate_source", ""),
            reg.get("reference_frame", ""),
            reg.get("coordinate_epoch", ""),
        )
        for candidate, path in votes:
            provenance_rows.append(
                {
                    "station_code": code,
                    "coordinate_xyz_m": candidate,
                    "source": "RINEX APPROX POSITION XYZ",
                    "source_file": path,
                    "coordinate_status": "PROVISIONAL",
                    "reference_frame": "UNKNOWN",
                    "coordinate_epoch": "UNKNOWN",
                }
            )
        if not votes:
            provenance_rows.append(
                {
                    "station_code": code,
                    "coordinate_xyz_m": "",
                    "source": "",
                    "source_file": "",
                    "coordinate_status": "MISSING",
                    "reference_frame": "UNKNOWN",
                    "coordinate_epoch": "UNKNOWN",
                }
            )
        windows = record["windows"]
        systems = sorted({s for item in record["files"] for s in (item.get("systems") or [])})
        intervals = sorted({r.get("interval_s") for r in record["files"] if r.get("interval_s")})
        lat, lon, height = ecef_to_geodetic(*xyz) if xyz else (None, None, None)
        canonical = _canonical_id(code)
        metadata_rows.append(
            {
                "station_code": code,
                "canonical_station_id": canonical,
                "alias_resolution": "CANONICAL_REGISTRY_PREFIX"
                if code in CANONICAL_PREFIX_TO_ID
                else "RESOLVED_EXISTING_ALIAS"
                if code in MARKER_TO_CANONICAL
                else "IDENTITY_UNVERIFIED",
                "observation_file_count": len(record["files"]),
                "first_date": min(record["days"]) if record["days"] else "",
                "last_date": max(record["days"]) if record["days"] else "",
                "observed_days": len(record["days"]),
                "sessions_with_observed_time_window": sum(1 for w in windows if w[1] >= w[0]),
                "coordinate_xyz_m": xyz or "",
                "approx_latitude_deg": lat if lat is not None else "",
                "approx_longitude_deg": lon if lon is not None else "",
                "approx_ellipsoidal_height_m": height if height is not None else "",
                "coordinate_status": status,
                "gnss_systems": systems,
                "observation_intervals_s": intervals,
                "interval_consistency": "UNKNOWN"
                if not intervals
                else "CONSISTENT"
                if len(intervals) == 1
                else "INCONSISTENT",
            }
        )
        record["xyz"] = xyz
        record["coordinate_status"] = status
    all_days = sorted({day for rec in stations.values() for day in rec["days"]})
    all_calendar_days = (
        [
            day.date().isoformat()
            for day in _date_range(
                datetime.fromisoformat(all_days[0]), datetime.fromisoformat(all_days[-1])
            )
        ]
        if all_days
        else []
    )
    windows_by_station_day: dict[tuple[str, str], list[tuple[datetime, datetime, str, str]]] = (
        defaultdict(list)
    )
    files_by_station_day: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for code, rec in stations.items():
        for file_row in rec["files"]:
            file_day = file_row.get("observation_date_from_filename")
            if not file_day and file_row.get("first_obs"):
                file_day = str(file_row["first_obs"])[:10]
            if file_day:
                files_by_station_day[(code, file_day)].append(file_row)
        for window in rec["windows"]:
            windows_by_station_day[(code, window[0].date().isoformat())].append(window)
    availability_rows: list[dict[str, Any]] = []
    for code in sorted(stations):
        for day in all_calendar_days:
            day_files = files_by_station_day.get((code, day), [])
            day_windows = windows_by_station_day.get((code, day), [])
            availability_rows.append(
                {
                    "station_code": code,
                    "date": day,
                    "availability": "OBSERVED_WINDOW_SCANNED"
                    if day_windows
                    else "OBSERVED_DATE_ONLY"
                    if day_files
                    else "MISSING",
                    "session_count": len(day_files),
                    "usable_window_count": len(day_windows),
                    "sessions_without_complete_time_window": len(day_files) - len(day_windows),
                    "time_systems": sorted({w[2] for w in day_windows}),
                    "intervals_s": sorted(
                        {r.get("interval_s") for r in day_files if r.get("interval_s")}
                    ),
                    "source_files": [r["relative_path"] for r in day_files],
                }
            )
    window_rows: list[dict[str, Any]] = []
    overlap: dict[tuple[str, str], set[str]] = defaultdict(set)
    matched_dates: set[str] = set()
    for n, a in enumerate(sorted(stations)):
        for b in sorted(stations)[n + 1 :]:
            days = sorted(
                {key[1] for key in windows_by_station_day if key[0] == a}
                & {key[1] for key in windows_by_station_day if key[0] == b}
            )
            for day in days:
                for wa in windows_by_station_day[(a, day)]:
                    for wb in windows_by_station_day[(b, day)]:
                        result = intersect_windows([wa, wb])
                        if result:
                            duration = (result[1] - result[0]).total_seconds()
                            window_rows.append(
                                {
                                    "stations": f"{a}+{b}",
                                    "date": day,
                                    "start": result[0].isoformat(),
                                    "end": result[1].isoformat(),
                                    "time_system": wa[2],
                                    "duration_s": duration,
                                    "source_files": [wa[3], wb[3]],
                                    "overlap_status": "HEADER_WINDOW_INTERSECTION_NOT_EPOCH_COUNT",
                                }
                            )
                            overlap[(a, b)].add(day)
                            matched_dates.add(day)
                        elif wa[2] != wb[2]:
                            window_rows.append(
                                {
                                    "stations": f"{a}+{b}",
                                    "date": day,
                                    "start": "",
                                    "end": "",
                                    "time_system": f"{wa[2]}|{wb[2]}",
                                    "duration_s": "",
                                    "source_files": [wa[3], wb[3]],
                                    "overlap_status": "TIME_SCALE_MISMATCH_UNRESOLVED",
                                }
                            )
    overlap_rows = []
    station_ids = sorted(stations)
    for a in station_ids:
        for b in station_ids:
            shared = (
                len(stations[a]["days"] & stations[b]["days"])
                if a != b
                else len(stations[a]["days"])
            )
            pair = (a, b) if a < b else (b, a)
            real_shared = len(overlap[pair]) if a != b else shared
            overlap_rows.append(
                {
                    "station_a": a,
                    "station_b": b,
                    "same_calendar_days": shared,
                    "header_window_overlap_days": real_shared,
                }
            )
    # A registry record needs explicit frame, epoch, and source to verify coordinates.
    coordinate_conflicts: list[dict[str, Any]] = []
    for code, rec in stations.items():
        coords = rec["xyz_votes"]
        if len(coords) > 1:
            origin = coords[0][0]
            for xyz, source in coords[1:]:
                delta = math.dist(origin, xyz)
                if delta > 0.01:
                    coordinate_conflicts.append(
                        {
                            "station_code": code,
                            "first_file": coords[0][1],
                            "other_file": source,
                            "difference_m": delta,
                            "investigation": (
                                "RINEX header values differ; frame, epoch, and ARP "
                                "cannot be inferred from these records"
                            ),
                        }
                    )
    phase2_coordinate_registry = (
        vault_root / "metadata/stations/osgof-2024-rinex-header-registry.csv"
    )
    if phase2_coordinate_registry.exists():
        with phase2_coordinate_registry.open(newline="", encoding="utf-8-sig") as stream:
            for row in csv.DictReader(stream):
                canonical = row.get("station_id", "")
                station_aliases = {
                    canonical[:4],
                    *(
                        alias
                        for alias, canonical_id in MARKER_TO_CANONICAL.items()
                        if canonical_id == canonical
                    ),
                }
                try:
                    records_from_header = json.loads(row.get("approximate_position_xyz_m", "[]"))
                    reference_xyz = next(
                        item["value"]
                        for item in records_from_header
                        if isinstance(item.get("value"), list)
                    )
                    reference_xyz_tuple = tuple(float(v) for v in reference_xyz)
                except (json.JSONDecodeError, StopIteration, TypeError, ValueError):
                    continue
                for alias in station_aliases:
                    candidate = stations.get(alias)
                    if not candidate or not candidate["xyz_votes"]:
                        continue
                    old_xyz = candidate["xyz_votes"][0][0]
                    coordinate_conflicts.append(
                        {
                            "station_code": alias,
                            "first_file": candidate["xyz_votes"][0][1],
                            "other_file": "2024 RINEX header registry",
                            "difference_m": math.dist(old_xyz, reference_xyz_tuple),
                            "investigation": (
                                "Both positions are RINEX approximate coordinates; the "
                                "2011/2024 frame and epoch alignment is undocumented. "
                                "Comparison is diagnostic only."
                            ),
                        }
                    )
    # Add simple per-target temporal context for geometry ranking.
    for code, rec in stations.items():
        rec["common_days"] = max(
            (len(v) for (a, b), v in overlap.items() if code in (a, b)), default=0
        )
        rec["navigation_match"] = 0
    geometries, held, rankings, geojson = _geometry(
        stations, southern_max_latitude_deg=southern_max_latitude_deg
    )
    external_navigation = _external_navigation_products(vault_root / "external-products")
    external_nav_dates = {
        row["date_from_name"] for row in external_navigation if row["date_from_name"]
    }
    archive_nav_dates = {
        r.get("observation_date_from_filename")
        for r in nav
        if r.get("observation_date_from_filename")
    }
    available_nav_dates = external_nav_dates | archive_nav_dates
    matched_nav_dates = sorted(set(all_days) & available_nav_dates)
    missing_nav_dates = sorted(set(all_days) - available_nav_dates)
    network_temporal_rows: list[dict[str, Any]] = []
    temporal_by_network_target: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for held_row in held:
        target = held_row["target_station"]
        refs = tuple(str(held_row["reference_stations"]).split("+"))
        network_id = "+".join((*refs, target))
        windows = _network_windows(windows_by_station_day, (*refs, target))
        temporal_by_network_target[(held_row["reference_stations"], target)] = windows
        good_windows = [
            w for w in windows if w["overlap_status"] == "COMMON_WINDOW_NOT_EPOCH_COUNT"
        ]
        held_row["common_observation_days"] = len(good_windows)
        held_row["common_window_duration_s_total"] = sum(
            float(w["duration_s"]) for w in good_windows
        )
        for window in windows:
            network_temporal_rows.append(
                {
                    "network_id": network_id,
                    "reference_stations": held_row["reference_stations"],
                    "target_station": target,
                    **window,
                }
            )
    for ranking in rankings:
        temporal_key = (ranking["reference_stations"], ranking["target_station"])
        windows = temporal_by_network_target.get(temporal_key, [])
        good_windows = [
            w for w in windows if w["overlap_status"] == "COMMON_WINDOW_NOT_EPOCH_COUNT"
        ]
        ranking["common_observation_days"] = len(good_windows)
        nav_days = len({w["date"] for w in good_windows} & available_nav_dates)
        ranking["navigation_matching_days"] = nav_days
        ranking["coordinate_provenance_status"] = (
            "VERIFIED" if ranking["coordinate_provenance_priority"] else "PROVISIONAL_OR_UNVERIFIED"
        )
        ranking["network_temporal_state"] = (
            "TEMPORAL_OVERLAP_AVAILABLE" if good_windows else "TEMPORAL_OVERLAP_INSUFFICIENT"
        )
        ranking["navigation_status"] = (
            "NAVIGATION_DATA_AVAILABLE" if nav_days else "NAVIGATION_DATA_INSUFFICIENT"
        )
        if not ranking["coordinate_provenance_priority"]:
            ranking["state"] = "COORDINATE_PROVENANCE_INSUFFICIENT"
        elif not good_windows:
            ranking["state"] = "TEMPORAL_OVERLAP_INSUFFICIENT"
        elif not nav_days:
            ranking["state"] = "NAVIGATION_DATA_INSUFFICIENT"
        elif ranking["containment"] == "INSIDE":
            ranking["state"] = "GEOMETRY_FEASIBLE"
        else:
            ranking["state"] = "NOT_EVALUABLE"
    rankings.sort(
        key=lambda row: (
            -row["coordinate_provenance_priority"],
            -row["containment_priority"],
            -row["common_observation_days"],
            -row["navigation_matching_days"],
            row["maximum_target_baseline_m"],
            row["reference_stations"],
            row["target_station"],
        )
    )
    for rank, ranking in enumerate(rankings, start=1):
        ranking["rank"] = rank
    # File-level pairwise overlap and full reference-plus-target overlap are both retained.
    window_rows.extend(network_temporal_rows)
    for row in records:
        row["duplicate_analysis"] = row["duplicate_status"]
    (output / "incoming_discovery.json").write_text(
        json.dumps(incoming_discovery, indent=2) + "\n", encoding="utf-8"
    )
    _csv(output / "file_inventory.csv", records)
    (output / "file_inventory.json").write_text(
        json.dumps(records, indent=2, default=str) + "\n", encoding="utf-8"
    )
    _csv(output / "duplicate_analysis.csv", dup_rows)
    _csv(output / "station_metadata.csv", metadata_rows)
    _csv(
        output / "rinex_header_audit.csv",
        [r for r in records if r["parsing_status"] != "NOT_RINEX"],
    )
    _csv(output / "observation_coverage.csv", [r for r in obs])
    _csv(output / "navigation_coverage.csv", [r for r in nav])
    _csv(output / "external_navigation_products.csv", external_navigation)
    _csv(output / "coordinate_provenance.csv", provenance_rows)
    _csv(output / "coordinate_discrepancies.csv", coordinate_conflicts)
    _csv(output / "station_day_availability.csv", availability_rows)
    _csv(output / "common_observation_windows.csv", window_rows)
    _csv(output / "station_overlap_matrix.csv", overlap_rows)
    _csv(
        output / "network_temporal_coverage.csv",
        network_temporal_rows
        + [
            {
                "network_id": "DATASET_SUMMARY",
                "station_count": len(stations),
                "calendar_days_with_observations": len(all_days),
                "days_with_pairwise_header_overlap": len(matched_dates),
                "time_scales_seen": sorted(
                    {w[2] for rec in stations.values() for w in rec["windows"]}
                ),
                "header_intersections_only": True,
                "epoch_counts_inspected": True,
            }
        ],
    )
    _csv(
        output / "navigation_availability.csv",
        [
            {
                "navigation_files": len(nav),
                "navigation_dates_from_headers_or_names": sorted(archive_nav_dates),
                "external_navigation_dates": sorted(external_nav_dates),
                "matched_observation_navigation_dates": matched_nav_dates,
                "observation_dates_requiring_navigation": missing_nav_dates,
                "external_navigation_product_count": len(external_navigation),
                "external_navigation_products_checked": True,
                "additional_products_downloaded": False,
            }
        ],
    )
    _csv(output / "network_geometry.csv", geometries)
    _csv(output / "reference_combinations.csv", geometries)
    _csv(output / "held_out_geometry.csv", held)
    _csv(output / "geometry_rankings.csv", rankings)
    (output / "network_geometry.geojson").write_text(
        json.dumps(geojson, indent=2) + "\n", encoding="utf-8"
    )
    manifest = {
        "archive_path": str(archive),
        "incoming_discovery": incoming_discovery,
        "archive_size": archive_size,
        "archive_sha256": archive_hash,
        "archive_member_count": len(records),
        "uncompressed_bytes_declared": sum(r["file_size"] for r in records),
        "corrupt_or_incomplete_files": bad_paths,
        "raw_data_extracted": False,
        "station_count": len(stations),
        "geometry_southern_max_latitude_deg": southern_max_latitude_deg,
        "observation_files": len(obs),
        "navigation_files": len(nav),
        "external_navigation_products": len(external_navigation),
        "date_coverage": [min(all_days), max(all_days)] if all_days else [],
        "common_header_overlap_days": len(matched_dates),
        "observation_dates_with_navigation": matched_nav_dates,
        "observation_dates_missing_navigation": missing_nav_dates,
        "coordinate_status_counts": {
            state: sum(1 for r in metadata_rows if r["coordinate_status"] == state)
            for state in ("VERIFIED", "PROVISIONAL", "MISSING")
        },
        "coordinate_source_limits": (
            "Only RINEX APPROX POSITION XYZ was found unless registry evidence "
            "supplies frame, epoch, and source."
        ),
        "overall_state": (
            "AUDIT_BLOCKED_FORMAT_OR_INTEGRITY_ISSUES"
            if bad_paths
            else "AUDIT_BLOCKED_COORDINATE_PROVENANCE"
            if any(r["coordinate_status"] != "VERIFIED" for r in metadata_rows)
            else "AUDIT_COMPLETE_DATA_INSUFFICIENT"
        ),
        "time_note": (
            "Header date/time fields are retained in declared system; no "
            "UTC/GPS conversion was applied."
        ),
        "navigation_note": (
            "This pipeline inventories archive navigation members; external "
            "BKG/IGS products are separately inspected by run script."
        ),
        "generated_utc": datetime.now(UTC).isoformat(),
        "software_version": "0.1.0",
    }
    (output / "raw_archive_manifest.json").write_text(
        json.dumps({"archives": [manifest]}, indent=2) + "\n", encoding="utf-8"
    )
    (output / "sha256_manifest.json").write_text(
        json.dumps(
            {
                "archive": {"path": str(archive), "size": archive_size, "sha256": archive_hash},
                "derived_files": (
                    "Generated from inventory; member hashes are in file_inventory.json"
                ),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (output / "audit_summary.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    derived_hashes = {}
    for path in sorted(output.iterdir()):
        if path.is_file() and path.name != "derived_sha256_manifest.json":
            digest, size = _archive_sha256(path)
            derived_hashes[path.name] = {"sha256": digest, "size_bytes": size}
    (output / "derived_sha256_manifest.json").write_text(
        json.dumps(derived_hashes, indent=2) + "\n", encoding="utf-8"
    )
    return manifest
