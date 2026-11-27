"""Read-only Version 1 Control-Plane API Router (Milestone B-08).

Implements the 10 read-only ``/api/v1`` endpoints documented in the Day 7
Backend Architecture Audit while strictly observing:
- ADR-007: Control plane stays strictly separate from real-time RTCM streams
  (no correction frames transit HTTP per epoch);
- ADR-011: Fail-closed integrity & honest scientific-readiness reporting
  (``OPERATIONAL_APPROVED`` remains ``FORBIDDEN``; transport/process health is
  never conflated with scientific validity);
- Zero secret or credential exposure in any endpoint payload.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from nlgcp_rtcm_generation.registry import MessageFamilyRegistry

from nlgcp_api.config import settings

_REPO_ROOT = Path(__file__).resolve().parents[4]
_B04_CATALOGUE_CSV = _REPO_ROOT / "docs/research/b04_station_coordinate_catalogue.csv"
_ARCHIVE_SECURITY_JSON = _REPO_ROOT / "research/archive/validation/security_findings_register.json"


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


@dataclass
class ControlPlaneState:
    """In-process read-only view of attached local services (optional)."""

    attached_caster: Any | None = None
    event_bus: Any | None = None
    rtcm_generation_counters: dict[str, int] = field(
        default_factory=lambda: {
            "requests_total": 0,
            "frames_encoded_total": 0,
            "admission_blocked_total": 0,
        }
    )


control_plane_state = ControlPlaneState()
v1_router = APIRouter(prefix="/api/v1", tags=["v1-control-plane"])


def _load_verified_station_catalogue() -> list[dict[str, Any]]:
    """Load station coordinate provenance honestly from B-04 catalogue CSV (read-only)."""
    if not _B04_CATALOGUE_CSV.is_file():
        return []
    stations_by_id: dict[str, dict[str, Any]] = {}
    with _B04_CATALOGUE_CSV.open(encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            sid = (row.get("station_id") or "").strip().upper()
            if not sid:
                continue
            entry = stations_by_id.setdefault(
                sid,
                {
                    "station_id": sid,
                    "live_stream_connected": False,
                    "scientific_validity": "HISTORICAL_ARCHIVE_COORDINATE_PROVENANCE_ONLY",
                    "epochs": [],
                },
            )
            entry["epochs"].append(
                {
                    "epoch_window": row.get("window"),
                    "reference_frame": row.get("native_frame"),
                    "coordinate_epoch": row.get("epoch_year"),
                    "verification_status": row.get("classification"),
                    "truth_ready": str(row.get("truth_ready", "")).lower() == "true",
                    "ecef_x_m": row.get("x_m"),
                    "ecef_y_m": row.get("y_m"),
                    "ecef_z_m": row.get("z_m"),
                    "antenna_type": row.get("antenna_type"),
                    "receiver_type": row.get("receiver_type"),
                }
            )
    return [stations_by_id[k] for k in sorted(stations_by_id)]


def _open_security_finding_counts() -> dict[str, int]:
    if not _ARCHIVE_SECURITY_JSON.is_file():
        return {"open": 0, "total": 0}
    try:
        data = json.loads(_ARCHIVE_SECURITY_JSON.read_text(encoding="utf-8"))
        findings = data.get("findings", [])
        return {
            "total": len(findings),
            "open": sum(1 for f in findings if f.get("status") == "OPEN"),
        }
    except (OSError, ValueError):
        return {"open": 0, "total": 0}


@v1_router.get("/health/summary")
def health_summary() -> dict[str, Any]:
    """1. Aggregated process health separated strictly from scientific validity."""
    caster = control_plane_state.attached_caster
    caster_status = (
        caster.status_snapshot().get("caster_status", "STOPPED") if caster else "NOT_ATTACHED"
    )
    return {
        "timestamp_utc": _utc_now_iso(),
        "service": settings.service_name,
        "process_health": "OK",
        "control_plane_separated_from_correction_plane": True,
        "caster_status": caster_status,
        "event_bus_stats": (
            control_plane_state.event_bus.stats() if control_plane_state.event_bus else None
        ),
        "scientific_validity": "NOT_ASSESSED",
        "operational_approved": False,
    }


@v1_router.get("/stations")
def list_stations() -> dict[str, Any]:
    """2a. Read-only station provenance catalogue (never fabricates live CORS feeds)."""
    stations = _load_verified_station_catalogue()
    return {
        "count": len(stations),
        "live_cors_ingestion_status": "BLOCKED_NO_AUTHORIZED_LIVE_CREDENTIALS",
        "stations": stations,
    }


@v1_router.get("/stations/{station_id}")
def get_station(station_id: str) -> dict[str, Any]:
    """2b. Detailed provenance record for one catalogued station."""
    target = station_id.strip().upper()
    for row in _load_verified_station_catalogue():
        if row["station_id"] == target:
            return row
    raise HTTPException(
        status_code=404,
        detail=f"Station {target!r} not found in provenance catalogue",
    )


@v1_router.get("/correction/engine/status")
def correction_engine_status() -> dict[str, Any]:
    """3. Current Phase 6/7/8/11 correction engine policy and gate states."""
    return {
        "timestamp_utc": _utc_now_iso(),
        "decision_policy_version": "v1.0",
        "phase6_operational_spatial_default": "ZERO",
        "phase6_experimental_interior_candidate": "ipp_idw2_causal_and_offline_research_only",
        "phase7_operational_vrs_mode": "VRS_GEOMETRY_ONLY",
        "operational_vrs_permitted": False,
        "operational_approved": False,
        "operational_classification_policy": "FORBIDDEN",
        "active_blockers": [
            "VRS_OPERATIONAL_NOT_APPROVED",
            "AUTHENTIC_LIVE_CORS_STREAM_UNAVAILABLE",
            "HARDWARE_RECEIVER_VALIDATION_BLOCKED",
        ],
    }


@v1_router.get("/correction/rtcm/stats")
def correction_rtcm_stats() -> dict[str, Any]:
    """4. Phase 11 message-family registry statuses and runtime generation counts."""
    registry = MessageFamilyRegistry()
    return {
        "timestamp_utc": _utc_now_iso(),
        "operational_approved": False,
        "counters": dict(control_plane_state.rtcm_generation_counters),
        "message_families": registry.as_dict(),
    }


@v1_router.get("/caster/status")
def caster_status() -> dict[str, Any]:
    """5. Read-only loopback NTRIP caster status snapshot."""
    caster = control_plane_state.attached_caster
    if caster is None:
        return {
            "attached": False,
            "caster_status": "NOT_RUNNING",
            "network_boundary": "127.0.0.1_LOOPBACK_ONLY",
            "operational_approved": False,
        }
    snap = caster.status_snapshot()
    return {
        "attached": True,
        "network_boundary": "127.0.0.1_LOOPBACK_ONLY",
        "operational_approved": False,
        **snap,
    }


@v1_router.get("/caster/clients")
def caster_clients() -> dict[str, Any]:
    """6. Secret-free active client session listing (never exposes credentials)."""
    caster = control_plane_state.attached_caster
    sessions = caster.diagnostics.active_sessions_snapshot() if caster is not None else []
    return {
        "active_count": len(sessions),
        "sessions": sessions,
    }


@v1_router.get("/caster/mountpoints")
def caster_mountpoints() -> dict[str, Any]:
    """7. Registered mountpoint metadata including synthetic-only labels."""
    caster = control_plane_state.attached_caster
    if caster is None:
        return {"attached": False, "mountpoints": []}
    rows = []
    for name in caster.registry.names():
        defn = caster.registry.get(name)
        if defn is not None:
            rows.append(
                {
                    "name": defn.name,
                    "identifier": defn.identifier,
                    "format": defn.rtcm_format,
                    "nav_system": defn.nav_system,
                    "synthetic_only": defn.synthetic_only,
                    "experimental_vrs_only": defn.experimental_vrs_only,
                    "operational_approved": False,
                }
            )
    return {"attached": True, "mountpoints": rows}


@v1_router.get("/diagnostics")
def diagnostics_summary() -> dict[str, Any]:
    """8. Separated five-dimension diagnostics without collapsing scientific state."""
    caster = control_plane_state.attached_caster
    if caster is not None:
        caster_health = caster.status_snapshot().get("health", {})
    else:
        caster_health = {
            "SERVICE_HEALTH": "STOPPED",
            "CONNECTION_HEALTH": "IDLE",
            "STREAM_HEALTH": "IDLE",
            "RTCM_FRAME_HEALTH": "NO_FRAMES",
            "SCIENTIFIC_READINESS": "NOT_VALID_SYNTHETIC_TEST_ONLY",
        }
    return {
        "timestamp_utc": _utc_now_iso(),
        "control_plane_health": "HEALTHY",
        "caster_health": caster_health,
        "security_findings_summary": _open_security_finding_counts(),
    }


@v1_router.get("/diagnostics/errors")
def diagnostics_errors(limit: int = 50) -> dict[str, Any]:
    """9. Redacted recent fault events from bounded caster diagnostics ring buffer."""
    bounded_limit = max(1, min(limit, 200))
    caster = control_plane_state.attached_caster
    faults = (
        caster.diagnostics.recent_faults_snapshot(limit=bounded_limit)
        if caster is not None
        else []
    )
    return {
        "count": len(faults),
        "limit": bounded_limit,
        "events": faults,
    }


@v1_router.get("/readiness/scientific")
def scientific_readiness() -> dict[str, Any]:
    """10. Structured scientific and operational gate ledger (fail-closed)."""
    return {
        "timestamp_utc": _utc_now_iso(),
        "operational_approved": False,
        "operational_classification": "FORBIDDEN",
        "gates": {
            "phase6_operational_spatial_model": "ZERO",
            "phase7_operational_vrs_mode": "VRS_GEOMETRY_ONLY",
            "phase8_automatic_vrs": "BLOCKED",
            "phase10_live_cors_ingestion": "BLOCKED_NO_AUTHORIZED_LIVE_CREDENTIALS",
            "phase11_rtcm_registry_max_status": "SYNTHETICALLY_VALIDATED",
            "phase12_network_boundary": "127.0.0.1_LOOPBACK_ONLY",
            "phase16_field_receiver_validation": "BLOCKED_HARDWARE_ACCESS",
            "b04_2011_coordinates": "VERIFIED_IGS05_IGS08_PPP_FLOAT",
            "b05_causal_atmosphere": "INDEPENDENTLY_VALIDATED_RESEARCH_ONLY",
        },
        "security_findings": _open_security_finding_counts(),
        "notice": (
            "Control-plane availability does NOT imply scientific positioning validity "
            "or operational RTK/NRTK service approval."
        ),
    }
