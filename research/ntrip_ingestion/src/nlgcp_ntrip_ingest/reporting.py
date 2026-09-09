"""Capture validation and summarisation (offline, no network)."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from typing import Any


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_capture(capture_dir: Path) -> dict[str, Any]:
    """Validate a closed capture directory; findings, never exceptions."""
    findings: list[str] = []
    expected = ("stream.rtcm3", "arrival-index.csv", "source-table.txt", "capture.json")
    for name in expected:
        if not (capture_dir / name).is_file():
            findings.append(f"MISSING_FILE {name}")
    meta: dict[str, Any] = {}
    meta_path = capture_dir / "capture.json"
    if meta_path.is_file():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            findings.append(f"MALFORMED_CAPTURE_JSON {exc}")
    sums_path = capture_dir / "SHA256SUMS.txt"
    if sums_path.is_file() and meta_path.is_file():
        try:
            recorded: dict[str, str] = {}
            for line in sums_path.read_text(encoding="utf-8").splitlines():
                parts = line.split()
                if len(parts) == 2:
                    recorded[parts[1]] = parts[0]
            for name in expected:
                observed = sha256_file(capture_dir / name)
                if recorded.get(name) != observed:
                    findings.append(f"SHA_MISMATCH {name}")
            stream_hash = sha256_file(capture_dir / "stream.rtcm3")
            if meta.get("stream_sha256") and meta["stream_sha256"] != stream_hash:
                findings.append("STREAM_HASH_MISMATCH capture.json vs stream.rtcm3")
        except OSError as exc:
            findings.append(f"SHA_CHECK_FAILED {exc}")
    index_path = capture_dir / "arrival-index.csv"
    rows = 0
    last_mono: int | None = None
    last_seq: int | None = None
    if index_path.is_file():
        try:
            with open(index_path, newline="", encoding="utf-8") as handle:
                reader = csv.DictReader(handle)
                for row in reader:
                    rows += 1
                    try:
                        seq = int(row["sequence"])
                        mono = int(row["arrival_monotonic_ns"])
                    except (KeyError, ValueError):
                        findings.append(f"MALFORMED_INDEX_ROW {rows}")
                        break
                    if last_seq is not None and seq != last_seq + 1:
                        findings.append(f"INDEX_SEQUENCE_GAP at={seq}")
                    if last_mono is not None and mono < last_mono:
                        findings.append("INDEX_MONOTONIC_REGRESSION")
                        break
                    last_seq, last_mono = seq, mono
        except OSError as exc:
            findings.append(f"INDEX_READ_FAILED {exc}")
    status = "VALID" if not findings else "INVALID"
    return {
        "status": status,
        "findings": findings,
        "index_rows": rows,
        "metadata": meta,
    }


def summarize_capture(capture_dir: Path) -> dict[str, Any]:
    """Summarise a capture directory for evidence bundles."""
    validation = validate_capture(capture_dir)
    meta = validation["metadata"]
    return {
        "capture_dir": str(capture_dir),
        "status": validation["status"],
        "findings": validation["findings"],
        "index_rows": validation["index_rows"],
        "capture_id": meta.get("capture_id", ""),
        "provider": meta.get("provider", ""),
        "station_mapping": meta.get("station_mapping", ""),
        "capture_status": meta.get("capture_status", ""),
        "bytes_received": meta.get("bytes_received", 0),
        "valid_frames": meta.get("valid_frames", 0),
        "invalid_frames": meta.get("invalid_frames", 0),
        "observed_message_types": meta.get("observed_message_types", []),
        "reconnects": meta.get("reconnects", 0),
        "stream_sha256": meta.get("stream_sha256", ""),
    }
