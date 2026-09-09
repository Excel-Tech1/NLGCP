"""Phase 8 decision integration (§16-§18).

Phase 9 consumes the ``CorrectionDecisionPhase9`` handoff and never
recalculates scientific decisions.  It requires a compatible replay
source for the selected station/mountpoint and fails closed otherwise:

- SINGLE_BASE → compatible source for the selected reference required,
  else REPLAY = BLOCKED (SELECTED_CORRECTION_SOURCE_UNAVAILABLE).  No
  silent substitution of another station.
- NO_CORRECTION → emit no correction stream (admissible empty run).
- VRS → compatible approved VRS correction artifact required; none
  exists on the current line (operational VRS BLOCKED), so fail closed.

A replayed transport stream is not proof of correction accuracy:
``transport success ≠ positioning success`` is preserved in every
outcome record.
"""

from __future__ import annotations

from dataclasses import dataclass

from nlgcp_rtcm_replay.models import (
    SELECTED_CORRECTION_SOURCE_UNAVAILABLE,
    RTCMSource,
)


@dataclass(frozen=True, slots=True)
class HandoffDecision:
    """Minimal parsed Phase 8 handoff (mode/source/reference/status)."""

    mode: str
    source: str
    reference_station: str | None
    virtual_station: str | None
    status: str
    decision_fingerprint: str


@dataclass(frozen=True, slots=True)
class HandoffOutcome:
    admitted: bool
    reason: str
    selected_source_id: str | None


def handoff_from_dict(payload: dict[str, object]) -> HandoffDecision:
    try:
        provenance = payload.get("provenance")
        fingerprint = ""
        if isinstance(provenance, dict):
            fingerprint = str(
                provenance.get("decision_fingerprint", "")
            ) or str(provenance.get("phase8_decision_fingerprint", ""))
        return HandoffDecision(
            mode=str(payload["mode"]),
            source=str(payload.get("source", "")),
            reference_station=(
                None
                if payload.get("reference_station") is None
                else str(payload["reference_station"])
            ),
            virtual_station=(
                None
                if payload.get("virtual_station") is None
                else str(payload["virtual_station"])
            ),
            status=str(payload.get("status", "")),
            decision_fingerprint=fingerprint,
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"malformed Phase 8 handoff: {exc}") from exc


def resolve_handoff(
    decision: HandoffDecision,
    candidates: list[RTCMSource],
) -> HandoffOutcome:
    """Bind a Phase 8 decision to a compatible replay source, fail closed."""
    if decision.mode == "NO_CORRECTION":
        return HandoffOutcome(
            admitted=True,
            reason="NO_CORRECTION: no correction stream emitted; "
            "transport success != positioning success",
            selected_source_id=None,
        )
    if decision.mode == "VRS":
        wanted = decision.virtual_station or decision.source
        match = next(
            (
                c
                for c in candidates
                if c.source_id == wanted or c.station_id == (decision.virtual_station or "")
            ),
            None,
        )
        if match is None:
            return HandoffOutcome(
                admitted=False,
                reason=(
                    "VRS_CORRECTION_ARTIFACT_UNAVAILABLE: operational VRS "
                    "remains BLOCKED; no approved VRS correction artifact exists"
                ),
                selected_source_id=None,
            )
        return HandoffOutcome(
            admitted=True,
            reason="VRS artifact bound; transport success != positioning success",
            selected_source_id=match.source_id,
        )
    if decision.mode == "SINGLE_BASE":
        wanted = decision.reference_station or decision.source
        match = next(
            (c for c in candidates if c.station_id == wanted or c.source_id == wanted),
            None,
        )
        if match is None:
            return HandoffOutcome(
                admitted=False,
                reason=(
                    f"{SELECTED_CORRECTION_SOURCE_UNAVAILABLE}: Phase 8 selected "
                    f"{wanted} but no compatible replay source exists; "
                    "no silent substitution performed"
                ),
                selected_source_id=None,
            )
        return HandoffOutcome(
            admitted=True,
            reason="SINGLE_BASE source bound; transport success != positioning success",
            selected_source_id=match.source_id,
        )
    return HandoffOutcome(
        admitted=False,
        reason=f"UNKNOWN_DECISION_MODE: {decision.mode}",
        selected_source_id=None,
    )
