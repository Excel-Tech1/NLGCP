"""Archive, RINEX, temporal and geometry primitives for the NIGNET audit."""

from __future__ import annotations

import bz2
import gzip
import hashlib
import itertools
import math
import re
import shutil
import stat
import tarfile
import zipfile
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import BinaryIO, cast

WGS84_A = 6378137.0
WGS84_F = 1 / 298.257223563
WGS84_E2 = WGS84_F * (2 - WGS84_F)
BUFFER_SIZE = 1024 * 1024


@dataclass(frozen=True)
class RinexHeader:
    version: str = ""
    file_type: str = "unknown"
    marker_name: str = ""
    marker_number: str = ""
    receiver_serial: str = ""
    receiver_type: str = ""
    receiver_version: str = ""
    antenna_serial: str = ""
    antenna_type: str = ""
    antenna_delta_hen: tuple[float, float, float] | None = None
    approx_xyz: tuple[float, float, float] | None = None
    time_system: str = ""
    first_obs: str = ""
    last_obs: str = ""
    interval_s: float | None = None
    systems: tuple[str, ...] = ()
    observables: tuple[str, ...] = ()
    header_lines: int = 0
    missing_fields: tuple[str, ...] = ()
    parse_status: str = "incomplete"


def open_payload(path: Path) -> BinaryIO:
    """Open common transport compression without changing the source file."""
    suffixes = [s.lower() for s in path.suffixes]
    if suffixes and suffixes[-1] == ".gz":
        return cast(BinaryIO, gzip.open(path, "rb"))
    if suffixes and suffixes[-1] == ".bz2":
        return cast(BinaryIO, bz2.open(path, "rb"))
    return path.open("rb")


def sha256_stream(stream: BinaryIO) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    while chunk := stream.read(BUFFER_SIZE):
        digest.update(chunk)
        size += len(chunk)
    return digest.hexdigest(), size


def classify_file(name: str, head: bytes = b"") -> tuple[str, str]:
    lower = name.lower()
    compression = (
        "gzip"
        if lower.endswith(".gz")
        else "bzip2"
        if lower.endswith(".bz2")
        else "unix_compress"
        if lower.endswith(".z")
        else "none"
    )
    text = head[:4096].decode("ascii", errors="ignore")
    version = next(
        (line[:9].strip() for line in text.splitlines() if "RINEX VERSION / TYPE" in line), ""
    )
    if version:
        line = next(line for line in text.splitlines() if "RINEX VERSION / TYPE" in line)
        marker = line[20:21].upper()
        return (
            "observation"
            if marker in {"O", ""}
            else "navigation"
            if marker in {"N", "G", "H", "L", "J", "C"}
            else "rinex_other",
            compression,
        )
    if re.search(r"\.(\d{2}d|crx)(\.gz|\.bz2|\.z)?$", lower):
        return "hatanaka_observation", compression
    if re.search(r"\.(\d{2}[oOdDnNgGlL]|rnx)(\.gz|\.bz2|\.z)?$", lower):
        ext = re.search(r"\.(\d{2})([odngl])", lower)
        if ext:
            return ("observation" if ext.group(2) == "o" else "navigation", compression)
        if ".rnx" in lower:
            return ("rinex_unknown", compression)
    if re.search(r"\.(crx|d)(\.gz|\.bz2|\.z)?$", lower) or lower.endswith(".d.gz"):
        return "hatanaka_observation", compression
    if any(s in lower for s in ("sinex", ".snx")):
        return "sinex", compression
    if any(
        s in lower for s in ("station", "coordinate", "coord", "site", "readme", "log", "metadata")
    ):
        return "metadata_or_document", compression
    return "unsupported", compression


def _float_fields(value: str, count: int) -> tuple[float, ...] | None:
    try:
        vals = tuple(float(v.replace("D", "E")) for v in value.split()[:count])
    except ValueError:
        return None
    return vals if len(vals) == count and all(math.isfinite(v) for v in vals) else None


