"""Unified atmospheric estimate and validation status schema (Phase 6/7).

Preserves explicit provenance, estimation method, units, uncertainty, and
honest validation status across ionospheric, tropospheric, spatial, and
downstream VRS consumers without collapsing software testing into scientific
validation.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any


class ValidationStatus(StrEnum):
    """Strict separation of software, technical, and scientific validation."""

    IMPLEMENTED = "IMPLEMENTED"
    UNIT_TESTED = "UNIT_TESTED"
    TECHNICALLY_VALIDATED = "TECHNICALLY_VALIDATED"
    SCIENTIFICALLY_VALIDATED = "SCIENTIFICALLY_VALIDATED"
    BLOCKED = "BLOCKED"
    NOT_PERFORMED = "NOT_PERFORMED"


class AtmosphericComponent(StrEnum):
    """Explicit separation of physical atmospheric error components."""

    RAW_STEC_UNBIASED_UNAVAILABLE = "RAW_STEC_UNBIASED_UNAVAILABLE"
    BIAS_CORRECTED_STEC = "BIAS_CORRECTED_STEC"
    VTEC_UNBIASED_UNAVAILABLE = "VTEC_UNBIASED_UNAVAILABLE"
    ROT_TECU_PER_MIN = "ROT_TECU_PER_MIN"
    ROTI_TECU_PER_MIN = "ROTI_TECU_PER_MIN"
    SLANT_IONO_L1_DIFF = "SLANT_IONO_L1_DIFF"
    ZHD_MODEL = "ZHD_MODEL"
    ZWD_MODEL = "ZWD_MODEL"
    ZTD_MODEL = "ZTD_MODEL"
    ZTD_PPP_PRIDE = "ZTD_PPP_PRIDE"
    SLANT_TROPO_TOTAL = "SLANT_TROPO_TOTAL"
    INTERPOLATED_SPATIAL_IONO = "INTERPOLATED_SPATIAL_IONO"
    INTERPOLATED_SPATIAL_TROPO = "INTERPOLATED_SPATIAL_TROPO"


@dataclass(frozen=True, slots=True)
class AtmosphericEstimate:
    """Canonical atmospheric estimate carrying full provenance to Phase 7/11."""

    station_id: str
    satellite_id: str | None
    epoch_iso: str
    component: AtmosphericComponent
    value: float
    units: str
    estimation_method: str
    source_observations: tuple[str, ...]
    model_version: str
    quality_indicators: dict[str, Any] = field(default_factory=dict)
    uncertainty: float | None = None
    provenance: dict[str, Any] = field(default_factory=dict)
    validation_status: ValidationStatus = ValidationStatus.IMPLEMENTED

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["component"] = str(self.component)
        payload["validation_status"] = str(self.validation_status)
        payload["source_observations"] = list(self.source_observations)
        return payload
