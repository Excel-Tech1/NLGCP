"""Reusable broadcast-navigation recovery for the Southern Nigeria audit.

The module separates four deterministic stages:

1. read audit evidence and build a dated recovery target manifest;
2. generate documented archive candidates in priority order;
3. download through an injectable transport with explicit failure statuses;
4. validate compression, RINEX structure, date, and satellite coverage.

No positioning, correction generation, or accuracy assessment is performed.
"""

from __future__ import annotations

import csv
import gzip
import hashlib
import json
import re
import shutil
from collections.abc import Callable, Iterable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from .archive_access import (
    ArchiveDownloader,
    Credentials,
    DownloadConfig,
    DownloadRequest,
    Transport,
    UrllibTransport,
    expected_magic_for,
)
from .recovery import decompress_unix_compress, parse_rinex2_navigation

STATUS_VALIDATED = "VALIDATED"
STATUS_PARTIAL = "PARTIAL"
STATUS_MISSING = "MISSING"
STATUS_REJECTED = "REJECTED"
STATUS_SOURCE_UNAVAILABLE = "SOURCE_UNAVAILABLE"
STATUS_AUTHENTICATION_REQUIRED = "AUTHENTICATION_REQUIRED"

DEFAULT_PROVIDERS = ("CDDIS", "BKG", "IGN", "GSSC", "SIO")
PROVIDER_LABELS = {
    "CDDIS": "NASA CDDIS",
    "BKG": "BKG/IGS public archive",
    "IGN": "IGN public archive",
    "GSSC": "ESA GSSC archive",
    "SIO": "SIO/SOPAC archive",
}
MERGED_RINEX3_START_YEAR = 2017
RINEX2_FILENAME = re.compile(
    r"^(?P<prefix>brdc|auto)(?P<doy>\d{3})0\.(?P<yy>\d{2})(?P<system>[ng])"
    r"\.(?P<compression>Z|GZ)$",
    re.IGNORECASE,
)
RINEX3_FILENAME = re.compile(
    r"^BRDC00IGS_R_(?P<year>\d{4})(?P<doy>\d{3})\d{4}_01D_MN\.rnx\.gz$",
    re.IGNORECASE,
)
RINEX3_EPOCH = re.compile(
    r"^(?P<system>[A-Z])(?P<prn>\d{2})[ \t]+"
    r"(?P<year>\d{4})[ \t]+(?P<month>\d{1,2})[ \t]+(?P<day>\d{1,2})[ \t]+"
    r"(?P<hour>\d{1,2})[ \t]+(?P<minute>\d{1,2})[ \t]+(?P<second>[\d.]+)"
)
RINEX2_EPOCH = re.compile(
    r"^\s*(?P<prn>\d{1,2})\s+(?P<yy>\d{1,2})\s+(?P<month>\d{1,2})\s+"
    r"(?P<day>\d{1,2})\s+(?P<hour>\d{1,2})\s+(?P<minute>\d{1,2})\s+"
    r"(?P<second>\d{1,2}(?:\.\d+)?)\s+(?P<flag>[0-6])\s+(?P<count>\d+)"
)
CONSTELLATION_NAMES = {
    "G": "GPS",
    "R": "GLONASS",
    "E": "GALILEO",
    "C": "BEIDOU",
    "J": "QZSS",
    "S": "SBAS",
}
SYSTEM_CODES = {"GPS": "N", "GLONASS": "G"}
SYSTEM_ORDER = {"GPS": 0, "GLONASS": 1}
RINEX3_RECORD_LENGTH = {"G": 8, "R": 4, "E": 8, "C": 8, "J": 8, "S": 4}
STATUS_RANK = {
    STATUS_VALIDATED: 5,
    STATUS_PARTIAL: 4,
    STATUS_REJECTED: 3,
    STATUS_MISSING: 2,
    STATUS_AUTHENTICATION_REQUIRED: 1,
    STATUS_SOURCE_UNAVAILABLE: 0,
}
TARGET_FIELDS = (
    "date",
    "year",
    "doy",
    "network_id",
    "stations",
    "target_stations",
    "required_systems",
    "required_satellites",
    "window_count",
    "windows_json",
    "source_files_json",
    "notes",
)
CANDIDATE_FIELDS = (
    "target_date",
    "system",
    "rinex_version",
    "provider",
    "candidate_source",
    "filename",
    "url",
    "compression",
    "priority",
    "applicable",
    "notes",
)
ATTEMPT_FIELDS = (
    "target_date",
    "year",
    "doy",
    "network_id",
    "stations",
    "product_system",
    "product_type",
    "rinex_version",
    "provider",
    "candidate_source",
    "original_url",
    "actual_download_url",
    "filename",
    "http_status",
    "download_status",
    "download_error",
    "file_size",
    "sha256",
    "download_timestamp_utc",
    "stored_path",
    "compression_status",
    "rinex_validation_status",
    "navigation_epoch_count",
    "navigation_epoch_dates",
    "first_epoch",
    "last_epoch",
    "satellites",
    "constellations",
    "health_zero_record_count",
    "health_nonzero_record_count",
    "validation_warnings",
    "recovery_status",
    "failure_reason",
)
RECORD_FIELDS = (
    "target_date",
    "year",
    "doy",
    "network_id",
    "stations",
    "product_system",
    "recovery_status",
    "failure_reason",
    "attempt_count",
    "attempted_providers",
    "best_provider",
    "filename",
    "file_size",
    "sha256",
    "navigation_epoch_count",
    "satellites",
    "constellations",
    "validation_warnings",
    "stored_path",
    "admitted_path",
)
DATE_FIELDS = (
    "date",
    "year",
    "doy",
    "network_id",
    "stations",
    "required_systems",
    "gps_status",
    "gps_satellite_count",
    "gps_epoch_count",
    "glonass_status",
    "glonass_satellite_count",
    "glonass_epoch_count",
    "mixed_status",
    "mixed_satellite_count",
    "mixed_epoch_count",
    "date_coverage_status",
    "warnings",
)


class NavigationValidationError(ValueError):
    """A payload failed a terminal navigation validation check."""

    def __init__(self, reason: str, *, compression_status: str = "NOT_ATTEMPTED") -> None:
        super().__init__(reason)
        self.reason = reason
        self.compression_status = compression_status


@dataclass(frozen=True)
class ObservationWindow:
    """A candidate station/day observation window from the audit."""

    start: str
    end: str
    time_system: str
    duration_s: float
    source_files: tuple[str, ...]

    def to_json(self) -> dict[str, object]:
        return {
            "start": self.start,
            "end": self.end,
            "time_system": self.time_system,
            "duration_s": self.duration_s,
            "source_files": list(self.source_files),
        }


@dataclass(frozen=True)
class RecoveryTarget:
    """One observation date selected for navigation recovery."""

    date: str
    year: int
    doy: int
    network_id: str
    stations: tuple[str, ...]
    target_stations: tuple[str, ...]
    windows: tuple[ObservationWindow, ...]
    required_systems: tuple[str, ...]
    required_satellites: tuple[str, ...]
    source_files: tuple[str, ...]
    notes: tuple[str, ...] = ()

    def to_json(self) -> dict[str, object]:
        return {
            "date": self.date,
            "year": self.year,
            "doy": self.doy,
            "network_id": self.network_id,
            "stations": list(self.stations),
            "target_stations": list(self.target_stations),
            "required_systems": list(self.required_systems),
            "required_satellites": list(self.required_satellites),
            "windows": [window.to_json() for window in self.windows],
            "source_files": list(self.source_files),
            "notes": list(self.notes),
        }


@dataclass(frozen=True)
class TargetInventory:
    """Selected targets plus the deterministic selection record."""

    targets: tuple[RecoveryTarget, ...]
    selection: dict[str, object]


@dataclass(frozen=True)
class ArchiveCandidate:
    """A documented archive product candidate for one target date."""

    target_date: str
    product_system: str
    rinex_version: str
    provider: str
    candidate_source: str
    filename: str
    url: str
    compression: str
    priority: int
    applicable: bool = True
    notes: tuple[str, ...] = ()

    @property
    def product_type(self) -> str:
        return "RINEX2_NAV" if self.rinex_version == "2" else "RINEX3_NAV"

    @property
    def requires_auth(self) -> bool:
        return self.provider == "CDDIS"

    @property
    def expected_system_code(self) -> str:
        return SYSTEM_CODES.get(self.product_system, "MIXED")

    def to_json(self) -> dict[str, object]:
        return {
            "target_date": self.target_date,
            "system": self.product_system,
            "rinex_version": self.rinex_version,
            "provider": self.provider,
            "candidate_source": self.candidate_source,
            "filename": self.filename,
            "url": self.url,
            "compression": self.compression,
            "priority": self.priority,
            "applicable": self.applicable,
            "notes": list(self.notes),
        }


@dataclass(frozen=True)
class FilenameInfo:
    """Parsed product date and system from a documented filename."""

    filename: str
    year: int
    doy: int
    system: str
    rinex_version: str
    compression: str
    prefix: str