def parse_rinex_header(stream: BinaryIO) -> RinexHeader:
    """Parse standard fixed-column RINEX 2/3/4 headers, leaving absent data blank."""
    values: dict[str, object] = {}
    systems: set[str] = set()
    obs: set[str] = set()
    lines = 0
    ended = False
    for raw in stream:
        line = raw.decode("ascii", errors="replace").rstrip("\r\n")
        lines += 1
        label = line[60:80].strip() if len(line) >= 60 else ""
        body = line[:60]
        if label == "RINEX VERSION / TYPE":
            values["version"] = body[:9].strip()
            marker = body[20:21].strip().upper()
            values["file_type"] = (
                "observation"
                if marker == "O"
                else "navigation"
                if marker in {"N", "G", "H", "L", "J", "C", "B", "I"}
                else "unknown"
            )
            if str(values["version"]).startswith("2"):
                legacy_system = body[40:41].strip().upper()
                if legacy_system:
                    systems.add("MIXED" if legacy_system == "M" else legacy_system)
        elif label == "MARKER NAME":
            values["marker_name"] = body.strip()
        elif label == "MARKER NUMBER":
            values["marker_number"] = body.strip()
        elif label == "REC # / TYPE / VERS":
            values["receiver_serial"], values["receiver_type"], values["receiver_version"] = (
                body[i : i + 20].strip() for i in (0, 20, 40)
            )
        elif label == "ANT # / TYPE":
            values["antenna_serial"], values["antenna_type"] = (
                body[:20].strip(),
                body[20:40].strip(),
            )
        elif label == "APPROX POSITION XYZ":
            values["approx_xyz"] = _float_fields(body, 3)
        elif label == "ANTENNA: DELTA H/E/N":
            values["antenna_delta_hen"] = _float_fields(body, 3)
        elif label == "INTERVAL":
            parsed = _float_fields(body, 1)
            values["interval_s"] = parsed[0] if parsed else None
        elif label == "TIME OF FIRST OBS":
            values["first_obs"] = body[:43].strip()
            values["time_system"] = body[48:51].strip().upper()
        elif label == "TIME OF LAST OBS":
            values["last_obs"] = body[:43].strip()
            if not values.get("time_system"):
                values["time_system"] = body[48:51].strip().upper()
        elif label == "SYS / # / OBS TYPES":
            system = body[:1].strip().upper()
            if system:
                systems.add(system)
                obs.update(re.findall(r"[A-Z][0-9][A-Z0-9]", body[6:60]))
        elif label == "# / TYPES OF OBSERV":
            obs.update(re.findall(r"[A-Z][0-9][A-Z0-9]", body[6:60]))
            obs.update(re.findall(r"[A-Z][0-9]", body[6:60]))
        elif label == "END OF HEADER":
            ended = True
            break
        if lines > 1000:
            break
    missing = tuple(k for k in ("version", "marker_name", "approx_xyz") if not values.get(k))
    return RinexHeader(
        version=str(values.get("version", "")),
        file_type=str(values.get("file_type", "unknown")),
        marker_name=str(values.get("marker_name", "")),
        marker_number=str(values.get("marker_number", "")),
        receiver_serial=str(values.get("receiver_serial", "")),
        receiver_type=str(values.get("receiver_type", "")),
        receiver_version=str(values.get("receiver_version", "")),
        antenna_serial=str(values.get("antenna_serial", "")),
        antenna_type=str(values.get("antenna_type", "")),
        antenna_delta_hen=cast(tuple[float, float, float] | None, values.get("antenna_delta_hen")),
        approx_xyz=cast(tuple[float, float, float] | None, values.get("approx_xyz")),
        time_system=str(values.get("time_system", "")),
        first_obs=str(values.get("first_obs", "")),
        last_obs=str(values.get("last_obs", "")),
        interval_s=cast(float | None, values.get("interval_s")),
        systems=tuple(sorted(systems)),
        observables=tuple(sorted(obs)),
        header_lines=lines,
        missing_fields=missing,
        parse_status="parsed" if ended else "incomplete_header",
    )


def station_code(filename: str, marker: str = "", marker_number: str = "") -> str:
    """Prefer the original four-character legacy filename code, then marker fields."""
    base = Path(filename).name
    match = re.match(r"([A-Za-z0-9]{4})", base)
    if match:
        return match.group(1).upper()
    for candidate in (marker, marker_number):
        clean = re.sub(r"[^A-Za-z0-9]", "", candidate)
        if clean:
            return clean.upper()
    return ""


