"""Streaming RINEX 2 observation analysis for the historical 2024 corpus."""

from __future__ import annotations

import math
import statistics
from collections import Counter, defaultdict
from collections.abc import Iterable, Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

from nlgcp_api.phase2_dataset import parse_rinex2_epoch
from nlgcp_api.rinex_inventory import format_datetime, parse_epoch_fields

from nlgcp_gnss_qc.models import GapRecord, RinexAnalysis, RinexHeader

CONSTELLATIONS = {
    "G": "GPS",
    "R": "GLONASS",
    "E": "Galileo",
    "C": "BeiDou",
    "S": "SBAS",
    "J": "QZSS",
    "I": "NavIC",
}


class RinexParseError(ValueError):
    """Raised when a session is not structurally analysable as RINEX 2."""


def analyse_rinex2(lines: Iterable[str], *, year: int, day_of_year: int) -> RinexAnalysis:
    """Measure a RINEX 2 observation session without loading observations in memory."""

    iterator = iter(lines)
    header_lines: list[str] = []
    for line in iterator:
        header_lines.append(line)
        if _label(line) == "END OF HEADER":
            break
    else:
        raise RinexParseError("END OF HEADER not found")

    header, warnings = parse_header(header_lines)
    if header.rinex_version is None or not header.rinex_version.startswith("2"):
        raise RinexParseError(
            f"Phase 4 historical parser requires RINEX 2.x; got {header.rinex_version!r}"
        )
    if not header.observation_types:
        raise RinexParseError("# / TYPES OF OBSERV not found or empty")

    epochs: list[datetime] = []
    satellite_counts: list[int] = []
    constellation_counts: dict[str, list[int]] = defaultdict(list)
    cycle_slip_indicators = 0
    observation_lines = math.ceil(len(header.observation_types) / 5)

    for line in iterator:
        parsed = parse_rinex2_epoch(line)
        if parsed is None:
            if line.strip():
                warnings.append("unrecognised non-empty body line outside an epoch")
            continue
        epoch, flag = parsed
        record_count = _record_count(line)
        if flag not in {0, 1}:
            _consume(iterator, record_count, "special-event records")
            continue

        satellite_ids = _satellites_from_epoch(line)
        continuation_count = max(math.ceil(record_count / 12) - 1, 0)
        for _ in range(continuation_count):
            continuation = _next(iterator, "satellite-list continuation")
            satellite_ids.extend(_satellites_from_epoch(continuation))
        satellite_ids = satellite_ids[:record_count]
        if len(satellite_ids) != record_count:
            raise RinexParseError(
                f"epoch {format_datetime(epoch)} declares {record_count} satellites "
                f"but lists {len(satellite_ids)}"
            )

        counts = Counter(_constellation(satellite_id) for satellite_id in satellite_ids)
        for constellation in set(CONSTELLATIONS.values()) | set(counts):
            constellation_counts[constellation].append(counts.get(constellation, 0))
        epochs.append(epoch)
        satellite_counts.append(record_count)

        for _satellite_id in satellite_ids:
            observation_rows = [
                _next(iterator, "satellite observation records") for _ in range(observation_lines)
            ]
            cycle_slip_indicators += _count_phase_lli(observation_rows, header.observation_types)

    if not epochs:
        raise RinexParseError("no normal observation epochs found")
    return _analysis(
        header,
        epochs,
        satellite_counts,
        constellation_counts,
        cycle_slip_indicators,
        warnings,
        year,
        day_of_year,
    )


