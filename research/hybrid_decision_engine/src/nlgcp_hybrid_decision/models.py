"""Typed request/response models and upstream science contracts (Phase 8).

Conventions follow Phases 4/5/6: frozen dataclasses, JSON-serialisable
``as_dict()`` payloads, machine-readable enums, and fail-closed parsing
that never invents coordinates or silently upgrades a scientific gate.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any


class CorrectionMode(StrEnum):
    """Externally meaningful correction decision."""

    VRS = "VRS"
    SINGLE_BASE = "SINGLE_BASE"
    NO_CORRECTION = "NO_CORRECTION"


class DecisionStatus(StrEnum):
    """Operational qualifier for the chosen mode."""

    OK = "OK"
    DEGRADED = "DEGRADED"
    BLOCKED = "BLOCKED"
    DIAGNOSTIC_ONLY = "DIAGNOSTIC_ONLY"


class DesiredMode(StrEnum):
    """Rover-requested selection strategy."""

    AUTO = "AUTO"
    VRS_ONLY = "VRS_ONLY"
    SINGLE_BASE_ONLY = "SINGLE_BASE_ONLY"


class VRSStatus(StrEnum):
    """Stable contract for upstream Phase 7 VRS approval state."""

    APPROVED = "APPROVED"
    PROVISIONAL = "PROVISIONAL"
    NOT_VALIDATED = "NOT_VALIDATED"
    BLOCKED = "BLOCKED"
    UNAVAILABLE = "UNAVAILABLE"


class SpatialModelStatus(StrEnum):
    """Stable contract for upstream Phase 6 model validation state."""

    APPROVED = "APPROVED"
    PROVISIONAL = "PROVISIONAL"
    REJECTED = "REJECTED"
    BLOCKED = "BLOCKED"
    UNAVAILABLE = "UNAVAILABLE"


class IntegrityStatus(StrEnum):
    """Transparent integrity outcome (no pseudo-scientific scores)."""

    PASS = "PASS"
    DEGRADED = "DEGRADED"
    BLOCKED = "BLOCKED"


class NetworkGeometryStatus(StrEnum):
    """Network geometry adequacy outcome."""

    PASS = "PASS"
    INSUFFICIENT = "INSUFFICIENT"
    EXTRAPOLATION = "EXTRAPOLATION"
    UNASSESSED = "UNASSESSED"


class QCStatus(StrEnum):
    """Phase 4 QC admission outcome consumed by Phase 8."""

    ACCEPT = "ACCEPT"
    WARN = "WARN"
    REJECT = "REJECT"
    BLOCKED = "BLOCKED"
    MISSING = "MISSING"


class ReasonCode(StrEnum):
    """Stable machine-readable decision reason codes."""

    VRS_APPROVED = "VRS_APPROVED"
    VRS_MODEL_NOT_VALIDATED = "VRS_MODEL_NOT_VALIDATED"
    VRS_GEOMETRY_INSUFFICIENT = "VRS_GEOMETRY_INSUFFICIENT"
    VRS_UPSTREAM_REVIEW_PENDING = "VRS_UPSTREAM_REVIEW_PENDING"
    VRS_TARGET_LEAKAGE = "VRS_TARGET_LEAKAGE"
    VRS_PROVENANCE_INVALID = "VRS_PROVENANCE_INVALID"
    VRS_NOT_REQUESTED = "VRS_NOT_REQUESTED"
    VRS_MODE_NOT_PERMITTED = "VRS_MODE_NOT_PERMITTED"
    SINGLE_BASE_SELECTED = "SINGLE_BASE_SELECTED"
    SINGLE_BASE_TOO_DISTANT = "SINGLE_BASE_TOO_DISTANT"
    SINGLE_BASE_QC_REJECTED = "SINGLE_BASE_QC_REJECTED"
    SINGLE_BASE_NAVIGATION_MISSING = "SINGLE_BASE_NAVIGATION_MISSING"
    SINGLE_BASE_NOT_PERMITTED = "SINGLE_BASE_NOT_PERMITTED"
    SINGLE_BASE_FALLBACK_DISABLED = "SINGLE_BASE_FALLBACK_DISABLED"
    NO_ACCEPTABLE_CORRECTION_SOURCE = "NO_ACCEPTABLE_CORRECTION_SOURCE"
    NO_NAVIGATION_PRODUCT = "NO_NAVIGATION_PRODUCT"
    NO_QC_ADMITTED_STATIONS = "NO_QC_ADMITTED_STATIONS"
    INVALID_TARGET_COORDINATE = "INVALID_TARGET_COORDINATE"
    STALE_PROVENANCE = "STALE_PROVENANCE"
    DIAGNOSTIC_PREVIEW = "DIAGNOSTIC_PREVIEW"


BLOCKED_MESSAGE = "SCIENTIFIC DECISION BLOCKED - PHASE 8 ADMISSION REQUIREMENTS NOT MET"


class DecisionBlocked(RuntimeError):
    """Raised when a decision request would violate scientific requirements."""


@dataclass(frozen=True, slots=True)
class DecisionRequest:
    """Formal rover correction decision request."""

    request_id: str
    request_time: str
    target_latitude: float | None = None
    target_longitude: float | None = None
    target_height: float | None = None
    target_ecef: tuple[float, float, float] | None = None
    target_station_id: str | None = None
    requested_start_time: str = ""
    requested_end_time: str = ""
    desired_mode: DesiredMode = DesiredMode.AUTO
    allow_fallback: bool = True
    diagnostic: bool = False
    year: int = 2024
    day_of_year: int = 26
    receiver_capabilities: dict[str, Any] = field(default_factory=dict)
    constellations: tuple[str, ...] = ()
    supported_rtcm_messages: tuple[str, ...] = ()
    sampling_requirement_seconds: float | None = None
    maximum_acceptable_latency_seconds: float | None = None

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["desired_mode"] = str(self.desired_mode)
        payload["target_ecef"] = list(self.target_ecef) if self.target_ecef else None
        payload["constellations"] = list(self.constellations)
        payload["supported_rtcm_messages"] = list(self.supported_rtcm_messages)
        return payload

    def validate(self) -> list[str]:
        problems: list[str] = []
        if not self.request_id:
            problems.append("request_id must be non-empty")
        if not self.request_time:
            problems.append("request_time must be non-empty")
        if self.desired_mode not in (
            DesiredMode.AUTO,
            DesiredMode.VRS_ONLY,
            DesiredMode.SINGLE_BASE_ONLY,
        ):
            problems.append(f"unknown desired_mode: {self.desired_mode}")
        if not 1 <= self.day_of_year <= 366:
            problems.append(f"day_of_year out of range: {self.day_of_year}")
        if (
            self.target_ecef is None
            and self.target_station_id is None
            and (self.target_latitude is None or self.target_longitude is None)
        ):
            problems.append(
                "target coordinate required: supply target_ecef, "
                "target_station_id, or target_latitude/target_longitude"
            )
        if self.target_ecef is not None and len(self.target_ecef) != 3:
            problems.append("target_ecef must hold exactly 3 components")
        if self.target_latitude is not None and not -90.0 <= self.target_latitude <= 90.0:
            problems.append(f"target_latitude out of range: {self.target_latitude}")
        if self.target_longitude is not None and not -180.0 <= self.target_longitude <= 180.0:
            problems.append(f"target_longitude out of range: {self.target_longitude}")
        return problems

    def assert_valid(self) -> None:
        problems = self.validate()
        if problems:
            raise DecisionBlocked(f"{BLOCKED_MESSAGE}: {'; '.join(problems)}")


def request_from_dict(payload: dict[str, Any]) -> DecisionRequest:
    """Build a request from JSON, failing closed on malformed input."""
    try:
        desired = DesiredMode(str(payload.get("desired_mode", "AUTO")))
    except ValueError as exc:
        raise DecisionBlocked(f"{BLOCKED_MESSAGE}: unknown desired_mode: {exc}") from exc
    try:
        ecef_raw = payload.get("target_ecef")
        ecef: tuple[float, float, float] | None = None
        if ecef_raw is not None:
            ecef = (float(ecef_raw[0]), float(ecef_raw[1]), float(ecef_raw[2]))
        lat = payload.get("target_latitude")
        lon = payload.get("target_longitude")
        h = payload.get("target_height")
        return DecisionRequest(
            request_id=str(payload["request_id"]),
            request_time=str(payload["request_time"]),
            target_latitude=None if lat is None else float(lat),
            target_longitude=None if lon is None else float(lon),
            target_height=None if h is None else float(h),
            target_ecef=ecef,
            target_station_id=(
                None if payload.get("target_station_id") is None
                else str(payload["target_station_id"])
            ),
            requested_start_time=str(payload.get("requested_start_time", "")),
            requested_end_time=str(payload.get("requested_end_time", "")),
            desired_mode=desired,
            allow_fallback=bool(payload.get("allow_fallback", True)),
            diagnostic=bool(payload.get("diagnostic", False)),
            year=int(payload.get("year", 2024)),
            day_of_year=int(payload.get("day_of_year", 26)),
            receiver_capabilities=dict(payload.get("receiver_capabilities", {})),
            constellations=tuple(str(c) for c in payload.get("constellations", [])),
            supported_rtcm_messages=tuple(
                str(m) for m in payload.get("supported_rtcm_messages", [])
            ),
            sampling_requirement_seconds=(
                None
                if payload.get("sampling_requirement_seconds") is None
                else float(payload["sampling_requirement_seconds"])
            ),
            maximum_acceptable_latency_seconds=(
                None
                if payload.get("maximum_acceptable_latency_seconds") is None
                else float(payload["maximum_acceptable_latency_seconds"])
            ),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise DecisionBlocked(
            f"{BLOCKED_MESSAGE}: malformed decision request: {exc}"
        ) from exc


@dataclass(frozen=True, slots=True)
class SpatialCorrectionAssessment:
    """Stable Phase 6 contract consumed by Phase 8.

    Phase 8 never inspects which interpolator Phase 6 used internally;
    it consumes only the validated assessment outcome.
    """

    model_name: str
    validation_status: SpatialModelStatus
    validation_metric: float | None = None
    control_metric: float | None = None
    beats_zero_control: bool | None = None
    beats_nearest_control: bool | None = None
    sample_count: int | None = None
    geometry_status: str = "UNASSESSED"
    extrapolation: bool = False
    fingerprint: str = ""
    provenance: str = ""

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["validation_status"] = str(self.validation_status)
        return payload


@dataclass(frozen=True, slots=True)
class VRSCapabilityAssessment:
    """Stable Phase 7 contract consumed by Phase 8."""

    status: VRSStatus
    experiment_id: str = ""
    target: str = ""
    reference_stations: tuple[str, ...] = ()
    anchor: str = ""
    correction_mode: str = ""
    model_status: SpatialModelStatus = SpatialModelStatus.UNAVAILABLE
    observation_coverage: str = ""
    validation_status: str = ""
    target_leakage_status: str = ""
    fingerprint: str = ""
    provenance: str = ""

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["status"] = str(self.status)
        payload["model_status"] = str(self.model_status)
        payload["reference_stations"] = list(self.reference_stations)
        return payload


def spatial_assessment_from_dict(payload: dict[str, Any]) -> SpatialCorrectionAssessment:
    try:
        return SpatialCorrectionAssessment(
            model_name=str(payload.get("model_name", "")),
            validation_status=SpatialModelStatus(
                str(payload.get("validation_status", "UNAVAILABLE"))
            ),
            validation_metric=(
                None if payload.get("validation_metric") is None
                else float(payload["validation_metric"])
            ),
            control_metric=(
                None if payload.get("control_metric") is None
                else float(payload["control_metric"])
            ),
            beats_zero_control=payload.get("beats_zero_control"),
            beats_nearest_control=payload.get("beats_nearest_control"),
            sample_count=(
                None if payload.get("sample_count") is None else int(payload["sample_count"])
            ),
            geometry_status=str(payload.get("geometry_status", "UNASSESSED")),
            extrapolation=bool(payload.get("extrapolation", False)),
            fingerprint=str(payload.get("fingerprint", "")),
            provenance=str(payload.get("provenance", "")),
        )
    except (TypeError, ValueError) as exc:
        raise DecisionBlocked(
            f"{BLOCKED_MESSAGE}: malformed Phase 6 assessment: {exc}"
        ) from exc


def vrs_assessment_from_dict(payload: dict[str, Any]) -> VRSCapabilityAssessment:
    try:
        return VRSCapabilityAssessment(
            status=VRSStatus(str(payload.get("status", "UNAVAILABLE"))),
            experiment_id=str(payload.get("experiment_id", "")),
            target=str(payload.get("target", "")),
            reference_stations=tuple(str(s) for s in payload.get("reference_stations", [])),
            anchor=str(payload.get("anchor", "")),
            correction_mode=str(payload.get("correction_mode", "")),
            model_status=SpatialModelStatus(str(payload.get("model_status", "UNAVAILABLE"))),
            observation_coverage=str(payload.get("observation_coverage", "")),
            validation_status=str(payload.get("validation_status", "")),
            target_leakage_status=str(payload.get("target_leakage_status", "")),
            fingerprint=str(payload.get("fingerprint", "")),
            provenance=str(payload.get("provenance", "")),
        )
    except (TypeError, ValueError) as exc:
        raise DecisionBlocked(
            f"{BLOCKED_MESSAGE}: malformed Phase 7 assessment: {exc}"
        ) from exc


@dataclass(frozen=True, slots=True)
class StationCandidate:
    """One candidate physical reference station with eligibility evidence."""

    station_id: str
    distance_m: float | None
    qc_status: QCStatus
    navigation_available: bool
    navigation_sha256: str | None
    coordinate_verified: bool
    coordinate_frame: str | None
    coordinate_epoch: str | None
    observation_coverage: str | None
    common_interval: str | None
    equipment_metadata: dict[str, Any]
    phase4_fingerprint: str
    eligible: bool
    ineligibility_reasons: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["qc_status"] = str(self.qc_status)
        payload["ineligibility_reasons"] = list(self.ineligibility_reasons)
        return payload


@dataclass(frozen=True, slots=True)
class CorrectionDecision:
    """Machine-readable Phase 8 decision response."""

    decision_id: str
    request_id: str
    timestamp: str
    mode: CorrectionMode
    status: DecisionStatus
    reason_code: ReasonCode
    reason_text: str
    selected_reference: str | None = None
    selected_network: tuple[str, ...] = ()
    selected_vrs_experiment: str | None = None
    candidate_references: tuple[str, ...] = ()
    distance_to_selected_reference_m: float | None = None
    network_station_count: int = 0
    network_geometry_status: NetworkGeometryStatus = NetworkGeometryStatus.UNASSESSED
    qc_status: str = ""
    spatial_model_status: SpatialModelStatus = SpatialModelStatus.UNAVAILABLE
    vrs_status: VRSStatus = VRSStatus.UNAVAILABLE
    integrity_status: IntegrityStatus = IntegrityStatus.BLOCKED
    provenance: dict[str, Any] = field(default_factory=dict)
    fallback_used: bool = False
    warnings: tuple[str, ...] = ()
    blockers: tuple[str, ...] = ()
    decision_fingerprint: str = ""
    diagnostic: bool = False

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["mode"] = str(self.mode)
        payload["status"] = str(self.status)
        payload["reason_code"] = str(self.reason_code)
        payload["network_geometry_status"] = str(self.network_geometry_status)
        payload["spatial_model_status"] = str(self.spatial_model_status)
        payload["vrs_status"] = str(self.vrs_status)
        payload["integrity_status"] = str(self.integrity_status)
        payload["selected_network"] = list(self.selected_network)
        payload["candidate_references"] = list(self.candidate_references)
        payload["warnings"] = list(self.warnings)
        payload["blockers"] = list(self.blockers)
        return payload


@dataclass(frozen=True, slots=True)
class CorrectionDecisionPhase9:
    """Stable Phase 9 interface: what later replay/streaming may consume.

    Phase 9 must not need to understand Phase 8 internal gate logic.
    """

    mode: CorrectionMode
    source: str
    reference_station: str | None
    virtual_station: str | None
    correction_artifact: str | None
    status: DecisionStatus
    valid_from: str
    valid_until: str
    provenance: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["mode"] = str(self.mode)
        payload["status"] = str(self.status)
        return payload


def phase9_view(decision: CorrectionDecision, request: DecisionRequest) -> CorrectionDecisionPhase9:
    """Project a full decision onto the minimal Phase 9 handoff record."""
    if decision.mode == CorrectionMode.VRS:
        source = decision.selected_vrs_experiment or "VRS"
    elif decision.mode == CorrectionMode.SINGLE_BASE:
        source = decision.selected_reference or "SINGLE_BASE"
    else:
        source = "NO_CORRECTION"
    return CorrectionDecisionPhase9(
        mode=decision.mode,
        source=source,
        reference_station=decision.selected_reference,
        virtual_station=(
            decision.selected_vrs_experiment if decision.mode == CorrectionMode.VRS else None
        ),
        correction_artifact=None,
        status=decision.status,
        valid_from=request.requested_start_time,
        valid_until=request.requested_end_time,
        provenance=dict(decision.provenance),
    )