def coordinate_provenance_status(
    approx_xyz: tuple[float, float, float] | None,
    source: str = "",
    reference_frame: str = "",
    coordinate_epoch: str = "",
) -> str:
    """Classify coordinates using only explicit source/frame/epoch evidence."""
    if approx_xyz is None:
        return "MISSING"
    if source.strip() and reference_frame.strip() and coordinate_epoch.strip():
        return "VERIFIED"
    return "PROVISIONAL"


def parse_header_time(value: str, default_system: str = "") -> tuple[datetime | None, str]:
    """Parse RINEX civil date fields without converting between time scales."""
    parts = value.split()
    if len(parts) < 6:
        return None, default_system
    try:
        year, month, day, hour, minute = map(int, parts[:5])
        sec = float(parts[5])
        if year < 100:
            year += 2000 if year < 80 else 1900
        whole = int(sec)
        micros = round((sec - whole) * 1_000_000)
        dt = datetime(year, month, day, hour, minute, whole, micros)
        system = parts[6].upper() if len(parts) >= 7 else default_system.upper()
        return dt, system
    except (ValueError, OverflowError):
        return None, default_system


def intersect_windows(
    windows: Sequence[tuple[datetime, datetime, str, str]],
) -> tuple[datetime, datetime] | None:
    if not windows or len({scale for _, _, scale, _ in windows}) != 1:
        return None
    if not windows[0][2].strip():
        return None
    start = max(item[0] for item in windows)
    end = min(item[1] for item in windows)
    return (start, end) if end >= start else None


def ecef_to_geodetic(x: float, y: float, z: float) -> tuple[float, float, float]:
    lon = math.atan2(y, x)
    p = math.hypot(x, y)
    lat = math.atan2(z, p * (1 - WGS84_E2))
    for _ in range(12):
        n = WGS84_A / math.sqrt(1 - WGS84_E2 * math.sin(lat) ** 2)
        h = p / max(math.cos(lat), 1e-15) - n
        next_lat = math.atan2(z, p * (1 - WGS84_E2 * n / (n + h)))
        if abs(next_lat - lat) < 1e-14:
            lat = next_lat
            break
        lat = next_lat
    n = WGS84_A / math.sqrt(1 - WGS84_E2 * math.sin(lat) ** 2)
    h = p / max(math.cos(lat), 1e-15) - n
    return math.degrees(lat), math.degrees(lon), h


def ecef_to_enu(
    xyz: tuple[float, float, float], origin: tuple[float, float, float]
) -> tuple[float, float, float]:
    lat, lon, _ = map(math.radians, ecef_to_geodetic(*origin))
    dx, dy, dz = (xyz[i] - origin[i] for i in range(3))
    return (
        -math.sin(lon) * dx + math.cos(lon) * dy,
        -math.sin(lat) * math.cos(lon) * dx
        - math.sin(lat) * math.sin(lon) * dy
        + math.cos(lat) * dz,
        math.cos(lat) * math.cos(lon) * dx
        + math.cos(lat) * math.sin(lon) * dy
        + math.sin(lat) * dz,
    )


def enu_to_ecef(
    enu: tuple[float, float, float], origin: tuple[float, float, float]
) -> tuple[float, float, float]:
    lat, lon, _ = map(math.radians, ecef_to_geodetic(*origin))
    east, north, up = enu
    dx = (
        -math.sin(lon) * east
        - math.sin(lat) * math.cos(lon) * north
        + math.cos(lat) * math.cos(lon) * up
    )
    dy = (
        math.cos(lon) * east
        - math.sin(lat) * math.sin(lon) * north
        + math.cos(lat) * math.sin(lon) * up
    )
    dz = math.cos(lat) * north + math.sin(lat) * up
    return origin[0] + dx, origin[1] + dy, origin[2] + dz


def convex_hull(points: Sequence[tuple[float, float]]) -> list[tuple[float, float]]:
    pts = sorted(set(points))
    if len(pts) <= 1:
        return pts

    def cross(o: tuple[float, float], a: tuple[float, float], b: tuple[float, float]) -> float:
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower: list[tuple[float, float]] = []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 1e-10:
            lower.pop()
        lower.append(p)
    upper: list[tuple[float, float]] = []
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 1e-10:
            upper.pop()
        upper.append(p)
    return lower[:-1] + upper[:-1]


