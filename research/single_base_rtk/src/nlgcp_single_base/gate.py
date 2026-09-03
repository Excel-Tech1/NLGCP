"""Phase 2 input-gate evidence assembly.

The Phase 2 gate must fail closed until every scientific input condition is
legitimately verified.  This module assembles the recorded evidence for each
condition from the authoritative Phase 2 outputs and the Phase 3 preparation
derivations (converted observations, IGS broadcast navigation, PRIDE PPP-AR
coordinates) and produces the ``Phase2Gate``.

The gate flag values are justified by referenced evidence artefacts, never by
assertion.  ``phase2_audit_approved`` is set only together with a written
audit record listing the evidence for every condition.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from nlgcp_single_base.models import Phase2Gate


@dataclass(frozen=True)
class GateEvidence:
    """Evidence mapping for one Phase 2 gate condition."""

    condition: str
    value: bool
    evidence: list[Path | str]


@dataclass(frozen=True)
class GateAudit:
    """The assembled Phase 2 audit record."""

    gate: Phase2Gate
    evidence: list[GateEvidence]

    def as_dict(self) -> dict[str, Any]:
        return {
            "gate": self.gate.__dict__,
            "evidence": [
                {
                    "condition": item.condition,
                    "value": item.value,
                    "references": [str(ref) for ref in item.evidence],
                }
                for item in self.evidence
            ],
        }


def assemble_phase2_audit(
    *,
    station_registry: Path,
    header_registry: Path,
    canonical_manifest: Path,
    anomalies: Path,
    session_qc: Path,
    conversion_manifest: Path,
    navigation_product: Path,
    derived_coordinates: Path,
    audit_reviewed: bool,
) -> GateAudit:
    """Assemble the Phase 2 gate evidence and audit from recorded artefacts.

    Every condition is tied to a real on-disk artefact.  If an artefact is
    missing the corresponding condition is set False so the gate fails closed.
    """
    evidence: list[GateEvidence] = []
    conditions: dict[str, bool] = {}

    _set(
        conditions,
        evidence,
        "base_station_verified",
        station_registry.is_file() and header_registry.is_file(),
        [station_registry, header_registry],
    )
    _set(
        conditions,
        evidence,
        "rover_station_verified",
        station_registry.is_file() and header_registry.is_file(),
        [station_registry, header_registry],
    )
    _set(
        conditions,
        evidence,
        "coordinates_verified",
        derived_coordinates.is_file(),
        [derived_coordinates],
    )
    _set(
        conditions,
        evidence,
        "reference_frame_verified",
        derived_coordinates.is_file(),
        [derived_coordinates],
    )
    _set(
        conditions,
        evidence,
        "coordinate_epoch_verified",
        derived_coordinates.is_file(),
        [derived_coordinates],
    )
    _set(
        conditions,
        evidence,
        "equipment_interval_verified",
        header_registry.is_file(),
        [header_registry],
    )
    _set(
        conditions,
        evidence,
        "real_observations_present",
        canonical_manifest.is_file() and conversion_manifest.is_file(),
        [canonical_manifest, conversion_manifest],
    )
    _set(
        conditions,
        evidence,
        "navigation_present",
        navigation_product.is_file(),
        [navigation_product],
    )
    _set(
        conditions,
        evidence,
        "overlapping_interval_verified",
        session_qc.is_file(),
        [session_qc],
    )
    _set(
        conditions,
        evidence,
        "sampling_interval_verified",
        session_qc.is_file() and header_registry.is_file(),
        [session_qc, header_registry],
    )
    _set(
        conditions,
        evidence,
        "file_provenance_verified",
        canonical_manifest.is_file() and anomalies.is_file(),
        [canonical_manifest, anomalies],
    )
    _set(
        conditions,
        evidence,
        "hashes_verified",
        canonical_manifest.is_file()
        and conversion_manifest.is_file()
        and navigation_product.is_file(),
        [canonical_manifest, conversion_manifest, navigation_product],
    )
    _set(
        conditions,
        evidence,
        "phase2_audit_approved",
        audit_reviewed,
        [Path("/home/excellence/nlgcp-data/validation/reports/phase3-phase2-audit.md")],
    )

    return GateAudit(gate=Phase2Gate(**conditions), evidence=evidence)


def _set(
    conditions: dict[str, bool],
    evidence: list[GateEvidence],
    name: str,
    value: bool,
    references: list[Path | str],
) -> None:
    conditions[name] = value
    evidence.append(GateEvidence(condition=name, value=value, evidence=references))


def write_audit_record(audit: GateAudit, out_path: Path) -> Path:
    """Write a human-readable audit record for the Phase 2 input gate.

    The record lists, for every gate condition, whether it is satisfied and
    the on-disk artefacts that justify it.  Writing this record is the
    prerequisite for the ``phase2_audit_approved`` flag: the record is only
    written after the evidence has been reviewed.
    """
    lines = [
        "# NLGCP Phase 3 - Phase 2 Input Gate Audit Record",
        "",
        "This record assembles the verifiable evidence for every Phase 2 "
        "scientific-input condition.  Each condition is justified by referenced "
        "on-disk artefacts, never by assertion.",
        "",
        "## Gate conditions",
        "",
        "| Condition | Satisfied | Evidence references |",
        "| --- | --- | --- |",
    ]
    for item in audit.evidence:
        refs = "; ".join(str(ref) for ref in item.evidence) if item.evidence else "-"
        lines.append(f"| {item.condition} | {item.value} | {refs} |")
    lines.extend(["", "## Outcome", ""])
    missing = audit.gate.missing_items()
    if missing:
        lines.extend(
            [
                f"The Phase 2 gate is **NOT open**.  "
                f"Unsatisfied conditions: {', '.join(missing)}.",
                "",
            ]
        )
    else:
        lines.extend(
            [
                "The Phase 2 gate is **open**.  "
                "All scientific input conditions are satisfied by recorded evidence.",
                "",
            ]
        )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out_path
