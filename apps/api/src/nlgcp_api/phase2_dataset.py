"""Canonical archive and report-only QC for preserved historical RINEX data."""

from __future__ import annotations

import csv
import json
import math
import os
import re
import shutil
import subprocess
import tempfile
from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import asdict, dataclass, replace
from datetime import UTC, date, datetime, timedelta
from pathlib import Path, PurePosixPath
from typing import Any

from nlgcp_api.rinex_inventory import format_datetime, parse_epoch_fields, sha256_file

RINEX2_NAME = re.compile(
    r"^(?P<marker>[A-Za-z0-9]{4})(?P<doy>\d{3})(?P<session>[A-Za-z0-9])"
    r"(?: \((?P<copy>\d+)\))?"
    r"\.(?P<year>\d{2})(?P<kind>[A-Za-z])(?:\.(?P<compression>Z|gz))?$"
)
STATION_FOLDER = re.compile(r"^(?P<station>[A-Z0-9]{9})\s+(?P<place>.+?)\s+-\s+Nigeria$")
OBSERVATION_KINDS = {"d", "o"}
NAVIGATION_KINDS = {"n", "g", "h", "l", "p", "q"}


class Phase2DatasetError(RuntimeError):
    """Raised when preserved data cannot be handled without ambiguity."""


@dataclass(frozen=True, slots=True)
class DeliveryFile:
    """One understood file in a preserved delivery."""

    source_path: Path
    source_relative_path: str
    station_id: str
    place_name: str
    year: int
    day_of_year: int
    session: str
    artifact_type: str
    filename: str
    size_bytes: int
    sha256: str

    @property
    def canonical_relative_path(self) -> str:
        return str(
            PurePosixPath(
                "raw",
                "nignet",
                str(self.year),
                self.station_id,
                f"{self.day_of_year:03d}",
                self.artifact_type,
                re.sub(r" \(\d+\)(?=\.)", "", self.filename),
            )
        )


@dataclass(frozen=True, slots=True)
class ArchiveRecord:
    """A verified source-to-canonical archive mapping."""

    source_relative_path: str
    canonical_relative_path: str
    station_id: str
    year: int
    day_of_year: int
    artifact_type: str
    size_bytes: int
    sha256: str


@dataclass(frozen=True, slots=True)
class DuplicateRecord:
    """An exact duplicate excluded from the canonical archive."""

    excluded_source_relative_path: str
    retained_source_relative_path: str
    canonical_relative_path: str
    sha256: str


@dataclass(frozen=True, slots=True)
class ArchiveResult:
    """Result of an idempotent canonical archive build."""

    records: list[ArchiveRecord]
    exact_duplicates: list[DuplicateRecord]


@dataclass(frozen=True, slots=True)
class HeaderMetadata:
    """Metadata stated by one RINEX header; coordinates remain frame-unknown."""

    rinex_version: str | None
    marker_name: str | None
    marker_number: str | None
    observer: str | None
    agency: str | None
    receiver_serial: str | None
    receiver_type: str | None
    receiver_firmware: str | None
    antenna_serial: str | None
    antenna_type: str | None
    approximate_position_xyz_m: tuple[float, float, float] | None
    antenna_delta_hen_m: tuple[float, float, float] | None
    header_interval_seconds: float | None
    header_first_epoch: datetime | None
    header_last_epoch: datetime | None


@dataclass(frozen=True, slots=True)
class EpochGap:
    """A discontinuity between successive observation epochs."""

    station_id: str
    day_of_year: int
    previous_epoch: str
    current_epoch: str
    elapsed_seconds: float
    expected_interval_seconds: float
    estimated_missing_epochs: int


@dataclass(frozen=True, slots=True)
class SessionQC:
    """Deterministic completeness metrics for one daily observation session."""

    canonical_relative_path: str
    sha256: str
    station_id: str
    year: int
    day_of_year: int
    filename_date: str
    parser_status: str
    converter_exit_code: int | None
    converter_message: str | None
    header: HeaderMetadata
    first_epoch: datetime | None
    last_epoch: datetime | None
    sampling_interval_seconds: float | None
    epoch_count: int
    duplicate_epoch_count: int
    backward_epoch_count: int
    internal_gap_count: int
    estimated_missing_internal_epochs: int | None
    expected_daily_epochs: int | None
    observed_epoch_fraction: float | None
    start_offset_seconds: float | None
    end_shortfall_seconds: float | None
    completeness: str
    warnings: list[str]


