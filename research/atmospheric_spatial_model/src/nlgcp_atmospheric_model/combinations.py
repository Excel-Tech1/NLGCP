"""GNSS measurement combinations (Phase 6).

Implements only combinations supported by the available observations:

* geometry-free phase combination (GPS L1/L2, metres);
* between-station single differences of the geometry-free observable;
* arc-detrended double-differenced ionospheric residual proxies.

All equations are documented in ``docs/phase6-atmospheric-spatial-model.md``
with literature provenance. Sign conventions:

* phase observables converted cycles -> metres with a positive wavelength;
* ``GF = L1 - L2`` in metres (geometry-free: geometry, clocks, troposphere
  cancel to first order);
* single difference ``SD_AB = GF_A - GF_B`` (satellite biases cancel);
* arc detrending subtracts the per-station-pair, per-satellite continuous-arc
  median, removing the (constant-per-arc) ambiguity and residual hardware
  bias terms. The remainder is labelled a *differential residual proxy*,
  dominated by differential ionosphere plus unmodelled effects — never
  absolute TEC.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from .constants import (
    GPS_L1_HZ,
    GPS_L2_HZ,
    IONO_COEFF_M_HZ2_PER_TECU,
)
from .observations import GPS_L1_WAVELENGTH_M, GPS_L2_WAVELENGTH_M, StationDataset

GAMMA_GPS = (GPS_L1_HZ / GPS_L2_HZ) ** 2
GF_TO_L1_FACTOR = 1.0 / (GAMMA_GPS - 1.0)
"""Scale arc-detrended GF (m) to L1 slant ionospheric variation (m).

