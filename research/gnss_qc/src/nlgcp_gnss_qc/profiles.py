"""Load and validate named, versioned Phase 4 QC profiles."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class ProfileError(ValueError):
    """Raised when a QC profile is absent or structurally unsafe."""


@dataclass(frozen=True, slots=True)
class QCProfile:
    name: str
    version: str
    status: str
    expected_interval_seconds: float | None
    sampling_tolerance_seconds: float
    accept_completeness_fraction: float
    reject_below_completeness_fraction: float
    maximum_warn_gap_seconds: float
    require_dual_frequency_phase: bool
    require_navigation: bool
    require_verified_coordinates: bool
    warn_on_partial_session: bool
    config_sha256: str


def default_profile_path() -> Path:
    return Path(__file__).resolve().parents[2] / "config" / "qc-profiles-v1.0.json"


def load_profiles(path: Path | None = None) -> dict[str, QCProfile]:
    """Return all configured profiles after strict range/type validation."""

    profile_path = (path or default_profile_path()).resolve()
    raw = profile_path.read_bytes()
    payload: dict[str, Any] = json.loads(raw)
    version = _required_text(payload, "profile_set_version")
    status = _required_text(payload, "status")
    digest = hashlib.sha256(raw).hexdigest()
    entries = payload.get("profiles")
    if not isinstance(entries, dict) or not entries:
        raise ProfileError("profiles must be a non-empty object")
    result: dict[str, QCProfile] = {}
    for name, value in entries.items():
        if not isinstance(name, str) or not isinstance(value, dict):
            raise ProfileError("profile entries must map names to objects")
        accept = _fraction(value, "accept_completeness_fraction")
        reject = _fraction(value, "reject_below_completeness_fraction")
        if reject > accept:
            raise ProfileError(f"{name}: reject threshold exceeds accept threshold")
        expected = value.get("expected_interval_seconds")
        if expected is not None and (not isinstance(expected, (int, float)) or expected <= 0):
            raise ProfileError(f"{name}: expected interval must be positive or null")
        result[name] = QCProfile(
            name=name,
            version=version,
            status=status,
            expected_interval_seconds=float(expected) if expected is not None else None,
            sampling_tolerance_seconds=_nonnegative(value, "sampling_tolerance_seconds"),
            accept_completeness_fraction=accept,
            reject_below_completeness_fraction=reject,
            maximum_warn_gap_seconds=_nonnegative(value, "maximum_warn_gap_seconds"),
            require_dual_frequency_phase=_boolean(value, "require_dual_frequency_phase"),
            require_navigation=_boolean(value, "require_navigation"),
            require_verified_coordinates=_boolean(value, "require_verified_coordinates"),
            warn_on_partial_session=_boolean(value, "warn_on_partial_session"),
            config_sha256=digest,
        )
    return result


def _required_text(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise ProfileError(f"{key} must be a non-empty string")
    return value


def _fraction(payload: dict[str, Any], key: str) -> float:
    value = payload.get(key)
    if not isinstance(value, (int, float)) or not 0 <= value <= 1:
        raise ProfileError(f"{key} must be between 0 and 1")
    return float(value)


def _nonnegative(payload: dict[str, Any], key: str) -> float:
    value = payload.get(key)
    if not isinstance(value, (int, float)) or value < 0:
        raise ProfileError(f"{key} must be non-negative")
    return float(value)


def _boolean(payload: dict[str, Any], key: str) -> bool:
    value = payload.get(key)
    if not isinstance(value, bool):
        raise ProfileError(f"{key} must be boolean")
    return value