def parse_header(lines: Iterable[str]) -> tuple[RinexHeader, list[str]]:
    """Parse required RINEX 2 header metadata and retain explicit unknowns."""

    values: dict[str, Any] = {}
    warnings: list[str] = []
    observation_types: list[str] = []
    observation_type_count: int | None = None
    for line in lines:
        label = _label(line)
        content = line[:60].ljust(60)
        if label == "RINEX VERSION / TYPE":
            values["rinex_version"] = content[:9].strip() or None
            values["rinex_type"] = content[20:21].strip() or None
            values["satellite_system"] = content[40:41].strip() or None
        elif label == "MARKER NAME":
            values["marker_name"] = content.strip() or None
        elif label == "MARKER NUMBER":
            values["marker_number"] = content[:20].strip() or None
        elif label == "OBSERVER / AGENCY":
            values["observer"] = content[:20].strip() or None
            values["agency"] = content[20:40].strip() or None
        elif label == "REC # / TYPE / VERS":
            values["receiver_number"] = content[:20].strip() or None
            values["receiver_type"] = content[20:40].strip() or None
            values["receiver_version"] = content[40:60].strip() or None
        elif label == "ANT # / TYPE":
            values["antenna_number"] = content[:20].strip() or None
            values["antenna_type"] = content[20:60].strip() or None
        elif label == "APPROX POSITION XYZ":
            values["approximate_xyz_m"] = _float_tuple(content, 3)
        elif label == "ANTENNA: DELTA H/E/N":
            values["antenna_delta_hen_m"] = _float_tuple(content, 3)
        elif label == "# / TYPES OF OBSERV":
            if observation_type_count is None:
                try:
                    observation_type_count = int(content[:6])
                except ValueError as exc:
                    raise RinexParseError("invalid observation-type count") from exc
            observation_types.extend(
                value
                for value in (content[index : index + 6].strip() for index in range(6, 60, 6))
                if value
            )
        elif label == "INTERVAL":
            values["declared_interval_seconds"] = _float_or_none(content[:10])
        elif label == "TIME OF FIRST OBS":
            parsed = parse_epoch_fields(content[:43].split(), warnings)
            values["time_of_first_observation"] = format_datetime(parsed)
            values["time_system"] = content[48:51].strip() or None
        elif label == "TIME OF LAST OBS":
            parsed = parse_epoch_fields(content[:43].split(), warnings)
            values["time_of_last_observation"] = format_datetime(parsed)
        elif label == "LEAP SECONDS":
            try:
                values["leap_seconds"] = int(content[:6])
            except ValueError:
                warnings.append("invalid LEAP SECONDS value")
    if observation_type_count is not None and len(observation_types) != observation_type_count:
        raise RinexParseError(
            f"header declares {observation_type_count} observation types but lists "
            f"{len(observation_types)}"
        )
    interval = values.get("declared_interval_seconds")
    if interval is not None and interval <= 0:
        warnings.append("non-positive declared interval ignored")
        values["declared_interval_seconds"] = None
    return RinexHeader(observation_types=tuple(observation_types), **values), warnings


def phase_frequencies(observation_types: tuple[str, ...]) -> tuple[str, ...]:
    """Return frequency designators stated by carrier-phase observation codes."""

    return tuple(
        sorted({value[1] for value in observation_types if len(value) >= 2 and value[0] == "L"})
    )


