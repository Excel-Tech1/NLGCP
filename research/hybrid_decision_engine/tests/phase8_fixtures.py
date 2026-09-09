"""Synthetic fixtures for Phase 8 tests.

SYNTHETIC TEST DATA — NOT VALID FOR SCIENTIFIC RESULTS.
"""

from __future__ import annotations

from nlgcp_hybrid_decision.discovery import DiscoveryResult
from nlgcp_hybrid_decision.models import (
    DecisionRequest,
    DesiredMode,
    QCStatus,
    SpatialCorrectionAssessment,
    SpatialModelStatus,
    StationCandidate,
    VRSCapabilityAssessment,
    VRSStatus,
)
from nlgcp_hybrid_decision.policy import DEFAULT_POLICY, DecisionPolicy

TARGET_ECEF = (6308877.98392, 772269.10256, 530087.60603)


def make_candidate(
    station_id: str,
    *,
    distance_m: float | None = 105553.0,
    qc: QCStatus = QCStatus.ACCEPT,
    nav: bool = True,
    coord: bool = True,
    coverage: str | None = "2024-01-26T00:00:00Z/2024-01-27T00:00:00Z",
    fingerprint: str = "fp-",
) -> StationCandidate:
    reasons: list[str] = []
    if qc != QCStatus.ACCEPT:
        reasons.append(f"QC_{qc}")
    if not nav:
        reasons.append("NO_NAVIGATION_PRODUCT")
    if not coord:
        reasons.append("UNVERIFIED_COORDINATE")
    if coverage is None:
        reasons.append("NO_COVERAGE")
    return StationCandidate(
        station_id=station_id,
        distance_m=distance_m,
        qc_status=qc,
        navigation_available=nav,
        navigation_sha256="navsha" if nav else None,
        coordinate_verified=coord,
        coordinate_frame="IGS20" if coord else None,
        coordinate_epoch="2024-01-26T11:59:42Z" if coord else None,
        observation_coverage=coverage,
        common_interval=coverage,
        equipment_metadata={"receiver_type": "SYNTH"},
        phase4_fingerprint=f"{fingerprint}{station_id}",
        eligible=not reasons,
        ineligibility_reasons=tuple(reasons),
    )


def make_discovery(
    stations: list[StationCandidate] | None = None,
    *,
    target_ecef: tuple[float, float, float] | None = TARGET_ECEF,
    target_station_id: str | None = "PHRI00NGA",
) -> DiscoveryResult:
    return DiscoveryResult(
        target_ecef_m=target_ecef,
        target_station_id=target_station_id,
        target_resolved_from="synthetic",
        candidates=tuple(stations if stations is not None else [
            make_candidate("ABFC00NGA", distance_m=470870.0),
            make_candidate("EKAK00NGA", distance_m=105553.0),
            make_candidate("MGBO00NGA", distance_m=1029000.0),
        ]),
        verified_coordinates_fingerprint="synth-coords-fp",
        warnings=(),
    )


def make_compact_discovery(
    *,
    target_ecef: tuple[float, float, float] | None = TARGET_ECEF,
    target_station_id: str | None = "PHRI00NGA",
) -> DiscoveryResult:
    """Three nearby ACCEPT references: geometry PASS without extrapolation.

    SYNTHETIC compact geometry used to exercise the fully-approved VRS
    path, which the real sparse Nigerian network cannot satisfy.
    """
    return DiscoveryResult(
        target_ecef_m=target_ecef,
        target_station_id=target_station_id,
        target_resolved_from="synthetic-compact",
        candidates=tuple([
            make_candidate("REF_A00NGA", distance_m=20000.0),
            make_candidate("REF_B00NGA", distance_m=30000.0),
            make_candidate("REF_C00NGA", distance_m=40000.0),
        ]),
        verified_coordinates_fingerprint="synth-coords-fp",
        warnings=(),
    )


def make_request(
    *,
    desired: DesiredMode = DesiredMode.AUTO,
    allow_fallback: bool = True,
    diagnostic: bool = False,
    request_id: str = "req-synth-001",
) -> DecisionRequest:
    return DecisionRequest(
        request_id=request_id,
        request_time="2024-01-26T12:00:00Z",
        target_ecef=TARGET_ECEF,
        target_station_id="PHRI00NGA",
        desired_mode=desired,
        allow_fallback=allow_fallback,
        diagnostic=diagnostic,
        year=2024,
        day_of_year=26,
    )


def approved_spatial() -> SpatialCorrectionAssessment:
    return SpatialCorrectionAssessment(
        model_name="synth-idw",
        validation_status=SpatialModelStatus.APPROVED,
        validation_metric=1.0,
        control_metric=2.984,
        beats_zero_control=True,
        beats_nearest_control=True,
        sample_count=100,
        geometry_status="PASS",
        extrapolation=False,
        fingerprint="synth-spatial-fp",
        provenance="synthetic review board approval",
    )


