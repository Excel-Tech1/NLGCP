"""Domain contracts for correction generation.

The models keep GNSS time, transport time, scientific admission and binary
serialization metadata separate.  A non-empty field is not treated as proof
that the corresponding scientific input is valid; the explicit verification
flags are required by the admission gate.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any


class GenerationMode(StrEnum):
    SINGLE_BASE = "SINGLE_BASE"
    VRS = "VRS"
    NO_CORRECTION = "NO_CORRECTION"


class GenerationStatus(StrEnum):
    ACCEPTED = "ACCEPTED"
    BLOCKED = "BLOCKED"
    NO_CORRECTION = "NO_CORRECTION"
    ENCODED = "ENCODED"


class OutputClassification(StrEnum):
    SYNTHETIC_TEST_ONLY = "SYNTHETIC_TEST_ONLY"
    DIAGNOSTIC_ONLY = "DIAGNOSTIC_ONLY"
    RESEARCH_VALIDATION = "RESEARCH_VALIDATION"
    OPERATIONAL_APPROVED = "OPERATIONAL_APPROVED"


class ReasonCode(StrEnum):
    NO_CORRECTION_REQUESTED = "NO_CORRECTION_REQUESTED"
    INPUT_SOURCE_UNAVAILABLE = "INPUT_SOURCE_UNAVAILABLE"
    AUTHENTIC_INPUT_SOURCE_UNAVAILABLE = "AUTHENTIC_INPUT_SOURCE_UNAVAILABLE"
    INPUT_SOURCE_UNVERIFIED = "INPUT_SOURCE_UNVERIFIED"
    STATION_IDENTITY_UNVERIFIED = "STATION_IDENTITY_UNVERIFIED"
    COORDINATE_UNVERIFIED = "COORDINATE_UNVERIFIED"
    GNSS_EPOCH_UNAVAILABLE = "GNSS_EPOCH_UNAVAILABLE"
    CORRECTION_MODEL_NOT_APPROVED = "CORRECTION_MODEL_NOT_APPROVED"
    VRS_OPERATIONAL_NOT_APPROVED = "VRS_OPERATIONAL_NOT_APPROVED"
    ENCODER_NOT_VALIDATED = "ENCODER_NOT_VALIDATED"
    UNSUPPORTED_MESSAGE_TYPE = "UNSUPPORTED_MESSAGE_TYPE"
    OUT_OF_RANGE_FIELD = "OUT_OF_RANGE_FIELD"
    MISSING_REQUIRED_FIELD = "MISSING_REQUIRED_FIELD"
    PROVENANCE_INCOMPLETE = "PROVENANCE_INCOMPLETE"
    DECISION_NOT_ADMISSIBLE = "DECISION_NOT_ADMISSIBLE"
    OPERATIONAL_CLASSIFICATION_FORBIDDEN = "OPERATIONAL_CLASSIFICATION_FORBIDDEN"


class VerificationState(StrEnum):
    VERIFIED = "VERIFIED"
    SYNTHETIC_TEST_ONLY = "SYNTHETIC_TEST_ONLY"
    UNVERIFIED = "UNVERIFIED"


class AdmissionBlocked(RuntimeError):
    """Raised only by strict helpers; normal generation returns a result."""


def _finite(value: float) -> bool:
    return math.isfinite(value)


@dataclass(frozen=True, slots=True)
class CoordinateProvenance:
    station_id: str
    ecef_xyz_m: tuple[float, float, float]
    reference_frame: str
    coordinate_epoch: str
    source: str
    fingerprint: str
    verification_state: VerificationState

    def validate(self) -> list[str]:
        problems: list[str] = []
        if not self.station_id:
            problems.append("station_id is required")
        if len(self.ecef_xyz_m) != 3 or not all(_finite(v) for v in self.ecef_xyz_m):
            problems.append("ecef_xyz_m must contain three finite values")
        if not self.reference_frame:
            problems.append("reference_frame is required")
        if not self.coordinate_epoch:
            problems.append("coordinate_epoch is required")
        if not self.source or not self.fingerprint:
            problems.append("coordinate source and fingerprint are required")
        return problems

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["verification_state"] = str(self.verification_state)
        payload["ecef_xyz_m"] = list(self.ecef_xyz_m)
        return payload


@dataclass(frozen=True, slots=True)
class EpochContract:
    """Distinct transport and GNSS time concepts."""

    gnss_epoch: str | None
    source_arrival_time: str | None = None
    generation_time: str | None = None
    transmission_time: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class CorrectionGenerationRequest:
    request_id: str
    decision_id: str
    decision_fingerprint: str
    decision_status: str
    mode: GenerationMode
    reference_station_id: str | None
    virtual_station_id: str | None
    coordinate: CoordinateProvenance | None
    epoch: EpochContract
    gnss_systems: tuple[str, ...]
    input_source_fingerprint: str
    input_source_admitted: bool
    station_identity_verified: bool
    coordinate_verified: bool
    correction_model_fingerprint: str | None
    correction_model_approved: bool
    output_message_family: str
    encoder_version: str
    scientific_status: str
    classification: OutputClassification
    synthetic_fixture: bool = False

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["mode"] = str(self.mode)
        payload["classification"] = str(self.classification)
        payload["gnss_systems"] = list(self.gnss_systems)
        payload["coordinate"] = self.coordinate.as_dict() if self.coordinate else None
        payload["epoch"] = self.epoch.as_dict()
        return payload


@dataclass(frozen=True, slots=True)
class CorrectionGenerationContext:
    request: CorrectionGenerationRequest
    fields: dict[str, Any] = field(default_factory=dict)
    observations: tuple[dict[str, Any], ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "request": self.request.as_dict(),
            "fields": dict(self.fields),
            "observations": [dict(row) for row in self.observations],
        }


@dataclass(frozen=True, slots=True)
class GeneratedCorrectionFrame:
    message_family: str
    message_number: int
    payload_length: int
    frame_length: int
    crc_hex: str
    frame_sha256: str
    raw_bytes: bytes
    request_fingerprint: str
    encoder_version: str
    input_status: str
    classification: OutputClassification
    scientific_status: str

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["raw_bytes"] = self.raw_bytes.hex()
        payload["classification"] = str(self.classification)
        return payload


@dataclass(frozen=True, slots=True)
class CorrectionGenerationResult:
    request_id: str
    decision_id: str
    status: GenerationStatus
    reason_codes: tuple[ReasonCode, ...]
    frames: tuple[GeneratedCorrectionFrame, ...]
    classification: OutputClassification
    provenance: dict[str, Any]
    mode: GenerationMode = GenerationMode.NO_CORRECTION
    reference_station_id: str | None = None
    virtual_station_id: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "decision_id": self.decision_id,
            "status": str(self.status),
            "reason_codes": [str(code) for code in self.reason_codes],
            "frames": [frame.as_dict() for frame in self.frames],
            "classification": str(self.classification),
            "provenance": dict(self.provenance),
            "mode": str(self.mode),
            "reference_station_id": self.reference_station_id,
            "virtual_station_id": self.virtual_station_id,
        }
