"""Versioned Phase 12 consumer artifact; no transport implementation."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class CorrectionStreamArtifact:
    schema_version: str
    stream_id: str
    decision_id: str
    mode: str
    station_id: str | None
    virtual_station_id: str | None
    message_families: tuple[str, ...]
    generation_status: str
    frame_source: str
    validity_start: str | None
    validity_end: str | None
    classification: str
    provenance_fingerprint: str

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["message_families"] = list(self.message_families)
        return payload
