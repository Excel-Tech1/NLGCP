"""Phase 4 QC admission layer for network experiments.

Never selects a session merely because a file exists.  Every candidate
must carry a Phase 4 ``network_rtk`` QC result; admission requires
``overall_classification == ACCEPT`` unless the experiment is explicitly
labelled diagnostic.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from nlgcp_network_rtk import ADMISSION_SCHEMA_VERSION

NETWORK_QC_PROFILE = "network_rtk"


@dataclass(frozen=True, slots=True)
class AdmittedSession:
    """One Phase 4-admitted observation session with full provenance."""

    station_id: str
    year: int
    day_of_year: int
    observation_path: str
    observation_sha256: str | None
    converted_sha256: str | None
    navigation_path: str | None
    navigation_sha256: str | None
    qc_profile: str
    qc_profile_version: str
    qc_status: str
    rejection_block_reason: str | None
    file_hashes: dict[str, str | None]
    phase4_result_fingerprint: str
    station_metadata_provenance: str | None
    equipment_metadata: dict[str, Any]
    sampling_interval_seconds: float | None
    first_epoch: str | None
    last_epoch: str | None
    epochs_observed: int | None
    coordinate_frame: str | None
    coordinate_epoch: str | None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class AdmissionSummary:
    """Per-DOY admission outcome with machine-readable block reasons."""

    year: int
    day_of_year: int
    qc_profile: str
    admitted: tuple[AdmittedSession, ...]
    rejected: tuple[dict[str, Any], ...]
    blocked_reasons: tuple[str, ...]
    diagnostic: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": ADMISSION_SCHEMA_VERSION,
            "year": self.year,
            "day_of_year": self.day_of_year,
            "qc_profile": self.qc_profile,
            "diagnostic": self.diagnostic,
            "admitted": [row.as_dict() for row in self.admitted],
            "rejected": list(self.rejected),
            "blocked_reasons": list(self.blocked_reasons),
            "admitted_station_count": len(self.admitted),
            "rejected_station_count": len(self.rejected),
        }


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
    """List stations with a Phase 4 QC result file for the day (sorted)."""
    day_root = data_root / "processed" / "qc" / "profiles" / profile / "sessions" / str(year)
    if not day_root.is_dir():
        return []
    stations: list[str] = []
    for station_dir in sorted(day_root.iterdir()):
        candidate = station_dir / f"{day_of_year:03d}" / "qc-result.json"
        if station_dir.is_dir() and candidate.is_file():
            stations.append(station_dir.name)
    return stations


def admit_day(
    data_root: Path,
    *,
    year: int,
    day_of_year: int,
    profile: str = NETWORK_QC_PROFILE,
    diagnostic: bool = False,
    candidate_stations: list[str] | None = None,
) -> AdmissionSummary:
    """Admit Phase 4 ACCEPT sessions for one day, recording everything else."""
    stations = candidate_stations or discover_stations_for_day(
        data_root, profile=profile, year=year, day_of_year=day_of_year
    )
    admitted: list[AdmittedSession] = []
    rejected: list[dict[str, Any]] = []
    for station_id in sorted(stations):
        path = qc_result_path(
            data_root, profile=profile, station_id=station_id, year=year, day_of_year=day_of_year
        )
        if not path.is_file():
            rejected.append(
                {
                    "station_id": station_id,
                    "decision": "BLOCKED",
                    "reason": f"no Phase 4 {profile} QC result for {year}-{day_of_year:03d}",
                }
            )
            continue
        try:
            payload: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            rejected.append(
                {
                    "station_id": station_id,
                    "decision": "BLOCKED",
                    "reason": f"unreadable Phase 4 QC result: {exc}",
                }
            )
            continue
        status = str(payload.get("overall_classification", "BLOCKED"))
        if status != "ACCEPT" and not diagnostic:
            rejected.append(
                {
                    "station_id": station_id,
                    "decision": status if status in {"REJECT", "BLOCKED"} else "REJECT",
                    "reason": _decision_reason(payload, status),
                    "qc_profile": str(payload.get("qc_profile", {}).get("name", profile)),
                    "result_fingerprint": str(payload.get("result_fingerprint", "")),
                }
            )
            continue
        try:
            admitted.append(_admitted_session(data_root, payload, diagnostic=diagnostic))
        except (KeyError, TypeError, ValueError) as exc:
            rejected.append(
                {
                    "station_id": station_id,
                    "decision": "BLOCKED",
                    "reason": f"malformed QC result: {exc}",
                }
            )
    blocked: list[str] = []
    if not admitted:
        blocked.append(f"no {profile} ACCEPT sessions for {year}-{day_of_year:03d}")
    return AdmissionSummary(
        year=year,
        day_of_year=day_of_year,
        qc_profile=profile,
        admitted=tuple(admitted),
        rejected=tuple(rejected),
        blocked_reasons=tuple(blocked),
        diagnostic=diagnostic,
    )


def session_eligibility_rows(summary: AdmissionSummary) -> list[dict[str, Any]]:
    """Flatten admission into station-eligibility rows for summaries."""
    rows: list[dict[str, Any]] = []
    for row in summary.admitted:
        rows.append(
            {
                "year": row.year,
                "day_of_year": row.day_of_year,
                "station_id": row.station_id,
                "decision": "ADMITTED",
                "qc_status": row.qc_status,
                "reason": "",
                "observation_sha256": row.observation_sha256,
                "phase4_fingerprint": row.phase4_result_fingerprint,
            }
        )
    for item in summary.rejected:
        rows.append(
            {
                "year": summary.year,
                "day_of_year": summary.day_of_year,
                "station_id": str(item.get("station_id", "")),
                "decision": str(item.get("decision", "REJECT")),
                "qc_status": str(item.get("decision", "")),
                "reason": str(item.get("reason", "")),
                "observation_sha256": "",
                "phase4_fingerprint": str(item.get("result_fingerprint", "")),
            }
        )
    return sorted(rows, key=lambda r: (r["day_of_year"], r["station_id"]))


def admission_fingerprint(summary: AdmissionSummary) -> str:
    material = {
        "year": summary.year,
        "day_of_year": summary.day_of_year,
        "qc_profile": summary.qc_profile,
        "diagnostic": summary.diagnostic,
        "admitted": sorted(
            (row.station_id, row.phase4_result_fingerprint) for row in summary.admitted
        ),
    }
    return hashlib.sha256(
        json.dumps(material, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _decision_reason(payload: dict[str, Any], status: str) -> str:
    findings = payload.get("findings", [])
    severe = [
        f"{f.get('finding_code')}:{f.get('severity')}:{f.get('message', '')}"
        for f in findings
        if isinstance(f, dict) and f.get("severity") in {"REJECT", "BLOCKED", "WARN"}
    ]
    detail = "; ".join(severe[:5]) if severe else "no passing admission under profile"
    return f"Phase 4 {status}: {detail}"


def _admitted_session(
    data_root: Path, payload: dict[str, Any], *, diagnostic: bool
) -> AdmittedSession:
    identity = payload.get("station_identity", {})
    source = payload.get("source", {})
    conversion = payload.get("conversion") or {}
    navigation = payload.get("navigation")
    rinex = payload.get("rinex") or {}
    header = rinex.get("header") or {}
    coord = payload.get("coordinate_eligibility") or {}
    findings = payload.get("findings", [])
    severe = "; ".join(
        f"{f.get('finding_code')}:{f.get('severity')}"
        for f in findings
        if isinstance(f, dict) and f.get("severity") in {"REJECT", "BLOCKED"}
    )
    converted_path = str(conversion.get("converted_path", ""))
    obs_candidates = [converted_path] if converted_path else []
    observation_path = next((p for p in obs_candidates if p), converted_path)
    _ = data_root  # paths in QC results are absolute; data_root anchors discovery only
    return AdmittedSession(
        station_id=str(identity.get("canonical_station_id", "")),
        year=int(identity.get("year", payload.get("station_identity", {}).get("year", 0)) or 0),
        day_of_year=int(identity.get("day_of_year", 0) or 0),
        observation_path=observation_path,
        observation_sha256=_optional_text(source.get("observed_sha256"))
        or _optional_text(source.get("manifest_sha256")),
        converted_sha256=_optional_text(conversion.get("converted_sha256")),
        navigation_path=_optional_text((navigation or {}).get("relative_path")),
        navigation_sha256=_optional_text((navigation or {}).get("sha256")),
        qc_profile=str(payload.get("qc_profile", {}).get("name", NETWORK_QC_PROFILE)),
        qc_profile_version=str(payload.get("qc_profile", {}).get("version", "")),
        qc_status=str(payload.get("overall_classification", "BLOCKED")),
        rejection_block_reason=(severe or None),
        file_hashes={
            "manifest_sha256": _optional_text(source.get("manifest_sha256")),
            "observed_sha256": _optional_text(source.get("observed_sha256")),
            "converted_sha256": _optional_text(conversion.get("converted_sha256")),
            "decompressed_sha256": _optional_text(conversion.get("decompressed_sha256")),
            "navigation_sha256": _optional_text((navigation or {}).get("sha256")),
        },
        phase4_result_fingerprint=str(payload.get("result_fingerprint", "")),
        station_metadata_provenance=_optional_text(coord.get("source_path")),
        equipment_metadata={
            "receiver_type": header.get("receiver_type"),
            "receiver_number": header.get("receiver_number"),
            "receiver_version": header.get("receiver_version"),
            "antenna_type": header.get("antenna_type"),
            "antenna_number": header.get("antenna_number"),
            "marker_name": header.get("marker_name"),
            "marker_number": header.get("marker_number"),
            "diagnostic_experiment": diagnostic,
        },
        sampling_interval_seconds=_optional_float(rinex.get("empirical_interval_seconds")),
        first_epoch=_optional_text(rinex.get("first_epoch")),
        last_epoch=_optional_text(rinex.get("last_epoch")),
        epochs_observed=_optional_int(rinex.get("epochs_observed")),
        coordinate_frame=_optional_text(coord.get("reference_frame")),
        coordinate_epoch=_optional_text(coord.get("coordinate_epoch")),
    )


def _optional_text(value: Any) -> str | None:
    return str(value) if isinstance(value, str) and value else None


def _optional_float(value: Any) -> float | None:
    return float(value) if isinstance(value, (int, float)) else None


def _optional_int(value: Any) -> int | None:
    return int(value) if isinstance(value, int) else None
