"""RTKLIB solution parsing and benchmark metrics."""

from __future__ import annotations

import csv
import math
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from nlgcp_single_base.coordinates import (
    EcefCoordinate,
    GeodeticCoordinate,
    ecef_delta_to_enu,
    geodetic_to_ecef,
)
from nlgcp_single_base.models import BLOCKED_MESSAGE, ScientificExecutionBlocked


class SolutionQuality(StrEnum):
    """RTKLIB v2.4.2-p13 SOLQ_* solution quality states."""

    NO_SOLUTION = "NO_SOLUTION"
    FIX = "FIX"
    FLOAT = "FLOAT"
    SBAS = "SBAS"
    DGPS = "DGPS"
    SINGLE = "SINGLE"
    PPP = "PPP"
    DEAD_RECKONING = "DEAD_RECKONING"
    UNKNOWN = "UNKNOWN"


QUALITY_BY_CODE = {
    0: SolutionQuality.NO_SOLUTION,
    1: SolutionQuality.FIX,
    2: SolutionQuality.FLOAT,
    3: SolutionQuality.SBAS,
    4: SolutionQuality.DGPS,
    5: SolutionQuality.SINGLE,
    6: SolutionQuality.PPP,
    7: SolutionQuality.DEAD_RECKONING,
}


@dataclass(frozen=True)
class SolutionEpoch:
    """One parsed RTKLIB latitude/longitude/ellipsoidal-height solution epoch."""

    epoch: datetime
    coordinate: GeodeticCoordinate
    quality_code: int
    quality: SolutionQuality
    satellites: int | None
    age_s: float | None
    ratio: float | None


@dataclass(frozen=True)
class ParseDiagnostics:
    """Diagnostics that make parser losses explicit."""

    valid_rows: int
    malformed_rows: list[str]
    structural_mismatch: str | None = None


@dataclass(frozen=True)
class ParsedSolution:
    """Parsed epochs plus parser diagnostics."""

    epochs: list[SolutionEpoch]
    diagnostics: ParseDiagnostics


@dataclass(frozen=True)
class EpochResidual:
    """Per-epoch residuals against a known control coordinate."""

    epoch: datetime
    quality_code: int
    quality: SolutionQuality
    satellites: int | None
    east_m: float
    north_m: float
    up_m: float
    horizontal_error_m: float
    vertical_abs_error_m: float
    error_3d_m: float


def quality_from_code(code: int) -> SolutionQuality:
    """Map RTKLIB SOLQ integer codes from rtklib.h to named states."""

    return QUALITY_BY_CODE.get(code, SolutionQuality.UNKNOWN)


def parse_solution_pos(path: Path, *, strict: bool = True) -> ParsedSolution:
    """Parse RTKLIB `.pos` output configured as LLH, GPST hms, decimal degrees."""

    epochs: list[SolutionEpoch] = []
    malformed: list[str] = []
    saw_expected_header = False
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith("%"):
                if _is_expected_llh_header(stripped):
                    saw_expected_header = True
                continue
            fields = stripped.split()
            try:
                epochs.append(_parse_llh_fields(fields))
            except (ValueError, IndexError) as exc:
                malformed.append(f"line {line_number}: {exc}: {stripped}")

    structural_mismatch = None
    if not saw_expected_header:
        structural_mismatch = "expected RTKLIB LLH GPST header was not found"
    diagnostics = ParseDiagnostics(
        valid_rows=len(epochs),
        malformed_rows=malformed,
        structural_mismatch=structural_mismatch,
    )
    if strict and (structural_mismatch or malformed):
        reason = structural_mismatch or "; ".join(malformed[:3])
        raise ScientificExecutionBlocked(f"{BLOCKED_MESSAGE}: RTKLIB output parse failed: {reason}")
    return ParsedSolution(epochs=epochs, diagnostics=diagnostics)


