"""Report-only RINEX discovery and inventory tooling."""

from __future__ import annotations

import gzip
import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from statistics import median


@dataclass(frozen=True, slots=True)
class RinexInventoryRecord:
    """Structured inventory metadata for one discovered candidate file."""

    relative_vault_path: str
    filename: str
    station_marker: str | None
    rinex_version: str | None
    file_type: str
    compression: str | None
    file_size_bytes: int
    observation_date: str | None
    first_epoch: str | None
    last_epoch: str | None
    approximate_sampling_interval_seconds: float | None
    sha256: str
    parser_status: str
    warnings: list[str]
    errors: list[str]


RINEX_TEXT_SUFFIXES = {".rnx", ".obs", ".nav"}
COMPRESSED_SUFFIXES = {".gz", ".z", ".zip"}
RINEX2_TYPE_SUFFIXES = {
    "o": "observation",
    "d": "observation",
    "n": "navigation",
    "g": "navigation",
    "p": "navigation",
    "l": "navigation",
    "h": "navigation",
    "q": "navigation",
    "c": "navigation",
}


def discover_rinex_inventory(data_root: Path) -> list[RinexInventoryRecord]:
    """Recursively discover RINEX candidate files under ``data_root``."""

    root = data_root.expanduser().resolve()
    records = [
        inventory_file(path, root)
        for path in sorted(root.rglob("*"))
        if path.is_file() and is_rinex_candidate(path)
    ]
    return sorted(records, key=lambda record: record.relative_vault_path)


def write_inventory(
    records: list[RinexInventoryRecord],
    output_path: Path,
) -> None:
    """Write deterministic machine-readable JSON inventory output."""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = [asdict(record) for record in records]
    output_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def default_inventory_output_path(data_root: Path) -> Path:
    """Return the default Phase 2 manifest path."""

    return data_root / "manifests" / "rinex-inventory.json"


def inventory_file(path: Path, data_root: Path) -> RinexInventoryRecord:
    """Build one inventory record without modifying the source file."""

    warnings: list[str] = []
    errors: list[str] = []
    relative_path = PurePosixPath(path.resolve().relative_to(data_root).as_posix())
    compression = compression_type(path)
    file_type = infer_file_type_from_name(path)
    station_marker = infer_station_from_name(path)
    rinex_version: str | None = None
    first_epoch: datetime | None = None
    last_epoch: datetime | None = None
    parser_status = "parsed"

    try:
        lines = read_text_lines(path, compression)
    except UnsupportedCompressionError as exc:
        parser_status = "not_parsed"
        warnings.append(str(exc))
        lines = []
    except UnicodeDecodeError as exc:
        parser_status = "error"
        errors.append(f"file is not readable as RINEX text: {exc}")
        lines = []
    except OSError as exc:
        parser_status = "error"
        errors.append(f"failed to read file: {exc}")
        lines = []

    if lines:
        header = parse_header(lines, warnings)
        rinex_version = header.rinex_version
        if header.file_type is not None:
            file_type = header.file_type
        if header.station_marker is not None:
            station_marker = header.station_marker
        first_epoch = header.first_epoch
        last_epoch = header.last_epoch
        body_epochs = parse_body_epochs(lines, file_type, warnings)
        if body_epochs:
            first_epoch = first_epoch or body_epochs[0]
            last_epoch = last_epoch or body_epochs[-1]
        if rinex_version is None:
            parser_status = "warning"
            warnings.append("RINEX VERSION / TYPE header not found")
    else:
        if parser_status == "parsed":
            parser_status = "warning"
            warnings.append("empty RINEX candidate")
        body_epochs = []

    sampling_interval = approximate_sampling_interval(body_epochs)
    observation_date = (first_epoch or date_from_filename(path))

    return RinexInventoryRecord(
        relative_vault_path=str(relative_path),
        filename=path.name,
        station_marker=station_marker,
        rinex_version=rinex_version,
        file_type=file_type,
        compression=compression,
        file_size_bytes=path.stat().st_size,
        observation_date=observation_date.date().isoformat()
        if observation_date is not None
        else None,
        first_epoch=format_datetime(first_epoch),
        last_epoch=format_datetime(last_epoch),
        approximate_sampling_interval_seconds=sampling_interval,
        sha256=sha256_file(path),
        parser_status=parser_status,
        warnings=warnings,
        errors=errors,
    )


@dataclass(frozen=True, slots=True)
class HeaderMetadata:
    rinex_version: str | None
    file_type: str | None
    station_marker: str | None
    first_epoch: datetime | None
    last_epoch: datetime | None


class UnsupportedCompressionError(RuntimeError):
    """Raised when a candidate uses a known but locally unsupported compression."""


def is_rinex_candidate(path: Path) -> bool:
    """Return whether a path looks like a RINEX observation/navigation file."""

    name = path.name.lower()
    suffixes = [suffix.lower() for suffix in path.suffixes]
    if not suffixes:
        return False
    if suffixes[-1] in COMPRESSED_SUFFIXES:
        suffixes = suffixes[:-1]
    if suffixes and suffixes[-1] in RINEX_TEXT_SUFFIXES:
        return True
    if len(name) >= 12:
        last = suffixes[-1].lstrip(".") if suffixes else ""
        return len(last) == 3 and last[:2].isdigit() and last[2] in RINEX2_TYPE_SUFFIXES
    return False


def compression_type(path: Path) -> str | None:
    suffix = path.suffix.lower()
    if suffix == ".gz":
        return "gzip"
    if suffix == ".z":
        return "unix-compress"
    if suffix == ".zip":
        return "zip"
    return None