def point_in_polygon(point: tuple[float, float], polygon: Sequence[tuple[float, float]]) -> str:
    if len(polygon) < 3:
        return "DEGENERATE"
    x, y = point
    inside = False
    for i, (x1, y1) in enumerate(polygon):
        x2, y2 = polygon[(i + 1) % len(polygon)]
        cross = (x - x1) * (y2 - y1) - (y - y1) * (x2 - x1)
        if (
            abs(cross) <= 1e-8
            and min(x1, x2) - 1e-8 <= x <= max(x1, x2) + 1e-8
            and min(y1, y2) - 1e-8 <= y <= max(y1, y2) + 1e-8
        ):
            return "BOUNDARY"
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            inside = not inside
    return "INSIDE" if inside else "OUTSIDE"


def safe_extract_zip(archive: Path, destination: Path, required_bytes: int | None = None) -> None:
    """Extract without overwrite and reject traversal, special files and links."""
    with zipfile.ZipFile(archive) as zf:
        infos = zf.infolist()
        needed = sum(i.file_size for i in infos if not i.is_dir())
        if (
            required_bytes is not None
            and shutil.disk_usage(
                destination.parent if destination.parent.exists() else Path("/")
            ).free
            < required_bytes
        ):
            raise OSError("insufficient free space for requested extraction reserve")
        if (
            shutil.disk_usage(destination.parent if destination.parent.exists() else Path("/")).free
            < needed
        ):
            raise OSError(f"insufficient disk space: need {needed} bytes")
        root = destination.resolve()
        for info in infos:
            name = info.filename.replace("\\", "/")
            pure = PurePosixPath(name)
            mode = info.external_attr >> 16
            member_type = stat.S_IFMT(mode)
            if (
                pure.is_absolute()
                or ".." in pure.parts
                or stat.S_ISLNK(mode)
                or stat.S_ISCHR(mode)
                or stat.S_ISBLK(mode)
                or stat.S_ISFIFO(mode)
                or member_type not in {0, stat.S_IFREG, stat.S_IFDIR}
            ):
                raise ValueError(f"unsafe archive member: {info.filename}")
            target = (root / Path(*pure.parts)).resolve()
            if target != root and root not in target.parents:
                raise ValueError(f"archive path escapes destination: {info.filename}")
            if target.exists():
                raise FileExistsError(target)
        root.mkdir(parents=True, exist_ok=True)
        for info in infos:
            if info.is_dir():
                (root / Path(*PurePosixPath(info.filename).parts)).mkdir(
                    parents=True, exist_ok=True
                )
                continue
            target = root / Path(*PurePosixPath(info.filename).parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as source, target.open("xb") as sink:
                shutil.copyfileobj(source, sink, BUFFER_SIZE)


def safe_extract_tar(archive: Path, destination: Path) -> None:
    """Safely extract regular files and directories from a TAR-family archive."""
    with tarfile.open(archive, mode="r:*") as tf:
        members = tf.getmembers()
        required = sum(member.size for member in members if member.isfile())
        disk_path = destination.parent if destination.parent.exists() else Path("/")
        if shutil.disk_usage(disk_path).free < required:
            raise OSError(f"insufficient disk space: need {required} bytes")
        root = destination.resolve()
        for member in members:
            pure = PurePosixPath(member.name.replace("\\", "/"))
            if (
                pure.is_absolute()
                or ".." in pure.parts
                or not (member.isdir() or member.isfile())
                or member.issym()
                or member.islnk()
                or member.isdev()
            ):
                raise ValueError(f"unsafe archive member: {member.name}")
            target = (root / Path(*pure.parts)).resolve()
            if target != root and root not in target.parents:
                raise ValueError(f"archive path escapes destination: {member.name}")
            if target.exists():
                raise FileExistsError(target)
        root.mkdir(parents=True, exist_ok=True)
        for member in members:
            target = root / Path(*PurePosixPath(member.name).parts)
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            source = tf.extractfile(member)
            if source is None:
                raise OSError(f"cannot read archive member: {member.name}")
            with source, target.open("xb") as sink:
                shutil.copyfileobj(source, sink, BUFFER_SIZE)


def combinations(
    stations: Sequence[str], sizes: Sequence[int] = (3, 4, 5)
) -> Iterator[tuple[str, ...]]:
    for size in sizes:
        if size <= len(stations):
            yield from itertools.combinations(sorted(stations), size)