def pre_review_spatial() -> SpatialCorrectionAssessment:
    return SpatialCorrectionAssessment(
        model_name="none-promoted",
        validation_status=SpatialModelStatus.UNAVAILABLE,
        validation_metric=None,
        control_metric=2.984,
        beats_zero_control=False,
        beats_nearest_control=False,
        sample_count=17768,
        geometry_status="UNASSESSED",
        extrapolation=False,
        fingerprint="phase6-pre-review-no-promoted-model",
        provenance="Phase 6/7 scientific review pending",
    )


def reviewed_spatial() -> SpatialCorrectionAssessment:
    """Reviewed Phase 6 geometry-v3: zero wins, no interpolator promoted.

    SYNTHETIC wrapper around observed values — NOT VALID FOR SCIENTIFIC
    RESULTS beyond the recorded reviewed evidence (zero 3.076 m,
    n=15948, all folds EXTRAPOLATION).
    """
    return SpatialCorrectionAssessment(
        model_name="zero",
        validation_status=SpatialModelStatus.REJECTED,
        validation_metric=3.076,
        control_metric=3.076,
        beats_zero_control=False,
        beats_nearest_control=True,
        sample_count=15948,
        geometry_status="EXTRAPOLATION",
        extrapolation=True,
        fingerprint="phase6-reviewed-geometry-v3-zero-3076-n15948",
        provenance=(
            "Reviewed Phase 6 atm-2024d026-phri-target-geometry-v3; "
            "best model zero RMSE 3.076 m (IDW 3.352 / nearest 3.757 / "
            "planar 14.373 m, n=15948); all folds EXTRAPOLATION; "
            "no spatial model promoted"
        ),
    )


def approved_vrs() -> VRSCapabilityAssessment:
    return VRSCapabilityAssessment(
        status=VRSStatus.APPROVED,
        experiment_id="synth-vrs-001",
        target="PHRI00NGA",
        reference_stations=("ABFC00NGA", "EKAK00NGA", "MGBO00NGA"),
        anchor="EKAK00NGA",
        correction_mode="SYNTHETIC",
        model_status=SpatialModelStatus.APPROVED,
        observation_coverage="complete",
        validation_status="APPROVED",
        target_leakage_status="PASS",
        fingerprint="synth-vrs-fp",
        provenance="synthetic review board approval",
    )


def pre_review_vrs() -> VRSCapabilityAssessment:
    return VRSCapabilityAssessment(
        status=VRSStatus.NOT_VALIDATED,
        experiment_id="",
        target="PHRI00NGA",
        reference_stations=("ABFC00NGA", "EKAK00NGA", "MGBO00NGA"),
        anchor="",
        correction_mode="ZERO / VRS_GEOMETRY_ONLY",
        model_status=SpatialModelStatus.UNAVAILABLE,
        observation_coverage="",
        validation_status="NOT_VALIDATED",
        target_leakage_status="",
        fingerprint="phase7-pre-review-not-validated",
        provenance="Phase 6/7 scientific review pending",
    )


def reviewed_vrs() -> VRSCapabilityAssessment:
    """Reviewed Phase 7 geometry-v3: synthesis reviewed, operational blocked.

    SYNTHETIC wrapper around observed reviewed values — NOT VALID FOR
    SCIENTIFIC RESULTS beyond the recorded evidence.  Review verdict
    APPROVED_WITH_PROVISIONAL_LIMITATIONS lives in validation_status;
    operational status stays BLOCKED (geometry-only diagnostic only).
    """
    return VRSCapabilityAssessment(
        status=VRSStatus.BLOCKED,
        experiment_id="vrs-2024d026-phri-geometry-v3",
        target="PHRI00NGA",
        reference_stations=("ABFC00NGA", "EKAK00NGA", "MGBO00NGA"),
        anchor="EKAK00NGA",
        correction_mode="ZERO / VRS_GEOMETRY_ONLY",
        model_status=SpatialModelStatus.REJECTED,
        observation_coverage="480/480 epochs; 30 GPS sats",
        validation_status="APPROVED_WITH_PROVISIONAL_LIMITATIONS",
        target_leakage_status="PASS",
        fingerprint="phase7-reviewed-geometry-v3-phri-24556",
        provenance=(
            "Reviewed Phase 7 vrs-2024d026-phri-geometry-v3; synthesis "
            "reviewed APPROVED_WITH_PROVISIONAL_LIMITATIONS; mode "
            "ZERO / VRS_GEOMETRY_ONLY; promoted model NONE; operational "
            "corrected VRS NOT APPROVED; leakage PASS"
        ),
    )


def policy() -> DecisionPolicy:
    return DEFAULT_POLICY
