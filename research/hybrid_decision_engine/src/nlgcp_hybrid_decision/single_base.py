"""Deterministic single-base ranking (Phase 8).

Ranking factors, in strict gate order:

1. QC eligibility (single_base_rtk ACCEPT; WARN/REJECT/BLOCKED excluded
   from automatic selection)
2. navigation availability
3. coordinate verification
4. temporal overlap presence
5. distance (nearest among survivors only)
6. data completeness / station health as recorded

Distance never overrides a failed scientific gate: the nearest station
with QC REJECT must not be selected over a farther QC ACCEPT station.
"""

from __future__ import annotations

from dataclasses import asdict
from dataclasses import dataclass as std_dataclass
from typing import Any

from nlgcp_hybrid_decision.discovery import DiscoveryResult
from nlgcp_hybrid_decision.models import QCStatus, StationCandidate
from nlgcp_hybrid_decision.policy import DecisionPolicy


@std_dataclass(frozen=True, slots=True)
class SingleBaseAssessment:
    """Single-base fallback evaluation outcome."""

    available: bool
    selected_reference: str | None = None
    distance_m: float | None = None
    distance_band: str = "unknown"
    ranked: tuple[str, ...] = ()
    rejected: tuple[dict[str, Any], ...] = ()
    blockers: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["ranked"] = list(self.ranked)
        payload["rejected"] = list(self.rejected)
        payload["blockers"] = list(self.blockers)
        payload["warnings"] = list(self.warnings)
        return payload


def assess_single_base(
    discovery: DiscoveryResult,
    *,
    policy: DecisionPolicy,
    single_qc: dict[str, QCStatus] | None = None,
) -> SingleBaseAssessment:
    """Rank physical-base candidates deterministically (fail-closed)."""
    blockers: list[str] = []
    warnings: list[str] = []
    rejected: list[dict[str, Any]] = []
    pool = [c for c in discovery.candidates]
    if discovery.target_station_id is not None:
        pool = [c for c in pool if c.station_id != discovery.target_station_id]

    survivors: list[StationCandidate] = []
    for candidate in sorted(pool, key=lambda c: c.station_id):
        if single_qc is not None:
            status = single_qc.get(candidate.station_id, candidate.qc_status)
        else:
            status = candidate.qc_status
        if status != QCStatus.ACCEPT:
            rejected.append({
                "station_id": candidate.station_id,
                "reason": f"SINGLE_BASE_QC_{status}",
            })
            continue
        if not candidate.navigation_available:
            rejected.append({
                "station_id": candidate.station_id,
                "reason": "SINGLE_BASE_NAVIGATION_MISSING",
            })
            continue
        if not candidate.coordinate_verified:
            rejected.append({
                "station_id": candidate.station_id,
                "reason": "UNVERIFIED_COORDINATE",
            })
            continue
        if candidate.common_interval is None:
            rejected.append({
                "station_id": candidate.station_id,
                "reason": "NO_COMMON_INTERVAL",
            })
            continue
        survivors.append(candidate)

    if not survivors:
        blockers.append("NO_ACCEPTABLE_SINGLE_BASE_CANDIDATE")
        return SingleBaseAssessment(
            available=False, blockers=tuple(blockers), warnings=tuple(warnings),
            rejected=tuple(rejected),
        )

    # Deterministic order: distance first (None sorts last), then station id.
    ordered = sorted(
        survivors,
        key=lambda c: (c.distance_m is None, c.distance_m or float("inf"), c.station_id),
    )
    ranked = tuple(c.station_id for c in ordered)
    selected = ordered[0]
    band = policy.distance.band(selected.distance_m)
    selected_km = (selected.distance_m or 0.0) / 1000.0
    if band == "unknown":
        warnings.append(f"{selected.station_id}: distance unknown; expectation ungraded")
    elif band == "degraded":
        warnings.append(
            f"{selected.station_id}: {selected_km:.1f} km "
            "exceeds preferred band (PROVISIONAL); FLOAT-only metre-level "
            "performance must be assumed, no centimetre claim"
        )
    elif band == "maximum":
        warnings.append(
            f"{selected.station_id}: {selected_km:.1f} km "
            "in maximum-allowed band (PROVISIONAL); degraded expectations apply"
        )
    elif band == "beyond_maximum":
        rejected.append({
            "station_id": selected.station_id,
            "reason": "SINGLE_BASE_TOO_DISTANT",
        })
        blockers.append(
            f"SINGLE_BASE_TOO_DISTANT:{selected.station_id}:"
            f"{(selected.distance_m or 0.0) / 1000.0:.1f}km"
        )
        return SingleBaseAssessment(
            available=False,
            ranked=ranked,
            rejected=tuple(rejected),
            blockers=tuple(blockers),
            warnings=tuple(warnings),
        )
    return SingleBaseAssessment(
        available=True,
        selected_reference=selected.station_id,
        distance_m=selected.distance_m,
        distance_band=band,
        ranked=ranked,
        rejected=tuple(rejected),
        blockers=tuple(blockers),
        warnings=tuple(warnings),
    )
