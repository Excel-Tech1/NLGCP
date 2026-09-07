"""Reusable network observation/residual representation (Phase 6 input).

Only fields derivable from available evidence are populated.  RTKLIB
``.pos`` outputs yield per-epoch position residuals and solution quality,
not per-satellite observables, so satellite-level fields are recorded as
null with an explicit reason instead of being invented.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

UNAVAILABLE_SATELLITE_FIELDS = {
    "satellite_id": "not derivable from RTKLIB .pos output; no per-satellite observables parsed",
    "constellation": "not derivable from RTKLIB .pos output",
    "satellite_elevation": "not derivable from RTKLIB .pos output",
    "satellite_azimuth": "not derivable from RTKLIB .pos output",
    "common_satellite_count": "not recorded by the Phase 5 .pos parser",
}

RESIDUAL_FIELDS = [
    "epoch",
    "station_id",
    "baseline_id",
    "baseline_length_m",
    "solution_quality",
    "quality_code",
    "satellites",
    "east_residual_m",
    "north_residual_m",
    "up_residual_m",
    "horizontal_error_m",
    "error_3d_m",
    "satellite_id",
    "constellation",
    "satellite_elevation_deg",
    "satellite_azimuth_deg",
    "common_satellite_count",
]


def residual_rows_for_baseline(
    *,
    baseline_id: str,
    test_station: str,
    baseline_length_m: float,
    epochs_csv: Path,
) -> list[dict[str, Any]]:
    """Read one baseline's epochs.csv into network residual rows."""
    if not epochs_csv.is_file():
        return []
    rows: list[dict[str, Any]] = []
    with epochs_csv.open(encoding="utf-8", newline="") as handle:
        for record in csv.DictReader(handle):
            rows.append(
                {
                    "epoch": record.get("epoch", ""),
                    "station_id": test_station,
                    "baseline_id": baseline_id,
                    "baseline_length_m": baseline_length_m,
                    "solution_quality": record.get("quality", ""),
                    "quality_code": _as_int(record.get("quality_code")),
                    "satellites": _as_int(record.get("satellites")),
                    "east_residual_m": _as_float(record.get("east_m")),
                    "north_residual_m": _as_float(record.get("north_m")),
                    "up_residual_m": _as_float(record.get("up_m")),
                    "horizontal_error_m": _as_float(record.get("horizontal_error_m")),
                    "error_3d_m": _as_float(record.get("error_3d_m")),
                    "satellite_id": None,
                    "constellation": None,
                    "satellite_elevation_deg": None,
                    "satellite_azimuth_deg": None,
                    "common_satellite_count": None,
                }
            )
    return sorted(rows, key=lambda r: (str(r["epoch"]), str(r["baseline_id"])))


def write_residual_dataset(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    ordered = sorted(rows, key=lambda r: (str(r["epoch"]), str(r["baseline_id"])))
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=RESIDUAL_FIELDS)
        writer.writeheader()
        writer.writerows(ordered)


def dataset_readme() -> str:
    lines = [
        "# Phase 5 network observation/residual dataset",
        "",
        "Rows are per-baseline position residuals against the trusted rover",
        "control coordinate.  They are network INPUTS for later Phase 6",
        "modelling, not network corrections.",
        "",
        "## Unavailable fields (documented, not invented)",
        "",
    ]
    for name, reason in sorted(UNAVAILABLE_SATELLITE_FIELDS.items()):
        lines.append(f"- `{name}`: null. {reason}.")
    lines.append("")
    return "\n".join(lines)


def _as_float(value: Any) -> float | None:
    try:
        return float(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _as_int(value: Any) -> int | None:
    try:
        return int(float(value)) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None
