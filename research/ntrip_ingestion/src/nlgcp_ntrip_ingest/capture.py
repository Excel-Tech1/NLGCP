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
import re
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
