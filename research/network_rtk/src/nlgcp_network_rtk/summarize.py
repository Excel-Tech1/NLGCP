"""Summary aggregation over network experiments."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any


def summarize_data_root(data_root: Path) -> dict[str, Any]:
    summary_dir = data_root / "processed" / "network-rtk" / "summaries"
    experiments_dir = data_root / "processed" / "network-rtk" / "experiments"
    experiments: list[str] = []
    if experiments_dir.is_dir():
        experiments = sorted(p.name for p in experiments_dir.iterdir() if p.is_dir())
    files = {}
    names = (
        "network-experiments.csv",
        "baseline-matrix.csv",
        "station-eligibility.csv",
        "comparison.csv",
    )
    for name in names:
        path = summary_dir / name
        files[name] = _count_rows(path)
    return {
        "experiments": experiments,
        "experiment_count": len(experiments),
        "summary_files": files,
        "summary_dir": str(summary_dir),
    }


def _count_rows(path: Path) -> int:
    if not path.is_file():
        return 0
    with path.open(encoding="utf-8", newline="") as handle:
        return sum(1 for _ in csv.DictReader(handle))
