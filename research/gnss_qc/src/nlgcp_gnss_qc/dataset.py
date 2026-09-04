"""Canonical archive, identity, metadata, and external-product inputs."""

from __future__ import annotations

import gzip
import json
import re
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from nlgcp_api.rinex_inventory import sha256_file
from nlgcp_single_base.nav import brdc_source_url

from nlgcp_gnss_qc.models import SessionInput

CANONICAL_STATIONS: dict[str, tuple[str, ...]] = {
    "ABFC00NGA": ("ABFC",),
    "BKFP00NGA": ("BIKE",),
    "EKAK00NGA": ("EKAK",),
    "FUTY00NGA": ("YLAD",),
    "MGBO00NGA": ("MGBO",),
    "PHRI00NGA": ("PHRI",),
    "ULAG00NGA": ("LGLA",),
    "UNEC00NGA": ("ENEN", "UNEC"),
}
MARKER_TO_STATION = {
    marker: station_id for station_id, markers in CANONICAL_STATIONS.items() for marker in markers
}
RINEX2_NAME = re.compile(
    r"^(?P<marker>[A-Za-z0-9]{4})(?P<doy>\d{3})(?P<session>[A-Za-z0-9])"
    r"\.(?P<year>\d{2})(?P<kind>[A-Za-z])(?:\.(?P<compression>Z|gz))?$"
)
BRDC_LONG_NAME = re.compile(
    r"^BRDC[A-Z0-9]{2}[A-Z0-9]{3}_[A-Z]_"
    r"(?P<year>\d{4})(?P<doy>\d{3})\d{4}_01D_[A-Z]{2}\.rnx(?:\.gz)?$",
    re.IGNORECASE,
)
RINEX2_NAV_NAME = re.compile(
    r"^[A-Za-z0-9]{4}(?P<doy>\d{3})[A-Za-z0-9]\.(?P<year>\d{2})[NPGHQL]"
    r"(?:\.(?:Z|gz))?$",
    re.IGNORECASE,
)


class DatasetError(RuntimeError):
    """Raised for an invalid or ambiguous scientific input catalog."""


@dataclass(frozen=True, slots=True)
class NavigationProduct:
    product_type: str
    source: str | None
    relative_path: str
    coverage_start: str
    coverage_end: str
    sha256: str
    size_bytes: int
    acquisition_provenance: str | None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class CoordinateEligibility:
    station_id: str
    scientifically_valid: bool
    reference_frame: str | None
    coordinate_epoch: str | None
    source_path: str
    source_sha256: str


def load_session_inputs(data_root: Path) -> list[SessionInput]:
    """Load observation sessions from the existing canonical Phase 2 manifest."""

    manifest_path = data_root / "manifests" / "canonical-raw-archive-2024.json"
    payload: dict[str, Any] = json.loads(manifest_path.read_text(encoding="utf-8"))
    duplicate_map: dict[str, list[str]] = {}
    for duplicate in payload.get("exact_duplicates", []):
        duplicate_map.setdefault(duplicate["canonical_relative_path"], []).append(
            duplicate["excluded_source_relative_path"]
        )
    sessions: list[SessionInput] = []
    for row in payload.get("records", []):
        if row.get("artifact_type") != "observation":
            continue
        relative_path = str(row["canonical_relative_path"])
        sessions.append(
            SessionInput(
                station_id=str(row["station_id"]),
                year=int(row["year"]),
                day_of_year=int(row["day_of_year"]),
                relative_path=relative_path,
                source_relative_path=str(row["source_relative_path"]),
                sha256=str(row["sha256"]),
                size_bytes=int(row["size_bytes"]),
                exact_duplicate_sources=tuple(sorted(duplicate_map.get(relative_path, []))),
            )
        )
    if not sessions:
        raise DatasetError(f"canonical manifest has no observation records: {manifest_path}")
    return sorted(sessions, key=lambda row: (row.year, row.day_of_year, row.station_id))


def parse_filename(filename: str) -> tuple[str, int, int, str]:
    """Return marker, year, DOY, and kind for a canonical RINEX 2 filename."""

    match = RINEX2_NAME.fullmatch(filename)
    if match is None:
        raise DatasetError(f"unexpected RINEX 2 filename: {filename}")
    doy = int(match.group("doy"))
    if not 1 <= doy <= 366:
        raise DatasetError(f"day-of-year outside 1..366: {filename}")
    return (
        match.group("marker").upper(),
        2000 + int(match.group("year")),
        doy,
        match.group("kind").upper(),
    )