def discover_delivery(delivery_root: Path) -> list[DeliveryFile]:
    """Inventory understood RINEX files in an immutable provider delivery."""

    root = delivery_root.resolve()
    records: list[DeliveryFile] = []
    unknown: list[str] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(root)
        if len(relative.parts) < 3:
            unknown.append(relative.as_posix())
            continue
        folder_match = STATION_FOLDER.match(relative.parts[0])
        name_match = RINEX2_NAME.match(path.name)
        if folder_match is None or name_match is None:
            unknown.append(relative.as_posix())
            continue
        kind = name_match.group("kind").lower()
        if kind in OBSERVATION_KINDS:
            artifact_type = "observation"
        elif kind in NAVIGATION_KINDS:
            artifact_type = "navigation"
        else:
            unknown.append(relative.as_posix())
            continue
        year = 2000 + int(name_match.group("year"))
        records.append(
            DeliveryFile(
                source_path=path,
                source_relative_path=relative.as_posix(),
                station_id=folder_match.group("station"),
                place_name=folder_match.group("place"),
                year=year,
                day_of_year=int(name_match.group("doy")),
                session=name_match.group("session"),
                artifact_type=artifact_type,
                filename=path.name,
                size_bytes=path.stat().st_size,
                sha256=sha256_file(path),
            )
        )
    if unknown:
        preview = ", ".join(unknown[:5])
        raise Phase2DatasetError(
            f"delivery contains {len(unknown)} unclassified files; first: {preview}"
        )
    return records


def build_canonical_archive(
    delivery_root: Path,
    data_root: Path,
    *,
    copy_files: bool = True,
    delivery_files: list[DeliveryFile] | None = None,
) -> ArchiveResult:
    """Copy unique delivery files into canonical immutable paths and verify them."""

    delivery = delivery_files if delivery_files is not None else discover_delivery(delivery_root)
    by_target: dict[str, list[DeliveryFile]] = defaultdict(list)
    for item in delivery:
        by_target[item.canonical_relative_path].append(item)

    records: list[ArchiveRecord] = []
    duplicates: list[DuplicateRecord] = []
    for relative_target, candidates in sorted(by_target.items()):
        checksums = {candidate.sha256 for candidate in candidates}
        if len(checksums) != 1:
            sources = ", ".join(item.source_relative_path for item in candidates)
            raise Phase2DatasetError(
                f"canonical path collision with different content at {relative_target}: {sources}"
            )
        retained = sorted(
            candidates,
            key=lambda item: (
                re.search(r" \(\d+\)(?=\.)", item.filename) is not None,
                item.source_relative_path,
            ),
        )[0]
        target = data_root / relative_target
        if copy_files:
            _copy_verified_immutable(retained, target)
        elif target.exists() and sha256_file(target) != retained.sha256:
            raise Phase2DatasetError(f"canonical checksum mismatch: {relative_target}")
        records.append(
            ArchiveRecord(
                source_relative_path=retained.source_relative_path,
                canonical_relative_path=relative_target,
                station_id=retained.station_id,
                year=retained.year,
                day_of_year=retained.day_of_year,
                artifact_type=retained.artifact_type,
                size_bytes=retained.size_bytes,
                sha256=retained.sha256,
            )
        )
        for excluded in candidates:
            if excluded is retained:
                continue
            duplicates.append(
                DuplicateRecord(
                    excluded_source_relative_path=excluded.source_relative_path,
                    retained_source_relative_path=retained.source_relative_path,
                    canonical_relative_path=relative_target,
                    sha256=retained.sha256,
                )
            )
    return ArchiveResult(records=records, exact_duplicates=duplicates)


def _copy_verified_immutable(source: DeliveryFile, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        if not target.is_file() or sha256_file(target) != source.sha256:
            raise Phase2DatasetError(f"canonical target conflicts with source: {target}")
        target.chmod(0o444)
        return
    file_descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{target.name}.", suffix=".tmp", dir=target.parent
    )
    os.close(file_descriptor)
    temporary = Path(temporary_name)
    try:
        shutil.copyfile(source.source_path, temporary)
        if sha256_file(temporary) != source.sha256:
            raise Phase2DatasetError(f"copy verification failed for {source.source_path}")
        temporary.chmod(0o444)
        temporary.replace(target)
    finally:
        if temporary.exists():
            temporary.unlink()


def write_archive_manifest(result: ArchiveResult, output_path: Path) -> None:
    """Write the deterministic canonical archive mapping."""

    payload = {
        "schema_version": "1.0",
        "source_collection": "00-deliveries/osgof-2024/batch-001",
        "canonical_collection": "raw/nignet/2024",
        "policy": "byte-preserving verified copies; exact duplicates excluded",
        "records": [asdict(item) for item in result.records],
        "exact_duplicates": [asdict(item) for item in result.exact_duplicates],
    }
    _write_json(payload, output_path)