def residuals_against_control(
    epochs: list[SolutionEpoch],
    control_coordinate: GeodeticCoordinate,
) -> list[EpochResidual]:
    """Calculate ENU, horizontal, signed-up and 3D residuals."""

    control_ecef = geodetic_to_ecef(control_coordinate)
    residuals: list[EpochResidual] = []
    for epoch in epochs:
        solution_ecef = geodetic_to_ecef(epoch.coordinate)
        delta = EcefCoordinate(
            solution_ecef.x_m - control_ecef.x_m,
            solution_ecef.y_m - control_ecef.y_m,
            solution_ecef.z_m - control_ecef.z_m,
        )
        east, north, up = ecef_delta_to_enu(delta, control_coordinate)
        horizontal = math.hypot(east, north)
        residuals.append(
            EpochResidual(
                epoch=epoch.epoch,
                quality_code=epoch.quality_code,
                quality=epoch.quality,
                satellites=epoch.satellites,
                east_m=east,
                north_m=north,
                up_m=up,
                horizontal_error_m=horizontal,
                vertical_abs_error_m=abs(up),
                error_3d_m=math.sqrt(horizontal * horizontal + up * up),
            )
        )
    return residuals


def summarise_solution_state_metrics(
    epochs: list[SolutionEpoch],
    *,
    start_time_utc: str,
    end_time_utc: str,
    sampling_rate_hz: float,
) -> dict[str, float | int | None]:
    """Summarise state metrics using requested experiment time and sampling."""

    expected_epoch_count = expected_epochs(start_time_utc, end_time_utc, sampling_rate_hz)
    fix_count = sum(1 for epoch in epochs if epoch.quality is SolutionQuality.FIX)
    solution_count = len(epochs)
    return {
        "solution_epoch_count": solution_count,
        "expected_epoch_count": expected_epoch_count,
        "solution_availability": solution_count / expected_epoch_count,
        "fix_epoch_count": fix_count,
        "fix_rate_solution_epochs": fix_count / solution_count if solution_count else None,
        "fix_rate_expected_epochs": fix_count / expected_epoch_count,
        "ttff_seconds": ttff_seconds(epochs),
    }


def summarise_accuracy_metrics(
    residuals: list[EpochResidual],
) -> dict[str, float | int | None]:
    """Summarise accuracy metrics supported by trusted control coordinates."""

    if not residuals:
        return {
            "accuracy_epoch_count": 0,
            "mean_east_m": None,
            "mean_north_m": None,
            "mean_up_m": None,
            "east_rmse_m": None,
            "north_rmse_m": None,
            "up_rmse_m": None,
            "horizontal_rmse_m": None,
            "three_d_rmse_m": None,
            "vertical_abs_rmse_m": None,
        }

    return {
        "accuracy_epoch_count": len(residuals),
        "mean_east_m": _mean([item.east_m for item in residuals]),
        "mean_north_m": _mean([item.north_m for item in residuals]),
        "mean_up_m": _mean([item.up_m for item in residuals]),
        "east_rmse_m": _rmse([item.east_m for item in residuals]),
        "north_rmse_m": _rmse([item.north_m for item in residuals]),
        "up_rmse_m": _rmse([item.up_m for item in residuals]),
        "horizontal_rmse_m": _rmse([item.horizontal_error_m for item in residuals]),
        "three_d_rmse_m": _rmse([item.error_3d_m for item in residuals]),
        "vertical_abs_rmse_m": _rmse([item.vertical_abs_error_m for item in residuals]),
    }


def expected_epochs(start_time_utc: str, end_time_utc: str, sampling_rate_hz: float) -> int:
    """Expected epoch count with inclusive endpoints at the requested interval."""

    if sampling_rate_hz <= 0:
        raise ScientificExecutionBlocked(f"{BLOCKED_MESSAGE}: invalid sampling rate")
    start = parse_iso_utc(start_time_utc)
    end = parse_iso_utc(end_time_utc)
    duration = (end - start).total_seconds()
    if duration < 0:
        raise ScientificExecutionBlocked(f"{BLOCKED_MESSAGE}: end time precedes start time")
    interval = 1.0 / sampling_rate_hz
    return int(math.floor(duration / interval + 1e-9)) + 1