def read_text_lines(path: Path, compression: str | None) -> list[str]:
    if compression == "gzip":
        with gzip.open(path, "rt", encoding="ascii") as source:
            return source.readlines()
    if compression is not None:
        raise UnsupportedCompressionError(
            f"compression {compression} is discovered but not parsed"
        )
    return path.read_text(encoding="ascii").splitlines(keepends=True)


def parse_header(lines: list[str], warnings: list[str]) -> HeaderMetadata:
    version: str | None = None
    file_type: str | None = None
    station_marker: str | None = None
    first_epoch: datetime | None = None
    last_epoch: datetime | None = None

    for line in lines:
        label = line[60:].strip() if len(line) >= 60 else ""
        if "RINEX VERSION / TYPE" in label:
            version = line[:20].strip() or None
            type_code = line[20:21].strip().upper()
            file_type = {"O": "observation", "N": "navigation"}.get(
                type_code,
                "unknown",
            )
        elif "MARKER NAME" in label:
            station_marker = line[:60].strip() or None
        elif "TIME OF FIRST OBS" in label:
            first_epoch = parse_epoch_fields(line[:43].split(), warnings)
        elif "TIME OF LAST OBS" in label:
            last_epoch = parse_epoch_fields(line[:43].split(), warnings)
        elif "END OF HEADER" in label:
            break

    return HeaderMetadata(
        rinex_version=version,
        file_type=file_type,
        station_marker=station_marker,
        first_epoch=first_epoch,
        last_epoch=last_epoch,
    )


def parse_body_epochs(
    lines: list[str],
    file_type: str,
    warnings: list[str],
) -> list[datetime]:
    """Parse observation epochs where plainly available."""

    if file_type != "observation":
        return []

    in_body = False
    epochs: list[datetime] = []
    for line in lines:
        label = line[60:].strip() if len(line) >= 60 else ""
        if not in_body:
            if "END OF HEADER" in label:
                in_body = True
            continue
        parsed = parse_observation_epoch_line(line, warnings)
        if parsed is not None:
            epochs.append(parsed)
    return sorted(epochs)


def parse_observation_epoch_line(
    line: str,
    warnings: list[str],
) -> datetime | None:
    if line.startswith(">"):
        return parse_epoch_fields(line[1:].split()[:6], warnings)
    if len(line) >= 32 and line[0] == " ":
        parts = line[:32].split()
        if len(parts) >= 6:
            year = int(parts[0])
            year += 2000 if year < 80 else 1900
            return parse_epoch_fields([str(year), *parts[1:6]], warnings)
    return None


def parse_epoch_fields(fields: list[str], warnings: list[str]) -> datetime | None:
    if len(fields) < 6:
        return None
    try:
        year = int(float(fields[0]))
        month = int(float(fields[1]))
        day = int(float(fields[2]))
        hour = int(float(fields[3]))
        minute = int(float(fields[4]))
        second_value = float(fields[5])
        second = int(second_value)
        microsecond = int(round((second_value - second) * 1_000_000))
        return datetime(
            year,
            month,
            day,
            hour,
            minute,
            second,
            microsecond,
            tzinfo=UTC,
        )
    except ValueError:
        warnings.append("could not parse one epoch timestamp")
        return None


def approximate_sampling_interval(epochs: list[datetime]) -> float | None:
    if len(epochs) < 2:
        return None
    intervals = [
        (current - previous).total_seconds()
        for previous, current in zip(epochs, epochs[1:], strict=False)
        if current > previous
    ]
    if not intervals:
        return None
    return float(median(intervals))


def infer_file_type_from_name(path: Path) -> str:
    name = path.name.lower()
    suffixes = [suffix.lower() for suffix in path.suffixes]
    if suffixes and suffixes[-1] in COMPRESSED_SUFFIXES:
        suffixes = suffixes[:-1]
    if suffixes:
        suffix = suffixes[-1]
        if suffix == ".obs":
            return "observation"
        if suffix == ".nav":
            return "navigation"
        if suffix == ".rnx":
            if "_mo." in name:
                return "observation"
            if "_mn." in name:
                return "navigation"
            return "unknown"
        rinex2 = suffix.lstrip(".")
        if len(rinex2) == 3 and rinex2[:2].isdigit():
            return RINEX2_TYPE_SUFFIXES.get(rinex2[2], "unknown")
    return "unknown"


def infer_station_from_name(path: Path) -> str | None:
    name = path.name
    if "_" in name:
        marker = name.split("_", maxsplit=1)[0]
        return marker or None
    stem = path.stem
    if path.suffix.lower() in COMPRESSED_SUFFIXES:
        stem = Path(stem).stem
    if len(stem) >= 4:
        return stem[:4].upper()
    return None


def date_from_filename(path: Path) -> datetime | None:
    stem = path.stem
    if path.suffix.lower() in COMPRESSED_SUFFIXES:
        stem = Path(stem).stem
    parts = stem.split("_")
    for part in parts:
        if len(part) >= 7 and part[:7].isdigit():
            year = int(part[:4])
            day_of_year = int(part[4:7])
            return datetime.strptime(f"{year} {day_of_year}", "%Y %j").replace(
                tzinfo=UTC
            )
    if len(stem) >= 7 and stem[4:7].isdigit():
        year_suffix = path.suffix.lower().lstrip(".")[:2]
        if len(year_suffix) >= 2 and year_suffix[:2].isdigit():
            year = 2000 + int(year_suffix)
            day_of_year = int(stem[4:7])
            return datetime.strptime(f"{year} {day_of_year}", "%Y %j").replace(
                tzinfo=UTC
            )
    return None


def format_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source_file:
        for chunk in iter(lambda: source_file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