def parse_header(lines: Iterable[str]) -> HeaderMetadata:
    """Parse station/equipment facts explicitly stated in a RINEX header."""

    values: dict[str, Any] = {}
    warnings: list[str] = []
    for line in lines:
        label = line[60:].strip() if len(line) >= 60 else ""
        content = line[:60]
        if "RINEX VERSION / TYPE" in label:
            values["rinex_version"] = content[:20].strip() or None
        elif "MARKER NAME" in label:
            values["marker_name"] = content.strip() or None
        elif "MARKER NUMBER" in label:
            values["marker_number"] = content.strip() or None
        elif "OBSERVER / AGENCY" in label:
            values["observer"] = content[:20].strip() or None
            values["agency"] = content[20:40].strip() or None
        elif "REC # / TYPE / VERS" in label:
            values["receiver_serial"] = content[:20].strip() or None
            values["receiver_type"] = content[20:40].strip() or None
            values["receiver_firmware"] = content[40:60].strip() or None
        elif "ANT # / TYPE" in label:
            values["antenna_serial"] = content[:20].strip() or None
            values["antenna_type"] = content[20:60].strip() or None
        elif "APPROX POSITION XYZ" in label:
            values["approximate_position_xyz_m"] = _float_tuple(content, 3)
        elif "ANTENNA: DELTA H/E/N" in label:
            values["antenna_delta_hen_m"] = _float_tuple(content, 3)
        elif label == "INTERVAL":
            parsed = _float_tuple(content, 1)
            values["header_interval_seconds"] = parsed[0] if parsed else None
        elif "TIME OF FIRST OBS" in label:
            values["header_first_epoch"] = parse_epoch_fields(content[:43].split(), warnings)
        elif "TIME OF LAST OBS" in label:
            values["header_last_epoch"] = parse_epoch_fields(content[:43].split(), warnings)
        elif "END OF HEADER" in label:
            break
    return HeaderMetadata(
        rinex_version=values.get("rinex_version"),
        marker_name=values.get("marker_name"),
        marker_number=values.get("marker_number"),
        observer=values.get("observer"),
        agency=values.get("agency"),
        receiver_serial=values.get("receiver_serial"),
        receiver_type=values.get("receiver_type"),
        receiver_firmware=values.get("receiver_firmware"),
        antenna_serial=values.get("antenna_serial"),
        antenna_type=values.get("antenna_type"),
        approximate_position_xyz_m=values.get("approximate_position_xyz_m"),
        antenna_delta_hen_m=values.get("antenna_delta_hen_m"),
        header_interval_seconds=values.get("header_interval_seconds"),
        header_first_epoch=values.get("header_first_epoch"),
        header_last_epoch=values.get("header_last_epoch"),
    )


def parse_rinex2_epoch(line: str) -> tuple[datetime, int] | None:
    """Parse a fixed-column RINEX 2 epoch record, excluding observation rows."""

    if (
        len(line) < 32
        or any(line[index] != " " for index in (0, 3, 6, 9, 12, 26, 27, 29))
        or not line[1:3].isdigit()
        or not line[28:29].isdigit()
        or not line[30:32].strip().isdigit()
    ):
        return None
    try:
        year = int(line[1:3])
        year += 2000 if year < 80 else 1900
        month = int(line[4:6])
        day = int(line[7:9])
        hour = int(line[10:12])
        minute = int(line[13:15])
        seconds = float(line[15:26])
        whole_seconds = int(seconds)
        microseconds = round((seconds - whole_seconds) * 1_000_000)
        epoch = datetime(
            year,
            month,
            day,
            hour,
            minute,
            whole_seconds,
            microseconds,
            tzinfo=UTC,
        )
        return epoch, int(line[28])
    except ValueError:
        return None