Carrier: GF = -I1 - (-I2) = I1*(gamma - 1); I1 = GF/(gamma - 1).
"""

GF_METHOD = "GF=L1_cycles*lambda1-L2_cycles*lambda2 (metres); IS-GPS-200 frequencies"
SD_METHOD = "SD_AB=GF_A-GF_B per epoch/satellite (satellite biases cancel)"
DD_DETREND_METHOD = (
    "arc-detrended double-differenced residual: SD_AB minus per-arc median "
    "(ambiguity/hardware-bias constant per continuous arc removed)"
)


def gf_phase_m(l1_cycles: float, l2_cycles: float) -> float:
    """Geometry-free phase combination in metres (GPS L1/L2)."""
    return l1_cycles * GPS_L1_WAVELENGTH_M - l2_cycles * GPS_L2_WAVELENGTH_M


def gf_to_l1_iono_m(gf_m: float) -> float:
    """Map a geometry-free value (m) to L1 slant ionospheric delay (m)."""
    return gf_m * GF_TO_L1_FACTOR


def gf_iono_to_tecu(l1_iono_m: float) -> float:
    """First-order slant TEC (TECU) from L1 ionospheric delay (m).

    I1(m) = 40.308 * TEC / f1^2 with TEC in electrons/m^2, so
    TECU = I1 * f1^2 / (40.308 * 1e16). Yields ~0.162 m per TECU on L1.
    """
    return l1_iono_m * GPS_L1_HZ * GPS_L1_HZ / IONO_COEFF_M_HZ2_PER_TECU


def _wavelength(constellation: str, code: str) -> float | None:
    if constellation == "G" and code == "L1":
        return GPS_L1_WAVELENGTH_M
    if constellation == "G" and code == "L2":
        return GPS_L2_WAVELENGTH_M
    return None


@dataclass(slots=True)
class ArcState:
    """Continuous-arc tracker for one station/satellite pair."""

    arc_id: int = 0
    values: list[float] = field(default_factory=list)


def compute_gf_series(
    dataset: StationDataset,
    satellite_id: str,
    *,
    slip_threshold_m: float = 0.5,
    step_s: float | None = None,
) -> dict[str, list[tuple[str, float, int]]]:
    """Per-epoch geometry-free phase (m) with arc segmentation.

    Returns ``{satellite: [(epoch_iso, gf_m, arc_id)]}`` for the requested
    satellite. A new arc starts on an observation gap (the satellite missing
    from an epoch, or missing L1/L2), on an epoch spacing wider than
    ``1.5 * step_s`` (so decimated datasets must pass their effective
    sampling ``interval * stride``), on a *change* of the L1/L2 LLI flags
    between consecutive epochs, or on a GF jump larger than
    ``slip_threshold_m`` (documented heuristic for cycle-slip segmentation,
    not a measurement).

    LLI changes (rather than any nonzero LLI) delimit arcs because a flag
    that is constant across an entire day cannot encode per-epoch events:
    the PHRI00NGA DOY 026 file carries a static LLI=4 on every L2
    observable (a Trimble NETR9/converter annotation), yet its header
    declares full-cycle tracking (``WAVELENGTH FACT L1/2 = 1 1``), its
    L1/L2 cycle ratio equals ``f1/f2`` (1.2834, proving full-cycle L2),
    and its GF series is smooth and physical. Splitting on any nonzero
    LLI would shred that station into singleton arcs; transitions
    (``4 -> 5`` loss-of-lock, ``-> None``) still open new arcs, and the
    GF-jump test provides independent slip protection.
    """
    constellation = satellite_id[0] if satellite_id else ""
    lam1 = _wavelength(constellation, "L1")
    lam2 = _wavelength(constellation, "L2")
    series: list[tuple[str, float, int]] = []
    if lam1 is None or lam2 is None:
        return {satellite_id: series}
    arc_id = 0
    previous: float | None = None
    previous_time: float | None = None
    previous_lli: tuple[int, int] | None = None
    base_step = step_s if step_s is not None else dataset.header.interval_s
    nominal_step = base_step if base_step else 30.0
    for epoch in dataset.epochs:
        obs = dataset.data.get(epoch, {}).get(satellite_id)
        if obs is None:
            previous = None  # gap ends the continuous arc
            previous_time = None
            previous_lli = None
            continue
        l1 = obs.values.get("L1")
        l2 = obs.values.get("L2")
        if l1 is None or l2 is None or any((obs.lli.get(code) or 0) & 2 for code in ("L1", "L2")):
            previous = None
            previous_time = None
            previous_lli = None
            continue
        gf = l1 * lam1 - l2 * lam2
        lli = (obs.lli.get("L1") or 0, obs.lli.get("L2") or 0)
        now = _epoch_seconds(epoch)
        if previous is None:
            if series:
                # Resuming after a gap (or after epochs without usable
                # L1/L2): the ambiguity state is unknown, so a new arc
                # starts here rather than rejoining the pre-gap arc.
                arc_id += 1
        else:
            gap_break = (
                now is not None
                and previous_time is not None
                and (now - previous_time) > 1.5 * nominal_step + 1e-6
            )
            lli_break = previous_lli is not None and (
                lli != previous_lli or any(flag & 1 for flag in lli)
            )
            if gap_break or lli_break or obs.epoch_flag or abs(gf - previous) > slip_threshold_m:
                arc_id += 1
        series.append((epoch, gf, arc_id))
        previous = gf
        previous_time = now
        previous_lli = lli
    return {satellite_id: series}


def _epoch_seconds(epoch_iso: str) -> float | None:
    try:
        return datetime.fromisoformat(epoch_iso).timestamp()
    except ValueError:
        return None


def arc_detrend(series: list[tuple[str, float, int]]) -> list[tuple[str, float, int, float]]:
    """Subtract the per-arc median; returns ``(epoch, gf, arc, detrended)``."""
    by_arc: dict[int, list[float]] = {}
    for _, gf, arc in series:
        by_arc.setdefault(arc, []).append(gf)
    medians = {arc: _median(vals) for arc, vals in by_arc.items()}
    return [(epoch, gf, arc, gf - medians[arc]) for epoch, gf, arc in series]


def single_difference(
    series_a: list[tuple[str, float, int]],
    series_b: list[tuple[str, float, int]],
) -> list[tuple[str, float]]:
    """Between-station single difference of GF values on common epochs."""
    map_b = {epoch: gf for epoch, gf, _ in series_b}
    return [(epoch, gf_a - map_b[epoch]) for epoch, gf_a, _ in series_a if epoch in map_b]


def _median(values: list[float]) -> float:
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2 == 1:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2.0


__all__ = [
    "DD_DETREND_METHOD",
    "GAMMA_GPS",
    "GF_METHOD",
    "GF_TO_L1_FACTOR",
    "SD_METHOD",
    "arc_detrend",
    "compute_gf_series",
    "gf_iono_to_tecu",
    "gf_phase_m",
    "gf_to_l1_iono_m",
    "single_difference",
]