@dataclass(frozen=True)
class ValidationResult:
    """Validation outcome for one downloaded product."""

    status: str
    rinex_validation_status: str
    compression_status: str
    reason: str
    warnings: tuple[str, ...]
    compressed_size: int
    compressed_sha256: str
    decompressed_sha256: str
    navigation_epoch_count: int = 0
    navigation_epoch_dates: tuple[str, ...] = ()
    first_epoch: str = ""
    last_epoch: str = ""
    satellites: tuple[str, ...] = ()
    constellations: tuple[str, ...] = ()
    health_zero_record_count: int = 0
    health_nonzero_record_count: int = 0

    def with_hashes(self, size: int, sha256: str) -> ValidationResult:
        return ValidationResult(
            status=self.status,
            rinex_validation_status=self.rinex_validation_status,
            compression_status=self.compression_status,
            reason=self.reason,
            warnings=self.warnings,
            compressed_size=size,
            compressed_sha256=sha256,
            decompressed_sha256=self.decompressed_sha256,
            navigation_epoch_count=self.navigation_epoch_count,
            navigation_epoch_dates=self.navigation_epoch_dates,
            first_epoch=self.first_epoch,
            last_epoch=self.last_epoch,
            satellites=self.satellites,
            constellations=self.constellations,
            health_zero_record_count=self.health_zero_record_count,
            health_nonzero_record_count=self.health_nonzero_record_count,
        )


def _empty_validation(
    status: str,
    reason: str,
    *,
    compression_status: str = "NOT_ATTEMPTED",
) -> ValidationResult:
    return ValidationResult(
        status=status,
        rinex_validation_status="NOT_ATTEMPTED",
        compression_status=compression_status,
        reason=reason,
        warnings=(),
        compressed_size=0,
        compressed_sha256="",
        decompressed_sha256="",
    )


@dataclass(frozen=True)
class Attempt:
    """One candidate attempt for a target/system pair."""

    provider: str
    candidate_source: str
    product_type: str
    rinex_version: str
    original_url: str
    actual_download_url: str
    filename: str
    http_status: int
    download_status: str
    download_error: str
    file_size: int
    sha256: str
    download_timestamp_utc: str
    stored_path: str
    admitted_path: str
    compression_status: str
    rinex_validation_status: str
    navigation_epoch_count: int
    navigation_epoch_dates: tuple[str, ...]
    first_epoch: str
    last_epoch: str
    satellites: tuple[str, ...]
    constellations: tuple[str, ...]
    health_zero_record_count: int
    health_nonzero_record_count: int
    validation_warnings: tuple[str, ...]
    recovery_status: str
    failure_reason: str
    priority: int

    def to_json(self) -> dict[str, object]:
        return {
            "provider": self.provider,
            "candidate_source": self.candidate_source,
            "product_type": self.product_type,
            "rinex_version": self.rinex_version,
            "original_url": self.original_url,
            "actual_download_url": self.actual_download_url,
            "filename": self.filename,
            "http_status": self.http_status,
            "download_status": self.download_status,
            "download_error": self.download_error,
            "file_size": self.file_size,
            "sha256": self.sha256,
            "download_timestamp_utc": self.download_timestamp_utc,
            "stored_path": self.stored_path,
            "admitted_path": self.admitted_path,
            "compression_status": self.compression_status,
            "rinex_validation_status": self.rinex_validation_status,
            "navigation_epoch_count": self.navigation_epoch_count,
            "navigation_epoch_dates": list(self.navigation_epoch_dates),
            "first_epoch": self.first_epoch,
            "last_epoch": self.last_epoch,
            "satellites": list(self.satellites),
            "constellations": list(self.constellations),
            "health_zero_record_count": self.health_zero_record_count,
            "health_nonzero_record_count": self.health_nonzero_record_count,
            "validation_warnings": list(self.validation_warnings),
            "recovery_status": self.recovery_status,
            "failure_reason": self.failure_reason,
        }


@dataclass(frozen=True)
class ProductRecovery:
    """Final status and attempt history for one target/system product."""

    target_date: str
    year: int
    doy: int
    network_id: str
    stations: tuple[str, ...]
    product_system: str
    attempts: tuple[Attempt, ...]
    best: Attempt | None
    final_status: str
    failure_reason: str


@dataclass(frozen=True)
class DateRecovery:
    """Final status and product records for one observation date."""

    target: RecoveryTarget
    products: tuple[ProductRecovery, ...]
    status: str
    warnings: tuple[str, ...]


def parse_iso_date(value: str) -> date:
    """Parse an ISO calendar date and reject datetime strings."""
    if len(value) != 10:
        raise ValueError(f"expected YYYY-MM-DD date, got {value!r}")
    return date.fromisoformat(value)


def doy_for_date(value: str) -> int:
    """Return the one-based day of year for an ISO date."""
    return parse_iso_date(value).timetuple().tm_yday


def date_for_doy(year: int, doy: int) -> str:
    """Return the ISO date for a one-based day of year."""
    maximum = date(year, 12, 31).timetuple().tm_yday
    if doy < 1 or doy > maximum:
        raise ValueError(f"day of year {doy} is outside year {year}")
    return (date(year, 1, 1) + timedelta(days=doy - 1)).isoformat()


def _two_digit_year(year: int) -> int:
    return year % 100


def rinex2_filename(year: int, doy: int, system: str, *, prefix: str = "brdc") -> str:
    """Build a documented RINEX 2 daily navigation filename."""
    suffix = "n" if system.upper() == "GPS" else "g"
    return f"{prefix}{doy:03d}0.{_two_digit_year(year):02d}{suffix}.Z"


def rinex3_filename(year: int, doy: int) -> str:
    """Build the documented merged RINEX 3 navigation filename."""
    return f"BRDC00IGS_R_{year}{doy:03d}0000_01D_MN.rnx.gz"


def merged_rinex3_available(year: int) -> bool:
    """Return whether the merged RINEX 3 BRDC product is documented for a year."""
    return year >= MERGED_RINEX3_START_YEAR


def parse_navigation_filename(filename: str) -> FilenameInfo | None:
    """Parse a documented RINEX 2 or merged RINEX 3 navigation filename."""
    match = RINEX2_FILENAME.match(filename)
    if match:
        yy = int(match.group("yy"))
        year = 2000 + yy if yy < 80 else 1900 + yy
        suffix = match.group("system").lower()
        return FilenameInfo(
            filename=filename,
            year=year,
            doy=int(match.group("doy")),
            system="GPS" if suffix == "n" else "GLONASS",
            rinex_version="2",
            compression="unix_compress",
            prefix=match.group("prefix").lower(),
        )
    match = RINEX3_FILENAME.match(filename)
    if match:
        return FilenameInfo(
            filename=filename,
            year=int(match.group("year")),
            doy=int(match.group("doy")),
            system="MIXED",
            rinex_version="3",
            compression="gzip",
            prefix="BRDC00IGS_R",
        )
    return None


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        return [dict(row) for row in reader]


def _json_string_list(value: str) -> tuple[str, ...]:
    if not value.strip():
        return ()
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return tuple(part.strip() for part in value.split(";") if part.strip())
    if isinstance(parsed, list):
        return tuple(str(item) for item in parsed)
    return (str(parsed),)


def _systems_from_audit(value: str) -> frozenset[str]:
    systems: set[str] = set()
    for item in _json_string_list(value):
        upper = item.strip().upper()
        if upper in {"MIXED", "M"}:
            systems.update({"GPS", "GLONASS"})
        elif upper.startswith("GPS") or upper == "G":
            systems.add("GPS")
        elif upper.startswith("GLONASS") or upper in {"GLO", "R"}:
            systems.add("GLONASS")
    return frozenset(systems)


def _network_stations(row: Mapping[str, str]) -> tuple[str, ...]:
    references = [item for item in row.get("reference_stations", "").split("+") if item]
    target = row.get("target_station", "").strip()
    if target:
        references.append(target)
    return tuple(sorted(set(references)))


def _window_from_row(row: Mapping[str, str]) -> ObservationWindow | None:
    start = row.get("start", "").strip()
    end = row.get("end", "").strip()
    if not start or not end:
        return None
    try:
        duration = float(row.get("duration_s", "0") or 0)
    except ValueError:
        duration = 0.0
    return ObservationWindow(
        start=start,
        end=end,
        time_system=row.get("time_system", "").strip(),
        duration_s=duration,
        source_files=_json_string_list(row.get("source_files", "")),
    )


