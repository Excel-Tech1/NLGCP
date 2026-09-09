"""Source admission: fail closed unless integrity passes (§6).

Verdict semantics (machine-readable):

- ACCEPT: every applicable check passed.
- WARN: admissible with recorded caveats (e.g. stray bytes resynced,
  CRC failures quarantined, approximate timing).
- REJECT: integrity failure — hash mismatch, no valid frames, unknown
  source type presented as RTCM, unlabelled synthetic data.
- BLOCKED: cannot evaluate — missing file, missing hash, unreadable
  input, oversized source beyond configured limits.

Unknown binary data is never silently processed as RTCM.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from nlgcp_rtcm_replay import PARSER_VERSION
from nlgcp_rtcm_replay.framing import MAX_RTCM_LENGTH, parse_stream
from nlgcp_rtcm_replay.inventory import build_inventory
from nlgcp_rtcm_replay.models import (
    KNOWN_STATIONS,
    SYNTHETIC_STATION_PREFIXES,
    AdmissionResult,
    AdmissionVerdict,
    RTCMSource,
    SourceType,
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def is_synthetic_station(station_id: str) -> bool:
    return station_id.startswith(SYNTHETIC_STATION_PREFIXES)


def source_fingerprint(source: RTCMSource, observed_sha256: str) -> str:
    material = "|".join(
        [
            PARSER_VERSION,
            source.source_id,
            str(source.source_type),
            source.station_id,
            source.mountpoint,
            str(source.byte_size),
            observed_sha256,
            source.capture_method,
            source.capture_provenance,
            source.rtcm_version,
        ]
    )
    return hashlib.sha256(material.encode()).hexdigest()


def admit_source(
    source: RTCMSource,
    *,
    known_stations: tuple[str, ...] = KNOWN_STATIONS,
    max_source_bytes: int = 512 * 1024 * 1024,
    max_frame_length: int = MAX_RTCM_LENGTH,
) -> AdmissionResult:
    """Admit or refuse a replay source, returning findings, not exceptions."""
    notes: list[str] = []  # informational (e.g. synthetic labelling)
    caveats: list[str] = []  # WARN-worthy conditions
    path = Path(source.source_path)
    if not path.is_file():
        return AdmissionResult(
            verdict=AdmissionVerdict.BLOCKED,
            findings=(f"BLOCKED source file missing: {source.source_path}",),
            source_fingerprint="",
        )
    if not source.sha256:
        return AdmissionResult(
            verdict=AdmissionVerdict.BLOCKED,
            findings=("BLOCKED no expected SHA-256 recorded for source",),
            source_fingerprint="",
        )
    observed = sha256_file(path)
    if observed != source.sha256:
        return AdmissionResult(
            verdict=AdmissionVerdict.REJECT,
            findings=(
                f"REJECT hash mismatch expected={source.sha256} observed={observed}",
            ),
            source_fingerprint=source_fingerprint(source, observed),
        )
    if source.source_type == SourceType.UNKNOWN:
        return AdmissionResult(
            verdict=AdmissionVerdict.REJECT,
            findings=("REJECT unknown source_type presented as RTCM",),
            source_fingerprint=source_fingerprint(source, observed),
        )
    if source.source_type == SourceType.SYNTHETIC_TEST_FIXTURE:
        if not is_synthetic_station(source.station_id):
            return AdmissionResult(
                verdict=AdmissionVerdict.REJECT,
                findings=(
                    "REJECT synthetic fixture must use a SYN/TEST station_id: "
                    f"{source.station_id}",
                ),
                source_fingerprint=source_fingerprint(source, observed),
            )
        notes.append("SYNTHETIC fixture labelled test-only, not field data")
    else:
        if not source.capture_provenance:
            return AdmissionResult(
                verdict=AdmissionVerdict.REJECT,
                findings=("REJECT non-synthetic source lacks capture provenance",),
                source_fingerprint=source_fingerprint(source, observed),
            )
        if not source.capture_method:
            caveats.append("WARN capture_method not recorded")
        if source.station_id not in known_stations:
            return AdmissionResult(
                verdict=AdmissionVerdict.REJECT,
                findings=(
                    f"REJECT unknown station/mountpoint: {source.station_id} "
                    f"{source.mountpoint}",
                ),
                source_fingerprint=source_fingerprint(source, observed),
            )
        if not source.verified:
            caveats.append("WARN source not marked verified")
    size = path.stat().st_size
    if size != source.byte_size:
        caveats.append(
            f"WARN byte_size metadata={source.byte_size} observed={size}"
        )
    if size > max_source_bytes:
        return AdmissionResult(
            verdict=AdmissionVerdict.BLOCKED,
            findings=(
                f"BLOCKED source size {size} exceeds limit {max_source_bytes}",
            ),
            source_fingerprint=source_fingerprint(source, observed),
        )
    raw = path.read_bytes()
    parsed = parse_stream(raw, max_frame_length=max_frame_length)
    inventory = build_inventory(parsed, parser_version=PARSER_VERSION)
    caveats.extend(inventory.findings)
    if inventory.frames_valid == 0:
        return AdmissionResult(
            verdict=AdmissionVerdict.REJECT,
            findings=tuple(
                ["REJECT no valid RTCM frames discovered", *notes, *caveats]
            ),
            source_fingerprint=source_fingerprint(source, observed),
            frames_discovered=len(parsed.frames),
            frames_valid=0,
        )
    verdict = AdmissionVerdict.WARN if caveats else AdmissionVerdict.ACCEPT
    if inventory.frames_invalid:
        verdict = AdmissionVerdict.WARN
        caveats.append(
            f"WARN {inventory.frames_invalid} invalid frame(s) quarantined, "
            "excluded from replay timeline"
        )
    return AdmissionResult(
        verdict=verdict,
        findings=tuple([*notes, *caveats]),
        source_fingerprint=source_fingerprint(source, observed),
        frames_discovered=len(parsed.frames),
        frames_valid=inventory.frames_valid,
    )
