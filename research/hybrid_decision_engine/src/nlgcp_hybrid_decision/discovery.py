"""Station candidate discovery (Phase 8).

Given a target coordinate and day, determine available candidate
physical reference stations and record QC status, navigation status,
coordinate verification, observation coverage, common interval,
equipment metadata, and provenance for each.

No station is ranked before eligibility is confirmed; ranking lives in
``single_base.py``.  No coordinates are invented: targets resolve from
an explicit ECEF vector or from verified coordinates by station id.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from nlgcp_hybrid_decision.models import DecisionBlocked, QCStatus, StationCandidate

NETWORK_QC_PROFILE = "network_rtk"
SINGLE_BASE_QC_PROFILE = "single_base_rtk"


@dataclass(frozen=True, slots=True)
class DiscoveryResult:
    """Candidate stations plus the resolved target coordinate."""

    target_ecef_m: tuple[float, float, float] | None
    target_station_id: str | None
    target_resolved_from: str
    candidates: tuple[StationCandidate, ...]
    verified_coordinates_fingerprint: str
    warnings: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "target_ecef_m": list(self.target_ecef_m) if self.target_ecef_m else None,
            "target_station_id": self.target_station_id,
            "target_resolved_from": self.target_resolved_from,
            "candidates": [c.as_dict() for c in self.candidates],
            "verified_coordinates_fingerprint": self.verified_coordinates_fingerprint,
            "warnings": list(self.warnings),
        }


def baseline_length_m(
    first: tuple[float, float, float], second: tuple[float, float, float]
) -> float:
    return math.sqrt(
        (first[0] - second[0]) ** 2
        + (first[1] - second[1]) ** 2
        + (first[2] - second[2]) ** 2
    )


def load_verified_coordinates(data_root: Path) -> dict[str, dict[str, Any]]:
    """Load only scientifically valid station coordinates (fail closed)."""
    path = data_root / "processed" / "single-base" / "derived-coordinates.json"
    if not path.is_file():
        raise DecisionBlocked(
            "SCIENTIFIC DECISION BLOCKED - PHASE 8 ADMISSION REQUIREMENTS NOT MET: "
            f"verified coordinates unavailable: {path}"
        )
    try:
        payload: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DecisionBlocked(
            "SCIENTIFIC DECISION BLOCKED - PHASE 8 ADMISSION REQUIREMENTS NOT MET: "
            f"unreadable verified coordinates: {exc}"
        ) from exc
    result: dict[str, dict[str, Any]] = {}
    for station_id, row in payload.get("stations", {}).items():
        if not isinstance(row, dict) or row.get("scientifically_valid") is not True:
            continue
        ecef = row.get("ecef") or {}
        try:
            result[station_id] = {
                "x_m": float(ecef["x_m"]),
                "y_m": float(ecef["y_m"]),
                "z_m": float(ecef["z_m"]),
                "reference_frame": str(row["reference_frame"]),
                "coordinate_epoch": str(row["coordinate_epoch"]),
                "provenance": str(
                    row.get("pos_file_path", "processed/single-base/derived-coordinates.json")
                ),
            }
        except (KeyError, TypeError, ValueError):
            continue
    return result


def qc_result_path(
    data_root: Path, *, profile: str, station_id: str, year: int, day_of_year: int
) -> Path:
    return (
        data_root
        / "processed"
        / "qc"
        / "profiles"
        / profile
        / "sessions"
        / str(year)
        / station_id
        / f"{day_of_year:03d}"
        / "qc-result.json"
    )


def discover_stations_for_day(
    data_root: Path, *, profile: str, year: int, day_of_year: int
) -> list[str]:
    day_root = data_root / "processed" / "qc" / "profiles" / profile / "sessions" / str(year)
    if not day_root.is_dir():
        return []
    stations: list[str] = []
    for station_dir in sorted(day_root.iterdir()):
        candidate = station_dir / f"{day_of_year:03d}" / "qc-result.json"
        if station_dir.is_dir() and candidate.is_file():
            stations.append(station_dir.name)
    return stations


def read_qc_result(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        payload: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload


def resolve_target_ecef(
    *,
    target_ecef: tuple[float, float, float] | None,
    target_station_id: str | None,
    verified: dict[str, dict[str, Any]],
) -> tuple[tuple[float, float, float] | None, str]:
    """Resolve the target coordinate without inventing positions."""
    if target_ecef is not None:
        return target_ecef, "explicit_target_ecef"
    if target_station_id is not None:
        row = verified.get(target_station_id)
        if row is None:
            return None, "unverified_target_station"
        return (row["x_m"], row["y_m"], row["z_m"]), "verified_station_coordinate"
    return None, "no_target_coordinate"


def discover_candidates(
    data_root: Path,
    *,
    year: int,
    day_of_year: int,
    target_ecef: tuple[float, float, float] | None,
    target_station_id: str | None,
    candidate_stations: list[str] | None = None,
) -> DiscoveryResult:
    """Build one StationCandidate per station with a QC result on the day."""
    verified = load_verified_coordinates(data_root)
    resolved, resolved_from = resolve_target_ecef(
        target_ecef=target_ecef,
        target_station_id=target_station_id,
        verified=verified,
    )
    warnings: list[str] = []
    if resolved is None:
        warnings.append(f"target coordinate unresolved: {resolved_from}")

    network_stations = set(
        discover_stations_for_day(
            data_root, profile=NETWORK_QC_PROFILE, year=year, day_of_year=day_of_year
        )
    )
    single_stations = set(
        discover_stations_for_day(
            data_root, profile=SINGLE_BASE_QC_PROFILE, year=year, day_of_year=day_of_year
        )
    )
    universe = sorted(network_stations | single_stations)
    if candidate_stations is not None:
        universe = sorted(set(universe) & set(candidate_stations))

    candidates: list[StationCandidate] = []
    for station_id in universe:
        network_payload = read_qc_result(
            qc_result_path(
                data_root,
                profile=NETWORK_QC_PROFILE,
                station_id=station_id,
                year=year,
                day_of_year=day_of_year,
            )
        )
        single_payload = read_qc_result(
            qc_result_path(
                data_root,
                profile=SINGLE_BASE_QC_PROFILE,
                station_id=station_id,
                year=year,
                day_of_year=day_of_year,
            )
        )
        candidates.append(
            _build_candidate(
                station_id=station_id,
                network_payload=network_payload,
                single_payload=single_payload,
                verified=verified,
                target_ecef=resolved,
                target_station_id=target_station_id,
            )
        )
    fingerprint = _coordinates_fingerprint(data_root, verified)
    return DiscoveryResult(
        target_ecef_m=resolved,
        target_station_id=target_station_id,
        target_resolved_from=resolved_from,
        candidates=tuple(sorted(candidates, key=lambda c: c.station_id)),
        verified_coordinates_fingerprint=fingerprint,
        warnings=tuple(warnings),
    )


def _build_candidate(
    *,
    station_id: str,
    network_payload: dict[str, Any] | None,
    single_payload: dict[str, Any] | None,
    verified: dict[str, dict[str, Any]],
    target_ecef: tuple[float, float, float] | None,
    target_station_id: str | None,
) -> StationCandidate:
    network_status = _qc_status_of(network_payload)
    single_status = _qc_status_of(single_payload)
    # Effective QC: best admission across the two RTK profiles is recorded;
    # each gate later selects the profile it requires (network vs single).
    effective = _better_status(network_status, single_status)
    primary = network_payload if network_payload is not None else single_payload
    coord = verified.get(station_id)
    coord_verified = coord is not None
    distance: float | None = None
    if target_ecef is not None and coord is not None:
        distance = baseline_length_m(
            target_ecef, (coord["x_m"], coord["y_m"], coord["z_m"])
        )
    elif target_station_id is not None and coord is not None and station_id == target_station_id:
        distance = 0.0
    navigation_available = False
    navigation_sha: str | None = None
    coverage: str | None = None
    common: str | None = None
    equipment: dict[str, Any] = {}
    fingerprint = ""
    reasons: list[str] = []
    if primary is None:
        reasons.append("NO_QC_RESULT")
    else:
        navigation = primary.get("navigation") or {}
        navigation_sha = navigation.get("sha256")
        navigation_available = bool(navigation_sha)
        if not navigation_available:
            reasons.append("NO_NAVIGATION_PRODUCT")
        rinex = primary.get("rinex") or {}
        first = rinex.get("first_epoch")
        last = rinex.get("last_epoch")
        if first and last:
            coverage = f"{first}/{last}"
            common = coverage
        header = (rinex.get("header") or {}) if isinstance(rinex, dict) else {}
        equipment = {
            "receiver_type": header.get("receiver_type"),
            "antenna_type": header.get("antenna_type"),
            "marker_name": header.get("marker_name"),
        }
        fingerprint = str(primary.get("result_fingerprint", ""))
        if effective in (QCStatus.REJECT, QCStatus.BLOCKED, QCStatus.MISSING):
            reasons.append(f"QC_{effective}")
    if not coord_verified:
        reasons.append("UNVERIFIED_COORDINATE")
    if target_ecef is None and not (target_station_id and station_id == target_station_id):
        reasons.append("TARGET_UNRESOLVED_FOR_DISTANCE")
    eligible = not reasons
    return StationCandidate(
        station_id=station_id,
        distance_m=distance,
        qc_status=effective,
        navigation_available=navigation_available,
        navigation_sha256=navigation_sha,
        coordinate_verified=coord_verified,
        coordinate_frame=coord["reference_frame"] if coord else None,
        coordinate_epoch=coord["coordinate_epoch"] if coord else None,
        observation_coverage=coverage,
        common_interval=common,
        equipment_metadata=equipment,
        phase4_fingerprint=fingerprint,
        eligible=eligible,
        ineligibility_reasons=tuple(reasons),
    )


def _qc_status_of(payload: dict[str, Any] | None) -> QCStatus:
    if payload is None:
        return QCStatus.MISSING
    try:
        return QCStatus(str(payload.get("overall_classification", "BLOCKED")))
    except ValueError:
        return QCStatus.BLOCKED


def _better_status(first: QCStatus, second: QCStatus) -> QCStatus:
    order = {
        QCStatus.ACCEPT: 0,
        QCStatus.WARN: 1,
        QCStatus.REJECT: 2,
        QCStatus.BLOCKED: 3,
        QCStatus.MISSING: 4,
    }
    return first if order[first] <= order[second] else second


def _coordinates_fingerprint(
    data_root: Path, verified: dict[str, dict[str, Any]]
) -> str:
    import hashlib

    path = data_root / "processed" / "single-base" / "derived-coordinates.json"
    try:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        digest = ""
    material = {
        "file_sha256": digest,
        "verified_stations": sorted(verified),
    }
    return hashlib.sha256(
        json.dumps(material, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def discovery_as_dict(result: DiscoveryResult) -> dict[str, Any]:
    return result.as_dict()


def candidate_from_dict(payload: dict[str, Any]) -> StationCandidate:
    """Rebuild a candidate from JSON (fixtures / cached discovery)."""
    required = (
        "station_id", "qc_status", "phase4_fingerprint", "eligible",
        "navigation_available", "coordinate_verified",
    )
    missing = [key for key in required if key not in payload]
    if missing:
        raise DecisionBlocked(
            "SCIENTIFIC DECISION BLOCKED - PHASE 8 ADMISSION REQUIREMENTS NOT MET: "
            f"malformed station candidate: missing keys {missing}"
        )
    try:
        return StationCandidate(
            station_id=str(payload["station_id"]),
            distance_m=(
                None if payload.get("distance_m") is None else float(payload["distance_m"])
            ),
            qc_status=QCStatus(str(payload.get("qc_status", "MISSING"))),
            navigation_available=bool(payload.get("navigation_available", False)),
            navigation_sha256=payload.get("navigation_sha256"),
            coordinate_verified=bool(payload.get("coordinate_verified", False)),
            coordinate_frame=payload.get("coordinate_frame"),
            coordinate_epoch=payload.get("coordinate_epoch"),
            observation_coverage=payload.get("observation_coverage"),
            common_interval=payload.get("common_interval"),
            equipment_metadata=dict(payload.get("equipment_metadata", {})),
            phase4_fingerprint=str(payload.get("phase4_fingerprint", "")),
            eligible=bool(payload.get("eligible", False)),
            ineligibility_reasons=tuple(
                str(r) for r in payload.get("ineligibility_reasons", [])
            ),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise DecisionBlocked(
            f"SCIENTIFIC DECISION BLOCKED - PHASE 8 ADMISSION REQUIREMENTS NOT MET: "
            f"malformed station candidate: {exc}"
        ) from exc
