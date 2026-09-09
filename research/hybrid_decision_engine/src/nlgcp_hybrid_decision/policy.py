"""Versioned decision policy (Phase 8).

Every threshold that is not empirically calibrated for Nigeria is
labelled PROVISIONAL.  Engineering defaults are never presented as
scientific conclusions.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from nlgcp_hybrid_decision import POLICY_SCHEMA_VERSION

POLICY_VERSION = "v1.0"
POLICY_STATUS_PROVISIONAL = "PROVISIONAL"
POLICY_STATUS_VALIDATED = "SCIENTIFICALLY_VALIDATED"
POLICY_STATUS_ENGINEERING = "ENGINEERING_DEFAULT"


@dataclass(frozen=True, slots=True)
class DistancePolicy:
    """Single-base distance expectation bands (metres)."""

    preferred_max_m: float = 150000.0
    degraded_max_m: float = 500000.0
    maximum_allowed_m: float = 1100000.0
    calibration: str = POLICY_STATUS_PROVISIONAL
    note: str = (
        "Distance bands are PROVISIONAL engineering defaults, not empirically "
        "calibrated for Nigeria. Distance never overrides a failed science gate."
    )

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def band(self, distance_m: float | None) -> str:
        if distance_m is None:
            return "unknown"
        if distance_m <= self.preferred_max_m:
            return "preferred"
        if distance_m <= self.degraded_max_m:
            return "degraded"
        if distance_m <= self.maximum_allowed_m:
            return "maximum"
        return "beyond_maximum"


@dataclass(frozen=True, slots=True)
class DecisionPolicy:
    """Complete versioned policy consumed by the decision engine."""

    policy_version: str = POLICY_VERSION
    schema_version: str = POLICY_SCHEMA_VERSION
    minimum_network_reference_count: int = 3
    minimum_network_reference_count_calibration: str = POLICY_STATUS_VALIDATED
    allow_extrapolation: bool = False
    single_base_fallback_enabled: bool = True
    require_approved_spatial_model_for_vrs: bool = True
    require_approved_vrs_for_vrs: bool = True
    warn_on_qc_warn: bool = True
    qc_warn_blocks_automatic: bool = True
    diagnostic_preview_enabled: bool = True
    minimum_common_interval_seconds: float = 3600.0
    minimum_common_interval_calibration: str = POLICY_STATUS_ENGINEERING
    distance: DistancePolicy = field(default_factory=DistancePolicy)
    notes: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["distance"] = self.distance.as_dict()
        payload["notes"] = list(self.notes)
        return payload

    def validate(self) -> list[str]:
        problems: list[str] = []
        if not self.policy_version:
            problems.append("policy_version must be non-empty")
        if self.minimum_network_reference_count < 3:
            problems.append("minimum_network_reference_count below justified floor 3")
        if self.distance.preferred_max_m <= 0:
            problems.append("distance.preferred_max_m must be positive")
        if not (
            self.distance.preferred_max_m
            <= self.distance.degraded_max_m
            <= self.distance.maximum_allowed_m
        ):
            problems.append("distance bands must satisfy preferred <= degraded <= maximum")
        if self.minimum_common_interval_seconds <= 0:
            problems.append("minimum_common_interval_seconds must be positive")
        return problems


DEFAULT_POLICY = DecisionPolicy(
    notes=(
        "VRS automatic selection requires Phase 6 APPROVED + Phase 7 APPROVED.",
        "Phase 4 WARN never auto-converts to ACCEPT.",
        "Distance bands PROVISIONAL: long Nigerian baselines may yield "
        "FLOAT-only metre-level results; communicate degraded expectations.",
    ),
)


def policy_from_dict(payload: dict[str, Any]) -> DecisionPolicy:
    try:
        distance_payload = payload.get("distance", {})
        if not isinstance(distance_payload, dict):
            raise ValueError("distance must be a mapping")
        distance = DistancePolicy(
            preferred_max_m=float(distance_payload.get("preferred_max_m", 150000.0)),
            degraded_max_m=float(distance_payload.get("degraded_max_m", 500000.0)),
            maximum_allowed_m=float(distance_payload.get("maximum_allowed_m", 1100000.0)),
            calibration=str(
                distance_payload.get("calibration", POLICY_STATUS_PROVISIONAL)
            ),
            note=str(distance_payload.get("note", DistancePolicy().note)),
        )
        return DecisionPolicy(
            policy_version=str(payload.get("policy_version", POLICY_VERSION)),
            schema_version=str(payload.get("schema_version", POLICY_SCHEMA_VERSION)),
            minimum_network_reference_count=int(
                payload.get("minimum_network_reference_count", 3)
            ),
            minimum_network_reference_count_calibration=str(
                payload.get(
                    "minimum_network_reference_count_calibration",
                    POLICY_STATUS_VALIDATED,
                )
            ),
            allow_extrapolation=bool(payload.get("allow_extrapolation", False)),
            single_base_fallback_enabled=bool(
                payload.get("single_base_fallback_enabled", True)
            ),
            require_approved_spatial_model_for_vrs=bool(
                payload.get("require_approved_spatial_model_for_vrs", True)
            ),
            require_approved_vrs_for_vrs=bool(
                payload.get("require_approved_vrs_for_vrs", True)
            ),
            warn_on_qc_warn=bool(payload.get("warn_on_qc_warn", True)),
            qc_warn_blocks_automatic=bool(payload.get("qc_warn_blocks_automatic", True)),
            diagnostic_preview_enabled=bool(
                payload.get("diagnostic_preview_enabled", True)
            ),
            minimum_common_interval_seconds=float(
                payload.get("minimum_common_interval_seconds", 3600.0)
            ),
            minimum_common_interval_calibration=str(
                payload.get(
                    "minimum_common_interval_calibration", POLICY_STATUS_ENGINEERING
                )
            ),
            distance=distance,
            notes=tuple(str(n) for n in payload.get("notes", ())),
        )
    except (TypeError, ValueError) as exc:
        raise ValueError(f"malformed decision policy: {exc}") from exc


def load_policy(path: Path) -> DecisionPolicy:
    payload: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    policy = policy_from_dict(payload)
    problems = policy.validate()
    if problems:
        raise ValueError(f"invalid decision policy {path}: {'; '.join(problems)}")
    return policy


def policy_fingerprint(policy: DecisionPolicy) -> str:
    material = json.dumps(policy.as_dict(), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(material.encode()).hexdigest()
