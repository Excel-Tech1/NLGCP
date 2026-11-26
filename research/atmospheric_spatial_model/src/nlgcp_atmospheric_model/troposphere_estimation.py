"""Tropospheric modelling, UNB3m climatology, and PRIDE PPP-AR ZTD validation (Phase 6 B2).

Distinguishes strictly between:
- Legacy standard-atmosphere prior (``0.12 m * exp(-h/2000)`` sea-level ZWD assumption);
- UNB3m (Leandro et al. 2006) latitude/DOY climatological Saastamoinen + Askne-Nordius
  ZHD/ZWD model (explicitly labelled MODELLED CLIMATOLOGY, NOT measured meteorology);
- Independent PPP-derived ZTD parsed from PRIDE PPP-AR ``ztd_*`` files
  (``ZTD = ZDD + ZWDini + ZWDcor``);
- Network-interpolated differential slant tropospheric corrections via Niell (1996)
  hydrostatic and wet mapping functions.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .atmospheric_schema import AtmosphericComponent, AtmosphericEstimate, ValidationStatus
from .metrics import prediction_metrics
from .provenance import sha256_file
from .troposphere import (
    a_priori_slant,
    ecef_to_geodetic,
    niell_hydrostatic_mapping,
    niell_wet_mapping,
)

TROPO_MODEL_VERSION = "phase6-tropo-unb3m-v2.0"
UNB3M_LABEL = (
    "MODELLED CLIMATOLOGY (UNB3m latitude/DOY table, Leandro et al. 2006) — "
    "NOT MEASURED STATION METEOROLOGY"
)

# Physical constants (Leandro et al. 2006, UNB3m neutral atmosphere model)
_K1 = 77.604  # K/mbar
_K2_PRIME = 16.6  # K/mbar (k2 - k1 * Rd/Rv)
_K3 = 377_600.0  # K^2/mbar
_RD = 287.054  # J/(kg*K)
_G0 = 9.80665  # m/s^2

# UNB3m Table 1: (lat_deg, P0_avg, T0_avg, RH_avg, beta_avg, lambda_avg,
#                 P0_amp, T0_amp, RH_amp, beta_amp, lambda_amp)
_UNB3M_TABLE: tuple[tuple[float, ...], ...] = (
    (15.0, 1013.25, 299.65, 75.0, 6.30e-3, 2.77, 0.00, 0.00, 0.0, 0.00e-3, 0.00),
    (30.0, 1017.25, 294.15, 80.0, 6.05e-3, 3.15, -3.75, 7.00, 0.0, 0.25e-3, 0.33),
    (45.0, 1015.75, 283.15, 76.0, 5.58e-3, 2.57, -2.25, 11.00, -1.0, 0.32e-3, 0.46),
    (60.0, 1011.75, 272.15, 77.5, 5.39e-3, 1.81, -1.75, 15.00, -2.5, 0.81e-3, 0.74),
    (75.0, 1013.00, 263.65, 82.5, 4.53e-3, 1.55, -0.50, 14.50, 2.5, 0.62e-3, 0.30),
)


@dataclass(frozen=True, slots=True)
class Unb3mTropoEstimate:
    """UNB3m climatological ZHD/ZWD/ZTD and optional Niell slant delay."""

    station_id: str
    epoch_iso: str
    doy: int
    lat_deg: float
    height_m: float
    pressure_hpa: float
    temperature_k: float
    rh_percent: float
    zhd_m: float
    zwd_m: float
    ztd_m: float
    elevation_deg: float | None = None
    slant_total_m: float | None = None
    meteorology_source: str = UNB3M_LABEL


@dataclass(frozen=True, slots=True)
class PrideZtdEpoch:
    """One epoch from a PRIDE PPP-AR ``ztd_*`` solution file."""

    station_id: str
    epoch_iso: str
    zhd_m: float
    zwd_init_m: float
    zwd_corr_m: float
    zwd_total_m: float
    ztd_total_m: float


def _interp_unb3m_params(lat_deg: float, doy: int) -> tuple[float, float, float, float, float]:
    """Interpolate UNB3m meteorological parameters for geodetic latitude and DOY."""
    abs_lat = abs(lat_deg)
    if abs_lat <= 15.0:
        row_lo = row_hi = _UNB3M_TABLE[0]
        frac = 0.0
    elif abs_lat >= 75.0:
        row_lo = row_hi = _UNB3M_TABLE[-1]
        frac = 0.0
    else:
        idx = int((abs_lat - 15.0) // 15.0)
        row_lo = _UNB3M_TABLE[idx]
        row_hi = _UNB3M_TABLE[idx + 1]
        frac = (abs_lat - row_lo[0]) / (row_hi[0] - row_lo[0])

    doy_min = 28.0 if lat_deg >= 0.0 else 211.0
    seasonal = math.cos(2.0 * math.pi * (doy - doy_min) / 365.25)

    values: list[float] = []
    for k in range(5):
        avg = row_lo[1 + k] + frac * (row_hi[1 + k] - row_lo[1 + k])
        amp = row_lo[6 + k] + frac * (row_hi[6 + k] - row_lo[6 + k])
        values.append(avg - amp * seasonal)
    return values[0], values[1], values[2], values[3], values[4]


def _saturation_vapor_pressure_hpa(temp_k: float) -> float:
    """Clausius-Clapeyron / UNB3m saturation water vapor pressure (hPa / mbar)."""
    temp_c = temp_k - 273.15
    return 6.1121 * math.exp((18.678 - temp_c / 234.5) * (temp_c / (257.14 + temp_c)))


def unb3m_zenith_delays(
    station_ecef_m: tuple[float, float, float],
    doy: int,
    *,
    station_id: str = "",
    epoch_iso: str = "",
    elevation_deg: float | None = None,
) -> Unb3mTropoEstimate:
    """Compute UNB3m climatological ZHD, ZWD, ZTD and optional Niell slant delay."""
    if not 1 <= doy <= 366:
        raise ValueError(f"doy must be in [1, 366], got {doy}")
    lat_rad, _, height_m = ecef_to_geodetic(station_ecef_m)
    lat_deg = math.degrees(lat_rad)
    h = max(0.0, height_m)
    p0, t0, rh, beta, lam = _interp_unb3m_params(lat_deg, doy)
    gm = 9.784 * (1.0 - 2.66e-3 * math.cos(2.0 * lat_rad) - 2.8e-7 * h)
    # Height scaling factor
    lapse_ratio = max(0.1, 1.0 - beta * h / t0)
    zhd_0 = (1.0e-6 * _K1 * _RD / gm) * p0
    zhd = zhd_0 * (lapse_ratio ** (_G0 / (_RD * beta)))

    # Mean temperature of water vapor Tm and surface vapor pressure e0
    e_sat = _saturation_vapor_pressure_hpa(t0)
    e0 = (rh / 100.0) * e_sat
    tm = t0 * (1.0 - (beta * _RD) / (gm * (lam + 1.0)))
    zwd_0 = (1.0e-6 * (tm * _K2_PRIME + _K3) * _RD / (gm * (lam + 1.0) - beta * _RD)) * (e0 / t0)
    zwd = zwd_0 * (lapse_ratio ** (((lam + 1.0) * _G0 / (_RD * beta)) - 1.0))

    slant: float | None = None
    if elevation_deg is not None:
        m_h = niell_hydrostatic_mapping(elevation_deg, lat_rad, h, doy)
        m_w = niell_wet_mapping(elevation_deg, lat_rad)
        slant = zhd * m_h + zwd * m_w

    return Unb3mTropoEstimate(
        station_id=station_id,
        epoch_iso=epoch_iso,
        doy=doy,
        lat_deg=lat_deg,
        height_m=height_m,
        pressure_hpa=p0 * (lapse_ratio ** (_G0 / (_RD * beta))),
        temperature_k=t0 - beta * h,
        rh_percent=rh,
        zhd_m=zhd,
        zwd_m=zwd,
        ztd_m=zhd + zwd,
        elevation_deg=elevation_deg,
        slant_total_m=slant,
    )


def parse_pride_ztd(
    path: Path, *, station_id: str | None = None
) -> tuple[list[PrideZtdEpoch], str]:
    """Parse a PRIDE PPP-AR ``ztd_*`` file into typed ZHD/ZWD/ZTD epochs + SHA-256."""
    digest = sha256_file(path)
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    header_station = station_id or ""
    in_body = False
    records: list[PrideZtdEpoch] = []
    for line in lines:
        if not in_body:
            if not header_station and line[60:].strip() == "STATION":
                header_station = line[:60].strip().upper()
            if "END OF HEADER" in line:
                in_body = True
            continue
        stripped = line.strip()
        if not stripped or stripped.startswith("*"):
            continue
        parts = stripped.split()
        if len(parts) < 9:
            continue
        try:
            yr, mo, dy, hr, mn = (int(parts[i]) for i in range(5))
            sec = float(parts[5])
            zdd = float(parts[6])
            zwd_ini = float(parts[7])
            zwd_cor = float(parts[8])
        except ValueError:
            continue
        whole = int(sec)
        micro = int(round((sec - whole) * 1_000_000))
        ep = f"{yr:04d}-{mo:02d}-{dy:02d}T{hr:02d}:{mn:02d}:{whole:02d}.{micro:06d}"
        zwd_tot = zwd_ini + zwd_cor
        records.append(
            PrideZtdEpoch(
                station_id=header_station,
                epoch_iso=ep,
                zhd_m=zdd,
                zwd_init_m=zwd_ini,
                zwd_corr_m=zwd_cor,
                zwd_total_m=zwd_tot,
                ztd_total_m=zdd + zwd_tot,
            )
        )
    return records, digest


def evaluate_tropo_against_pride(
    pride_by_station: dict[str, list[PrideZtdEpoch]],
    coords_by_station: dict[str, tuple[float, float, float]],
    *,
    doy: int,
) -> dict[str, Any]:
    """Benchmark legacy 0.12 m standard prior vs UNB3m climatology against PRIDE PPP-AR ZTD."""
    per_station: dict[str, Any] = {}
    legacy_ztd_res: list[float] = []
    legacy_zwd_res: list[float] = []
    unb3m_ztd_res: list[float] = []
    unb3m_zwd_res: list[float] = []
    unb3m_zhd_res: list[float] = []

    for sid in sorted(pride_by_station):
        if sid not in coords_by_station or not pride_by_station[sid]:
            continue
        xyz = coords_by_station[sid]
        legacy_term = a_priori_slant(
            station_id=sid,
            satellite_id="G01",
            epoch_iso=pride_by_station[sid][0].epoch_iso,
            elevation_deg=90.0,
            station_ecef_m=xyz,
            doy=doy,
        )
        unb = unb3m_zenith_delays(xyz, doy, station_id=sid)
        st_leg_ztd: list[float] = []
        st_leg_zwd: list[float] = []
        st_unb_ztd: list[float] = []
        st_unb_zwd: list[float] = []
        st_unb_zhd: list[float] = []
        pride_ztds: list[float] = []
        pride_zwds: list[float] = []
        for ep in pride_by_station[sid]:
            pride_ztds.append(ep.ztd_total_m)
            pride_zwds.append(ep.zwd_total_m)
            leg_ztd = legacy_term.zenith_hydrostatic_m + legacy_term.zenith_wet_m
            r_leg_ztd = leg_ztd - ep.ztd_total_m
            r_leg_zwd = legacy_term.zenith_wet_m - ep.zwd_total_m
            r_unb_ztd = unb.ztd_m - ep.ztd_total_m
            r_unb_zwd = unb.zwd_m - ep.zwd_total_m
            r_unb_zhd = unb.zhd_m - ep.zhd_m
            st_leg_ztd.append(r_leg_ztd)
            st_leg_zwd.append(r_leg_zwd)
            st_unb_ztd.append(r_unb_ztd)
            st_unb_zwd.append(r_unb_zwd)
            st_unb_zhd.append(r_unb_zhd)

        legacy_ztd_res.extend(st_leg_ztd)
        legacy_zwd_res.extend(st_leg_zwd)
        unb3m_ztd_res.extend(st_unb_ztd)
        unb3m_zwd_res.extend(st_unb_zwd)
        unb3m_zhd_res.extend(st_unb_zhd)

        per_station[sid] = {
            "epoch_count": len(pride_ztds),
            "height_m": round(unb.height_m, 2),
            "lat_deg": round(unb.lat_deg, 4),
            "pride_mean_ztd_m": round(sum(pride_ztds) / len(pride_ztds), 4),
            "pride_mean_zwd_m": round(sum(pride_zwds) / len(pride_zwds), 4),
            "legacy_ztd_m": round(
                legacy_term.zenith_hydrostatic_m + legacy_term.zenith_wet_m, 4
            ),
            "legacy_zwd_m": round(legacy_term.zenith_wet_m, 4),
            "unb3m_ztd_m": round(unb.ztd_m, 4),
            "unb3m_zwd_m": round(unb.zwd_m, 4),
            "legacy_ztd_rmse_m": prediction_metrics(st_leg_ztd)["rmse_m"],
            "unb3m_ztd_rmse_m": prediction_metrics(st_unb_ztd)["rmse_m"],
            "legacy_zwd_rmse_m": prediction_metrics(st_leg_zwd)["rmse_m"],
            "unb3m_zwd_rmse_m": prediction_metrics(st_unb_zwd)["rmse_m"],
        }

    return {
        "doy": doy,
        "reference_source": "PRIDE PPP-AR 3.2.8 independent ZTD estimates",
        "per_station": per_station,
        "aggregate": {
            "legacy_012m_prior_ztd": prediction_metrics(legacy_ztd_res),
            "legacy_012m_prior_zwd": prediction_metrics(legacy_zwd_res),
            "unb3m_climatology_ztd": prediction_metrics(unb3m_ztd_res),
            "unb3m_climatology_zwd": prediction_metrics(unb3m_zwd_res),
            "unb3m_climatology_zhd": prediction_metrics(unb3m_zhd_res),
        },
        "label": UNB3M_LABEL,
    }


def slant_tropo_from_ztd(
    *,
    station_ecef_m: tuple[float, float, float],
    elevation_deg: float,
    doy: int,
    zhd_m: float,
    zwd_m: float,
) -> float:
    """Map ZHD and ZWD to slant tropospheric delay (m) via Niell (1996)."""
    lat_rad, _, height_m = ecef_to_geodetic(station_ecef_m)
    h = max(0.0, height_m)
    m_h = niell_hydrostatic_mapping(elevation_deg, lat_rad, h, doy)
    m_w = niell_wet_mapping(elevation_deg, lat_rad)
    return zhd_m * m_h + zwd_m * m_w


def pride_to_atmospheric_estimates(
    epochs: list[PrideZtdEpoch], *, file_sha256: str
) -> list[AtmosphericEstimate]:
    """Convert PRIDE PPP-AR ZTD records into canonical ``AtmosphericEstimate`` records."""
    return [
        AtmosphericEstimate(
            station_id=ep.station_id,
            satellite_id=None,
            epoch_iso=ep.epoch_iso,
            component=AtmosphericComponent.ZTD_PPP_PRIDE,
            value=ep.ztd_total_m,
            units="m",
            estimation_method="PRIDE_PPP_AR_3.2.8_ZDD_plus_ZWDini_plus_ZWDcor",
            source_observations=("L1", "L2", "C1", "P2"),
            model_version="PRIDE-PPP-AR-3.2.8",
            quality_indicators={
                "zhd_m": round(ep.zhd_m, 5),
                "zwd_total_m": round(ep.zwd_total_m, 5),
            },
            uncertainty=None,
            provenance={"pride_ztd_sha256": file_sha256},
            validation_status=ValidationStatus.SCIENTIFICALLY_VALIDATED,
        )
        for ep in epochs
    ]