def _analysis(
    header: RinexHeader,
    epochs: list[datetime],
    satellite_counts: list[int],
    constellation_counts: dict[str, list[int]],
    cycle_slip_indicators: int,
    warnings: list[str],
    year: int,
    day_of_year: int,
) -> RinexAnalysis:
    positive_intervals = [
        (current - previous).total_seconds()
        for previous, current in zip(epochs, epochs[1:], strict=False)
        if current > previous
    ]
    empirical = statistics.median(positive_intervals) if positive_intervals else None
    interval = header.declared_interval_seconds or empirical
    duplicate_epochs = sum(
        current == previous for previous, current in zip(epochs, epochs[1:], strict=False)
    )
    backward_epochs = sum(
        current < previous for previous, current in zip(epochs, epochs[1:], strict=False)
    )
    gaps: list[GapRecord] = []
    internal_missing = 0
    if interval is not None:
        for previous, current in zip(epochs, epochs[1:], strict=False):
            elapsed = (current - previous).total_seconds()
            if elapsed > interval:
                gap_missing = max(round(elapsed / interval) - 1, 0)
                internal_missing += gap_missing
                gaps.append(
                    GapRecord(
                        start=format_datetime(previous) or "",
                        end=format_datetime(current) or "",
                        elapsed_seconds=elapsed,
                        expected_interval_seconds=interval,
                        missing_epochs=gap_missing,
                    )
                )
    filename_day = datetime.strptime(f"{year} {day_of_year:03d}", "%Y %j").replace(tzinfo=UTC)
    first = epochs[0]
    last = epochs[-1]
    expected = round(86400 / interval) if interval else None
    unique_epochs = len(set(epochs))
    start_offset = (first - filename_day).total_seconds()
    expected_last = filename_day + timedelta(seconds=86400 - interval) if interval else None
    end_shortfall = (expected_last - last).total_seconds() if expected_last else None
    start_missing = max(round(start_offset / interval), 0) if interval else 0
    end_missing = max(round((end_shortfall or 0) / interval), 0) if interval else 0
    missing_total = start_missing + internal_missing + end_missing if interval else None
    availability = (100.0 * unique_epochs / expected) if expected else None
    interval_consistent = None
    if interval is not None and positive_intervals:
        interval_consistent = all(value == interval for value in positive_intervals)
    constellation_statistics = {
        name: {
            "epochs_present": sum(value > 0 for value in counts),
            "minimum_per_epoch": min(counts),
            "median_per_epoch": float(statistics.median(counts)),
            "maximum_per_epoch": max(counts),
        }
        for name, counts in sorted(constellation_counts.items())
        if any(counts)
    }
    return RinexAnalysis(
        header=header,
        first_epoch=format_datetime(first),
        last_epoch=format_datetime(last),
        session_duration_seconds=(last - first).total_seconds() + (interval or 0),
        expected_session_duration_seconds=86400.0 if interval else None,
        declared_interval_seconds=header.declared_interval_seconds,
        empirical_interval_seconds=empirical,
        interval_consistent=interval_consistent,
        epochs_expected=expected,
        epochs_observed=len(epochs),
        unique_epochs_observed=unique_epochs,
        missing_epochs=missing_total,
        availability_percent=availability,
        duplicate_epochs=duplicate_epochs,
        backward_epochs=backward_epochs,
        gap_count=len(gaps),
        largest_gap_seconds=max((gap.elapsed_seconds for gap in gaps), default=None),
        total_missing_duration_seconds=(
            missing_total * interval if missing_total is not None and interval else None
        ),
        start_offset_seconds=start_offset,
        end_shortfall_seconds=end_shortfall,
        satellites_min=min(satellite_counts),
        satellites_median=float(statistics.median(satellite_counts)),
        satellites_max=max(satellite_counts),
        constellation_statistics=constellation_statistics,
        potential_cycle_slip_indicators=cycle_slip_indicators,
        gaps=tuple(gaps),
        parser_warnings=tuple(dict.fromkeys(warnings)),
    )


def _record_count(line: str) -> int:
    try:
        return int(line[29:32])
    except ValueError as exc:
        raise RinexParseError("invalid epoch satellite/event-record count") from exc


def _satellites_from_epoch(line: str) -> list[str]:
    content = line[32:68].ljust(36)
    return [
        content[index : index + 3].strip().upper()
        for index in range(0, 36, 3)
        if content[index : index + 3].strip()
    ]


def _constellation(satellite_id: str) -> str:
    if satellite_id and satellite_id[0].isalpha():
        return CONSTELLATIONS.get(satellite_id[0], f"Other:{satellite_id[0]}")
    return "GPS"


def _count_phase_lli(lines: list[str], observation_types: tuple[str, ...]) -> int:
    joined = "".join(line.rstrip("\n").ljust(80) for line in lines)
    total = 0
    for index, observation_type in enumerate(observation_types):
        if not observation_type.startswith("L"):
            continue
        field = joined[index * 16 : (index + 1) * 16]
        if len(field) >= 15 and field[:14].strip() and field[14:15].isdigit() and field[14] != "0":
            total += 1
    return total


def _consume(iterator: Iterator[str], count: int, context: str) -> None:
    for _ in range(count):
        _next(iterator, context)


def _next(iterator: Iterator[str], context: str) -> str:
    try:
        return next(iterator)
    except StopIteration as exc:
        raise RinexParseError(f"unexpected EOF while reading {context}") from exc


def _label(line: str) -> str:
    return line[60:80].strip() if len(line) >= 60 else ""


def _float_tuple(content: str, count: int) -> tuple[float, ...] | None:
    try:
        return tuple(float(value) for value in content.split()[:count])
    except ValueError:
        return None


def _float_or_none(value: str) -> float | None:
    try:
        return float(value)
    except ValueError:
        return None
