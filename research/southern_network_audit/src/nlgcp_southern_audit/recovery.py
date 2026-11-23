"""Conservative Phase 2 provenance, epoch-overlap, and admission primitives."""

from __future__ import annotations

import math
import re
import subprocess
from datetime import datetime
from typing import Any

RINEX2_EPOCH_LINE = re.compile(
    r"^\s*(\d{1,2})\s+(\d{1,2})\s+(\d{1,2})\s+(\d{1,2})\s+"
    r"(\d{1,2})\s+(\d{1,2}\.\d+)\s+([0-6])\s+(\d+)"
)


def coordinate_record_status(record: dict[str, str]) -> str:
    """Classify a coordinate-source row without filling missing provenance."""
    if not record.get("coordinate_xyz_m", "").strip():
        return "MISSING"
    identity_status = record.get("identity_status", "").strip().upper()
    if identity_status in {"CONFLICT", "UNRESOLVED"}:
        return "UNVERIFIED"
    required = ("source", "reference_frame", "coordinate_epoch", "reference_point")
    unavailable = {"UNKNOWN", "NOT STATED", "NOT REPORTED", "UNAVAILABLE", "N/A"}
    return (
        "VERIFIED"
        if identity_status == "IDENTITY_RECONCILED"
        and all(
            record.get(key, "").strip()
            and record.get(key, "").strip().upper() not in unavailable
            for key in required
        )
        else "PROVISIONAL"
    )


def reconcile_station_identity(observation_code: str, source_station_code: str) -> dict[str, str]:
    """Require exact station-code identity; aliases need a separate reviewed record."""
    obs = observation_code.strip().upper()
    src = source_station_code.strip().upper()
    if not obs or not src:
        return {"status": "UNRESOLVED", "observation_code": obs, "source_code": src}
    return {
        "status": "CODE_MATCH_MONUMENT_UNVERIFIED" if obs == src else "CONFLICT",
        "observation_code": obs,
        "source_code": src,
    }


def parse_rinex2_epoch_line(line: str) -> tuple[datetime, int] | None:
    """Parse one RINEX 2 epoch without converting its declared time scale."""
    match = RINEX2_EPOCH_LINE.match(line)
    if not match:
        return None
    try:
        yy, month, day, hour, minute = map(int, match.groups()[:5])
        year = 2000 + yy if yy < 80 else 1900 + yy
        seconds = float(match.group(6))
        whole = int(seconds)
        stamp = datetime(
            year,
            month,
            day,
            hour,
            minute,
            whole,
            round((seconds - whole) * 1_000_000),
        )
        return stamp, int(match.group(7))
    except (ValueError, OverflowError):
        return None


def exact_epoch_intersection(
    epochs_by_station: dict[str, set[datetime]],
    time_system_by_station: dict[str, str],
) -> dict[str, Any]:
    """Intersect recorded epochs only when every station declares one time scale."""
    if not epochs_by_station or set(epochs_by_station) != set(time_system_by_station):
        return {"status": "MISSING_STATION_EPOCHS", "epochs": [], "count": 0}
    systems = {time_system_by_station[key].strip().upper() for key in epochs_by_station}
    if "" in systems or len(systems) != 1:
        return {
            "status": "TIME_SYSTEM_INCOMPATIBLE",
            "time_systems": sorted(systems),
            "epochs": [],
            "count": 0,
        }
    sets = list(epochs_by_station.values())
    common = sorted(set.intersection(*sets)) if sets else []
    return {
        "status": "EXACT_COMMON_EPOCHS" if common else "NO_EXACT_COMMON_EPOCHS",
        "time_system": next(iter(systems)),
        "epochs": [stamp.isoformat() for stamp in common],
        "count": len(common),
    }