def analyse_rinex_lines(
    lines: Iterable[str],
    record: ArchiveRecord,
    *,
    converter_exit_code: int | None = None,
    converter_message: str | None = None,
) -> tuple[SessionQC, list[EpochGap]]:
    """Extract header facts and daily epoch continuity from decompressed RINEX."""

    header_lines: list[str] = []
    epochs: list[datetime] = []
    in_body = False
    for line in lines:
        if not in_body:
            header_lines.append(line)
            label = line[60:].strip() if len(line) >= 60 else ""
            if "END OF HEADER" in label:
                in_body = True
            continue
        parsed = parse_rinex2_epoch(line)
        if parsed is not None and parsed[1] in {0, 1}:
            epochs.append(parsed[0])

    header = parse_header(header_lines)
    warnings: list[str] = []
    if not in_body:
        warnings.append("END OF HEADER not found")
    intervals = [
        (current - previous).total_seconds()
        for previous, current in zip(epochs, epochs[1:], strict=False)
        if current > previous
    ]
    interval = header.header_interval_seconds
    if interval is None and intervals:
        interval = Counter(intervals).most_common(1)[0][0]
        warnings.append("sampling interval inferred from epoch mode")
    if interval is not None and interval <= 0:
        warnings.append("non-positive header interval")
        interval = None

    gap_rows: list[EpochGap] = []
    duplicate_epochs = 0
    backward_epochs = 0
    missing_internal = 0
    if interval is not None:
        for previous, current in zip(epochs, epochs[1:], strict=False):
            elapsed = (current - previous).total_seconds()
            if elapsed == 0:
                duplicate_epochs += 1
            elif elapsed < 0:
                backward_epochs += 1
            elif elapsed > interval:
                estimated = max(round(elapsed / interval) - 1, 0)
                missing_internal += estimated
                gap_rows.append(
                    EpochGap(
                        station_id=record.station_id,
                        day_of_year=record.day_of_year,
                        previous_epoch=format_datetime(previous) or "",
                        current_epoch=format_datetime(current) or "",
                        elapsed_seconds=elapsed,
                        expected_interval_seconds=interval,
                        estimated_missing_epochs=estimated,
                    )
                )

    filename_day = datetime.strptime(f"{record.year} {record.day_of_year:03d}", "%Y %j").replace(
        tzinfo=UTC
    )
    first = epochs[0] if epochs else None
    last = epochs[-1] if epochs else None
    expected = round(86_400 / interval) if interval else None
    fraction = len(set(epochs)) / expected if expected else None
    start_offset = (first - filename_day).total_seconds() if first else None
    expected_last = filename_day + timedelta(seconds=86_400 - interval) if interval else None
    end_shortfall = (
        (expected_last - last).total_seconds()
        if expected_last is not None and last is not None
        else None
    )
    if first is not None and first.date() != filename_day.date():
        warnings.append("first epoch date disagrees with filename day-of-year")
    if header.marker_name is None:
        warnings.append("MARKER NAME not found")
    if header.approximate_position_xyz_m is None:
        warnings.append("APPROX POSITION XYZ not found")

    parser_status = "parsed"
    if converter_exit_code not in {None, 0, 2} or not in_body or not epochs:
        parser_status = "error"
    elif converter_exit_code == 2 or warnings:
        parser_status = "warning"

    if parser_status == "error" or interval is None or first is None or last is None:
        completeness = "not_computable"
    elif (
        start_offset == 0
        and end_shortfall == 0
        and not gap_rows
        and duplicate_epochs == 0
        and backward_epochs == 0
        and len(epochs) == expected
    ):
        completeness = "complete"
    else:
        completeness = "incomplete"

    session = SessionQC(
        canonical_relative_path=record.canonical_relative_path,
        sha256=record.sha256,
        station_id=record.station_id,
        year=record.year,
        day_of_year=record.day_of_year,
        filename_date=filename_day.date().isoformat(),
        parser_status=parser_status,
        converter_exit_code=converter_exit_code,
        converter_message=converter_message or None,
        header=header,
        first_epoch=first,
        last_epoch=last,
        sampling_interval_seconds=interval,
        epoch_count=len(epochs),
        duplicate_epoch_count=duplicate_epochs,
        backward_epoch_count=backward_epochs,
        internal_gap_count=len(gap_rows),
        estimated_missing_internal_epochs=missing_internal if interval else None,
        expected_daily_epochs=expected,
        observed_epoch_fraction=fraction,
        start_offset_seconds=start_offset,
        end_shortfall_seconds=end_shortfall,
        completeness=completeness,
        warnings=warnings,
    )
    return session, gap_rows