def resolve_identity(station_id: str, filename_marker: str, header_marker: str | None) -> str:
    """Return CANONICAL_MATCH or KNOWN_ALIAS, otherwise fail closed."""

    if station_id not in CANONICAL_STATIONS:
        raise DatasetError(f"unresolved canonical station: {station_id}")
    markers = CANONICAL_STATIONS[station_id]
    if filename_marker not in markers:
        raise DatasetError(f"filename marker {filename_marker} is not registered for {station_id}")
    if header_marker is None or header_marker.upper() not in markers:
        raise DatasetError(f"RINEX marker {header_marker!r} is not registered for {station_id}")
    if filename_marker == station_id[:4] and header_marker.upper() == station_id[:4]:
        return "CANONICAL_MATCH"
    return "KNOWN_ALIAS"


def load_coordinate_eligibility(data_root: Path) -> dict[str, CoordinateEligibility]:
    """Load only explicit Phase 3 coordinate-admission facts."""

    path = data_root / "processed" / "single-base" / "derived-coordinates.json"
    if not path.is_file():
        return {}
    source_hash = sha256_file(path)
    payload: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    result: dict[str, CoordinateEligibility] = {}
    for station_id, row in payload.get("stations", {}).items():
        result[station_id] = CoordinateEligibility(
            station_id=station_id,
            scientifically_valid=row.get("scientifically_valid") is True,
            reference_frame=row.get("reference_frame"),
            coordinate_epoch=row.get("coordinate_epoch"),
            source_path=str(path.relative_to(data_root)),
            source_sha256=source_hash,
        )
    return result


def inventory_navigation_products(data_root: Path) -> list[NavigationProduct]:
    """Inventory dated broadcast navigation products without acquiring anything."""

    root = data_root / "external-products"
    products: list[NavigationProduct] = []
    if not root.is_dir():
        return products
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        coverage = _navigation_coverage(path)
        if coverage is None:
            continue
        long_match = BRDC_LONG_NAME.fullmatch(path.name)
        source = None
        provenance = None
        if long_match is not None and path.name.upper().startswith("BRDC00IGS"):
            product_year = int(long_match.group("year"))
            product_doy = int(long_match.group("doy"))
            source = "IGS merged broadcast navigation via BKG archive"
            provenance = brdc_source_url(product_year, product_doy)
        products.append(
            NavigationProduct(
                product_type="broadcast_navigation",
                source=source,
                relative_path=str(path.relative_to(data_root)),
                coverage_start=_iso(coverage[0]),
                coverage_end=_iso(coverage[1]),
                sha256=sha256_file(path),
                size_bytes=path.stat().st_size,
                acquisition_provenance=provenance,
            )
        )
    return products


def navigation_for_session(
    products: list[NavigationProduct], year: int, day_of_year: int
) -> NavigationProduct | None:
    start = datetime.strptime(f"{year} {day_of_year:03d}", "%Y %j").replace(tzinfo=UTC)
    for product in products:
        product_start = datetime.fromisoformat(product.coverage_start.replace("Z", "+00:00"))
        product_end = datetime.fromisoformat(product.coverage_end.replace("Z", "+00:00"))
        if product_start <= start < product_end:
            return product
    return None


def _navigation_coverage(path: Path) -> tuple[datetime, datetime] | None:
    long_match = BRDC_LONG_NAME.fullmatch(path.name)
    short_match = RINEX2_NAV_NAME.fullmatch(path.name)
    match = long_match or short_match
    if match is None:
        return _navigation_body_coverage(path)
    year_text = match.group("year")
    year = int(year_text) if len(year_text) == 4 else 2000 + int(year_text)
    start = datetime.strptime(f"{year} {int(match.group('doy')):03d}", "%Y %j").replace(tzinfo=UTC)
    return start, start + timedelta(days=1)


def _navigation_body_coverage(path: Path) -> tuple[datetime, datetime] | None:
    """Best-effort dated coverage for plainly readable RINEX navigation files."""

    try:
        with (
            gzip.open(path, "rt", encoding="ascii", errors="replace")
            if path.suffix.lower() == ".gz"
            else path.open("rt", encoding="ascii", errors="replace")
        ) as handle:
            for line in handle:
                if "END OF HEADER" in line:
                    break
            epochs: list[datetime] = []
            for line in handle:
                fields = line[:23].split()
                if len(fields) < 7:
                    continue
                try:
                    year = int(fields[1])
                    year += 2000 if year < 80 else 1900
                    epochs.append(
                        datetime(
                            year,
                            int(fields[2]),
                            int(fields[3]),
                            int(fields[4]),
                            int(fields[5]),
                            int(float(fields[6])),
                            tzinfo=UTC,
                        )
                    )
                except ValueError:
                    continue
            if not epochs:
                return None
            start = min(epochs).replace(hour=0, minute=0, second=0, microsecond=0)
            return start, max(epochs) + timedelta(hours=6)
    except OSError:
        return None


def _iso(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")
