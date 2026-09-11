"""Immutable authentic capture writer (incremental, crash-safe).

Layout::

    <root>/<provider>/<station>/<date>/
        stream.rtcm3        (byte-exact RTCM, appended incrementally)
        arrival-index.csv   (per-frame arrival timing sidecar)
        source-table.txt    (provider metadata snapshot)
        capture.json        (finalised metadata, no passwords)
        SHA256SUMS.txt      (integrity manifest)

Provider/mountpoint strings are untrusted: filesystem names are
sanitised while original values are preserved inside metadata.
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
import shutil
import time
from datetime import UTC, datetime
from pathlib import Path

from nlgcp_ntrip_ingest.models import ArrivalRecord, CaptureMetadata

INDEX_HEADER = [
    "sequence",
    "byte_offset",
    "frame_length",
    "arrival_utc",
    "arrival_monotonic_ns",
    "message_number",
    "crc_status",
    "frame_sha256",
]

_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")


class CaptureLimitExceeded(RuntimeError):
    """Capture must stop before a configured evidence/resource limit."""


class CaptureRotationPolicy:
    """Rotation boundaries are evaluated before writing a complete frame."""

    def __init__(
        self,
        *,
        max_bytes: int | None = None,
        max_frames: int | None = None,
        max_seconds: float | None = None,
        minimum_free_bytes: int = 0,
    ) -> None:
        if max_bytes is not None and max_bytes < 1:
            raise ValueError("max_bytes must be >= 1")
        if max_frames is not None and max_frames < 1:
            raise ValueError("max_frames must be >= 1")
        if max_seconds is not None and max_seconds <= 0:
            raise ValueError("max_seconds must be > 0")
        if minimum_free_bytes < 0:
            raise ValueError("minimum_free_bytes must be >= 0")
        self.max_bytes = max_bytes
        self.max_frames = max_frames
        self.max_seconds = max_seconds
        self.minimum_free_bytes = minimum_free_bytes

    def requires_rotation(
        self,
        *,
        current_bytes: int,
        current_frames: int,
        elapsed_seconds: float,
        next_frame_bytes: int,
    ) -> bool:
        return bool(
            (self.max_bytes is not None and current_bytes + next_frame_bytes > self.max_bytes)
            or (self.max_frames is not None and current_frames >= self.max_frames)
            or (self.max_seconds is not None and elapsed_seconds >= self.max_seconds)
        )

    def disk_allowed(self, path: Path) -> bool:
        return shutil.disk_usage(path).free >= self.minimum_free_bytes


def find_incomplete_captures(root: Path) -> tuple[Path, ...]:
    """Find raw capture directories without a completed metadata manifest."""
    found: list[Path] = []
    if not root.exists():
        return ()
    for stream in sorted(root.rglob("stream.rtcm3")):
        directory = stream.parent
        metadata = directory / "capture.json"
        if not metadata.exists():
            found.append(directory)
    return tuple(found)


def recover_incomplete_capture(capture_dir: Path) -> dict[str, object]:
    """Write a minimal PARTIAL/INTERRUPTED manifest without touching raw bytes.

    Completed captures are immutable and are never rewritten. The recovery
    manifest is intentionally conservative; Phase 9 still performs full
    binary admission and validation later.
    """
    metadata_path = capture_dir / "capture.json"
    if metadata_path.exists():
        payload = json.loads(metadata_path.read_text(encoding="utf-8"))
        return payload
    stream_path = capture_dir / "stream.rtcm3"
    if not stream_path.is_file():
        raise FileNotFoundError(stream_path)
    digest = hashlib.sha256(stream_path.read_bytes()).hexdigest()
    now = datetime.now(UTC).isoformat()
    payload: dict[str, object] = {
        "capture_id": capture_dir.name,
        "capture_status": "PARTIAL",
        "interruption_reason": "PROCESS_INTERRUPTED",
        "start_utc": None,
        "end_utc": now,
        "bytes_received": stream_path.stat().st_size,
        "valid_frames": None,
        "invalid_frames": None,
        "stream_sha256": digest,
        "raw_bytes_preserved": True,
        "scientific_validation": "DEFERRED_TO_PHASE9",
    }
    metadata_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    sums: list[str] = []
    for name in ("stream.rtcm3", "arrival-index.csv", "source-table.txt", "capture.json"):
        path = capture_dir / name
        if path.is_file():
            sums.append(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {name}\n")
    (capture_dir / "SHA256SUMS.txt").write_text("".join(sums), encoding="utf-8")
    return payload


def sanitize_identifier(value: str, *, fallback: str = "unknown") -> str:
    """Sanitise an untrusted string for use as a single path component."""
    cleaned = _UNSAFE.sub("_", value.strip().lstrip("/")).strip("._")
    if not cleaned or cleaned in (".", ".."):
        return fallback
    return cleaned[:64]


def utc_today() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d")


class CaptureWriter:
    """Incremental raw-capture writer; partial files stay analyzable."""

    def __init__(
        self,
        capture_dir: Path,
        *,
        capture_id: str,
        provider: str,
        caster_host: str,
        caster_port: int,
        mountpoint: str,
        station_mapping: str,
        tls_mode: str,
        authorization_provenance: str,
        software_commit: str,
        source_table_sha256: str,
        source_table_text: str,
        rotation_policy: CaptureRotationPolicy | None = None,
    ) -> None:
        self.capture_dir = capture_dir
        self.capture_dir.mkdir(parents=True, exist_ok=False)
        self._capture_id = capture_id
        self._provider = provider
        self._caster_host = caster_host
        self._caster_port = caster_port
        self._mountpoint = mountpoint
        self._station_mapping = station_mapping
        self._tls_mode = tls_mode
        self._authorization_provenance = authorization_provenance
        self._software_commit = software_commit
        self._source_table_sha256 = source_table_sha256
        self._rotation_policy = rotation_policy
        self._start_utc = datetime.now(UTC).isoformat()
        self._start_mono = time.monotonic()
        self._bytes = 0
        self._valid = 0
        self._invalid = 0
        self._message_types: dict[str, int] = {}
        self._disconnects = 0
        self._reconnects = 0
        self._hasher = hashlib.sha256()
        (self.capture_dir / "source-table.txt").write_text(
            source_table_text, encoding="utf-8"
        )
        self._stream = open(self.capture_dir / "stream.rtcm3", "wb")  # noqa: SIM115
        self._index = open(  # noqa: SIM115
            self.capture_dir / "arrival-index.csv", "w", newline="", encoding="utf-8"
        )
        self._index_writer = csv.writer(self._index)
        self._index_writer.writerow(INDEX_HEADER)
        self._index.flush()

    @classmethod
    def create(
        cls,
        root: Path,
        *,
        provider: str,
        mountpoint: str,
        station_id: str,
        date: str | None = None,
        capture_id: str,
        caster_host: str,
        caster_port: int,
        tls_mode: str,
        authorization_provenance: str,
        software_commit: str,
        source_table_sha256: str,
        source_table_text: str,
        rotation_policy: CaptureRotationPolicy | None = None,
    ) -> CaptureWriter:
        capture_dir = (
            root
            / sanitize_identifier(provider)
            / sanitize_identifier(station_id)
            / (date or utc_today())
            / sanitize_identifier(capture_id)
        )
        return cls(
            capture_dir,
            capture_id=capture_id,
            provider=provider,
            caster_host=caster_host,
            caster_port=caster_port,
            mountpoint=mountpoint,
            station_mapping=station_id,
            tls_mode=tls_mode,
            authorization_provenance=authorization_provenance,
            software_commit=software_commit,
            source_table_sha256=source_table_sha256,
            source_table_text=source_table_text,
            rotation_policy=rotation_policy,
        )

    @property
    def bytes_received(self) -> int:
        return self._bytes

    @property
    def valid_frames(self) -> int:
        return self._valid

    @property
    def invalid_frames(self) -> int:
        return self._invalid

    def note_reconnect(self) -> None:
        self._disconnects += 1
        self._reconnects += 1

    def write_frame(self, raw: bytes, arrival: ArrivalRecord) -> None:
        """Append one frame's bytes plus its arrival-index row (flushed)."""
        if self._rotation_policy is not None:
            elapsed = time.monotonic() - self._start_mono
            if self._rotation_policy.requires_rotation(
                current_bytes=self._bytes,
                current_frames=self._valid + self._invalid,
                elapsed_seconds=elapsed,
                next_frame_bytes=len(raw),
            ):
                raise CaptureLimitExceeded("CAPTURE_ROTATION_REQUIRED")
            if not self._rotation_policy.disk_allowed(self.capture_dir):
                raise CaptureLimitExceeded("CAPTURE_BLOCKED_DISK_LIMIT")
        self._stream.write(raw)
        self._stream.flush()
        self._index_writer.writerow(
            [
                arrival.sequence,
                arrival.byte_offset,
                arrival.frame_length,
                arrival.arrival_utc,
                arrival.arrival_monotonic_ns,
                arrival.message_number if arrival.message_number is not None else "",
                arrival.crc_status,
                arrival.frame_sha256,
            ]
        )
        self._index.flush()
        self._hasher.update(raw)
        self._bytes += len(raw)
        if arrival.crc_status == "PASS":
            self._valid += 1
        else:
            self._invalid += 1
        if arrival.message_number is not None:
            key = str(arrival.message_number)
            self._message_types[key] = self._message_types.get(key, 0) + 1

    def close(self, status: str) -> CaptureMetadata:
        """Finalise: close files, write capture.json + SHA256SUMS, freeze."""
        if status not in ("COMPLETE", "PARTIAL", "FAILED"):
            raise ValueError(f"unknown capture status: {status}")
        self._stream.close()
        self._index.close()
        end_utc = datetime.now(UTC).isoformat()
        duration_s = time.monotonic() - self._start_mono
        metadata = CaptureMetadata(
            capture_id=self._capture_id,
            provider=self._provider,
            caster_host=self._caster_host,
            caster_port=self._caster_port,
            mountpoint=self._mountpoint,
            station_mapping=self._station_mapping,
            start_utc=self._start_utc,
            end_utc=end_utc,
            duration_s=duration_s,
            bytes_received=self._bytes,
            valid_frames=self._valid,
            invalid_frames=self._invalid,
            observed_message_types=tuple(sorted(self._message_types)),
            disconnects=self._disconnects,
            reconnects=self._reconnects,
            tls_mode=self._tls_mode,
            software_commit=self._software_commit,
            source_table_sha256=self._source_table_sha256,
            stream_sha256=self._hasher.hexdigest(),
            authorization_provenance=self._authorization_provenance,
            capture_status=status,
        )
        import json

        (self.capture_dir / "capture.json").write_text(
            json.dumps(metadata.as_dict(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        sums: list[str] = []
        for name in ("stream.rtcm3", "arrival-index.csv", "source-table.txt", "capture.json"):
            digest = hashlib.sha256((self.capture_dir / name).read_bytes()).hexdigest()
            sums.append(f"{digest}  {name}\n")
        (self.capture_dir / "SHA256SUMS.txt").write_text("".join(sums), encoding="utf-8")
        return metadata
