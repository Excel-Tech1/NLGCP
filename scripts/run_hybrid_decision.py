#!/usr/bin/env python3
"""Operator CLI for the Phase 8 hybrid correction decision engine."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "research" / "hybrid_decision_engine" / "src"))

from nlgcp_hybrid_decision import ENGINE_VERSION  # noqa: E402
from nlgcp_hybrid_decision.decision import decide_full, utc_now_iso  # noqa: E402
from nlgcp_hybrid_decision.discovery import (  # noqa: E402
    discover_candidates,
    load_verified_coordinates,
)
from nlgcp_hybrid_decision.models import (  # noqa: E402
    DecisionRequest,
    QCStatus,
    SpatialCorrectionAssessment,
    VRSCapabilityAssessment,
    request_from_dict,
    spatial_assessment_from_dict,
    vrs_assessment_from_dict,
)
from nlgcp_hybrid_decision.policy import (  # noqa: E402
    DEFAULT_POLICY,
    DecisionPolicy,
    load_policy,
)
from nlgcp_hybrid_decision.reporting import (  # noqa: E402
    append_summary_rows,
    render_trace,
    write_decision_outputs,
)

DEFAULT_POLICY_PATH = (
    REPO_ROOT / "research" / "hybrid_decision_engine" / "config"
    / "hybrid-decision-policy-v1.json"
)

# Reviewed real-data defaults (Phase 6/7 scientific review COMPLETE).
# Phase 6 reviewed: best model ZERO (3.076 m beats IDW 3.352 / nearest
# 3.757 / planar 14.373 m, n=15948 identical samples, all folds
# EXTRAPOLATION); no non-zero interpolator promoted.  Represented as
# REJECTED for correction purposes: zero wins as the control and is NOT
# a promotable spatial correction model suitable for corrected VRS.
# Phase 7 reviewed: APPROVED_WITH_PROVISIONAL_LIMITATIONS for
# geometry-only synthesis (ZERO / VRS_GEOMETRY_ONLY, leakage PASS),
# but operational corrected VRS remains NOT APPROVED (fail-closed).
# Both assessments therefore block automatic corrected VRS while
# carrying reviewed fingerprints that invalidate pre-review decisions.
# Historical pre-review defaults used Phase 6 UNAVAILABLE (2.984 m,
# n=17768) / Phase 7 NOT_VALIDATED with fingerprints
# `phase6-pre-review-no-promoted-model` /
# `phase7-pre-review-not-validated` (SUPERSEDED).
DEFAULT_SPATIAL_REVIEWED = {
    "model_name": "zero",
    "validation_status": "REJECTED",
    "validation_metric": 3.076,
    "control_metric": 3.076,
    "beats_zero_control": False,
    "beats_nearest_control": True,
    "sample_count": 15948,
    "geometry_status": "EXTRAPOLATION",
    "extrapolation": True,
    "fingerprint": "phase6-reviewed-geometry-v3-zero-3076-n15948",
    "provenance": (
        "Reviewed Phase 6 atm-2024d026-phri-target-geometry-v3; "
        "best model zero RMSE 3.076 m (IDW 3.352 / nearest 3.757 / "
        "planar 14.373 m, n=15948 identical samples); all four folds "
        "EXTRAPOLATION; no spatial interpolation model promoted"
    ),
}

DEFAULT_VRS_REVIEWED = {
    "status": "BLOCKED",
    "experiment_id": "vrs-2024d026-phri-geometry-v3",
    "target": "",
    "reference_stations": ["ABFC00NGA", "EKAK00NGA", "MGBO00NGA"],
    "anchor": "EKAK00NGA",
    "correction_mode": "ZERO / VRS_GEOMETRY_ONLY",
    "model_status": "REJECTED",
    "observation_coverage": "480/480 epochs; 30 GPS sats",
    "validation_status": "APPROVED_WITH_PROVISIONAL_LIMITATIONS",
    "target_leakage_status": "PASS",
    "fingerprint": "phase7-reviewed-geometry-v3-phri-24556",
    "provenance": (
        "Reviewed Phase 7 vrs-2024d026-phri-geometry-v3; VRS synthesis "
        "reviewed APPROVED_WITH_PROVISIONAL_LIMITATIONS; mode "
        "ZERO / VRS_GEOMETRY_ONLY; promoted spatial model NONE; "
        "operational corrected VRS NOT APPROVED; target leakage PASS"
    ),
}

# Historical pre-review defaults (SUPERSEDED; retained for fingerprint-
# invalidation tests only).  Do NOT use for new decisions.
DEFAULT_SPATIAL_PRE_REVIEW = {
    "model_name": "none-promoted",
    "validation_status": "UNAVAILABLE",
    "validation_metric": None,
    "control_metric": 2.984,
    "beats_zero_control": False,
    "beats_nearest_control": False,
    "sample_count": 17768,
    "geometry_status": "UNASSESSED",
    "extrapolation": False,
    "fingerprint": "phase6-pre-review-no-promoted-model",
    "provenance": "Phase 6/7 scientific review pending; no interpolator promoted",
}

DEFAULT_VRS_PRE_REVIEW = {
    "status": "NOT_VALIDATED",
    "experiment_id": "",
    "target": "",
    "reference_stations": [],
    "anchor": "",
    "correction_mode": "ZERO / VRS_GEOMETRY_ONLY",
    "model_status": "UNAVAILABLE",
    "observation_coverage": "",
    "validation_status": "NOT_VALIDATED",
    "target_leakage_status": "",
    "fingerprint": "phase7-pre-review-not-validated",
    "provenance": "Phase 6/7 scientific review pending; automatic VRS NOT APPROVED",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, help="Override NLGCP_DATA_ROOT")
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY_PATH)
    parser.add_argument("--output-root", type=Path, default=None)
    sub = parser.add_subparsers(dest="command", required=True)

    inspect = sub.add_parser("inspect", help="Show candidate stations for a target/day")
    _add_request_args(inspect)

    plan = sub.add_parser("plan", help="Dry-run gates without writing outputs")
    _add_request_args(plan)
    _add_evidence_args(plan)

    decide = sub.add_parser("decide", help="Make and record a correction decision")
    _add_request_args(decide)
    _add_evidence_args(decide)
    decide.add_argument("--dry-run", action="store_true")
    decide.add_argument("--request", type=Path, default=None,
                        help="JSON decision request (overrides flag-built request)")

    explain = sub.add_parser("explain", help="Print the decision trace for a request")
    _add_request_args(explain)
    _add_evidence_args(explain)

    summary = sub.add_parser("summarize", help="Summarize recorded hybrid decisions")
    _ = summary
    return parser


def _add_request_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--request-id", default="req-manual-001")
    parser.add_argument("--target-station", default="PHRI00NGA")
    parser.add_argument("--target-ecef", nargs=3, type=float, default=None,
                        metavar=("X", "Y", "Z"))
    parser.add_argument("--year", type=int, default=2024)
    parser.add_argument("--doy", type=int, default=26)
    parser.add_argument("--desired-mode", default="AUTO",
                        choices=["AUTO", "VRS_ONLY", "SINGLE_BASE_ONLY"])
    parser.add_argument("--no-fallback", action="store_true")
    parser.add_argument("--diagnostic", action="store_true")


def _add_evidence_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--spatial", type=Path, default=None,
                        help="Phase 6 SpatialCorrectionAssessment JSON")
    parser.add_argument("--vrs", type=Path, default=None,
                        help="Phase 7 VRSCapabilityAssessment JSON")
    parser.add_argument("--target-leakage-pass", dest="leakage",
                        action="store_true", default=None)
    parser.add_argument("--target-leakage-fail", dest="leakage",
                        action="store_false")


def main() -> int:
    args = build_parser().parse_args()
    data_root = resolve_data_root(args.data_root)
    output_root = args.output_root or (data_root / "processed" / "hybrid-decisions")
    policy = load_policy_file(args.policy)

    if args.command == "summarize":
        print(json.dumps(summarize_outputs(output_root), indent=2, sort_keys=True))
        return 0
    if args.command == "inspect":
        request = build_request(args)
        discovery = discover_candidates(
            data_root, year=request.year, day_of_year=request.day_of_year,
            target_ecef=request.target_ecef,
            target_station_id=request.target_station_id,
        )
        print(json.dumps(discovery.as_dict(), indent=2, sort_keys=True, default=str))
        return 0

    request = load_request(args, data_root)
    spatial = load_spatial(args.spatial)
    vrs = load_vrs_assessment(args.vrs, target=request.target_station_id or "")
    leakage = args.leakage if getattr(args, "leakage", None) is not None else _default_leakage(vrs)
    discovery = discover_candidates(
        data_root, year=request.year, day_of_year=request.day_of_year,
        target_ecef=request.target_ecef,
        target_station_id=request.target_station_id,
    )
    single_qc = _single_base_qc_map(data_root, request)
    decision, network, single_base, vrs_gate = decide_full(
        request, discovery, spatial=spatial, vrs=vrs, policy=policy,
        single_qc=single_qc, target_leakage_pass=leakage,
        execution_timestamp=utc_now_iso(), git_commit=git_commit(),
    )
    trace = render_trace(
        request, discovery, network=network, single_base=single_base,
        vrs_gate=vrs_gate, spatial=spatial, vrs=vrs, decision=decision,
        policy=policy,
    )
    if args.command == "plan":
        print(json.dumps({
            "decision": decision.as_dict(),
            "network": network.as_dict(),
            "single_base": single_base.as_dict(),
            "vrs_gate": vrs_gate.as_dict(),
        }, indent=2, sort_keys=True, default=str))
        return 0
    if args.command == "explain":
        print(trace, end="")
        return 0
    if args.command == "decide":
        if args.dry_run:
            print(json.dumps(decision.as_dict(), indent=2, sort_keys=True, default=str))
            return 0
        paths = write_decision_outputs(
            output_root, request=request, discovery=discovery, network=network,
            single_base=single_base, vrs_gate=vrs_gate, spatial=spatial, vrs=vrs,
            decision=decision, policy=policy, trace=trace,
        )
        append_summary_rows(output_root, decision)
        print(json.dumps({
            "decision_id": decision.decision_id,
            "mode": str(decision.mode),
            "status": str(decision.status),
            "reason_code": str(decision.reason_code),
            "paths": paths,
        }, indent=2, sort_keys=True, default=str))
        return 0
    raise SystemExit(f"unknown command {args.command}")


def resolve_data_root(explicit: Path | None = None) -> Path:
    value = explicit or (
        Path(os.environ["NLGCP_DATA_ROOT"]) if "NLGCP_DATA_ROOT" in os.environ else None
    )
    if value is None:
        raise RuntimeError("NLGCP_DATA_ROOT is not configured")
    root = value.expanduser().resolve()
    if not root.is_dir():
        raise RuntimeError(f"NLGCP_DATA_ROOT is not a directory: {root}")
    return root


def load_policy_file(path: Path | None) -> DecisionPolicy:
    if path is not None and Path(path).is_file():
        return load_policy(Path(path))
    return DEFAULT_POLICY


def build_request(args: argparse.Namespace) -> DecisionRequest:
    ecef = tuple(args.target_ecef) if args.target_ecef else None
    payload: dict[str, Any] = {
        "request_id": str(args.request_id),
        "request_time": utc_now_iso(),
        "target_station_id": None if ecef else str(args.target_station),
        "target_ecef": list(ecef) if ecef else None,
        "desired_mode": str(args.desired_mode),
        "allow_fallback": not bool(args.no_fallback),
        "diagnostic": bool(args.diagnostic),
        "year": int(args.year),
        "day_of_year": int(args.doy),
    }
    request = request_from_dict(payload)
    problems = request.validate()
    if problems:
        raise SystemExit(f"invalid request: {'; '.join(problems)}")
    # Resolve explicit ECEF from verified coordinates when only a station id
    # was supplied on the CLI (targets are never invented).
    if request.target_ecef is None and request.target_station_id:
        verified = load_verified_coordinates(resolve_data_root(args.data_root))
        row = verified.get(request.target_station_id)
        if row is not None:
            return DecisionRequest(
                request_id=request.request_id,
                request_time=request.request_time,
                target_latitude=request.target_latitude,
                target_longitude=request.target_longitude,
                target_height=request.target_height,
                target_ecef=(row["x_m"], row["y_m"], row["z_m"]),
                target_station_id=request.target_station_id,
                requested_start_time=request.requested_start_time,
                requested_end_time=request.requested_end_time,
                desired_mode=request.desired_mode,
                allow_fallback=request.allow_fallback,
                diagnostic=request.diagnostic,
                year=request.year,
                day_of_year=request.day_of_year,
            )
    return request


def load_request(args: argparse.Namespace, data_root: Path) -> DecisionRequest:
    if getattr(args, "request", None):
        payload: dict[str, Any] = json.loads(Path(args.request).read_text(encoding="utf-8"))
        request = request_from_dict(payload)
        request.assert_valid()
        if request.target_ecef is None and request.target_station_id:
            verified = load_verified_coordinates(data_root)
            row = verified.get(request.target_station_id)
            if row is not None:
                request = DecisionRequest(
                    request_id=request.request_id,
                    request_time=request.request_time,
                    target_latitude=request.target_latitude,
                    target_longitude=request.target_longitude,
                    target_height=request.target_height,
                    target_ecef=(row["x_m"], row["y_m"], row["z_m"]),
                    target_station_id=request.target_station_id,
                    requested_start_time=request.requested_start_time,
                    requested_end_time=request.requested_end_time,
                    desired_mode=request.desired_mode,
                    allow_fallback=request.allow_fallback,
                    diagnostic=request.diagnostic,
                    year=request.year,
                    day_of_year=request.day_of_year,
                    receiver_capabilities=request.receiver_capabilities,
                    constellations=request.constellations,
                    supported_rtcm_messages=request.supported_rtcm_messages,
                )
        return request
    return build_request(args)


def load_spatial(path: Path | None) -> SpatialCorrectionAssessment:
    if path is not None:
        payload: dict[str, Any] = json.loads(Path(path).read_text(encoding="utf-8"))
        return spatial_assessment_from_dict(payload)
    return spatial_assessment_from_dict(dict(DEFAULT_SPATIAL_REVIEWED))


def load_vrs_assessment(path: Path | None, *, target: str) -> VRSCapabilityAssessment:
    if path is not None:
        payload: dict[str, Any] = json.loads(Path(path).read_text(encoding="utf-8"))
        return vrs_assessment_from_dict(payload)
    payload = dict(DEFAULT_VRS_REVIEWED)
    payload["target"] = target
    return vrs_assessment_from_dict(payload)


def _default_leakage(vrs: VRSCapabilityAssessment) -> bool | None:
    status = (vrs.target_leakage_status or "").strip().upper()
    if status in ("PASS", "NO_LEAKAGE", "EXCLUDED"):
        return True
    if status in ("FAIL", "LEAKAGE", "LEAKED"):
        return False
    return None


def _single_base_qc_map(data_root: Path, request: DecisionRequest) -> dict[str, QCStatus]:
    """Read per-station single_base_rtk QC outcomes for ranking (ACCEPT-only)."""
    mapping: dict[str, QCStatus] = {}
    day_root = (
        data_root / "processed" / "qc" / "profiles" / "single_base_rtk"
        / "sessions" / str(request.year)
    )
    if not day_root.is_dir():
        return mapping
    for station_dir in sorted(day_root.iterdir()):
        candidate = station_dir / f"{request.day_of_year:03d}" / "qc-result.json"
        if not candidate.is_file():
            continue
        try:
            payload: dict[str, Any] = json.loads(candidate.read_text(encoding="utf-8"))
            mapping[station_dir.name] = QCStatus(
                str(payload.get("overall_classification", "BLOCKED"))
            )
        except (OSError, ValueError, json.JSONDecodeError):
            mapping[station_dir.name] = QCStatus.BLOCKED
    return mapping


def summarize_outputs(output_root: Path) -> dict[str, Any]:
    import csv as csv_module

    decisions_path = output_root / "summaries" / "decisions.csv"
    rows: list[dict[str, str]] = []
    if decisions_path.is_file():
        with decisions_path.open(encoding="utf-8") as handle:
            rows = list(csv_module.DictReader(handle))
    by_mode: dict[str, int] = {}
    for row in rows:
        by_mode[row.get("mode", "")] = by_mode.get(row.get("mode", ""), 0) + 1
    return {
        "engine_version": ENGINE_VERSION,
        "output_root": str(output_root),
        "decision_count": len(rows),
        "by_mode": by_mode,
        "decisions_csv": str(decisions_path) if decisions_path.is_file() else None,
    }


def git_commit() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, check=True,
            text=True, capture_output=True,
        )
        return result.stdout.strip()
    except (subprocess.CalledProcessError, OSError):
        return "unknown"


if __name__ == "__main__":
    raise SystemExit(main())
