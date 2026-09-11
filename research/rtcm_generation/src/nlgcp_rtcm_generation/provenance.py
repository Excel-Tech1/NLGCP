"""Deterministic, secret-free generation provenance."""

from __future__ import annotations

import hashlib
import json
from typing import Any


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def fingerprint(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def request_fingerprint(request: Any) -> str:
    return fingerprint(request.as_dict())


def build_provenance(
    request: Any, *, registry_version: str, encoder_version: str
) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "request_fingerprint": request_fingerprint(request),
        "decision_id": request.decision_id,
        "decision_fingerprint": request.decision_fingerprint,
        "input_source_fingerprint": request.input_source_fingerprint,
        "correction_model_fingerprint": request.correction_model_fingerprint,
        "registry_version": registry_version,
        "encoder_version": encoder_version,
        "classification": str(request.classification),
    }
