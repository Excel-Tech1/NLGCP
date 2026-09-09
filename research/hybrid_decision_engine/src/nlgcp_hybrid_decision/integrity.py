"""Integrity status derivation (Phase 8).

A transparent PASS / DEGRADED / BLOCKED status is preferred over any
pseudo-scientific numeric score.  No 0-100 score is implemented.
"""

from __future__ import annotations

from nlgcp_hybrid_decision.models import (
    CorrectionMode,
    DecisionStatus,
    IntegrityStatus,
)


def derive_integrity(
    *,
    mode: CorrectionMode,
    status: DecisionStatus,
    warnings: tuple[str, ...],
    blockers: tuple[str, ...],
    fallback_used: bool,
    distance_band: str = "unknown",
) -> IntegrityStatus:
    """Derive integrity from explicit decision evidence."""
    _ = fallback_used
    _ = distance_band
    if mode == "NO_CORRECTION" or status == "BLOCKED" or blockers:
        if mode == "NO_CORRECTION" and status == "DIAGNOSTIC_ONLY":
            return IntegrityStatus.BLOCKED
        if blockers:
            return IntegrityStatus.BLOCKED
    if status in ("DEGRADED", "DIAGNOSTIC_ONLY") or warnings:
        return IntegrityStatus.DEGRADED
    if mode == "SINGLE_BASE" and status == "OK" and not warnings:
        return IntegrityStatus.PASS
    if mode == "VRS" and status == "OK":
        return IntegrityStatus.PASS
    if mode == "NO_CORRECTION":
        return IntegrityStatus.BLOCKED
    return IntegrityStatus.DEGRADED
