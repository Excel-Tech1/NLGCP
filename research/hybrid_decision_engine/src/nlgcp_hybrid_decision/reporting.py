"""Human-readable decision traces and output writing (Phase 8)."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from nlgcp_hybrid_decision import ENGINE_VERSION
from nlgcp_hybrid_decision.discovery import DiscoveryResult
from nlgcp_hybrid_decision.models import (
    CorrectionDecision,
    DecisionRequest,
    SpatialCorrectionAssessment,
    VRSCapabilityAssessment,
    phase9_view,
)
from nlgcp_hybrid_decision.network import NetworkAssessment
from nlgcp_hybrid_decision.policy import DecisionPolicy
from nlgcp_hybrid_decision.single_base import SingleBaseAssessment
from nlgcp_hybrid_decision.vrs import VRSAssessment


def render_trace(
    request: DecisionRequest,
    discovery: DiscoveryResult,
    *,
    network: NetworkAssessment,
    single_base: SingleBaseAssessment,
    vrs_gate: VRSAssessment,
    spatial: SpatialCorrectionAssessment,
    vrs: VRSCapabilityAssessment,
    decision: CorrectionDecision,
    policy: DecisionPolicy,
) -> str:
    """Render the thesis-ready human-readable decision trace."""
    target = request.target_station_id or "rover"
    if discovery.target_ecef_m:
        x, y, z = discovery.target_ecef_m
        target_line = f"{target} ECEF({x:.3f}, {y:.3f}, {z:.3f})"
    else:
        target_line = f"{target} (coordinate unresolved)"
    lines = [
        "NLGCP PHASE 8 DECISION TRACE",
        f"engine: nlgcp_hybrid_decision {ENGINE_VERSION} "
        f"policy {policy.policy_version}",
        "",
        "REQUEST",
        f"{request.request_id} / {request.year} DOY {request.day_of_year:03d} / "
        f"{request.desired_mode} fallback={request.allow_fallback} "
        f"diagnostic={request.diagnostic}",
        target_line,
        "",
        "CANDIDATES",
    ]
    for candidate in discovery.candidates:
        dist = (
            f"{candidate.distance_m / 1000.0:.3f} km"
            if candidate.distance_m is not None
            else "distance unknown"
        )
        lines.append(
            f"  {candidate.station_id}: QC={candidate.qc_status} "
            f"nav={'AVAILABLE' if candidate.navigation_available else 'MISSING'} "
            f"coord={'VERIFIED' if candidate.coordinate_verified else 'UNVERIFIED'} "
            f"{dist} eligible={candidate.eligible}"
        )
    lines += [
        "",
        "NETWORK",
        f"{network.admitted_count} admitted references "
        f"({', '.join(network.admitted_references) or 'none'})",
        f"geometry={network.geometry_status} "
        f"extent={_km(network.spatial_extent_m)} "
        f"triangle={network.triangle_area_m2} "
        f"extrapolation={network.extrapolation}",
    ]
    for blocker in network.blockers:
        lines.append(f"  blocker: {blocker}")
    lines += [
        "",
        "VRS",
        f"Phase 6 model {spatial.model_name or 'none'} = {spatial.validation_status}",
        f"Phase 7 = {vrs.status} ({vrs.experiment_id or 'no experiment'})",
        f"-> VRS {'SELECTABLE' if vrs_gate.selectable else 'BLOCKED'}: "
        f"{vrs_gate.reason_code}",
    ]
    lines += [
        "",
        "SINGLE BASE",
        f"available={single_base.available} "
        f"selected={single_base.selected_reference or 'none'} "
        f"distance={_km(single_base.distance_m)} "
        f"band={single_base.distance_band}",
        f"ranked: {', '.join(single_base.ranked) or 'none'}",
    ]
    for row in single_base.rejected:
        lines.append(f"  rejected: {row['station_id']}: {row['reason']}")
    lines += [
        "",
        "DECISION",
        f"{decision.mode} / {decision.status}",
        "",
        "REASON",
        f"{decision.reason_code}: {decision.reason_text}",
        "",
        f"fallback_used={decision.fallback_used} "
        f"integrity={decision.integrity_status} "
        f"fingerprint={decision.decision_fingerprint[:16]}...",
        "SYNTHETIC-ONLY NOTE: fixtures are labelled; real pilots read "
        "observed QC/coordinate/navigation evidence and never invent targets.",
    ]
    return "\n".join(lines) + "\n"


def write_decision_outputs(
    output_root: Path,
    *,
    request: DecisionRequest,
    discovery: DiscoveryResult,
    network: NetworkAssessment,
    single_base: SingleBaseAssessment,
    vrs_gate: VRSAssessment,
    spatial: SpatialCorrectionAssessment,
    vrs: VRSCapabilityAssessment,
    decision: CorrectionDecision,
    policy: DecisionPolicy,
    trace: str,
) -> dict[str, str]:
    """Write the per-request output bundle; return path manifest."""
    request_dir = output_root / "requests" / request.request_id
    request_dir.mkdir(parents=True, exist_ok=True)
    payloads: dict[str, dict[str, Any]] = {
        "request.json": {
            "schema": "request/1.0",
            **request.as_dict(),
        },
        "candidate-stations.json": discovery.as_dict(),
        "network-assessment.json": network.as_dict(),
        "vrs-assessment.json": {
            **vrs_gate.as_dict(),
            "upstream_spatial": spatial.as_dict(),
            "upstream_vrs": vrs.as_dict(),
        },
        "single-base-assessment.json": single_base.as_dict(),
        "decision.json": decision.as_dict(),
        "phase9-handoff.json": phase9_view(decision, request).as_dict(),
        "provenance.json": dict(decision.provenance),
        "policy.json": policy.as_dict(),
    }
    paths: dict[str, str] = {}
    for name, payload in payloads.items():
        path = request_dir / name
        path.write_text(
            json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
            encoding="utf-8",
        )
        paths[name] = str(path)
    trace_path = request_dir / "trace.txt"
    trace_path.write_text(trace, encoding="utf-8")
    paths["trace.txt"] = str(trace_path)
    return paths


def append_summary_rows(output_root: Path, decision: CorrectionDecision) -> None:
    """Append one row per summary CSV (decisions, blockers, fallback usage)."""
    summaries = output_root / "summaries"
    summaries.mkdir(parents=True, exist_ok=True)
    _append_csv(
        summaries / "decisions.csv",
        ["decision_id", "request_id", "timestamp", "mode", "status",
         "reason_code", "selected_reference", "fallback_used",
         "integrity_status", "decision_fingerprint"],
        [[
            decision.decision_id, decision.request_id, decision.timestamp,
            str(decision.mode), str(decision.status), str(decision.reason_code),
            decision.selected_reference or "", str(decision.fallback_used),
            str(decision.integrity_status), decision.decision_fingerprint,
        ]],
    )
    _append_csv(
        summaries / "blockers.csv",
        ["decision_id", "request_id", "blocker"],
        [[decision.decision_id, decision.request_id, b] for b in decision.blockers]
        or [[decision.decision_id, decision.request_id, ""]],
    )
    _append_csv(
        summaries / "fallback-usage.csv",
        ["decision_id", "request_id", "mode", "fallback_used", "selected_reference"],
        [[
            decision.decision_id, decision.request_id, str(decision.mode),
            str(decision.fallback_used), decision.selected_reference or "",
        ]],
    )


def _append_csv(path: Path, header: list[str], rows: list[list[str]]) -> None:
    exists = path.is_file()
    with path.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        if not exists:
            writer.writerow(header)
        writer.writerows(rows)


def _km(value: float | None) -> str:
    return f"{value / 1000.0:.3f} km" if value is not None else "unknown"