def load_recovery_targets(
    audit_run: Path,
    *,
    year: int | None = None,
    include_secondary: bool = False,
    constellation_evidence: Path | None = None,
) -> TargetInventory:
    """Read audit evidence and select recovery targets without hardcoded dates."""
    network_path = audit_run / "network_temporal_coverage.csv"
    observation_path = audit_run / "observation_coverage.csv"
    if not network_path.exists():
        raise FileNotFoundError(f"missing audit evidence: {network_path}")
    if not observation_path.exists():
        raise FileNotFoundError(f"missing audit evidence: {observation_path}")
    rows = [
        row
        for row in _read_csv(network_path)
        if row.get("network_id", "") != "DATASET_SUMMARY"
        and row.get("date", "").strip()
        and row.get("target_station", "").strip()
    ]
    observations = {row["relative_path"]: row for row in _read_csv(observation_path)}
    groups: dict[frozenset[str], list[dict[str, str]]] = {}
    for row in rows:
        row_date = row["date"].strip()
        try:
            parsed = parse_iso_date(row_date)
        except ValueError:
            continue
        if year is not None and parsed.year != year:
            continue
        stations = _network_stations(row)
        if not stations:
            continue
        groups.setdefault(frozenset(stations), []).append(row)
    if not groups:
        raise ValueError("no candidate observation windows found in audit evidence")
    ranked = sorted(
        groups.items(),
        key=lambda item: (-len({row["date"].strip() for row in item[1]}), tuple(sorted(item[0]))),
    )
    selected = ranked if include_secondary else ranked[:1]
    satellite_evidence: dict[tuple[str, str], set[str]] = {}
    if constellation_evidence is not None and constellation_evidence.exists():
        for row in _read_csv(constellation_evidence):
            if row.get("parse_status", "").strip().upper() != "PARSED":
                continue
            evidence_key = (
                row.get("date", "").strip(),
                row.get("station", "").strip().upper(),
            )
            for satellite in row.get("satellite_ids_observed", "").split(";"):
                if satellite.strip():
                    satellite_evidence.setdefault(evidence_key, set()).add(
                        satellite.strip().upper()
                    )
    targets: list[RecoveryTarget] = []
    candidate_records: list[dict[str, object]] = []
    for station_set, group_rows in selected:
        dates = sorted({row["date"].strip() for row in group_rows})
        network_id = "+".join(sorted(station_set))
        candidate_records.append(
            {
                "network_id": network_id,
                "stations": list(sorted(station_set)),
                "date_count": len(dates),
                "first_date": dates[0],
                "last_date": dates[-1],
            }
        )
        for target_date in dates:
            date_rows = [row for row in group_rows if row["date"].strip() == target_date]
            windows: dict[tuple[str, str, str, float], ObservationWindow] = {}
            source_files: set[str] = set()
            target_stations: set[str] = set()
            time_systems: set[str] = set()
            for row in date_rows:
                window = _window_from_row(row)
                if window is not None:
                    window_key = (
                        window.start,
                        window.end,
                        window.time_system,
                        window.duration_s,
                    )
                    existing = windows.get(window_key)
                    if existing is None:
                        windows[window_key] = window
                    else:
                        combined = tuple(
                            sorted(set(existing.source_files) | set(window.source_files))
                        )
                        windows[window_key] = ObservationWindow(
                            start=window.start,
                            end=window.end,
                            time_system=window.time_system,
                            duration_s=window.duration_s,
                            source_files=combined,
                        )
                    source_files.update(window.source_files)
                target_stations.add(row.get("target_station", "").strip())
                if row.get("time_system", "").strip():
                    time_systems.add(row["time_system"].strip())
            required_systems: set[str] = set()
            missing_system_evidence = False
            for source in source_files:
                observation = observations.get(source)
                if observation is None:
                    missing_system_evidence = True
                    continue
                systems = _systems_from_audit(observation.get("systems", ""))
                if systems:
                    required_systems.update(systems)
                else:
                    missing_system_evidence = True
            required_satellites: set[str] = set()
            for station in station_set:
                required_satellites.update(
                    satellite_evidence.get((target_date, station.upper()), set())
                )
            notes: list[str] = []
            if missing_system_evidence:
                notes.append("OBSERVATION_SYSTEM_EVIDENCE_INCOMPLETE")
            if not required_satellites:
                notes.append("NO_OBSERVATION_SATELLITE_EVIDENCE")
            if len(selected) > 1:
                notes.append("SECONDARY_CANDIDATE_INCLUDED")
            targets.append(
                RecoveryTarget(
                    date=target_date,
                    year=int(target_date[:4]),
                    doy=doy_for_date(target_date),
                    network_id=network_id,
                    stations=tuple(sorted(station_set)),
                    target_stations=tuple(sorted(target_stations)),
                    windows=tuple(sorted(windows.values(), key=lambda item: item.start)),
                    required_systems=tuple(
                        sorted(
                            required_systems,
                            key=lambda item: SYSTEM_ORDER.get(item, 99),
                        )
                    ),
                    required_satellites=tuple(sorted(required_satellites)),
                    source_files=tuple(sorted(source_files)),
                    notes=tuple(notes),
                )
            )
    selection: dict[str, object] = {
        "selection_rule": (
            "primary candidate is the station set with the most distinct observation dates; "
            "secondary candidates are included only when requested"
        ),
        "include_secondary": include_secondary,
        "year_filter": year,
        "candidate_networks": candidate_records,
        "selected_network": candidate_records[0]["network_id"] if candidate_records else "",
        "selected_date_count": len(targets),
        "time_systems_seen": sorted(
            {
                window.time_system
                for target in targets
                for window in target.windows
                if window.time_system
            }
        ),
    }
    return TargetInventory(
        targets=tuple(sorted(targets, key=lambda item: item.date)),
        selection=selection,
    )


def _provider_candidates(
    target: RecoveryTarget,
    system: str,
    providers: Sequence[str],
) -> list[ArchiveCandidate]:
    year, doy = target.year, target.doy
    yy = _two_digit_year(year)
    suffix = "n" if system == "GPS" else "g"
    filename = rinex2_filename(year, doy, system)
    candidates: list[ArchiveCandidate] = []
    priority = 0
    for provider in providers:
        urls: tuple[tuple[str, str], ...]
        candidate_filename = filename
        if provider == "CDDIS":
            base = "https://cddis.nasa.gov/archive/gnss/data/daily"
            urls = (
                (
                    f"{base}/{year}/{doy:03d}/{yy:02d}{suffix}/{filename}",
                    "CDDIS daily RINEX 2 navigation",
                ),
                (f"{base}/{year}/brdc/{filename}", "CDDIS yearly brdc RINEX 2 navigation"),
            )
        elif provider == "BKG":
            urls = (
                (
                    f"https://igs.bkg.bund.de/root_ftp/IGS/BRDC/{year}/{doy:03d}/{filename}",
                    "BKG daily RINEX 2 navigation",
                ),
            )
        elif provider == "IGN":
            urls = (
                (
                    f"https://igs.ign.fr/pub/igs/data/{year}/{doy:03d}/{filename}",
                    "IGN daily RINEX 2 navigation",
                ),
            )
        elif provider == "GSSC":
            urls = (
                (
                    f"https://gssc.esa.int/gnss/data/daily/{year}/{doy:03d}/"
                    f"{yy:02d}{suffix}/{filename}",
                    "GSSC daily RINEX 2 navigation",
                ),
            )
        elif provider == "SIO":
            sio_name = rinex2_filename(year, doy, system, prefix="auto")
            candidate_filename = sio_name
            urls = (
                (
                    f"https://lox.ucsd.edu/rinex/{year}/{doy:03d}/{sio_name}",
                    "SIO daily RINEX 2 navigation",
                ),
            )
        else:
            continue
        for url, label in urls:
            candidates.append(
                ArchiveCandidate(
                    target_date=target.date,
                    product_system=system,
                    rinex_version="2",
                    provider=provider,
                    candidate_source=label,
                    filename=candidate_filename,
                    url=url,
                    compression="unix_compress",
                    priority=priority,
                )
            )
            priority += 1
    return candidates


def _rinex3_candidates(
    target: RecoveryTarget,
    providers: Sequence[str],
) -> list[ArchiveCandidate]:
    year, doy = target.year, target.doy
    yy = _two_digit_year(year)
    filename = rinex3_filename(year, doy)
    applicable = merged_rinex3_available(year)
    notes = (
        ()
        if applicable
        else ("merged RINEX 3 BRDC product is not documented before 2017",)
    )
    candidates: list[ArchiveCandidate] = []
    priority = 1000
    for provider in providers:
        urls: tuple[tuple[str, str], ...]
        if provider == "CDDIS":
            base = "https://cddis.nasa.gov/archive/gnss/data/daily"
            urls = (
                (
                    f"{base}/{year}/{doy:03d}/{yy:02d}p/{filename}",
                    "CDDIS daily merged RINEX 3 navigation",
                ),
                (f"{base}/{year}/brdc/{filename}", "CDDIS yearly brdc merged RINEX 3 navigation"),
            )
        elif provider == "BKG":
            urls = (
                (
                    f"https://igs.bkg.bund.de/root_ftp/IGS/BRDC/{year}/{doy:03d}/{filename}",
                    "BKG daily merged RINEX 3 navigation",
                ),
            )
        elif provider == "IGN":
            urls = (
                (
                    f"https://igs.ign.fr/pub/igs/data/{year}/{doy:03d}/{filename}",
                    "IGN daily merged RINEX 3 navigation",
                ),
            )
        elif provider == "GSSC":
            urls = (
                (
                    f"https://gssc.esa.int/gnss/data/daily/{year}/{doy:03d}/"
                    f"{yy:02d}p/{filename}",
                    "GSSC daily merged RINEX 3 navigation",
                ),
            )
        else:
            continue
        for url, label in urls:
            candidates.append(
                ArchiveCandidate(
                    target_date=target.date,
                    product_system="MIXED",
                    rinex_version="3",
                    provider=provider,
                    candidate_source=label,
                    filename=filename,
                    url=url,
                    compression="gzip",
                    priority=priority,
                    applicable=applicable,
                    notes=notes,
                )
            )
            priority += 1
    return candidates


