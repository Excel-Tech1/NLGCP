"""Dual-frequency GPS ionospheric estimation pipeline (Phase 6 Workstream B1).

Separates strictly:
- Cycle-slip detection via Melbourne-Wubbena (MW) + Geometry-Free (GF) + LLI/gap;
- Raw uncalibrated phase-leveled STEC (explicitly retaining hardware DCB bias;
  external DCB products are never fabricated);
- Single-Layer Model (SLM, H_ion = 350 km) mapping function and Ionospheric
  Pierce Point (IPP) coordinates -> uncalibrated VTEC;
- Bias-free and ambiguity-free Rate of TEC (ROT, TECU/min) and 5-minute ROTI;
- Common-overlap pair-arc differential slant ionosphere (avoiding the
  mismatched-arc-median bias present when detrending stations independently).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from statistics import median
from typing import Any

from .atmospheric_schema import AtmosphericComponent, AtmosphericEstimate, ValidationStatus
from .combinations import GAMMA_GPS, GF_TO_L1_FACTOR
from .constants import GPS_L1_HZ, GPS_L2_HZ, IONO_COEFF_M_HZ2_PER_TECU, SPEED_OF_LIGHT_M_S
from .observations import GPS_L1_WAVELENGTH_M, GPS_L2_WAVELENGTH_M, StationDataset
from .troposphere import ecef_to_geodetic

IONO_MODEL_VERSION = "phase6-iono-v2.0"
EARTH_RADIUS_M = 6_371_000.0
DEFAULT_SLM_HEIGHT_M = 350_000.0
# Alpha_GF = 40.308e16 * (1/f2^2 - 1/f1^2) in m / TECU (~0.10504 m/TECU)
GF_M_PER_TECU = IONO_COEFF_M_HZ2_PER_TECU * (1.0 / (GPS_L2_HZ**2) - 1.0 / (GPS_L1_HZ**2))
L1_M_PER_TECU = IONO_COEFF_M_HZ2_PER_TECU / (GPS_L1_HZ**2)
MW_WAVELENGTH_M = SPEED_OF_LIGHT_M_S / (GPS_L1_HZ - GPS_L2_HZ)  # ~0.861918 m

DCB_UNAVAILABLE_STATUS = "UNAVAILABLE_EXTERNAL_DCB_NOT_FOUND"


@dataclass(frozen=True, slots=True)
class IonosphericPointEstimate:
    """Per-epoch/satellite ionospheric state at one station."""

    station_id: str
    satellite_id: str
    epoch_iso: str
    arc_id: int
    elevation_deg: float
    azimuth_deg: float
    ipp_lat_deg: float
    ipp_lon_deg: float
    slm_mapping_factor: float
    gf_phase_m: float
    gf_code_m: float
    code_pair_used: tuple[str, str]
    raw_stec_tecu: float
    bias_corrected_stec_tecu: float | None
    vtec_uncalibrated_tecu: float
    l1_slant_delay_uncalibrated_m: float
    rot_tecu_per_min: float | None
    roti_tecu_per_min: float | None
    dcb_status: str = DCB_UNAVAILABLE_STATUS
    cycle_slip_detected: bool = False


def slm_mapping_and_ipp(
    station_ecef_m: tuple[float, float, float],
    elevation_deg: float,
    azimuth_deg: float,
    *,
    shell_height_m: float = DEFAULT_SLM_HEIGHT_M,
) -> tuple[float, float, float]:
    """Compute Single-Layer Model mapping factor MF(el) and IPP (lat_deg, lon_deg)."""
    if not (0.0 < elevation_deg <= 90.0):
        raise ValueError(f"elevation_deg must be in (0, 90], got {elevation_deg}")
    lat_rad, lon_rad, _ = ecef_to_geodetic(station_ecef_m)
    el_rad = math.radians(elevation_deg)
    az_rad = math.radians(azimuth_deg)
    sin_zp = (EARTH_RADIUS_M / (EARTH_RADIUS_M + shell_height_m)) * math.cos(el_rad)
    sin_zp = max(-0.999999, min(0.999999, sin_zp))
    cos_zp = math.sqrt(max(1e-12, 1.0 - sin_zp * sin_zp))
    mf = 1.0 / cos_zp
    psi = (0.5 * math.pi - el_rad) - math.asin(sin_zp)
    sin_lat_ipp = math.sin(lat_rad) * math.cos(psi) + (
        math.cos(lat_rad) * math.sin(psi) * math.cos(az_rad)
    )
    sin_lat_ipp = max(-1.0, min(1.0, sin_lat_ipp))
    lat_ipp = math.asin(sin_lat_ipp)
    cos_lat_ipp = math.cos(lat_ipp)
    if abs(cos_lat_ipp) > 1e-12:
        sin_dlon = max(-1.0, min(1.0, math.sin(psi) * math.sin(az_rad) / cos_lat_ipp))
        lon_ipp = lon_rad + math.asin(sin_dlon)
    else:
        lon_ipp = lon_rad
    return mf, math.degrees(lat_ipp), math.degrees(lon_ipp)


def melbourne_wubbena_m(
    l1_cycles: float, l2_cycles: float, p1_or_c1_m: float, p2_m: float
) -> float:
    """Melbourne-Wubbena wide-lane combination in metres (geometry- & iono-free)."""
    l_wl = MW_WAVELENGTH_M * (l1_cycles - l2_cycles)
    p_nl = (GPS_L1_HZ * p1_or_c1_m + GPS_L2_HZ * p2_m) / (GPS_L1_HZ + GPS_L2_HZ)
    return l_wl - p_nl


def _epoch_sec(iso: str) -> float:
    return datetime.fromisoformat(iso).timestamp()


def estimate_station_ionosphere(
    dataset: StationDataset,
    station_ecef_m: tuple[float, float, float],
    topocentric_by_epoch_sat: dict[tuple[str, str], tuple[float, float]],
    *,
    min_elevation_deg: float = 15.0,
    gf_slip_threshold_m: float = 0.25,
    mw_slip_sigma: float = 4.0,
    mw_slip_floor_m: float = 0.75,
    min_arc_epochs: int = 4,
    roti_window_s: float = 300.0,
    shell_height_m: float = DEFAULT_SLM_HEIGHT_M,
    step_s: float | None = None,
) -> tuple[list[IonosphericPointEstimate], dict[str, Any]]:
    """Run MW+GF cycle-slip detection, phase-leveled STEC/VTEC, and ROT/ROTI.

    Uses ``P1`` when available, falling back explicitly to ``C1`` when ``P1`` is
    absent (as in the 2011 NIGNET archive). External DCBs are never fabricated;
    ``bias_corrected_stec_tecu`` stays ``None`` when no external DCB is supplied.
    """
    sats = sorted(
        {sat for sats_map in dataset.data.values() for sat in sats_map if sat.startswith("G")}
    )
    if step_s is not None and step_s > 0.0:
        nominal_step = step_s
    elif len(dataset.epochs) >= 2:
        dts = [
            _epoch_sec(dataset.epochs[i]) - _epoch_sec(dataset.epochs[i - 1])
            for i in range(1, min(len(dataset.epochs), 64))
        ]
        pos_dts = [d for d in dts if d > 0.0]
        nominal_step = median(pos_dts) if pos_dts else (dataset.header.interval_s or 30.0)
    else:
        nominal_step = dataset.header.interval_s or 30.0
    estimates: list[IonosphericPointEstimate] = []
    slips_gf = 0
    slips_mw = 0
    slips_lli_gap = 0
    arcs_total = 0
    arcs_short_dropped = 0

    for sat in sats:
        # Build raw continuous arcs for this satellite
        raw_arcs: list[list[dict[str, Any]]] = []
        current_arc: list[dict[str, Any]] = []
        prev_t: float | None = None
        prev_gf: float | None = None
        mw_n = 0
        mw_mean = 0.0
        mw_m2 = 0.0

        for ep in dataset.epochs:
            obs = dataset.data.get(ep, {}).get(sat)
            topo = topocentric_by_epoch_sat.get((ep, sat))
            if obs is None or topo is None:
                if current_arc:
                    raw_arcs.append(current_arc)
                    current_arc = []
                prev_t = None
                prev_gf = None
                mw_n = 0
                mw_mean = 0.0
                mw_m2 = 0.0
                continue
            el_deg, az_deg = topo
            if el_deg < min_elevation_deg:
                if current_arc:
                    raw_arcs.append(current_arc)
                    current_arc = []
                prev_t = None
                prev_gf = None
                mw_n = 0
                mw_mean = 0.0
                mw_m2 = 0.0
                continue
            l1 = obs.values.get("L1")
            l2 = obs.values.get("L2")
            p1 = obs.values.get("P1")
            c1 = obs.values.get("C1")
            p2 = obs.values.get("P2")
            code1_name = "P1" if p1 is not None else "C1"
            code1_val = p1 if p1 is not None else c1
            if (
                l1 is None
                or l2 is None
                or code1_val is None
                or p2 is None
                or any((obs.lli.get(c) or 0) & 2 for c in ("L1", "L2"))
            ):
                if current_arc:
                    raw_arcs.append(current_arc)
                    current_arc = []
                prev_t = None
                prev_gf = None
                mw_n = 0
                mw_mean = 0.0
                mw_m2 = 0.0
                continue

            gf_phase = l1 * GPS_L1_WAVELENGTH_M - l2 * GPS_L2_WAVELENGTH_M
            gf_code = p2 - code1_val
            mw_val = melbourne_wubbena_m(l1, l2, code1_val, p2)
            t_sec = _epoch_sec(ep)
            lli = (obs.lli.get("L1") or 0, obs.lli.get("L2") or 0)

            slip = False
            if prev_t is not None and prev_gf is not None:
                dt = t_sec - prev_t
                if (
                    dt > 1.5 * nominal_step + 1e-6
                    or obs.epoch_flag != 0
                    or any(f & 1 for f in lli)
                ):
                    slip = True
                    slips_lli_gap += 1
                elif abs(gf_phase - prev_gf) > gf_slip_threshold_m:
                    slip = True
                    slips_gf += 1
                elif mw_n >= 3:
                    mw_std = math.sqrt(mw_m2 / max(1, mw_n - 1))
                    thresh = max(mw_slip_floor_m, mw_slip_sigma * mw_std)
                    if abs(mw_val - mw_mean) > thresh:
                        slip = True
                        slips_mw += 1

            if slip and current_arc:
                raw_arcs.append(current_arc)
                current_arc = []
                mw_n = 0
                mw_mean = 0.0
                mw_m2 = 0.0

            # Welford running statistics for MW detector
            mw_n += 1
            delta = mw_val - mw_mean
            mw_mean += delta / mw_n
            mw_m2 += delta * (mw_val - mw_mean)

            current_arc.append(
                {
                    "epoch_iso": ep,
                    "t_sec": t_sec,
                    "el_deg": el_deg,
                    "az_deg": az_deg,
                    "gf_phase_m": gf_phase,
                    "gf_code_m": gf_code,
                    "code_pair": (code1_name, "P2"),
                    "slip": slip,
                }
            )
            prev_t = t_sec
            prev_gf = gf_phase

        if current_arc:
            raw_arcs.append(current_arc)

        for arc_idx, arc in enumerate(raw_arcs):
            if len(arc) < min_arc_epochs:
                arcs_short_dropped += 1
                continue
            arcs_total += 1
            # sin^2(elevation)-weighted carrier-to-code arc leveling
            w_sum = 0.0
            diff_sum = 0.0
            for pt in arc:
                w = math.sin(math.radians(pt["el_deg"])) ** 2
                stec_code = pt["gf_code_m"] / GF_M_PER_TECU
                stec_phase_rel = pt["gf_phase_m"] / GF_M_PER_TECU
                w_sum += w
                diff_sum += w * (stec_code - stec_phase_rel)
            level_offset_tecu = diff_sum / w_sum

            # Compute ROT (TECU/min) and sliding-window ROTI within this slip-free arc
            rot_series: list[tuple[float, float | None]] = []
            prev_stec_rel: float | None = None
            prev_arc_t: float | None = None
            for pt in arc:
                stec_rel = pt["gf_phase_m"] / GF_M_PER_TECU
                if prev_stec_rel is not None and prev_arc_t is not None:
                    dt_min = (pt["t_sec"] - prev_arc_t) / 60.0
                    rot = (stec_rel - prev_stec_rel) / dt_min if dt_min > 0 else None
                else:
                    rot = None
                rot_series.append((pt["t_sec"], rot))
                prev_stec_rel = stec_rel
                prev_arc_t = pt["t_sec"]

            for idx, pt in enumerate(arc):
                stec_raw = pt["gf_phase_m"] / GF_M_PER_TECU + level_offset_tecu
                mf, ipp_lat, ipp_lon = slm_mapping_and_ipp(
                    station_ecef_m,
                    pt["el_deg"],
                    pt["az_deg"],
                    shell_height_m=shell_height_m,
                )
                vtec_uncal = stec_raw / mf
                l1_delay_m = stec_raw * L1_M_PER_TECU
                cur_t = pt["t_sec"]
                rot_val = rot_series[idx][1]
                # Sliding window ROTI (std of ROT over [cur_t - roti_window_s, cur_t])
                win_rots = [
                    rv
                    for wt, rv in rot_series[: idx + 1]
                    if rv is not None and (cur_t - wt) <= roti_window_s + 1e-6
                ]
                roti_val: float | None = None
                if len(win_rots) >= 5:
                    mean_r = sum(win_rots) / len(win_rots)
                    var_r = sum((r - mean_r) ** 2 for r in win_rots) / (len(win_rots) - 1)
                    roti_val = math.sqrt(var_r)

                estimates.append(
                    IonosphericPointEstimate(
                        station_id=dataset.station_id,
                        satellite_id=sat,
                        epoch_iso=pt["epoch_iso"],
                        arc_id=arc_idx,
                        elevation_deg=pt["el_deg"],
                        azimuth_deg=pt["az_deg"],
                        ipp_lat_deg=ipp_lat,
                        ipp_lon_deg=ipp_lon,
                        slm_mapping_factor=mf,
                        gf_phase_m=pt["gf_phase_m"],
                        gf_code_m=pt["gf_code_m"],
                        code_pair_used=pt["code_pair"],
                        raw_stec_tecu=stec_raw,
                        bias_corrected_stec_tecu=None,
                        vtec_uncalibrated_tecu=vtec_uncal,
                        l1_slant_delay_uncalibrated_m=l1_delay_m,
                        rot_tecu_per_min=rot_val,
                        roti_tecu_per_min=roti_val,
                        dcb_status=DCB_UNAVAILABLE_STATUS,
                        cycle_slip_detected=bool(pt["slip"]),
                    )
                )

    summary = {
        "station_id": dataset.station_id,
        "satellites_processed": len(sats),
        "estimate_count": len(estimates),
        "arcs_retained": arcs_total,
        "arcs_short_dropped": arcs_short_dropped,
        "cycle_slips_gf": slips_gf,
        "cycle_slips_mw": slips_mw,
        "cycle_slips_lli_or_gap": slips_lli_gap,
        "dcb_status": DCB_UNAVAILABLE_STATUS,
        "shell_height_m": shell_height_m,
        "min_elevation_deg": min_elevation_deg,
    }
    return estimates, summary


def common_arc_sd_l1_iono(
    estimates_by_station: dict[str, list[IonosphericPointEstimate]],
    datum_station: str,
    *,
    min_common_arc_epochs: int = 4,
) -> tuple[dict[tuple[str, str, str], float], dict[str, Any]]:
    """Compute common-overlap pair-arc differential L1 slant ionosphere relative to datum.

    Unlike independent single-station arc detrending (which injects large median
    offsets whenever two stations have unequal arc spans), this routine:
    1. Matches ``(epoch, satellite)`` epochs simultaneously observed at both
       ``station`` and ``datum_station``;
    2. Segments pair-arcs whenever EITHER station starts a new slip-free arc;
    3. Subtracts the per-common-pair-arc median of ``GF_phase(station) - GF_phase(datum)``
       and scales by ``GF_TO_L1_FACTOR = 1 / (gamma - 1)``.

    Satellite DCBs cancel identically; residual receiver hardware bias is removed
    per common continuous arc alongside the double-difference ambiguity constant.
    """
    datum_map: dict[tuple[str, str], IonosphericPointEstimate] = {
        (e.epoch_iso, e.satellite_id): e for e in estimates_by_station.get(datum_station, [])
    }
    observed: dict[tuple[str, str, str], float] = {}
    pair_arcs_used = 0

    for sid, ests in sorted(estimates_by_station.items()):
        if sid == datum_station:
            for e in ests:
                observed[(e.epoch_iso, e.satellite_id, sid)] = 0.0
            continue
        by_sat_pair_arc: dict[tuple[str, int, int], list[tuple[str, float]]] = {}
        for e in ests:
            d_est = datum_map.get((e.epoch_iso, e.satellite_id))
            if d_est is None:
                continue
            sd_gf = e.gf_phase_m - d_est.gf_phase_m
            key = (e.satellite_id, e.arc_id, d_est.arc_id)
            by_sat_pair_arc.setdefault(key, []).append((e.epoch_iso, sd_gf))

        for (sat, _a1, _a2), pts in by_sat_pair_arc.items():
            if len(pts) < min_common_arc_epochs:
                continue
            pair_arcs_used += 1
            vals = sorted(v for _, v in pts)
            mid = len(vals) // 2
            med = vals[mid] if len(vals) % 2 == 1 else 0.5 * (vals[mid - 1] + vals[mid])
            for ep, sd_gf in pts:
                observed[(ep, sat, sid)] = (sd_gf - med) * GF_TO_L1_FACTOR

    return observed, {
        "datum_station": datum_station,
        "method": "COMMON_PAIR_ARC_MEDIAN_REMOVED_GF_SD_L1",
        "gamma_gps": GAMMA_GPS,
        "pair_arcs_used": pair_arcs_used,
        "sample_count": len(observed),
    }


def nighttime_leveled_sd_l1_iono(
    estimates_by_station: dict[str, list[IonosphericPointEstimate]],
    datum_station: str,
    *,
    nighttime_utc_hours: tuple[int, int] = (2, 5),
) -> tuple[dict[tuple[str, str, str], float], dict[str, Any]]:
    """Compute receiver-DCB-aligned differential L1 slant ionosphere via local nighttime floor.

    Across all GPS satellites, ``raw_stec(station) - raw_stec(datum)`` equals
    ``(STEC_true_station - STEC_true_datum) + (b_rx_station - b_rx_datum)``
    (satellite DCBs cancel identically). Estimating the single daily scalar
    receiver-DCB offset ``b_rx_station - b_rx_datum`` as the median vertical-mapped
    difference during pre-dawn local minimum (02:00-05:00 UTC in Nigeria / WAT+1)
    preserves full diurnal spatial ionospheric gradients across the day without
    removing the daytime mean per arc. Explicitly tagged experimental uncalibrated
    (no external IGS/CODE DCB product).
    """
    datum_map: dict[tuple[str, str], IonosphericPointEstimate] = {
        (e.epoch_iso, e.satellite_id): e for e in estimates_by_station.get(datum_station, [])
    }
    observed: dict[tuple[str, str, str], float] = {}
    rx_offsets_tecu: dict[str, float] = {datum_station: 0.0}
    h_lo, h_hi = nighttime_utc_hours

    for sid, ests in sorted(estimates_by_station.items()):
        if sid == datum_station:
            for e in ests:
                observed[(e.epoch_iso, e.satellite_id, sid)] = 0.0
            continue
        night_diffs: list[float] = []
        all_diffs: list[float] = []
        paired: list[tuple[IonosphericPointEstimate, IonosphericPointEstimate]] = []
        for e in ests:
            d_est = datum_map.get((e.epoch_iso, e.satellite_id))
            if d_est is None:
                continue
            paired.append((e, d_est))
            diff_tecu = e.raw_stec_tecu - d_est.raw_stec_tecu
            all_diffs.append(diff_tecu)
            hr = datetime.fromisoformat(e.epoch_iso).hour
            if h_lo <= hr < h_hi and e.elevation_deg >= 30.0 and d_est.elevation_deg >= 30.0:
                night_diffs.append(diff_tecu)
        ref_pool = sorted(night_diffs if len(night_diffs) >= 10 else all_diffs)
        if not ref_pool:
            continue
        mid = len(ref_pool) // 2
        rx_bias_tecu = (
            ref_pool[mid] if len(ref_pool) % 2 == 1 else 0.5 * (ref_pool[mid - 1] + ref_pool[mid])
        )
        rx_offsets_tecu[sid] = round(rx_bias_tecu, 4)
        for e, d_est in paired:
            sd_tecu = (e.raw_stec_tecu - d_est.raw_stec_tecu) - rx_bias_tecu
            observed[(e.epoch_iso, e.satellite_id, sid)] = sd_tecu * L1_M_PER_TECU

    return observed, {
        "datum_station": datum_station,
        "method": "NIGHTTIME_RX_BIAS_ALIGNED_PHASE_LEVELED_SD_L1",
        "dcb_status": "EXPERIMENTAL_NIGHTTIME_RX_PAIR_ALIGNMENT_NO_EXTERNAL_DCB",
        "nighttime_utc_hours": list(nighttime_utc_hours),
        "estimated_rx_pair_offsets_tecu": rx_offsets_tecu,
        "sample_count": len(observed),
    }


def to_atmospheric_estimates(
    points: list[IonosphericPointEstimate],
    *,
    source_file_sha256: str,
) -> list[AtmosphericEstimate]:
    """Convert ionospheric point estimates into canonical ``AtmosphericEstimate`` records."""
    out: list[AtmosphericEstimate] = []
    for p in points:
        prov = {
            "source_sha256": source_file_sha256,
            "arc_id": p.arc_id,
            "elevation_deg": round(p.elevation_deg, 3),
            "azimuth_deg": round(p.azimuth_deg, 3),
            "ipp_lat_deg": round(p.ipp_lat_deg, 4),
            "ipp_lon_deg": round(p.ipp_lon_deg, 4),
            "dcb_status": p.dcb_status,
        }
        out.append(
            AtmosphericEstimate(
                station_id=p.station_id,
                satellite_id=p.satellite_id,
                epoch_iso=p.epoch_iso,
                component=AtmosphericComponent.RAW_STEC_UNBIASED_UNAVAILABLE,
                value=p.raw_stec_tecu,
                units="TECU",
                estimation_method="phase_leveled_gf_stec_mw_gf_slip_detected",
                source_observations=("L1", "L2", *p.code_pair_used),
                model_version=IONO_MODEL_VERSION,
                quality_indicators={
                    "elevation_deg": round(p.elevation_deg, 2),
                    "slm_mf": round(p.slm_mapping_factor, 4),
                    "cycle_slip_detected": p.cycle_slip_detected,
                },
                uncertainty=None,
                provenance=prov,
                validation_status=ValidationStatus.TECHNICALLY_VALIDATED,
            )
        )
        if p.roti_tecu_per_min is not None:
            out.append(
                AtmosphericEstimate(
                    station_id=p.station_id,
                    satellite_id=p.satellite_id,
                    epoch_iso=p.epoch_iso,
                    component=AtmosphericComponent.ROTI_TECU_PER_MIN,
                    value=p.roti_tecu_per_min,
                    units="TECU/min",
                    estimation_method="5min_sliding_std_of_phase_rot_dcb_free",
                    source_observations=("L1", "L2"),
                    model_version=IONO_MODEL_VERSION,
                    quality_indicators={"elevation_deg": round(p.elevation_deg, 2)},
                    uncertainty=None,
                    provenance=prov,
                    validation_status=ValidationStatus.TECHNICALLY_VALIDATED,
                )
            )
    return out