def parse_rinex2_navigation(
    text: str,
    expected_date: str,
    expected_system: str,
    required_satellites: set[str] | None = None,
) -> dict[str, Any]:
    """Validate a legacy daily navigation payload's header and ephemeris records."""
    lines = text.splitlines()
    header_end = next(
        (index for index, line in enumerate(lines) if line[60:80].strip() == "END OF HEADER"),
        None,
    )
    header_lines = lines[: header_end + 1] if header_end is not None else []
    if header_end is None or not any("RINEX VERSION / TYPE" in line for line in header_lines):
        return {"status": "INVALID_OR_MISSING_RINEX_HEADER", "satellites": [], "epochs": []}
    header = next(line for line in header_lines if "RINEX VERSION / TYPE" in line)
    version = header[:9].strip()
    file_system = header[40:41].strip().upper()
    # RINEX 2 navigation file type is column 21: N is GPS and G is GLONASS.
    file_type = header[20:21].strip().upper()
    if not version.startswith("2") or file_type not in {"N", "G"}:
        return {
            "status": "UNSUPPORTED_NAVIGATION_HEADER",
            "version": version,
            "file_type": file_type,
        }
    if file_type != expected_system.upper():
        return {
            "status": "NAVIGATION_SYSTEM_MISMATCH",
            "version": version,
            "file_type": file_type,
            "expected_system": expected_system.upper(),
        }
    data_lines = lines[header_end + 1 :]
    record_length = 8 if file_type == "N" else 4
    sat_epochs: list[tuple[str, datetime]] = []
    health_flags: list[int] = []
    for offset in range(0, len(data_lines), record_length):
        record = data_lines[offset : offset + record_length]
        if len(record) < record_length:
            continue
        line = record[0]
        if len(line) < 22:
            continue
        try:
            prn_number = int(line[:2])
            yy, month, day, hour, minute = map(
                int, (line[3:5], line[6:8], line[9:11], line[12:14], line[15:17])
            )
            year = 2000 + yy if yy < 80 else 1900 + yy
            seconds = float(line[18:22])
            whole = int(seconds)
            stamp = datetime(year, month, day, hour, minute, whole, round((seconds - whole) * 1e6))
            constellation = "G" if file_type == "N" else "R"
            sat_epochs.append((f"{constellation}{prn_number:02d}", stamp))
            health_line = record[7] if file_type == "N" else record[1]
            fields = re.findall(r"[-+]?(?:\d+\.\d*|\.\d+|\d+)(?:[DEde][-+]?\d+)?", health_line)
            health_index = 1 if file_type == "N" else 3
            if len(fields) > health_index:
                health_flags.append(int(float(fields[health_index].replace("D", "E"))))
        except (ValueError, OverflowError):
            continue
    expected = datetime.fromisoformat(expected_date).date()
    actual_dates = sorted({stamp.date().isoformat() for _, stamp in sat_epochs})
    satellites = sorted({prn for prn, _ in sat_epochs})
    missing_satellites = sorted((required_satellites or set()) - set(satellites))
    status = (
        "NO_EXPECTED_DATE_EPHEMERIS"
        if not sat_epochs or expected_date not in actual_dates
        else "MISSING_SATELLITE_EPHEMERIDES"
        if missing_satellites
        else "VALIDATED"
    )
    return {
        "status": status,
        "version": version,
        "file_type": file_type,
        "header_system": file_system,
        "expected_date": expected_date,
        "ephemeris_record_count": len(sat_epochs),
        "satellites": satellites,
        "missing_required_satellites": missing_satellites,
        "epochs": [stamp.isoformat() for _, stamp in sat_epochs],
        "ephemeris_dates": actual_dates,
        "expected_day_present": expected in {stamp.date() for _, stamp in sat_epochs},
        "health_indicator_count": len(health_flags),
        "health_flag_values": sorted(set(health_flags)),
        "health_zero_record_count": sum(flag == 0 for flag in health_flags),
        "health_nonzero_record_count": sum(flag != 0 for flag in health_flags),
    }


