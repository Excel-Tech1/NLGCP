"""Ionospheric proxy layer (Phase 6).

Implements only what GPS L1/L2 geometry-free observables support:

* station geometry-free series (metres) and first-order L1 slant variation;
* between-station single differences per epoch/satellite;
* arc-detrended double-differenced residual proxies and per-pair spatial
  gradient proxies (metres per kilometre).

Nothing here is absolute TEC: arc-detrended values are labelled
``differential residual proxy`` with units, derivation method, baseline
distance, and input observation codes recorded per value.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .combinations import (
    DD_DETREND_METHOD,
    GF_METHOD,
    SD_METHOD,
    arc_detrend,
    compute_gf_series,
    gf_iono_to_tecu,
    gf_to_l1_iono_m,
)
from .observations import StationDataset


@dataclass(frozen=True, slots=True)
class IonosphericSample:
    """One ionospheric proxy value with full provenance."""

    epoch_iso: str
    satellite_id: str
    constellation: str
    reference_pair: tuple[str, ...]
    baseline_distance_m: float | None
    value_m: float
    value_tecu: float
    kind: str
    unit: str = "m (slant L1 variation); TECU first-order proxy"
    derivation_method: str = GF_METHOD
    input_obs_codes: tuple[str, ...] = ("L1", "L2")


def station_gf_detrended(
    dataset: StationDataset,
    satellite_id: str,
    *,
    slip_threshold_m: float = 0.5,
    step_s: float | None = None,
) -> dict[str, float]:
    """Arc-detrended GF series mapped ``{epoch: residual_m}``."""
    series = compute_gf_series(
        dataset, satellite_id, slip_threshold_m=slip_threshold_m, step_s=step_s
    )[satellite_id]
    return {epoch: detr for epoch, _, _, detr in arc_detrend(series)}


def station_gf_arcs(
    dataset: StationDataset,
    satellite_id: str,
    *,
    slip_threshold_m: float = 0.5,
    step_s: float | None = None,
) -> list[tuple[str, float, int, float]]:
    """Full arc-annotated detrended GF series for diagnostics/outputs."""
    series = compute_gf_series(
        dataset, satellite_id, slip_threshold_m=slip_threshold_m, step_s=step_s
    )[satellite_id]
    return arc_detrend(series)


def pair_sd_proxies(
    dataset_a: StationDataset,
    dataset_b: StationDataset,
    satellite_id: str,
    *,
    slip_threshold_m: float = 0.5,
    step_s: float | None = None,
) -> list[IonosphericSample]:
    """Single-differenced arc-detrended GF proxies for one station pair.

    Each station's GF series is detrended per continuous arc first (removing
    per-station ambiguity constants), then differenced on common epochs.
    Residual per-arc-median offsets are *not* re-removed here so that the
    values remain traceable station-pair observables; the caller documents
    the ``GF_SD_ARC_DETRENDED`` kind accordingly.
    """
    a = station_gf_detrended(
        dataset_a, satellite_id, slip_threshold_m=slip_threshold_m, step_s=step_s
    )
    b = station_gf_detrended(
        dataset_b, satellite_id, slip_threshold_m=slip_threshold_m, step_s=step_s
    )
    samples: list[IonosphericSample] = []
    for epoch in sorted(set(a) & set(b)):
        sd = a[epoch] - b[epoch]
        l1 = gf_to_l1_iono_m(sd)
        samples.append(IonosphericSample(
            epoch_iso=epoch,
            satellite_id=satellite_id,
            constellation=satellite_id[0] if satellite_id else "?",
            reference_pair=(dataset_a.station_id, dataset_b.station_id),
            baseline_distance_m=None,
            value_m=l1,
            value_tecu=gf_iono_to_tecu(l1),
            kind="GF_SD_ARC_DETRENDED",
            derivation_method=f"{GF_METHOD} | {SD_METHOD} | {DD_DETREND_METHOD}",
        ))
    return samples


def spatial_gradient_proxy(
    samples: list[IonosphericSample], baseline_distance_m: float
) -> list[dict[str, Any]]:
    """Attach per-kilometre gradient proxies to pair samples."""
    if baseline_distance_m <= 0:
        raise ValueError("baseline_distance_m must be positive")
    rows: list[dict[str, Any]] = []
    for sample in samples:
        rows.append({
            "epoch_iso": sample.epoch_iso,
            "satellite_id": sample.satellite_id,
            "reference_pair": list(sample.reference_pair),
            "baseline_distance_m": baseline_distance_m,
            "value_m": sample.value_m,
            "value_tecu": sample.value_tecu,
            "gradient_m_per_km": sample.value_m / (baseline_distance_m / 1000.0),
            "kind": sample.kind,
            "derivation_method": sample.derivation_method,
            "input_obs_codes": list(sample.input_obs_codes),
        })
    return rows
