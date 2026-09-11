"""Explicit RTCM field metadata and fail-closed numeric validation."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class FieldSpec:
    name: str
    bits: int
    signed: bool
    unit: str
    scale: float
    minimum: float
    maximum: float
    required: bool = True
    missing_representation: str = "unavailable"
    rounding: str = "nearest_even"

    def validate(self, value: Any) -> list[str]:
        if value is None:
            return [f"{self.name}: missing required value"] if self.required else []
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return [f"{self.name}: numeric value required"]
        if not math.isfinite(float(value)):
            return [f"{self.name}: NaN/Inf is forbidden"]
        if not self.bits or self.bits < 1:
            return [f"{self.name}: bits must be positive"]
        if self.scale <= 0:
            return [f"{self.name}: scale must be positive"]
        if float(value) < self.minimum or float(value) > self.maximum:
            return [
                f"{self.name}: {value} outside [{self.minimum}, {self.maximum}] {self.unit}"
            ]
        return []

    def encode_integer(self, value: float | int) -> int:
        problems = self.validate(value)
        if problems:
            raise ValueError("; ".join(problems))
        return int(round(float(value) / self.scale))


def validate_fields(specs: tuple[FieldSpec, ...], values: dict[str, Any]) -> None:
    problems: list[str] = []
    for spec in specs:
        problems.extend(spec.validate(values.get(spec.name)))
    if problems:
        raise ValueError("; ".join(problems))