def build_archive_candidates(
    target: RecoveryTarget,
    providers: Sequence[str] = DEFAULT_PROVIDERS,
) -> list[ArchiveCandidate]:
    """Generate deterministic archive candidates for one target date."""
    candidates: list[ArchiveCandidate] = []
    for system in target.required_systems:
        candidates.extend(_provider_candidates(target, system, providers))
    if target.required_systems:
        candidates.extend(_rinex3_candidates(target, providers))
    return candidates


def _navigation_header_line(lines: Sequence[str]) -> str | None:
    return next((line for line in lines if "RINEX VERSION / TYPE" in line), None)


def _header_end(lines: Sequence[str]) -> int | None:
    return next(
        (index for index, line in enumerate(lines) if line[60:80].strip() == "END OF HEADER"),
        None,
    )


def decompress_navigation_payload(
    payload: bytes,
    compression: str,
) -> tuple[bytes, str]:
    """Decompress a navigation payload and fail explicitly on corruption."""
    if compression == "unix_compress":
        if not payload.startswith(b"\x1f\x9d"):
            raise NavigationValidationError(
                "Unix-compress signature is missing",
                compression_status="MAGIC_MISMATCH",
            )
        try:
            return decompress_unix_compress(payload), "DECOMPRESSED"
        except (ValueError, RuntimeError) as exc:
            raise NavigationValidationError(
                f"invalid or corrupt Unix-compress payload: {exc}",
                compression_status="CORRUPT",
            ) from exc
    if compression == "gzip":
        if not payload.startswith(b"\x1f\x8b"):
            raise NavigationValidationError(
                "gzip signature is missing",
                compression_status="MAGIC_MISMATCH",
            )
        try:
            return gzip.decompress(payload), "DECOMPRESSED"
        except (OSError, EOFError, ValueError) as exc:
            raise NavigationValidationError(
                f"invalid or corrupt gzip payload: {exc}",
                compression_status="CORRUPT",
            ) from exc
    if compression == "none":
        return payload, "UNCOMPRESSED"
    raise NavigationValidationError(
        f"unsupported compression {compression!r}",
        compression_status="UNSUPPORTED",
    )


def _parse_rinex3_navigation(
    text: str,
    expected_date: str,
    required_satellites: set[str] | None = None,
) -> dict[str, Any]:
    lines = text.splitlines()
    header_end = _header_end(lines)
    header = _navigation_header_line(lines)
    if header_end is None or header is None:
        return {"status": "INVALID_OR_MISSING_RINEX_HEADER", "satellites": [], "epochs": []}
    version = header[:9].strip()
    if not version.startswith("3"):
        return {
            "status": "UNSUPPORTED_NAVIGATION_HEADER",
            "version": version,
            "file_type": header[20:21].strip().upper(),
        }
    file_type = header[20:21].strip().upper()
    if file_type not in {"N", ""}:
        return {
            "status": "UNSUPPORTED_NAVIGATION_HEADER",
            "version": version,
            "file_type": file_type,
        }
    epoch_records: list[tuple[str, datetime]] = []
    data_lines = lines[header_end + 1 :]
    index = 0
    while index < len(data_lines):
        match = RINEX3_EPOCH.match(data_lines[index])
        if not match:
            index += 1
            continue
        system = match.group("system").upper()
        record_length = RINEX3_RECORD_LENGTH.get(system)
        if record_length is None:
            index += 1
            continue
        try:
            stamp = datetime(
                int(match.group("year")),
                int(match.group("month")),
                int(match.group("day")),
                int(match.group("hour")),
                int(match.group("minute")),
                int(float(match.group("second"))),
            )
            epoch_records.append((f"{system}{int(match.group('prn')):02d}", stamp))
        except (ValueError, OverflowError):
            index += record_length
            continue
        index += record_length
    expected = parse_iso_date(expected_date)
    actual_dates = sorted({stamp.date().isoformat() for _, stamp in epoch_records})
    satellites = sorted({satellite for satellite, _ in epoch_records})
    missing = sorted((required_satellites or set()) - set(satellites))
    if not epoch_records:
        status = "NO_EPHEMERIS_RECORDS"
    elif expected_date not in actual_dates:
        status = "NO_EXPECTED_DATE_EPHEMERIS"
    elif missing:
        status = "MISSING_SATELLITE_EPHEMERIDES"
    else:
        status = "VALIDATED"
    return {
        "status": status,
        "version": version,
        "file_type": file_type,
        "header_system": header[40:41].strip().upper(),
        "expected_date": expected_date,
        "ephemeris_record_count": len(epoch_records),
        "satellites": satellites,
        "missing_required_satellites": missing,
        "epochs": [stamp.isoformat() for _, stamp in epoch_records],
        "ephemeris_dates": actual_dates,
        "expected_day_present": expected in {stamp.date() for _, stamp in epoch_records},
        "health_indicator_count": 0,
        "health_flag_values": [],
        "health_zero_record_count": 0,
        "health_nonzero_record_count": 0,
        "health_fields_parsed": False,
    }


def validate_navigation_bytes(
    payload: bytes,
    candidate: ArchiveCandidate,
    target: RecoveryTarget,
) -> ValidationResult:
    """Validate one compressed navigation payload against its target date."""
    compressed_sha256 = hashlib.sha256(payload).hexdigest()
    filename_info = parse_navigation_filename(candidate.filename)
    if filename_info is None:
        return _empty_validation(STATUS_REJECTED, "unrecognised navigation filename").with_hashes(
            len(payload), compressed_sha256
        )
    if filename_info.year != target.year or filename_info.doy != target.doy:
        return _empty_validation(
            STATUS_REJECTED,
            (
                f"filename date {filename_info.year}/{filename_info.doy:03d} does not match "
                f"target {target.year}/{target.doy:03d}"
            ),
        ).with_hashes(len(payload), compressed_sha256)
    if filename_info.rinex_version != candidate.rinex_version:
        return _empty_validation(
            STATUS_REJECTED,
            "filename RINEX version does not match candidate version",
        ).with_hashes(len(payload), compressed_sha256)
    if (
        candidate.product_system != "MIXED"
        and filename_info.system != candidate.product_system
    ):
        return _empty_validation(
            STATUS_REJECTED,
            "filename constellation does not match candidate constellation",
        ).with_hashes(len(payload), compressed_sha256)
    try:
        decompressed, compression_status = decompress_navigation_payload(
            payload, candidate.compression
        )
    except NavigationValidationError as exc:
        return _empty_validation(
            STATUS_REJECTED,
            exc.reason,
            compression_status=exc.compression_status,
        ).with_hashes(len(payload), compressed_sha256)
    try:
        text = decompressed.decode("ascii", errors="replace")
    except UnicodeError as exc:
        return _empty_validation(
            STATUS_REJECTED,
            f"payload is not ASCII text: {exc}",
            compression_status=compression_status,
        ).with_hashes(len(payload), compressed_sha256)
    lines = text.splitlines()
    header = _navigation_header_line(lines)
    if header is None or _header_end(lines) is None:
        return _empty_validation(
            STATUS_REJECTED,
            "missing or incomplete RINEX header",
            compression_status=compression_status,
        ).with_hashes(len(payload), compressed_sha256)
    version = header[:9].strip()
    required_satellites = {
        satellite
        for satellite in target.required_satellites
        if satellite.startswith("G" if candidate.product_system == "GPS" else "R")
    }
    if candidate.product_system == "MIXED":
        required_satellites = set(target.required_satellites)
    if version.startswith("2"):
        if candidate.product_system == "MIXED":
            return _empty_validation(
                STATUS_REJECTED,
                "RINEX 2 mixed navigation is not a supported candidate",
                compression_status=compression_status,
            ).with_hashes(len(payload), compressed_sha256)
        parsed = parse_rinex2_navigation(
            text,
            target.date,
            candidate.expected_system_code,
            required_satellites or None,
        )
    elif version.startswith("3"):
        parsed = _parse_rinex3_navigation(
            text,
            target.date,
            required_satellites or None,
        )
    else:
        return _empty_validation(
            STATUS_REJECTED,
            f"unsupported RINEX version {version!r}",
            compression_status=compression_status,
        ).with_hashes(len(payload), compressed_sha256)
    return _result_from_parsed(
        parsed,
        payload=payload,
        compressed_sha256=compressed_sha256,
        decompressed=decompressed,
        compression_status=compression_status,
        candidate=candidate,
        required_satellites=required_satellites,
    )


