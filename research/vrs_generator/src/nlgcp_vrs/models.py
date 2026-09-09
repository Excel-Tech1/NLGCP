"""Strict experiment and promotion contracts; no empirical defaults for approval."""

from __future__ import annotations

import math
import re
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Blocked(ValueError):
    """Missing or incompatible scientific evidence."""


def safe_id(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,95}", value):
        raise Blocked("unsafe experiment or station identifier")
    return value


class Definition(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)
    experiment_id: str
    year: int = Field(ge=1980, le=2099)
    day_of_year: int = Field(ge=1, le=366)
    target_station: str
    reference_stations: tuple[str, ...]
    source_network_experiment: str
    source_phase6_experiment: str
    coordinate_frame: Literal["IGS20"]
    coordinate_epoch: str
    start_time: str
    end_time: str
    time_system: Literal["GPS"] = "GPS"
    sampling_interval: float = Field(gt=0)
    correction_model: Literal["auto", "zero", "nearest", "idw", "planar"] = "auto"
    diagnostic: bool = False
    target_policy: Literal["verified_station_coordinate"] = "verified_station_coordinate"
    rinex_output: Literal[False] = False

    @model_validator(mode="after")
    def check_definition(self) -> Definition:
        for value in (
            self.experiment_id,
            self.target_station,
            self.source_network_experiment,
            self.source_phase6_experiment,
            *self.reference_stations,
        ):
            safe_id(value)
        if len(set(self.reference_stations)) != len(self.reference_stations):
            raise ValueError("duplicate references")
        if len(self.reference_stations) < 3:
            raise ValueError("Phase 7 network requires at least three admitted references")
        if self.target_station in self.reference_stations:
            raise ValueError("held-out target leakage")
        start, end = self.window()
        if start > end or any(
            t.year != self.year or t.timetuple().tm_yday != self.day_of_year for t in (start, end)
        ):
            raise ValueError("window must lie on the requested day")
        if not self.coordinate_epoch:
            raise ValueError("coordinate epoch required")
        if self.correction_model not in ("auto", "zero") and not self.diagnostic:
            raise ValueError("candidate model requires explicit diagnostic mode")
        return self

    def window(self) -> tuple[datetime, datetime]:
        times = tuple(datetime.fromisoformat(t) for t in (self.start_time, self.end_time))
        if any(t.tzinfo is not None for t in times):
            raise ValueError("GPST calendar labels must not have a UTC offset or Z")
        return times[0], times[1]

    @property
    def virtual_id(self) -> str:
        return "VRS_" + self.experiment_id


def anchor_selection(
    coords: dict[str, tuple[float, float, float]], target: tuple[float, float, float]
) -> dict[str, Any]:
    if not coords or not all(math.isfinite(x) for xyz in [target, *coords.values()] for x in xyz):
        raise Blocked("finite reference and target coordinates required")
    distance, station = min((math.dist(xyz, target), station) for station, xyz in coords.items())
    return {
        "station": station,
        "distance_m": distance,
        "reason": "nearest admitted reference by ECEF chord; lexical station tie break",
    }


def correction_gate(
    validation: dict[str, Any], requested: str = "auto", diagnostic: bool = False
) -> dict[str, Any]:
    if validation.get("status") != "COMPLETE":
        raise Blocked("Phase 6 completed validation is required even for geometry control")
    loocv = validation.get("loocv", {})
    models = loocv.get("models", {})
    if not isinstance(models, dict) or set(models) != {"zero", "nearest", "idw", "planar"}:
        raise Blocked("exact zero/nearest/idw/planar comparison required")
    count = loocv.get("comparison_keys", 0)
    if not isinstance(count, int) or count <= 0:
        raise Blocked("Phase 6 identical-sample validation missing")
    for model in ("zero", "nearest", "idw", "planar"):
        metric = models.get(model, {})
        value = metric.get("rmse_m")
        if (
            not isinstance(value, (int, float))
            or not math.isfinite(value)
            or value < 0
            or metric.get("count") != count
        ):
            raise Blocked("Phase 6 model metrics malformed or comparison samples incompatible")
    winner = min(models, key=lambda m: models[m]["rmse_m"])
    if loocv.get("best_model") != winner:
        raise Blocked("Phase 6 declared winner disagrees with metrics")
    if requested not in ("auto", "zero", "nearest", "idw", "planar"):
        raise Blocked("unknown model")
    # No reviewed sample-size/coverage/geometry thresholds or validated proxy-to-
    # observation translation exist. Numeric improvement is necessary, insufficient.
    candidates = {
        m: {
            "improves_zero": models[m]["rmse_m"] < models["zero"]["rmse_m"],
            "improves_nearest": models[m]["rmse_m"] < models["nearest"]["rmse_m"],
            "status": "NOT_APPROVED",
            "missing": [
                "reviewed coverage and sample-size criteria",
                "independent geometry/extrapolation acceptance",
                "validated proxy-to-observation datum translation",
                "resolution of Phase 6 navigation geometry audit",
            ],
        }
        for m in ("nearest", "idw", "planar")
    }
    if requested not in ("auto", "zero"):
        if not diagnostic:
            raise Blocked("candidate requires diagnostic mode")
        raise Blocked(
            "DIAGNOSTIC / NOT VALIDATED FOR AUTOMATIC CORRECTION: "
            "GF_SD_ARC_DETRENDED cannot yet be translated into code/phase corrections"
        )
    return {
        "mode": "VRS_GEOMETRY_ONLY",
        "spatial_correction": "ZERO",
        "validation_status": "NO_VALIDATED_INTERPOLATION_GAIN",
        "promoted_model": None,
        "phase6_recorded_winner": winner,
        "phase6_metrics": models,
        "candidates": candidates,
        "automatic_correction_approved": False,
        "watermark": "NO VALIDATED INTERPOLATION GAIN",
    }
