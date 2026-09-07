"""Baseline computation and research distance classification for Phase 3.

Baseline lengths are computed from verified ECEF station coordinates.  The
sprint requires recording the *actual* distance in kilometres for every
experiment rather than inventing category boundaries.  Distance categories are
assigned by explicit research thresholds whose scientific basis is
documented, and never replace the true measured distance.
"""

from __future__ import annotations

from dataclasses import dataclass

from nlgcp_single_base.coordinates import EcefCoordinate, baseline_distance_m


@dataclass(frozen=True)
class BaselineClass:
    """A nominal research distance class with its meaning."""

    name: str
    min_km_inclusive: float
    max_km_exclusive: float
    rationale: str


# Explicit, documented research categories.  These follow the conventional
# single-base RTK shorthand: short/medium/long baselines, with Nigeria's
# sparse reference geometry extending into the very-long range.  The true
# measured distance is always recorded separately and drives the analysis.
BASELINE_CLASSES: tuple[BaselineClass, ...] = (
    BaselineClass("short", 0.0, 20.0, "conventional short-range RTK domain"),
    BaselineClass(
        "medium", 20.0, 100.0, "intermediate range, partial ionospheric degradation"
    ),
    BaselineClass(
        "long",
        100.0,
        300.0,
        "long range, strong distance-dependent degradation expected",
    ),
    BaselineClass(
        "very_long",
        300.0,
        float("inf"),
        "very long range for sparse-reference Nigerian geometry",
    ),
)


def classify_baseline(distance_km: float) -> str:
    """Return the research class name for a baseline distance in km."""
    for cls in BASELINE_CLASSES:
        if distance_km >= cls.min_km_inclusive and distance_km < cls.max_km_exclusive:
            return cls.name
    return "unclassified"


@dataclass(frozen=True)
class Baseline:
    """A directional base->rover baseline with measured distance."""

    base_station_id: str
    rover_station_id: str
    distance_km: float
    distance_class: str

    @property
    def ordered_pair(self) -> tuple[str, str]:
        """Canonical unordered pair key for this baseline."""

        return tuple(sorted((self.base_station_id, self.rover_station_id)))  # type: ignore[return-value]


def compute_baseline(
    base_station_id: str,
    base_ecef: EcefCoordinate,
    rover_station_id: str,
    rover_ecef: EcefCoordinate,
) -> Baseline:
    """Compute a base->rover baseline from verified ECEF coordinates."""
    distance_km = baseline_distance_m(base_ecef, rover_ecef) / 1000.0
    return Baseline(
        base_station_id=base_station_id,
        rover_station_id=rover_station_id,
        distance_km=distance_km,
        distance_class=classify_baseline(distance_km),
    )


def baseline_matrix(
    stations: dict[str, EcefCoordinate],
) -> list[Baseline]:
    """Return all unordered station pair baselines.

    Base->rover and rover->base are not treated as independent scientific
    baselines; a single unordered pair is produced per station combination.
    Direction is applied later by specific experiments, not multiplied here.
    """
    names = list(stations)
    result: list[Baseline] = []
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            base, rover = names[i], names[j]
            distance_km = baseline_distance_m(stations[base], stations[rover]) / 1000.0
            result.append(
                Baseline(
                    base_station_id=base,
                    rover_station_id=rover,
                    distance_km=distance_km,
                    distance_class=classify_baseline(distance_km),
                )
            )
    return result