def _result_from_parsed(
    parsed: Mapping[str, Any],
    *,
    payload: bytes,
    compressed_sha256: str,
    decompressed: bytes,
    compression_status: str,
    candidate: ArchiveCandidate,
    required_satellites: set[str],
) -> ValidationResult:
    parsed_status = str(parsed.get("status", "REJECTED"))
    warnings: list[str] = []
    if parsed_status == "VALIDATED":
        status = STATUS_VALIDATED
    elif parsed_status == "MISSING_SATELLITE_EPHEMERIDES":
        status = STATUS_PARTIAL
        warnings.append(
            "MISSING_OBSERVED_SATELLITES: "
            + ",".join(str(item) for item in parsed.get("missing_required_satellites", []))
        )
    else:
        status = STATUS_REJECTED
    satellites = tuple(str(item) for item in parsed.get("satellites", []))
    epochs = tuple(str(item) for item in parsed.get("epochs", []))
    epoch_dates = tuple(str(item) for item in parsed.get("ephemeris_dates", []))
    constellations = tuple(
        sorted({CONSTELLATION_NAMES.get(satellite[0], satellite[0]) for satellite in satellites})
    )
    health_nonzero = int(parsed.get("health_nonzero_record_count", 0) or 0)
    health_zero = int(parsed.get("health_zero_record_count", 0) or 0)
    if len(epoch_dates) > 1:
        warnings.append("ADJACENT_DAY_EPHEMERIDES_PRESENT")
    if health_nonzero:
        warnings.append("NONZERO_HEALTH_FLAGS_PRESENT")
    if candidate.rinex_version == "3":
        warnings.append("RINEX3_HEALTH_FIELDS_NOT_PARSED")
    reason = "" if status != STATUS_REJECTED else f"navigation parser status: {parsed_status}"
    return ValidationResult(
        status=status,
        rinex_validation_status=parsed_status,
        compression_status=compression_status,
        reason=reason,
        warnings=tuple(warnings),
        compressed_size=len(payload),
        compressed_sha256=compressed_sha256,
        decompressed_sha256=hashlib.sha256(decompressed).hexdigest(),
        navigation_epoch_count=int(parsed.get("ephemeris_record_count", 0) or 0),
        navigation_epoch_dates=epoch_dates,
        first_epoch=min(epochs) if epochs else "",
        last_epoch=max(epochs) if epochs else "",
        satellites=satellites,
        constellations=constellations,
        health_zero_record_count=health_zero,
        health_nonzero_record_count=health_nonzero,
    )


def validate_downloaded_file(
    path: Path,
    candidate: ArchiveCandidate,
    target: RecoveryTarget,
) -> ValidationResult:
    """Read and validate one downloaded product file."""
    try:
        payload = path.read_bytes()
    except OSError as exc:
        return _empty_validation(STATUS_REJECTED, f"cannot read downloaded file: {exc}")
    result = validate_navigation_bytes(payload, candidate, target)
    return result.with_hashes(len(payload), hashlib.sha256(payload).hexdigest())


def _rank_attempt(attempt: Attempt) -> int:
    return STATUS_RANK.get(attempt.recovery_status, -1)


def _best_attempt(attempts: Sequence[Attempt]) -> Attempt | None:
    best: Attempt | None = None
    for attempt in attempts:
        if best is None or _rank_attempt(attempt) > _rank_attempt(best):
            best = attempt
    return best


def _relative(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def execute_candidate(
    target: RecoveryTarget,
    candidate: ArchiveCandidate,
    downloader: ArchiveDownloader,
    run_dir: Path,
) -> Attempt:
    """Download and validate one archive candidate."""
    attempt_dir = run_dir / "navigation-products" / "attempts" / candidate.provider.lower()
    request = DownloadRequest(
        url=candidate.url,
        filename=candidate.filename,
        provider=candidate.provider,
        requires_auth=candidate.requires_auth,
        expected_magic=expected_magic_for(candidate.filename),
        applicable=candidate.applicable,
        not_applicable_reason="; ".join(candidate.notes),
    )
    outcome = downloader.download(request, attempt_dir)
    validation = _empty_validation(STATUS_MISSING, outcome.error)
    if outcome.status in {"ACQUIRED", "CACHED"} and outcome.stored_path:
        validation = validate_downloaded_file(Path(outcome.stored_path), candidate, target)
    recovery_status = (
        validation.status
        if outcome.status in {"ACQUIRED", "CACHED"}
        else outcome.status
    )
    admitted_path = ""
    failure_reason = (
        validation.reason
        if outcome.status in {"ACQUIRED", "CACHED"}
        else outcome.error
    )
    if validation.status in {STATUS_VALIDATED, STATUS_PARTIAL} and outcome.stored_path:
        admitted_dir = run_dir / "navigation-products" / (
            "validated" if validation.status == STATUS_VALIDATED else "partial"
        )
        admitted_dir.mkdir(parents=True, exist_ok=True)
        admitted = admitted_dir / candidate.filename
        shutil.copy2(outcome.stored_path, admitted)
        admitted_path = _relative(admitted, run_dir)
    return Attempt(
        provider=candidate.provider,
        candidate_source=candidate.candidate_source,
        product_type=candidate.product_type,
        rinex_version=candidate.rinex_version,
        original_url=candidate.url,
        actual_download_url=outcome.final_url or outcome.url,
        filename=candidate.filename,
        http_status=outcome.http_status,
        download_status=outcome.status,
        download_error=outcome.error,
        file_size=outcome.size_bytes or validation.compressed_size,
        sha256=outcome.sha256 or validation.compressed_sha256,
        download_timestamp_utc=outcome.retrieved_utc,
        stored_path=_relative(Path(outcome.stored_path), run_dir) if outcome.stored_path else "",
        admitted_path=admitted_path,
        compression_status=validation.compression_status,
        rinex_validation_status=validation.rinex_validation_status,
        navigation_epoch_count=validation.navigation_epoch_count,
        navigation_epoch_dates=validation.navigation_epoch_dates,
        first_epoch=validation.first_epoch,
        last_epoch=validation.last_epoch,
        satellites=validation.satellites,
        constellations=validation.constellations,
        health_zero_record_count=validation.health_zero_record_count,
        health_nonzero_record_count=validation.health_nonzero_record_count,
        validation_warnings=validation.warnings,
        recovery_status=recovery_status,
        failure_reason=failure_reason,
        priority=candidate.priority,
    )


def recover_product(
    target: RecoveryTarget,
    system: str,
    candidates: Sequence[ArchiveCandidate],
    downloader: ArchiveDownloader,
    run_dir: Path,
) -> ProductRecovery:
    """Try candidates in priority order until a complete product is validated."""
    attempts: list[Attempt] = []
    for candidate in sorted(candidates, key=lambda item: item.priority):
        if candidate.product_system != system:
            continue
        attempt = execute_candidate(target, candidate, downloader, run_dir)
        attempts.append(attempt)
        if attempt.recovery_status == STATUS_VALIDATED:
            break
    best = _best_attempt(attempts)
    final_status = best.recovery_status if best is not None else STATUS_MISSING
    failure_reason = ""
    if best is not None and best.recovery_status != STATUS_VALIDATED:
        failure_reason = best.failure_reason or best.download_error
    if best is None:
        failure_reason = "no archive candidate generated"
    return ProductRecovery(
        target_date=target.date,
        year=target.year,
        doy=target.doy,
        network_id=target.network_id,
        stations=target.stations,
        product_system=system,
        attempts=tuple(attempts),
        best=best,
        final_status=final_status,
        failure_reason=failure_reason,
    )


def _effective_status(product: ProductRecovery | None) -> str:
    return product.final_status if product is not None else STATUS_MISSING


def _product_for_system(
    products: Sequence[ProductRecovery],
    system: str,
) -> ProductRecovery | None:
    candidates = [
        product
        for product in products
        if product.product_system in {system, "MIXED"}
    ]
    if not candidates:
        return None
    return max(
        candidates,
        key=lambda product: (
            STATUS_RANK.get(product.final_status, -1),
            product.product_system == system,
        ),
    )


def aggregate_date_status(
    products: Sequence[ProductRecovery],
    required_systems: Sequence[str],
) -> str:
    """Combine product statuses without promoting incomplete coverage."""
    statuses = [
        _effective_status(_product_for_system(products, system))
        for system in required_systems
    ]
    if not statuses:
        return STATUS_MISSING
    if all(status == STATUS_VALIDATED for status in statuses):
        return STATUS_VALIDATED
    if any(status in {STATUS_VALIDATED, STATUS_PARTIAL} for status in statuses):
        return STATUS_PARTIAL
    if any(status == STATUS_REJECTED for status in statuses):
        return STATUS_REJECTED
    if all(status == STATUS_MISSING for status in statuses):
        return STATUS_MISSING
    if any(status == STATUS_SOURCE_UNAVAILABLE for status in statuses):
        return STATUS_SOURCE_UNAVAILABLE
    if any(status == STATUS_AUTHENTICATION_REQUIRED for status in statuses):
        return STATUS_AUTHENTICATION_REQUIRED
    return STATUS_MISSING


def _date_warnings(
    target: RecoveryTarget,
    status: str,
    products: Sequence[ProductRecovery],
) -> tuple[str, ...]:
    warnings: list[str] = []
    if not target.required_systems:
        warnings.append("OBSERVATION_SYSTEMS_UNKNOWN")
    if status == STATUS_PARTIAL:
        missing = [
            system
            for system in target.required_systems
            if _effective_status(_product_for_system(products, system)) != STATUS_VALIDATED
        ]
        if missing:
            warnings.append("NOT_ALL_REQUIRED_SYSTEMS_VALIDATED: " + ",".join(missing))
    for product in products:
        if product.best is not None:
            warnings.extend(product.best.validation_warnings)
    return tuple(sorted(set(warnings)))


def build_date_recoveries(
    targets: Sequence[RecoveryTarget],
    products: Sequence[ProductRecovery],
) -> list[DateRecovery]:
    """Build deterministic date-level recovery summaries."""
    by_date: dict[str, list[ProductRecovery]] = {}
    for product in products:
        by_date.setdefault(product.target_date, []).append(product)
    result: list[DateRecovery] = []
    for target in sorted(targets, key=lambda item: item.date):
        date_products = tuple(
            sorted(by_date.get(target.date, []), key=lambda item: item.product_system)
        )
        status = aggregate_date_status(date_products, target.required_systems)
        result.append(
            DateRecovery(
                target=target,
                products=date_products,
                status=status,
                warnings=_date_warnings(target, status, date_products),
            )
        )
    return result


def _jsonable(value: object) -> object:
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    return value


def _csv_value(value: object) -> object:
    if isinstance(value, (list, tuple, dict)):
        return json.dumps(_jsonable(value), sort_keys=True)
    return value


def _write_csv(path: Path, fieldnames: Sequence[str], rows: Iterable[Mapping[str, object]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(fieldnames), extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: _csv_value(value) for key, value in row.items()})


def _write_json(path: Path, payload: object) -> None:
    with path.open("w", encoding="utf-8") as stream:
        json.dump(_jsonable(payload), stream, indent=2, sort_keys=True)
        stream.write("\n")


def write_target_manifests(
    run_dir: Path,
    audit_run: Path,
    inventory: TargetInventory,
    audit_summary: Mapping[str, object],
) -> dict[str, str]:
    """Write the machine-readable target manifest and its CSV projection."""
    run_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "audit_run": str(audit_run),
        "audit_summary": _jsonable(dict(audit_summary)),
        "selection": inventory.selection,
        "target_count": len(inventory.targets),
        "targets": [target.to_json() for target in inventory.targets],
    }
    json_path = run_dir / "recovery_targets.json"
    csv_path = run_dir / "recovery_targets.csv"
    _write_json(json_path, payload)
    rows = [
        {
            "date": target.date,
            "year": target.year,
            "doy": target.doy,
            "network_id": target.network_id,
            "stations": target.stations,
            "target_stations": target.target_stations,
            "required_systems": target.required_systems,
            "required_satellites": target.required_satellites,
            "window_count": len(target.windows),
            "windows_json": [window.to_json() for window in target.windows],
            "source_files_json": target.source_files,
            "notes": target.notes,
        }
        for target in inventory.targets
    ]
    _write_csv(csv_path, TARGET_FIELDS, rows)
    return {"targets_json": str(json_path), "targets_csv": str(csv_path)}