def analyse_crinex_file(
    path: Path,
    record: ArchiveRecord,
) -> tuple[SessionQC, list[EpochGap]]:
    """Stream Unix-compressed CRINEX through CRX2RNX without derived raw files."""

    uncompress = subprocess.Popen(
        ["uncompress", "-c", str(path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if uncompress.stdout is None:
        raise Phase2DatasetError("failed to open uncompress stdout")
    converter = subprocess.Popen(
        ["CRX2RNX"],
        stdin=uncompress.stdout,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="ascii",
        errors="replace",
    )
    uncompress.stdout.close()
    if converter.stdout is None:
        raise Phase2DatasetError("failed to open CRX2RNX stdout")
    session, gaps = analyse_rinex_lines(converter.stdout, record)
    converter.stdout.close()
    converter_stderr = converter.stderr.read() if converter.stderr is not None else ""
    converter_code = converter.wait()
    uncompress_stderr = uncompress.stderr.read() if uncompress.stderr is not None else b""
    uncompress_code = uncompress.wait()
    messages = converter_stderr.strip()
    if uncompress_stderr:
        messages = "\n".join(
            filter(None, [messages, uncompress_stderr.decode(errors="replace").strip()])
        )
    effective_code = converter_code if uncompress_code == 0 else uncompress_code
    session = replace(
        session,
        converter_exit_code=effective_code,
        converter_message=messages or None,
        parser_status="error" if effective_code not in {0, 2} else session.parser_status,
        completeness=("not_computable" if effective_code not in {0, 2} else session.completeness),
    )
    return session, gaps


def build_station_registry(
    sessions: list[SessionQC],
    place_names: dict[str, str],
) -> list[dict[str, Any]]:
    """Aggregate header-stated facts without inventing coordinate reference data."""

    by_station: dict[str, list[SessionQC]] = defaultdict(list)
    for session in sessions:
        by_station[session.station_id].append(session)
    registry: list[dict[str, Any]] = []
    for station_id, rows in sorted(by_station.items()):
        parsed = [row for row in rows if row.parser_status != "error"]
        first_epochs = [row.first_epoch for row in parsed if row.first_epoch is not None]
        last_epochs = [row.last_epoch for row in parsed if row.last_epoch is not None]
        registry.append(
            {
                "station_id": station_id,
                "station_name": place_names.get(station_id),
                "network": "NIGNET",
                "provider": "OSGoF",
                "country": "Nigeria",
                "operational_status": "unknown",
                "first_observation": format_datetime(min(first_epochs)) if first_epochs else None,
                "last_observation": format_datetime(max(last_epochs)) if last_epochs else None,
                "session_count": len(rows),
                "parsed_session_count": len(parsed),
                "complete_session_count": sum(row.completeness == "complete" for row in rows),
                "marker_names": _variants(row.header.marker_name for row in parsed),
                "marker_numbers": _variants(row.header.marker_number for row in parsed),
                "receivers": _variants(
                    _joined(
                        row.header.receiver_serial,
                        row.header.receiver_type,
                        row.header.receiver_firmware,
                    )
                    for row in parsed
                ),
                "antennas": _variants(
                    _joined(row.header.antenna_serial, row.header.antenna_type) for row in parsed
                ),
                "approximate_position_xyz_m": _tuple_variants(
                    row.header.approximate_position_xyz_m for row in parsed
                ),
                "coordinate_reference_frame": None,
                "coordinate_epoch": None,
                "coordinate_use": (
                    "RINEX APPROX POSITION XYZ; suitable only for approximate geometry/QC "
                    "until frame, epoch, and authoritative coordinates are supplied"
                ),
                "sampling_intervals_seconds": _number_variants(
                    row.sampling_interval_seconds for row in parsed
                ),
                "source": "RINEX headers in raw/nignet/2024",
            }
        )
    return registry


def calculate_baselines(registry: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Calculate pairwise ECEF chord distances from modal approximate header positions."""

    positions: dict[str, tuple[float, float, float]] = {}
    variants: dict[str, int] = {}
    for station in registry:
        coordinate_rows = station["approximate_position_xyz_m"]
        if coordinate_rows:
            positions[station["station_id"]] = tuple(coordinate_rows[0]["value"])
            variants[station["station_id"]] = len(coordinate_rows)
    baselines: list[dict[str, Any]] = []
    station_ids = sorted(positions)
    for index, station_a in enumerate(station_ids):
        for station_b in station_ids[index + 1 :]:
            difference = [
                second - first
                for first, second in zip(positions[station_a], positions[station_b], strict=True)
            ]
            baselines.append(
                {
                    "station_a": station_a,
                    "station_b": station_b,
                    "ecef_chord_distance_km": math.sqrt(sum(value * value for value in difference))
                    / 1000,
                    "coordinate_source": "modal RINEX APPROX POSITION XYZ",
                    "reference_frame": None,
                    "station_a_position_variant_count": variants[station_a],
                    "station_b_position_variant_count": variants[station_b],
                    "scientific_status": "approximate_metadata_qc_only",
                }
            )
    return baselines


def calculate_pairwise_overlap(sessions: list[SessionQC]) -> list[dict[str, Any]]:
    """Calculate exact temporal intersections of parsed daily station sessions."""

    by_station_date: dict[str, dict[str, SessionQC]] = defaultdict(dict)
    for session in sessions:
        if session.first_epoch is not None and session.last_epoch is not None:
            by_station_date[session.station_id][session.filename_date] = session
    overlaps: list[dict[str, Any]] = []
    station_ids = sorted(by_station_date)
    for index, station_a in enumerate(station_ids):
        for station_b in station_ids[index + 1 :]:
            common_dates = sorted(set(by_station_date[station_a]) & set(by_station_date[station_b]))
            daily_seconds: list[float] = []
            for day in common_dates:
                left = by_station_date[station_a][day]
                right = by_station_date[station_b][day]
                assert left.first_epoch is not None and right.first_epoch is not None
                assert left.last_epoch is not None and right.last_epoch is not None
                start = max(left.first_epoch, right.first_epoch)
                end = min(left.last_epoch, right.last_epoch)
                if start is not None and end is not None and end >= start:
                    intervals = [
                        value
                        for value in (
                            left.sampling_interval_seconds,
                            right.sampling_interval_seconds,
                        )
                        if value is not None
                    ]
                    interval = min(intervals) if intervals else 0
                    daily_seconds.append((end - start).total_seconds() + interval)
                else:
                    daily_seconds.append(0)
            overlaps.append(
                {
                    "station_a": station_a,
                    "station_b": station_b,
                    "common_session_days": len(common_dates),
                    "days_with_positive_overlap": sum(value > 0 for value in daily_seconds),
                    "total_overlap_hours": sum(daily_seconds) / 3600,
                    "minimum_daily_overlap_hours": min(daily_seconds) / 3600
                    if daily_seconds
                    else None,
                    "maximum_daily_overlap_hours": max(daily_seconds) / 3600
                    if daily_seconds
                    else None,
                }
            )
    return overlaps


def missing_days_by_station(sessions: list[SessionQC], year: int) -> list[dict[str, Any]]:
    """Report absent daily sessions both within observed spans and across the named year."""

    days_in_year = 366 if date(year, 12, 31).timetuple().tm_yday == 366 else 365
    present: dict[str, set[int]] = defaultdict(set)
    for session in sessions:
        present[session.station_id].add(session.day_of_year)
    rows: list[dict[str, Any]] = []
    for station_id, station_days in sorted(present.items()):
        first = min(station_days)
        last = max(station_days)
        rows.append(
            {
                "station_id": station_id,
                "first_present_day_of_year": first,
                "last_present_day_of_year": last,
                "present_session_days": len(station_days),
                "missing_days_within_observed_span": [
                    day for day in range(first, last + 1) if day not in station_days
                ],
                "days_without_session_in_calendar_year": [
                    day for day in range(1, days_in_year + 1) if day not in station_days
                ],
                "calendar_year_scope_note": (
                    "absence is reported, not classified as provider outage; no expected delivery "
                    "schedule was supplied"
                ),
            }
        )
    return rows


def write_phase2_outputs(
    data_root: Path,
    archive: ArchiveResult,
    sessions: list[SessionQC],
    gaps: list[EpochGap],
    place_names: dict[str, str],
) -> dict[str, Path]:
    """Write deterministic registries, QC tables, geometry, overlap, and report."""

    manifests = data_root / "manifests"
    metadata = data_root / "metadata" / "stations"
    reports = data_root / "validation" / "reports"
    qc_dir = data_root / "processed" / "qc" / "2024"
    for directory in (manifests, metadata, reports, qc_dir):
        directory.mkdir(parents=True, exist_ok=True)

    archive_path = manifests / "canonical-raw-archive-2024.json"
    write_archive_manifest(archive, archive_path)
    registry = build_station_registry(sessions, place_names)
    baselines = calculate_baselines(registry)
    overlap = calculate_pairwise_overlap(sessions)
    missing = missing_days_by_station(sessions, 2024)

    registry_path = metadata / "osgof-2024-rinex-header-registry.json"
    _write_json({"schema_version": "1.0", "stations": registry}, registry_path)
    registry_csv_path = metadata / "osgof-2024-rinex-header-registry.csv"
    _write_registry_csv(registry, registry_csv_path)
    sessions_path = qc_dir / "sessions.csv"
    _write_sessions_csv(sessions, sessions_path)
    gaps_path = qc_dir / "epoch-gaps.csv"
    _write_dataclass_csv(gaps, gaps_path, list(EpochGap.__dataclass_fields__))
    missing_path = qc_dir / "missing-days.json"
    _write_json({"year": 2024, "stations": missing}, missing_path)
    baselines_path = qc_dir / "baseline-geometry.json"
    _write_json(
        {"coordinate_status": "frame_unknown_header_approximation", "baselines": baselines},
        baselines_path,
    )
    overlap_path = qc_dir / "pairwise-overlap.json"
    _write_json(
        {
            "overlap_definition": "intersection of first-to-last epoch windows by date",
            "pairs": overlap,
        },
        overlap_path,
    )
    summary_path = reports / "phase2-acquisition-qc-2024.json"
    summary = _summary(archive, sessions, gaps, registry, baselines, overlap, missing)
    _write_json(summary, summary_path)
    report_path = reports / "phase2-acquisition-qc-2024.md"
    report_path.write_text(_markdown_report(summary, registry), encoding="utf-8")
    package_paths = _write_station_import_packages(data_root, archive_path, registry, sessions)
    return {
        "archive_manifest": archive_path,
        "station_registry_json": registry_path,
        "station_registry_csv": registry_csv_path,
        "sessions": sessions_path,
        "epoch_gaps": gaps_path,
        "missing_days": missing_path,
        "baseline_geometry": baselines_path,
        "pairwise_overlap": overlap_path,
        "summary_json": summary_path,
        "report": report_path,
        **{f"station_package_{index}": path for index, path in enumerate(package_paths)},
    }


def _summary(
    archive: ArchiveResult,
    sessions: list[SessionQC],
    gaps: list[EpochGap],
    registry: list[dict[str, Any]],
    baselines: list[dict[str, Any]],
    overlap: list[dict[str, Any]],
    missing: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "phase": "Phase 2 - Data Acquisition & Station Registry",
        "dataset": "preserved OSGoF/NIGNET 2024 delivery batch-001",
        "scope_stop": "Phase 3 not started",
        "raw_archive": {
            "canonical_files": len(archive.records),
            "exact_duplicates_excluded": len(archive.exact_duplicates),
            "total_bytes": sum(item.size_bytes for item in archive.records),
        },
        "stations": len(registry),
        "sessions": {
            "total": len(sessions),
            "parsed": sum(item.parser_status != "error" for item in sessions),
            "complete": sum(item.completeness == "complete" for item in sessions),
            "incomplete": sum(item.completeness == "incomplete" for item in sessions),
            "not_computable": sum(item.completeness == "not_computable" for item in sessions),
        },
        "epoch_gaps": {
            "events": len(gaps),
            "estimated_missing_epochs": sum(item.estimated_missing_epochs for item in gaps),
        },
        "missing_days": missing,
        "baseline_geometry": {
            "pair_count": len(baselines),
            "minimum_chord_km": min(
                (row["ecef_chord_distance_km"] for row in baselines), default=None
            ),
            "maximum_chord_km": max(
                (row["ecef_chord_distance_km"] for row in baselines), default=None
            ),
            "status": "approximate_metadata_qc_only; reference frame and epoch unknown",
        },
        "pairwise_overlap": {
            "pair_count": len(overlap),
            "maximum_common_session_days": max(
                (row["common_session_days"] for row in overlap), default=0
            ),
            "minimum_common_session_days": min(
                (row["common_session_days"] for row in overlap), default=0
            ),
        },
        "scientific_limitations": [
            (
                "RINEX APPROX POSITION XYZ values do not declare a coordinate "
                "reference frame or epoch."
            ),
            "Baseline distances are ECEF chord approximations for acquisition planning/QC only.",
            (
                "Calendar-day absence is not labelled as an outage because no expected "
                "provider schedule was supplied."
            ),
            (
                "No RTK, PPP, correction generation, accuracy validation, or Phase 3 "
                "processing was performed."
            ),
        ],
    }


def _markdown_report(summary: dict[str, Any], registry: list[dict[str, Any]]) -> str:
    raw = summary["raw_archive"]
    sessions = summary["sessions"]
    gaps = summary["epoch_gaps"]
    geometry = summary["baseline_geometry"]
    overlap = summary["pairwise_overlap"]
    station_rows = "\n".join(
        f"| {station['station_id']} | {station['station_name']} | {station['session_count']} | "
        f"{station['complete_session_count']} | {station['first_observation']} | "
        f"{station['last_observation']} |"
        for station in registry
    )
    limitations = "\n".join(f"- {item}" for item in summary["scientific_limitations"])
    overlap_range = (
        f"{overlap['minimum_common_session_days']}–{overlap['maximum_common_session_days']}"
    )
    return f"""# Phase 2 Acquisition and QC Report — Preserved 2024 Dataset

## Scope and result

This report covers the preserved OSGoF/NIGNET 2024 delivery batch-001. Phase 2
acquisition, canonical archiving, RINEX-header metadata extraction, registry
generation, file/session QC, approximate baseline geometry, and temporal overlap
analysis were performed. Phase 3 was not started.

## Canonical raw archive

- Delivered files: {raw["canonical_files"] + raw["exact_duplicates_excluded"]}
- Canonical byte-preserved files: {raw["canonical_files"]}
- Exact duplicates excluded: {raw["exact_duplicates_excluded"]}
- Canonical bytes: {raw["total_bytes"]}
- Layout: `raw/nignet/2024/<station>/<DOY>/<artifact-type>/<original-filename>`
- Integrity: every canonical file was compared with the source SHA-256 and made read-only.

## Station registry

| Canonical station | Place | Sessions | Complete | First epoch | Last epoch |
|---|---|---:|---:|---|---|
{station_rows}

Header marker names, marker numbers, receiver/firmware, antenna/radome, antenna
delta, intervals, and approximate ECEF positions are retained in the
machine-readable registry. Current operational status remains unknown.

## Session and gap QC

- Sessions analysed: {sessions["total"]}
- Parsed sessions: {sessions["parsed"]}
- Complete daily sessions: {sessions["complete"]}
- Incomplete daily sessions: {sessions["incomplete"]}
- Not computable: {sessions["not_computable"]}
- Internal epoch-gap events: {gaps["events"]}
- Estimated missing epochs within sessions: {gaps["estimated_missing_epochs"]}

Completeness is exact: midnight start, the expected final epoch, the expected
epoch count, and no internal, duplicate, or backward epochs. No empirical
acceptance threshold was introduced. Missing-day lists are reported both within
each observed station span and across calendar year 2024; absence is not
classified as an outage because the delivery has no declared expected schedule.

## Geometry and overlap

- Pairwise baselines: {geometry["pair_count"]}
- Approximate minimum ECEF chord: {_format_number(geometry["minimum_chord_km"])} km
- Approximate maximum ECEF chord: {_format_number(geometry["maximum_chord_km"])} km
- Pairwise temporal-overlap rows: {overlap["pair_count"]}
- Common-session-day range: {overlap_range}

## Scientific limitations

{limitations}

## Phase boundary

This report completes the requested Phase 2 acquisition/QC work only. It makes
no positioning or correction-accuracy claim and does not initiate Phase 3
single-base RTK processing.
"""


def _write_station_import_packages(
    data_root: Path,
    archive_manifest: Path,
    registry: list[dict[str, Any]],
    sessions: list[SessionQC],
) -> list[Path]:
    manifest_relative = archive_manifest.relative_to(data_root).as_posix()
    manifest_sha = sha256_file(archive_manifest)
    by_station = defaultdict(list)
    for session in sessions:
        if session.parser_status != "error":
            by_station[session.station_id].append(session)
    outputs: list[Path] = []
    for station in registry:
        station_id = station["station_id"]
        representative = sorted(
            by_station[station_id], key=lambda row: row.canonical_relative_path
        )[0]
        payload = {
            "schema_version": "1.0",
            "sources": [
                {
                    "key": "delivery-manifest",
                    "source_type": "canonical_archive_manifest",
                    "path": manifest_relative,
                    "source_reference": (
                        "Preserved OSGoF/NIGNET 2024 batch-001 canonical archive manifest"
                    ),
                    "source_date": None,
                    "expected_sha256": manifest_sha,
                    "notes": "Provider and collection provenance.",
                },
                {
                    "key": "rinex-header",
                    "source_type": "rinex_observation_header",
                    "path": representative.canonical_relative_path,
                    "source_reference": f"Representative preserved RINEX header for {station_id}",
                    "source_date": representative.filename_date,
                    "expected_sha256": representative.sha256,
                    "notes": (
                        "Station identity and observed data span; current operational "
                        "state is not inferred."
                    ),
                },
            ],
            "provider": {
                "provider_code": "OSGOF",
                "provider_name": "OSGoF",
                "operator_name": None,
                "country": "Nigeria",
                "source_key": "delivery-manifest",
                "notes": (
                    "Name retained exactly as stated in delivered RINEX headers/"
                    "delivery provenance."
                ),
            },
            "station": {
                "station_code": station_id,
                "station_name": station["station_name"],
                "network": "NIGNET",
                "operator_name": None,
                "country": "Nigeria",
                "status": "unknown",
                "first_observation": station["first_observation"],
                "last_observation": station["last_observation"],
                "source_key": "rinex-header",
                "notes": "Historical RINEX exists; current operational status is unknown.",
            },
            "coordinates": [],
            "equipment": [],
        }
        output = data_root / "metadata" / "stations" / f"osgof-2024-{station_id}.json"
        _write_json(payload, output)
        outputs.append(output)
    return outputs


def _write_sessions_csv(sessions: list[SessionQC], output_path: Path) -> None:
    fields = [
        "canonical_relative_path",
        "sha256",
        "station_id",
        "year",
        "day_of_year",
        "filename_date",
        "parser_status",
        "converter_exit_code",
        "converter_message",
        "marker_name",
        "marker_number",
        "first_epoch",
        "last_epoch",
        "sampling_interval_seconds",
        "epoch_count",
        "duplicate_epoch_count",
        "backward_epoch_count",
        "internal_gap_count",
        "estimated_missing_internal_epochs",
        "expected_daily_epochs",
        "observed_epoch_fraction",
        "start_offset_seconds",
        "end_shortfall_seconds",
        "completeness",
        "warnings",
    ]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=fields)
        writer.writeheader()
        for item in sessions:
            row = asdict(item)
            row["marker_name"] = item.header.marker_name
            row["marker_number"] = item.header.marker_number
            row["first_epoch"] = format_datetime(item.first_epoch)
            row["last_epoch"] = format_datetime(item.last_epoch)
            row["warnings"] = "; ".join(item.warnings)
            row.pop("header")
            writer.writerow(row)


def _write_registry_csv(registry: list[dict[str, Any]], output_path: Path) -> None:
    fields = [
        "station_id",
        "station_name",
        "network",
        "provider",
        "country",
        "operational_status",
        "first_observation",
        "last_observation",
        "session_count",
        "parsed_session_count",
        "complete_session_count",
        "marker_names",
        "marker_numbers",
        "receivers",
        "antennas",
        "approximate_position_xyz_m",
        "coordinate_reference_frame",
        "coordinate_epoch",
        "sampling_intervals_seconds",
        "source",
    ]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for station in registry:
            row = dict(station)
            for field in (
                "marker_names",
                "marker_numbers",
                "receivers",
                "antennas",
                "approximate_position_xyz_m",
                "sampling_intervals_seconds",
            ):
                row[field] = json.dumps(row[field], sort_keys=True, separators=(",", ":"))
            writer.writerow(row)


def _write_dataclass_csv(items: list[Any], output_path: Path, fields: list[str]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=fields)
        writer.writeheader()
        for item in items:
            writer.writerow(asdict(item))


def _write_json(payload: Any, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=_json_default) + "\n",
        encoding="utf-8",
    )


def _json_default(value: object) -> str:
    if isinstance(value, datetime):
        return format_datetime(value) or ""
    raise TypeError(f"not JSON serializable: {type(value).__name__}")


def _float_tuple(content: str, length: int) -> tuple[float, ...] | None:
    try:
        values = tuple(float(value) for value in content.split()[:length])
    except ValueError:
        return None
    return values if len(values) == length else None


def _joined(*values: str | None) -> str | None:
    retained = [value for value in values if value]
    return " | ".join(retained) if retained else None


def _variants(values: Iterable[str | None]) -> list[dict[str, Any]]:
    counts = Counter(value for value in values if value is not None)
    return [
        {"value": value, "session_count": count}
        for value, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    ]


def _tuple_variants(
    values: Iterable[tuple[float, float, float] | None],
) -> list[dict[str, Any]]:
    counts = Counter(value for value in values if value is not None)
    return [
        {"value": list(value), "session_count": count}
        for value, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    ]


def _number_variants(values: Iterable[float | None]) -> list[dict[str, Any]]:
    counts = Counter(value for value in values if value is not None)
    return [
        {"value": value, "session_count": count}
        for value, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    ]


def _format_number(value: float | None) -> str:
    return f"{value:.3f}" if value is not None else "not computable"
