"""Profile-specific, explicit QC findings and admission decisions."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from nlgcp_gnss_qc.dataset import CoordinateEligibility, NavigationProduct
from nlgcp_gnss_qc.models import Finding, FindingSeverity, RinexAnalysis, SessionInput
from nlgcp_gnss_qc.profiles import QCProfile
from nlgcp_gnss_qc.rinex import phase_frequencies


def classify_session(
    session: SessionInput,
    analysis: RinexAnalysis,
    profile: QCProfile,
    *,
    identity_status: str,
    source_path: Path,
    observed_sha256: str,
    navigation: NavigationProduct | None,
    coordinate: CoordinateEligibility | None,
) -> list[Finding]:
    """Build findings; the overall result is derived separately from severities."""

    findings: list[Finding] = []

    def add(
        code: str,
        severity: FindingSeverity,
        category: str,
        message: str,
        *,
        measured: Any = None,
        expected: Any = None,
        threshold: Any = None,
        evidence: dict[str, Any] | None = None,
    ) -> None:
        findings.append(
            Finding(
                finding_code=code,
                severity=severity,
                category=category,
                station_id=session.station_id,
                year=session.year,
                day_of_year=session.day_of_year,
                file=session.relative_path,
                message=message,
                measured_value=measured,
                expected_value=expected,
                threshold=threshold,
                evidence=evidence or {},
            )
        )

    add("FILE_PRESENT", FindingSeverity.PASS, "file_integrity", "Canonical input exists")
    if observed_sha256 == session.sha256:
        add(
            "HASH_VERIFIED",
            FindingSeverity.PASS,
            "file_integrity",
            "Observed SHA-256 matches the canonical manifest",
            measured=observed_sha256,
            expected=session.sha256,
        )
    else:
        add(
            "HASH_MISMATCH",
            FindingSeverity.REJECT,
            "file_integrity",
            "Observed SHA-256 does not match the canonical manifest",
            measured=observed_sha256,
            expected=session.sha256,
        )
    if session.exact_duplicate_sources:
        add(
            "EXACT_DUPLICATE",
            FindingSeverity.WARN,
            "file_integrity",
            "An exact source-delivery duplicate was excluded from canonical use",
            measured=list(session.exact_duplicate_sources),
            evidence={"canonical_retained": session.relative_path},
        )
    if identity_status == "CANONICAL_MATCH":
        add(
            "CANONICAL_MATCH",
            FindingSeverity.PASS,
            "station_identity",
            "Folder, filename, header, and canonical station identity agree",
        )
    else:
        add(
            "KNOWN_ALIAS",
            FindingSeverity.WARN,
            "station_identity",
            "Filename/header marker is an explicitly registered station alias",
            measured=analysis.header.marker_name,
            expected=session.station_id,
        )

    _temporal_findings(add, analysis, profile)
    frequencies = phase_frequencies(analysis.header.observation_types)
    if len(frequencies) >= 2:
        add(
            "DUAL_FREQUENCY_AVAILABLE",
            FindingSeverity.PASS,
            "observation_types",
            "Header states carrier-phase observations on at least two frequencies",
            measured=list(frequencies),
        )
    elif profile.require_dual_frequency_phase:
        add(
            "REQUIRED_PHASE_OBSERVABLE_MISSING",
            FindingSeverity.REJECT,
            "observation_types",
            "Profile requires carrier-phase observations on two frequencies",
            measured=list(frequencies),
            expected="at least two distinct L* frequency designators",
        )
    if len(analysis.constellation_statistics) > 1:
        add(
            "MIXED_GNSS_AVAILABLE",
            FindingSeverity.PASS,
            "constellations",
            "More than one constellation is present",
            measured=sorted(analysis.constellation_statistics),
        )
    if analysis.potential_cycle_slip_indicators:
        add(
            "POTENTIAL_CYCLE_SLIP_INDICATORS",
            FindingSeverity.PASS,
            "continuity",
            "Non-zero carrier-phase loss-of-lock indicators were observed; "
            "they are measured but do not affect admission because no calibrated "
            "threshold exists",
            measured=analysis.potential_cycle_slip_indicators,
            threshold="not calibrated",
        )
    for warning in analysis.parser_warnings:
        add("PARSER_WARNING", FindingSeverity.WARN, "rinex_structure", warning)

    if profile.require_navigation:
        if navigation is None:
            add(
                "NAVIGATION_PRODUCT_MISSING",
                FindingSeverity.BLOCKED,
                "external_products",
                "Profile requires broadcast navigation but no compatible product is catalogued",
            )
        else:
            add(
                "NAVIGATION_PRODUCT_AVAILABLE",
                FindingSeverity.PASS,
                "external_products",
                "A temporally compatible broadcast-navigation product is catalogued",
                measured=navigation.relative_path,
                evidence={"sha256": navigation.sha256},
            )
            if navigation.acquisition_provenance is None:
                add(
                    "NAVIGATION_PROVENANCE_MISSING",
                    FindingSeverity.WARN,
                    "external_products",
                    "Product bytes are hashed but acquisition provenance was not available",
                    measured=navigation.relative_path,
                )

    if profile.require_verified_coordinates:
        if coordinate is None:
            add(
                "COORDINATE_METADATA_MISSING",
                FindingSeverity.BLOCKED,
                "coordinate_eligibility",
                "No verified coordinate record is available for this station",
            )
        elif not coordinate.scientifically_valid:
            add(
                "COORDINATE_NOT_SCIENTIFICALLY_VALID",
                FindingSeverity.BLOCKED,
                "coordinate_eligibility",
                "Coordinate admission record explicitly marks this station ineligible",
                evidence={"source": coordinate.source_path, "sha256": coordinate.source_sha256},
            )
        elif not _coordinate_applies_to_day(coordinate, session):
            add(
                "COORDINATE_INTERVAL_UNVERIFIED",
                FindingSeverity.BLOCKED,
                "coordinate_eligibility",
                "Verified coordinate epoch does not establish an effective interval "
                "for this station-day",
                measured=coordinate.coordinate_epoch,
                expected=f"effective-dated coverage of {session.year}-{session.day_of_year:03d}",
            )
        else:
            add(
                "COORDINATE_ELIGIBLE",
                FindingSeverity.PASS,
                "coordinate_eligibility",
                "A scientifically admitted coordinate and reference frame apply to this date",
                measured={
                    "reference_frame": coordinate.reference_frame,
                    "coordinate_epoch": coordinate.coordinate_epoch,
                },
                evidence={"source": coordinate.source_path, "sha256": coordinate.source_sha256},
            )
    add(
        "SOURCE_SIZE_VERIFIED",
        FindingSeverity.PASS
        if source_path.stat().st_size == session.size_bytes
        else FindingSeverity.REJECT,
        "file_integrity",
        "Observed byte size compared with canonical manifest",
        measured=source_path.stat().st_size,
        expected=session.size_bytes,
    )
    return findings


def _temporal_findings(add: Any, analysis: RinexAnalysis, profile: QCProfile) -> None:
    fraction = (analysis.availability_percent or 0.0) / 100.0
    if analysis.duplicate_epochs or analysis.backward_epochs:
        add(
            "MALFORMED_EPOCH_SEQUENCE",
            FindingSeverity.REJECT,
            "sampling",
            "Duplicate or backward epochs make the sequence scientifically unsafe",
            measured={
                "duplicate_epochs": analysis.duplicate_epochs,
                "backward_epochs": analysis.backward_epochs,
            },
        )
    if (
        profile.expected_interval_seconds is not None
        and analysis.empirical_interval_seconds is not None
        and abs(analysis.empirical_interval_seconds - profile.expected_interval_seconds)
        > profile.sampling_tolerance_seconds
    ):
        add(
            "UNEXPECTED_SAMPLING_INTERVAL",
            FindingSeverity.REJECT,
            "sampling",
            "Empirical interval is outside the profile tolerance",
            measured=analysis.empirical_interval_seconds,
            expected=profile.expected_interval_seconds,
            threshold=profile.sampling_tolerance_seconds,
        )
    else:
        add(
            "SAMPLING_INTERVAL_VERIFIED",
            FindingSeverity.PASS,
            "sampling",
            "Empirical sampling interval is usable for this profile",
            measured=analysis.empirical_interval_seconds,
            expected=profile.expected_interval_seconds,
        )
    if fraction < profile.reject_below_completeness_fraction:
        add(
            "SEVERE_SESSION_TRUNCATION",
            FindingSeverity.REJECT,
            "temporal",
            "Session completeness is below the profile's provisional usable floor",
            measured=fraction,
            expected=profile.accept_completeness_fraction,
            threshold=profile.reject_below_completeness_fraction,
        )
    elif fraction < profile.accept_completeness_fraction and profile.warn_on_partial_session:
        add(
            "PARTIAL_SESSION",
            FindingSeverity.WARN,
            "temporal",
            "Session is usable with awareness but is not nominally complete",
            measured=fraction,
            expected=profile.accept_completeness_fraction,
        )
    else:
        add(
            "FULL_SESSION",
            FindingSeverity.PASS,
            "temporal",
            "Session meets the profile completeness criterion",
            measured=fraction,
            expected=profile.accept_completeness_fraction,
        )
    if (
        analysis.largest_gap_seconds is not None
        and analysis.largest_gap_seconds > profile.maximum_warn_gap_seconds
    ):
        add(
            "MAJOR_OBSERVATION_GAP",
            FindingSeverity.REJECT,
            "gaps",
            "Largest internal gap exceeds the profile's provisional tolerance",
            measured=analysis.largest_gap_seconds,
            threshold=profile.maximum_warn_gap_seconds,
        )
    elif analysis.gap_count:
        add(
            "OBSERVATION_GAPS",
            FindingSeverity.WARN,
            "gaps",
            "Internal observation gaps are present",
            measured={
                "gap_count": analysis.gap_count,
                "largest_gap_seconds": analysis.largest_gap_seconds,
            },
        )


def _coordinate_applies_to_day(coordinate: CoordinateEligibility, session: SessionInput) -> bool:
    if not coordinate.coordinate_epoch:
        return False
    epoch = datetime.fromisoformat(coordinate.coordinate_epoch.replace("Z", "+00:00"))
    return epoch.year == session.year and int(epoch.strftime("%j")) == session.day_of_year