def write_candidate_manifests(
    run_dir: Path,
    targets: Sequence[RecoveryTarget],
    candidates_by_date: Mapping[str, Sequence[ArchiveCandidate]],
) -> dict[str, str]:
    """Write the deterministic archive candidate plan."""
    json_path = run_dir / "archive_candidates.json"
    csv_path = run_dir / "archive_candidates.csv"
    payload = {
        "candidate_count": sum(len(value) for value in candidates_by_date.values()),
        "candidates": [
            candidate.to_json()
            for target in sorted(targets, key=lambda item: item.date)
            for candidate in candidates_by_date.get(target.date, [])
        ],
    }
    _write_json(json_path, payload)
    rows = [
        {
            "target_date": candidate.target_date,
            "system": candidate.product_system,
            "rinex_version": candidate.rinex_version,
            "provider": candidate.provider,
            "candidate_source": candidate.candidate_source,
            "filename": candidate.filename,
            "url": candidate.url,
            "compression": candidate.compression,
            "priority": candidate.priority,
            "applicable": candidate.applicable,
            "notes": candidate.notes,
        }
        for target in sorted(targets, key=lambda item: item.date)
        for candidate in candidates_by_date.get(target.date, [])
    ]
    _write_csv(csv_path, CANDIDATE_FIELDS, rows)
    return {"candidates_json": str(json_path), "candidates_csv": str(csv_path)}


def _attempt_row(
    target: RecoveryTarget,
    product_system: str,
    attempt: Attempt,
) -> dict[str, object]:
    return {
        "target_date": target.date,
        "year": target.year,
        "doy": target.doy,
        "network_id": target.network_id,
        "stations": target.stations,
        "product_system": product_system,
        "product_type": attempt.product_type,
        "rinex_version": attempt.rinex_version,
        "provider": attempt.provider,
        "candidate_source": attempt.candidate_source,
        "original_url": attempt.original_url,
        "actual_download_url": attempt.actual_download_url,
        "filename": attempt.filename,
        "http_status": attempt.http_status,
        "download_status": attempt.download_status,
        "download_error": attempt.download_error,
        "file_size": attempt.file_size,
        "sha256": attempt.sha256,
        "download_timestamp_utc": attempt.download_timestamp_utc,
        "stored_path": attempt.stored_path,
        "compression_status": attempt.compression_status,
        "rinex_validation_status": attempt.rinex_validation_status,
        "navigation_epoch_count": attempt.navigation_epoch_count,
        "navigation_epoch_dates": attempt.navigation_epoch_dates,
        "first_epoch": attempt.first_epoch,
        "last_epoch": attempt.last_epoch,
        "satellites": attempt.satellites,
        "constellations": attempt.constellations,
        "health_zero_record_count": attempt.health_zero_record_count,
        "health_nonzero_record_count": attempt.health_nonzero_record_count,
        "validation_warnings": attempt.validation_warnings,
        "recovery_status": attempt.recovery_status,
        "failure_reason": attempt.failure_reason,
    }


def _record_row(product: ProductRecovery) -> dict[str, object]:
    best = product.best
    return {
        "target_date": product.target_date,
        "year": product.year,
        "doy": product.doy,
        "network_id": product.network_id,
        "stations": product.stations,
        "product_system": product.product_system,
        "recovery_status": product.final_status,
        "failure_reason": product.failure_reason,
        "attempt_count": len(product.attempts),
        "attempted_providers": [attempt.provider for attempt in product.attempts],
        "best_provider": best.provider if best is not None else "",
        "filename": best.filename if best is not None else "",
        "file_size": best.file_size if best is not None else 0,
        "sha256": best.sha256 if best is not None else "",
        "navigation_epoch_count": best.navigation_epoch_count if best is not None else 0,
        "satellites": best.satellites if best is not None else (),
        "constellations": best.constellations if best is not None else (),
        "validation_warnings": best.validation_warnings if best is not None else (),
        "stored_path": best.stored_path if best is not None else "",
        "admitted_path": best.admitted_path if best is not None else "",
    }


def _coverage_row(recovery: DateRecovery) -> dict[str, object]:
    gps = _product_for_system(recovery.products, "GPS")
    glonass = _product_for_system(recovery.products, "GLONASS")
    mixed = next(
        (product for product in recovery.products if product.product_system == "MIXED"),
        None,
    )

    def _status(product: ProductRecovery | None) -> str:
        return product.final_status if product is not None else STATUS_MISSING

    def _satellites(product: ProductRecovery | None, prefix: str) -> int:
        if product is None or product.best is None:
            return 0
        return sum(1 for satellite in product.best.satellites if satellite.startswith(prefix))

    def _epochs(product: ProductRecovery | None) -> int:
        if product is None or product.best is None or product.product_system == "MIXED":
            return 0
        return product.best.navigation_epoch_count

    return {
        "date": recovery.target.date,
        "year": recovery.target.year,
        "doy": recovery.target.doy,
        "network_id": recovery.target.network_id,
        "stations": recovery.target.stations,
        "required_systems": recovery.target.required_systems,
        "gps_status": _status(gps),
        "gps_satellite_count": _satellites(gps, "G"),
        "gps_epoch_count": _epochs(gps),
        "glonass_status": _status(glonass),
        "glonass_satellite_count": _satellites(glonass, "R"),
        "glonass_epoch_count": _epochs(glonass),
        "mixed_status": _status(mixed),
        "mixed_satellite_count": len(mixed.best.satellites) if mixed and mixed.best else 0,
        "mixed_epoch_count": mixed.best.navigation_epoch_count if mixed and mixed.best else 0,
        "date_coverage_status": recovery.status,
        "warnings": recovery.warnings,
    }