def ttff_seconds(epochs: list[SolutionEpoch]) -> float | None:
    """Elapsed time from first valid solution epoch to first FIX epoch."""

    if not epochs:
        return None
    first_epoch = epochs[0].epoch
    for epoch in epochs:
        if epoch.quality is SolutionQuality.FIX:
            return (epoch.epoch - first_epoch).total_seconds()
    return None


def assert_epochs_within_window(
    epochs: list[SolutionEpoch],
    start_time_utc: str,
    end_time_utc: str,
) -> None:
    """Fail closed if parsed RTKLIB output escapes the requested window."""

    start = parse_iso_utc(start_time_utc)
    end = parse_iso_utc(end_time_utc)
    for epoch in epochs:
        if epoch.epoch < start or epoch.epoch > end:
            raise ScientificExecutionBlocked(
                f"{BLOCKED_MESSAGE}: RTKLIB output epoch outside requested window"
            )


def parse_iso_utc(timestamp: str) -> datetime:
    """Parse an ISO timestamp as timezone-aware UTC."""

    value = timestamp.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def write_epoch_csv(path: Path, residuals: list[EpochResidual]) -> None:
    """Write machine-readable per-epoch residuals."""

    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "epoch",
                "quality_code",
                "quality",
                "satellites",
                "east_m",
                "north_m",
                "up_m",
                "horizontal_error_m",
                "vertical_abs_error_m",
                "error_3d_m",
            ],
        )
        writer.writeheader()
        for item in residuals:
            writer.writerow(
                {
                    **item.__dict__,
                    "epoch": item.epoch.isoformat(),
                    "quality": item.quality.value,
                }
            )


def solution_epochs_json(epochs: list[SolutionEpoch]) -> list[dict[str, Any]]:
    """Render solution state epochs to JSON-safe dictionaries."""

    return [
        {
            "epoch": epoch.epoch.isoformat(),
            "latitude_deg": epoch.coordinate.latitude_deg,
            "longitude_deg": epoch.coordinate.longitude_deg,
            "height_m": epoch.coordinate.height_m,
            "quality_code": epoch.quality_code,
            "quality": epoch.quality.value,
            "satellites": epoch.satellites,
            "age_s": epoch.age_s,
            "ratio": epoch.ratio,
        }
        for epoch in epochs
    ]


def _parse_llh_fields(fields: list[str]) -> SolutionEpoch:
    if len(fields) < 14:
        raise ValueError(f"expected at least 14 RTKLIB LLH fields, got {len(fields)}")
    epoch = _parse_rtklib_gpst_hms(fields[0], fields[1])
    quality_code = int(fields[5])
    return SolutionEpoch(
        epoch=epoch,
        coordinate=GeodeticCoordinate(float(fields[2]), float(fields[3]), float(fields[4])),
        quality_code=quality_code,
        quality=quality_from_code(quality_code),
        satellites=int(fields[6]),
        age_s=float(fields[13]),
        ratio=float(fields[14]) if len(fields) > 14 else None,
    )


def _parse_rtklib_gpst_hms(date_field: str, time_field: str) -> datetime:
    if "/" in date_field:
        date = datetime.strptime(f"{date_field} {time_field}", "%Y/%m/%d %H:%M:%S.%f")
    else:
        date = datetime.strptime(f"{date_field} {time_field}", "%Y-%m-%d %H:%M:%S.%f")
    return date.replace(tzinfo=UTC)


def _is_expected_llh_header(line: str) -> bool:
    return (
        "GPST" in line
        and "latitude(deg)" in line
        and "longitude(deg)" in line
        and "height(m)" in line
        and "age(s)" in line
        and "ratio" in line
    )


def _rmse(values: list[float]) -> float:
    return math.sqrt(sum(value * value for value in values) / len(values))


def _mean(values: list[float]) -> float:
    return sum(values) / len(values)
