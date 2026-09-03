"""Machine-readable and human-readable table generation for Phase 3.

Tables are written as CSV/JSON for machine consumption and rendered as
Markdown for human review.  All tables derive from stored result files.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any


def write_csv(path: Path, rows: list[dict[str, Any]]) -> Path:
    """Write a CSV table from a list of row dicts (ordered by their keys)."""
    if not rows:
        raise ValueError(f"cannot write empty table: {path}")
    fieldnames = list(rows[0])
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: _as_str(value) for key, value in row.items()})
    return path


def write_json_table(path: Path, payload: Any) -> Path:
    """Write a JSON table/artifact."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def render_markdown_table(rows: list[dict[str, Any]]) -> str:
    """Render a list of row dicts as a Markdown table."""
    if not rows:
        return "_No rows._"
    headers = list(rows[0])
    lines = [
        "| " + " | ".join(str(h) for h in headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(_as_str(row.get(h)) for h in headers) + " |")
    return "\n".join(lines)


def station_metadata_table(
    station_metadata: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Flatten a station metadata dictionary into rows keyed by station."""
    return [
        {"station_id": station, **metadata}
        for station, metadata in sorted(station_metadata.items())
    ]


def _as_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:.6g}"
    return str(value)