def write_recovery_outputs(
    run_dir: Path,
    *,
    targets: Sequence[RecoveryTarget],
    products: Sequence[ProductRecovery],
    recoveries: Sequence[DateRecovery],
    inventory: TargetInventory,
    audit_run: Path,
    audit_summary: Mapping[str, object],
    authentication: Mapping[str, object],
    run_id: str,
    generated_utc: str,
) -> dict[str, str]:
    """Write JSON, CSV, Markdown, and checksum recovery evidence."""
    attempt_rows: list[dict[str, object]] = []
    for product in products:
        target = next(
            (item for item in targets if item.date == product.target_date),
            None,
        )
        if target is None:
            continue
        for attempt in product.attempts:
            attempt_rows.append(_attempt_row(target, product.product_system, attempt))
    inventory_csv = run_dir / "navigation_product_inventory.csv"
    _write_csv(inventory_csv, ATTEMPT_FIELDS, attempt_rows)
    records_csv = run_dir / "navigation_recovery_records.csv"
    _write_csv(records_csv, RECORD_FIELDS, [_record_row(product) for product in products])
    coverage_csv = run_dir / "navigation_date_coverage.csv"
    _write_csv(coverage_csv, DATE_FIELDS, [_coverage_row(recovery) for recovery in recoveries])
    status_counts = _status_counts(recoveries)
    product_counts: dict[str, int] = {}
    for product in products:
        product_counts[product.final_status] = product_counts.get(product.final_status, 0) + 1
    overall_status = _overall_status(recoveries)
    manifest = {
        "run_id": run_id,
        "generated_utc": generated_utc,
        "audit_run": str(audit_run),
        "audit_summary": _jsonable(dict(audit_summary)),
        "selection": inventory.selection,
        "authentication": dict(authentication),
        "target_count": len(targets),
        "targets": [target.to_json() for target in targets],
        "records": [
            {
                "target_date": product.target_date,
                "year": product.year,
                "doy": product.doy,
                "network_id": product.network_id,
                "stations": list(product.stations),
                "product_system": product.product_system,
                "recovery_status": product.final_status,
                "failure_reason": product.failure_reason,
                "best_attempt": product.best.to_json() if product.best else None,
                "attempts": [attempt.to_json() for attempt in product.attempts],
            }
            for product in products
        ],
        "date_summary": [
            {
                "date": recovery.target.date,
                "year": recovery.target.year,
                "doy": recovery.target.doy,
                "network_id": recovery.target.network_id,
                "stations": list(recovery.target.stations),
                "required_systems": list(recovery.target.required_systems),
                "status": recovery.status,
                "warnings": list(recovery.warnings),
            }
            for recovery in recoveries
        ],
        "date_status_counts": status_counts,
        "product_status_counts": product_counts,
        "overall_status": overall_status,
        "scientific_admission": "NOT_ASSESSED_BY_THIS_TOOL",
        "limitations": [
            "Navigation recovery is not positioning validation.",
            "No RTK, NRTK, VRS, RTCM generation, FIX claim, or accuracy claim was made.",
            "VALIDATED means compression, RINEX header, target-date ephemeris, and "
            "available satellite-coverage checks passed for this product.",
            "Coordinate provenance and station-identity gates remain outside this manifest.",
        ],
    }
    manifest_path = run_dir / "navigation_recovery_manifest.json"
    _write_json(manifest_path, manifest)
    report_path = run_dir / "navigation_recovery_report.md"
    report_path.write_text(
        _human_report(
            run_id=run_id,
            generated_utc=generated_utc,
            audit_run=audit_run,
            inventory=inventory,
            recoveries=recoveries,
            authentication=authentication,
            status_counts=status_counts,
            product_counts=product_counts,
            overall_status=overall_status,
        ),
        encoding="utf-8",
    )
    checksum_path = run_dir / "sha256_manifest.txt"
    _write_checksum_manifest(run_dir, checksum_path)
    return {
        "manifest_json": str(manifest_path),
        "inventory_csv": str(inventory_csv),
        "records_csv": str(records_csv),
        "coverage_csv": str(coverage_csv),
        "report_md": str(report_path),
        "sha256_manifest": str(checksum_path),
    }


def _status_counts(recoveries: Sequence[DateRecovery]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for recovery in recoveries:
        counts[recovery.status] = counts.get(recovery.status, 0) + 1
    return dict(sorted(counts.items()))


def _overall_status(recoveries: Sequence[DateRecovery]) -> str:
    statuses = [recovery.status for recovery in recoveries]
    if not statuses:
        return STATUS_MISSING
    if all(status == STATUS_VALIDATED for status in statuses):
        return STATUS_VALIDATED
    if any(status in {STATUS_VALIDATED, STATUS_PARTIAL} for status in statuses):
        return STATUS_PARTIAL
    if any(status == STATUS_REJECTED for status in statuses):
        return STATUS_REJECTED
    if all(status == STATUS_MISSING for status in statuses):
        return STATUS_MISSING
    if any(status == STATUS_SOURCE_UNAVAILABLE for status in statuses):
        return STATUS_SOURCE_UNAVAILABLE
    if any(status == STATUS_AUTHENTICATION_REQUIRED for status in statuses):
        return STATUS_AUTHENTICATION_REQUIRED
    return STATUS_MISSING


def _write_checksum_manifest(run_dir: Path, path: Path) -> None:
    lines: list[str] = []
    for candidate in sorted(run_dir.rglob("*")):
        if not candidate.is_file() or candidate == path:
            continue
        digest = hashlib.sha256(candidate.read_bytes()).hexdigest()
        lines.append(f"{digest}  {_relative(candidate, run_dir)}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _human_report(
    *,
    run_id: str,
    generated_utc: str,
    audit_run: Path,
    inventory: TargetInventory,
    recoveries: Sequence[DateRecovery],
    authentication: Mapping[str, object],
    status_counts: Mapping[str, int],
    product_counts: Mapping[str, int],
    overall_status: str,
) -> str:
    lines = [
        "# Southern Nigeria Navigation Recovery",
        "",
        f"- Run: `{run_id}`",
        f"- Generated: {generated_utc}",
        f"- Audit evidence: `{audit_run}`",
        f"- Selected network: `{inventory.selection.get('selected_network', '')}`",
        f"- Target dates: {len(inventory.targets)}",
        f"- Overall navigation recovery status: `{overall_status}`",
        f"- CDDIS credentials configured: "
        f"`{authentication.get('cddis_credentials_configured', False)}`",
        "",
        "## Source policy",
        "",
        "CDDIS is the primary documented source. BKG, IGN, ESA GSSC, and SIO are",
        "traceable alternates. Candidates are attempted in deterministic priority",
        "order; a missing or rejected product is never promoted to success.",
        "",
        "## Results",
        "",
        "| Date | DOY | GPS | GLONASS | Date status | Warnings |",
        "|---|---:|---|---|---|---|",
    ]
    for recovery in recoveries:
        by_system = {product.product_system: product for product in recovery.products}
        gps = by_system.get("GPS")
        glonass = by_system.get("GLONASS")
        lines.append(
            f"| {recovery.target.date} | {recovery.target.doy} | "
            f"{gps.final_status if gps else STATUS_MISSING} | "
            f"{glonass.final_status if glonass else STATUS_MISSING} | "
            f"{recovery.status} | {'; '.join(recovery.warnings) or '-'} |"
        )
    lines.extend(
        [
            "",
            "## Status counts",
            "",
            f"- Date statuses: `{json.dumps(dict(status_counts), sort_keys=True)}`",
            f"- Product statuses: `{json.dumps(dict(product_counts), sort_keys=True)}`",
            "",
            "## Validation criteria",
            "",
            "- Compression signature and complete decompression.",
            "- RINEX header, version, and navigation file type.",
            "- Filename year/day-of-year matches the requested observation date.",
            "- At least one navigation epoch on the requested date.",
            "- Constellation/system matches the requested product.",
            "- Observed-satellite evidence is checked when supplied; missing evidence",
            "  is recorded as a warning and never silently assumed.",
            "- Nonzero health flags are recorded, not filtered out.",
            "",
            "## Limitations",
            "",
            "- Navigation recovery is not positioning validation.",
            "- No RTK, NRTK, VRS, RTCM, FIX, or accuracy claim was made.",
            "- A validated navigation file does not validate station coordinates,",
            "  monument identity, observation quality, or scientific admission.",
            "- CDDIS access requires Earthdata Login; this run records authentication",
            "  readiness and falls back only to documented public alternates.",
            "",
            "## Evidence",
            "",
            "- `recovery_targets.json`, `recovery_targets.csv`",
            "- `archive_candidates.json`, `archive_candidates.csv`",
            "- `navigation_product_inventory.csv`, `navigation_recovery_records.csv`",
            "- `navigation_date_coverage.csv`",
            "- `navigation_recovery_manifest.json`",
            "- `navigation-products/`",
            "- `sha256_manifest.txt`",
            "",
        ]
    )
    return "\n".join(lines)


def _audit_summary(audit_run: Path) -> dict[str, object]:
    path = audit_run / "audit_summary.json"
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as stream:
        parsed = json.load(stream)
    return parsed if isinstance(parsed, dict) else {}


def _write_dry_run_outputs(
    run_dir: Path,
    *,
    run_id: str,
    generated_utc: str,
    audit_run: Path,
    inventory: TargetInventory,
    candidates_by_date: Mapping[str, Sequence[ArchiveCandidate]],
    authentication: Mapping[str, object],
) -> dict[str, str]:
    candidates = [
        candidate.to_json()
        for target in sorted(inventory.targets, key=lambda item: item.date)
        for candidate in candidates_by_date.get(target.date, [])
    ]
    payload = {
        "run_id": run_id,
        "generated_utc": generated_utc,
        "dry_run": True,
        "audit_run": str(audit_run),
        "planned_output": str(run_dir),
        "authentication": dict(authentication),
        "target_count": len(inventory.targets),
        "target_dates": [target.date for target in inventory.targets],
        "candidate_count": len(candidates),
        "candidates": candidates,
    }
    json_path = run_dir / "dry_run_plan.json"
    _write_json(json_path, payload)
    lines = [
        "# Navigation Recovery Dry Run",
        "",
        f"- Run: `{run_id}`",
        f"- Generated: {generated_utc}",
        f"- Planned output: `{run_dir}`",
        f"- Audit evidence: `{audit_run}`",
        f"- Target dates: {len(inventory.targets)}",
        f"- Candidate products: {len(candidates)}",
        f"- CDDIS credentials configured: "
        f"`{authentication.get('cddis_credentials_configured', False)}`",
        "",
        "## Target dates",
        "",
        "| Date | DOY | Stations | Required systems |",
        "|---|---:|---|---|",
    ]
    for target in inventory.targets:
        lines.append(
            f"| {target.date} | {target.doy} | {', '.join(target.stations)} | "
            f"{', '.join(target.required_systems)} |"
        )
    lines.extend(
        [
            "",
            "## Candidate sources",
            "",
            "| Date | System | Provider | RINEX | Applicable | Filename |",
            "|---|---|---|---|---|---|",
        ]
    )
    for target in inventory.targets:
        for candidate in candidates_by_date.get(target.date, []):
            lines.append(
                f"| {candidate.target_date} | {candidate.product_system} | "
                f"{candidate.provider} | {candidate.rinex_version} | "
                f"{candidate.applicable} | `{candidate.filename}` |"
            )
    md_path = run_dir / "dry_run_plan.md"
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"dry_run_json": str(json_path), "dry_run_md": str(md_path)}


