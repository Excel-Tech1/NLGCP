"""Real-data loaders: manifest, QC tables, navigation inventory (IO boundary).

Pure logic lives in ``coverage.py``/``overlap.py`` so tests never touch disk.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
from pathlib import Path


def load_manifest_records(manifest_path: str) -> list[dict[str, object]]:
    """Load canonical raw-archive records."""
    with open(manifest_path, encoding="utf-8") as handle:
        payload = json.load(handle)
    records = payload.get("records", [])
    return [dict(record) for record in records]


def load_qc_session_table(csv_path: str) -> list[dict[str, str]]:
    """Load a Phase 4 ``session-qc-summary.csv`` table."""
    with open(csv_path, encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def nav_inventory_by_day(
    product_dir: str, validation_csv: str = ""
) -> dict[int, str]:
    """Map DOY to a validated merged-BRDC filename.

    When a navigation inventory CSV is available, only rows whose product
    validation is ``ACCEPTED`` and whose stored bytes still match the recorded
    SHA-256 are admitted.  The directory-only fallback exists for the initial
    planning stage, before a validation inventory has been written; it is
    intentionally not used once the inventory exists.
    """
    inventory: dict[int, str] = {}
    base = Path(product_dir)
    if not base.is_dir():
        return inventory
    if validation_csv and Path(validation_csv).is_file():
        with open(validation_csv, encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                if row.get("validation_status") != "ACCEPTED":
                    continue
                try:
                    doy = int(row["doy"])
                except (KeyError, TypeError, ValueError):
                    continue
                stored = Path(row.get("stored_path", ""))
                if not stored.is_file() or stored.parent != base:
                    continue
                recorded_hash = row.get("sha256", "")
                if recorded_hash and sha256_file(str(stored)) != recorded_hash:
                    continue
                inventory.setdefault(doy, stored.name)
        return inventory
    for entry in sorted(base.iterdir()):
        if not entry.is_file() or not entry.name.endswith(".rnx.gz"):
            continue
        parsed_doy = _doy_from_brdc_name(entry.name)
        if parsed_doy is not None and entry.stat().st_size > 0:
            inventory.setdefault(parsed_doy, entry.name)
    return inventory


def sha256_file(path: str) -> str:
    """Return the hex SHA-256 of a file."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while True:
            chunk = handle.read(65536)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def data_root_from_env(explicit: str = "") -> str:
    """Resolve ``NLGCP_DATA_ROOT`` with an explicit override first."""
    if explicit:
        return explicit
    root = os.environ.get("NLGCP_DATA_ROOT", "")
    if not root:
        raise ValueError("NLGCP_DATA_ROOT is not configured")
    if not os.path.isdir(root):
        raise ValueError(f"NLGCP_DATA_ROOT is not a directory: {root}")
    return root


def _doy_from_brdc_name(name: str) -> int | None:
    # BRDC00IGS_R_20240260000_01D_MN.rnx.gz -> 026
    try:
        core = name.split("_R_2024")[1]
        return int(core[:3])
    except (IndexError, ValueError):
        return None