def scientific_admission(
    station_coordinate_statuses: dict[str, str],
    navigation_statuses: dict[str, str],
    time_systems: dict[str, str],
    exact_common_epoch_count: int,
    identity_statuses: dict[str, str] | None = None,
    reference_points: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Fail-closed admission gate for a reference set plus held-out station."""
    reasons: list[str] = []
    if not station_coordinate_statuses or any(
        value != "VERIFIED" for value in station_coordinate_statuses.values()
    ):
        reasons.append("COORDINATES_NOT_ALL_VERIFIED")
    if (
        not identity_statuses
        or set(identity_statuses) != set(station_coordinate_statuses)
        or any(value != "IDENTITY_RECONCILED" for value in identity_statuses.values())
    ):
        reasons.append("STATION_IDENTITY_NOT_RECONCILED")
    if (
        not reference_points
        or set(reference_points) != set(station_coordinate_statuses)
        or any(
            not value.strip()
            or value.strip().upper()
            in {"UNKNOWN", "NOT STATED", "NOT REPORTED", "UNAVAILABLE", "N/A"}
            for value in reference_points.values()
        )
        or len({value.strip().upper() for value in reference_points.values()}) != 1
    ):
        reasons.append("REFERENCE_POINT_INCOMPATIBLE_OR_UNKNOWN")
    if not navigation_statuses or any(
        value != "VALIDATED" for value in navigation_statuses.values()
    ):
        reasons.append("REQUIRED_NAVIGATION_NOT_VALIDATED")
    systems = {value.strip().upper() for value in time_systems.values()}
    if not time_systems or "" in systems or len(systems) != 1:
        reasons.append("TIME_SYSTEM_INCOMPATIBLE_OR_UNKNOWN")
    if exact_common_epoch_count < 1:
        reasons.append("NO_EXACT_COMMON_OBSERVATION_EPOCHS")
    return {"state": "ADMITTED" if not reasons else "BLOCKED", "reasons": reasons}


def coordinate_gated_geometry(
    stations: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Return only coordinate-verified station inputs or an explicit block state."""
    unverified = sorted(
        station_id
        for station_id, record in stations.items()
        if record.get("coordinate_status") != "VERIFIED" or not record.get("xyz")
    )
    reference_points = {
        str(record.get("reference_point", "")).strip().upper()
        for record in stations.values()
        if record.get("coordinate_status") == "VERIFIED"
    }
    if len(reference_points) > 1:
        return {
            "state": "BLOCKED_REFERENCE_POINT_MISMATCH",
            "station_ids_blocking": sorted(stations),
            "stations": {},
        }
    if unverified:
        return {
            "state": "BLOCKED_COORDINATES_NOT_VERIFIED",
            "station_ids_blocking": unverified,
            "stations": {},
        }
    return {
        "state": "READY_FOR_GEOMETRY_CALCULATION",
        "station_ids_blocking": [],
        "stations": stations,
    }


def coordinate_transformation_status(
    transform_parameters: tuple[float, ...] | None,
    station_velocity_m_per_year: tuple[float, float, float] | None,
) -> str:
    """Require finite documented parameters and velocity before any epoch/frame transform."""
    if transform_parameters is None or station_velocity_m_per_year is None:
        return "TRANSFORMATION_UNAVAILABLE"
    values = (*transform_parameters, *station_velocity_m_per_year)
    if not values or any(
        not isinstance(value, (int, float)) or not math.isfinite(value) for value in values
    ):
        return "INVALID_TRANSFORMATION_INPUT"
    return "TRANSFORMATION_INPUTS_PRESENT_REVIEW_REQUIRED"


def decompress_unix_compress(payload: bytes) -> bytes:
    """Decode one .Z file via the system uncompress utility; fail on corruption."""
    try:
        result = subprocess.run(
            ["uncompress", "-c"], input=payload, capture_output=True, check=True
        )
    except FileNotFoundError as exc:
        raise RuntimeError("required external dependency 'uncompress' is unavailable") from exc
    except subprocess.CalledProcessError as exc:
        raise ValueError("invalid or corrupt Unix-compress payload") from exc
    return result.stdout