def authentication_report(credentials: Credentials) -> dict[str, object]:
    """Describe authentication readiness without exposing secret values."""
    methods: list[str] = []
    if credentials.token:
        methods.append("BEARER_TOKEN")
    if credentials.username and credentials.password:
        methods.append("BASIC_AUTH")
    return {
        "cddis_credentials_configured": credentials.ready,
        "methods": methods,
        "environment_variables": [
            "CDDIS_TOKEN or EARTHDATA_TOKEN",
            "CDDIS_USERNAME and CDDIS_PASSWORD (or EARTHDATA_* equivalents)",
        ],
        "credentials_persisted": False,
    }


def run_recovery(
    audit_run: Path,
    output_root: Path,
    *,
    run_id: str | None = None,
    dry_run: bool = True,
    year: int | None = None,
    include_secondary: bool = False,
    constellation_evidence: Path | None = None,
    workers: int = 4,
    providers: Sequence[str] = DEFAULT_PROVIDERS,
    download_config: DownloadConfig | None = None,
    credentials: Credentials | None = None,
    transport: Transport | None = None,
    now: Callable[[], datetime] | None = None,
) -> dict[str, object]:
    """Plan or execute navigation recovery and return a deterministic summary."""
    clock = now or (lambda: datetime.now(UTC))
    generated = clock()
    run_id = run_id or f"run-{generated.strftime('%Y%m%dT%H%M%SZ')}"
    run_dir = output_root / run_id
    if not dry_run and (run_dir / "navigation_recovery_manifest.json").exists():
        raise FileExistsError(
            f"recovery run already completed in {run_dir}; choose a new --run-id"
        )
    inventory = load_recovery_targets(
        audit_run,
        year=year,
        include_secondary=include_secondary,
        constellation_evidence=constellation_evidence,
    )
    audit_summary = _audit_summary(audit_run)
    target_paths = write_target_manifests(run_dir, audit_run, inventory, audit_summary)
    candidates_by_date = {
        target.date: build_archive_candidates(target, providers)
        for target in inventory.targets
    }
    candidate_paths = write_candidate_manifests(run_dir, inventory.targets, candidates_by_date)
    credentials = credentials or Credentials.from_environment()
    authentication = authentication_report(credentials)
    if dry_run:
        dry_paths = _write_dry_run_outputs(
            run_dir,
            run_id=run_id,
            generated_utc=generated.isoformat(),
            audit_run=audit_run,
            inventory=inventory,
            candidates_by_date=candidates_by_date,
            authentication=authentication,
        )
        return {
            "run_id": run_id,
            "run_dir": str(run_dir),
            "dry_run": True,
            "target_count": len(inventory.targets),
            "target_dates": [target.date for target in inventory.targets],
            "candidate_count": sum(len(value) for value in candidates_by_date.values()),
            "authentication": authentication,
            "planned_output": str(run_dir),
            "targets_json": target_paths["targets_json"],
            "candidates_csv": candidate_paths["candidates_csv"],
            **dry_paths,
        }
    downloader = ArchiveDownloader(
        transport or UrllibTransport(),
        download_config or DownloadConfig(),
        credentials,
        now=clock,
    )
    tasks: list[tuple[RecoveryTarget, str]] = [
        (target, system)
        for target in sorted(inventory.targets, key=lambda item: item.date)
        for system in target.required_systems
    ]
    results: dict[tuple[str, str], ProductRecovery] = {}
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = {
            pool.submit(
                recover_product,
                target,
                system,
                candidates_by_date[target.date],
                downloader,
                run_dir,
            ): (target.date, system)
            for target, system in tasks
        }
        for future in as_completed(futures):
            product = future.result()
            results[(product.target_date, product.product_system)] = product
    for target in inventory.targets:
        if not target.required_systems:
            continue
        date_products = [
            product
            for product in results.values()
            if product.target_date == target.date
        ]
        if all(
            _effective_status(_product_for_system(date_products, system))
            == STATUS_VALIDATED
            for system in target.required_systems
        ):
            continue
        applicable_mixed = [
            candidate
            for candidate in candidates_by_date[target.date]
            if candidate.product_system == "MIXED" and candidate.applicable
        ]
        if not applicable_mixed:
            continue
        mixed = recover_product(
            target,
            "MIXED",
            candidates_by_date[target.date],
            downloader,
            run_dir,
        )
        if mixed.attempts:
            results[(target.date, "MIXED")] = mixed
    for target in inventory.targets:
        if target.required_systems:
            continue
        results[(target.date, "UNKNOWN")] = ProductRecovery(
            target_date=target.date,
            year=target.year,
            doy=target.doy,
            network_id=target.network_id,
            stations=target.stations,
            product_system="UNKNOWN",
            attempts=(),
            best=None,
            final_status=STATUS_MISSING,
            failure_reason="OBSERVATION_SYSTEMS_UNKNOWN",
        )
    products = tuple(
        sorted(
            results.values(),
            key=lambda item: (item.target_date, item.product_system),
        )
    )
    recoveries = build_date_recoveries(inventory.targets, products)
    paths = write_recovery_outputs(
        run_dir,
        targets=inventory.targets,
        products=products,
        recoveries=recoveries,
        inventory=inventory,
        audit_run=audit_run,
        audit_summary=audit_summary,
        authentication=authentication,
        run_id=run_id,
        generated_utc=generated.isoformat(),
    )
    status_counts = _status_counts(recoveries)
    return {
        "run_id": run_id,
        "run_dir": str(run_dir),
        "dry_run": False,
        "target_count": len(inventory.targets),
        "target_dates": [target.date for target in inventory.targets],
        "candidate_count": sum(len(value) for value in candidates_by_date.values()),
        "authentication": authentication,
        "overall_status": _overall_status(recoveries),
        "date_status_counts": status_counts,
        "targets_json": target_paths["targets_json"],
        "candidates_csv": candidate_paths["candidates_csv"],
        **paths,
    }
