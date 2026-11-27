"""Causal epoch-by-epoch tropospheric ZWD residual filter & spatial/gradient metrics (B-05).

Separates strictly between:
- UNB3m (Leandro et al. 2006) climatological ZHD/ZWD prior (MODELLED CLIMATOLOGY);
- Observed/estimated ZTD/ZWD (e.g., from PRIDE PPP-AR or causal network estimation);
- Causal exponentially-weighted ZWD residual state with bounded memory, explicit
  variance, time-gap relaxation toward the UNB3m climatological prior, and
  station-health gating (strictly causal: epoch ``k`` uses only epochs ``<= k``).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime

from .troposphere_estimation import UNB3M_LABEL, slant_tropo_from_ztd, unb3m_zenith_delays

CAUSAL_TROPO_VERSION = "b05-causal-tropo-v1.0"


@dataclass(frozen=True, slots=True)
class CausalTropoState:
    """Explicit causal filter state for one station at epoch ``k``."""

    station_id: str
    epoch_iso: str
    doy: int
    unb3m_zhd_m: float
    unb3m_zwd_m: float
    residual_zwd_est_m: float
    residual_zwd_sigma_m: float
    causal_zwd_m: float
    causal_ztd_m: float
    sample_count: int
    healthy: bool
    stale: bool
    gap_s: float
    meteorology_source: str = UNB3M_LABEL


class CausalTropoZwdFilter:
    """Strictly causal epoch-by-epoch ZWD residual estimator around UNB3m prior.

    Models ``ZWD(t) = ZWD_UNB3m(lat, h, doy) + delta_ZWD(t)`` where ``delta_ZWD(t)``
    evolves as a damped random-walk / EWMA filter that decays exponentially back toward
    ``0.0`` (i.e. pure UNB3m) across data gaps and raises variance when unhealthy or stale.
    """

    def __init__(
        self,
        *,
        station_id: str,
        station_ecef_m: tuple[float, float, float],
        tau_correlation_s: float = 7200.0,
        process_sigma_m: float = 0.015,
        prior_sigma_m: float = 0.080,
        max_gap_before_stale_s: float = 900.0,
    ) -> None:
        self.station_id = station_id
        self.station_ecef_m = station_ecef_m
        self.tau_correlation_s = tau_correlation_s
        self.process_sigma_m = process_sigma_m
        self.prior_sigma_m = prior_sigma_m
        self.max_gap_before_stale_s = max_gap_before_stale_s

        self._last_t_s: float | None = None
        self._res_m: float = 0.0
        self._var_m2: float = prior_sigma_m**2
        self._count: int = 0

    def predict_at(self, epoch_iso: str, *, doy: int) -> CausalTropoState:
        """Predict causal ZWD/ZTD at ``epoch_iso`` using ONLY state from epochs ``< t``."""
        t_s = datetime.fromisoformat(epoch_iso).timestamp()
        unb = unb3m_zenith_delays(self.station_ecef_m, doy, station_id=self.station_id)
        if self._last_t_s is None:
            return CausalTropoState(
                station_id=self.station_id,
                epoch_iso=epoch_iso,
                doy=doy,
                unb3m_zhd_m=unb.zhd_m,
                unb3m_zwd_m=unb.zwd_m,
                residual_zwd_est_m=0.0,
                residual_zwd_sigma_m=self.prior_sigma_m,
                causal_zwd_m=unb.zwd_m,
                causal_ztd_m=unb.ztd_m,
                sample_count=0,
                healthy=True,
                stale=True,
                gap_s=0.0,
            )
        dt = max(0.0, t_s - self._last_t_s)
        phi = math.exp(-dt / max(1.0, self.tau_correlation_s))
        pred_res = phi * self._res_m
        # Stationary variance approaches prior_sigma_m^2 as dt -> inf
        q_step = (1.0 - phi * phi) * (self.prior_sigma_m**2)
        pred_var = (phi * phi) * self._var_m2 + q_step
        stale = dt > self.max_gap_before_stale_s
        zwd_pred = max(0.0, unb.zwd_m + pred_res)
        return CausalTropoState(
            station_id=self.station_id,
            epoch_iso=epoch_iso,
            doy=doy,
            unb3m_zhd_m=unb.zhd_m,
            unb3m_zwd_m=unb.zwd_m,
            residual_zwd_est_m=pred_res,
            residual_zwd_sigma_m=math.sqrt(max(0.0, pred_var)),
            causal_zwd_m=zwd_pred,
            causal_ztd_m=unb.zhd_m + zwd_pred,
            sample_count=self._count,
            healthy=not stale,
            stale=stale,
            gap_s=dt,
        )

    def update(
        self,
        epoch_iso: str,
        *,
        doy: int,
        observed_zwd_m: float | None,
        obs_sigma_m: float = 0.008,
        station_healthy: bool = True,
    ) -> CausalTropoState:
        """Causal scalar Kalman update using current-epoch observation (if healthy)."""
        t_s = datetime.fromisoformat(epoch_iso).timestamp()
        unb = unb3m_zenith_delays(self.station_ecef_m, doy, station_id=self.station_id)

        if self._last_t_s is None:
            dt = 0.0
            pred_res = self._res_m
            pred_var = self._var_m2
        else:
            dt = max(0.0, t_s - self._last_t_s)
            phi = math.exp(-dt / max(1.0, self.tau_correlation_s))
            pred_res = phi * self._res_m
            q_step = (1.0 - phi * phi) * (self.process_sigma_m**2 + 0.25 * (self.prior_sigma_m**2))
            pred_var = min(self.prior_sigma_m**2, (phi * phi) * self._var_m2 + q_step)

        stale = dt > self.max_gap_before_stale_s and self._last_t_s is not None
        if station_healthy and observed_zwd_m is not None and math.isfinite(observed_zwd_m):
            meas_res = observed_zwd_m - unb.zwd_m
            r_var = max(1e-8, obs_sigma_m * obs_sigma_m)
            gain = pred_var / (pred_var + r_var)
            self._res_m = pred_res + gain * (meas_res - pred_res)
            self._var_m2 = max(1e-8, (1.0 - gain) * pred_var)
            self._last_t_s = t_s
            self._count += 1
            stale = False
        else:
            # No healthy update -> retain decayed state with inflated uncertainty
            self._res_m = pred_res
            self._var_m2 = pred_var
            if self._last_t_s is not None:
                stale = True

        zwd_est = max(0.0, unb.zwd_m + self._res_m)
        return CausalTropoState(
            station_id=self.station_id,
            epoch_iso=epoch_iso,
            doy=doy,
            unb3m_zhd_m=unb.zhd_m,
            unb3m_zwd_m=unb.zwd_m,
            residual_zwd_est_m=self._res_m,
            residual_zwd_sigma_m=math.sqrt(max(0.0, self._var_m2)),
            causal_zwd_m=zwd_est,
            causal_ztd_m=unb.zhd_m + zwd_est,
            sample_count=self._count,
            healthy=station_healthy,
            stale=stale,
            gap_s=dt,
        )

    def slant_delay_m(
        self, state: CausalTropoState, *, elevation_deg: float
    ) -> float:
        """Map causal ZHD/ZWD state to slant tropospheric delay (m) via Niell."""
        return slant_tropo_from_ztd(
            station_ecef_m=self.station_ecef_m,
            elevation_deg=elevation_deg,
            doy=state.doy,
            zhd_m=state.unb3m_zhd_m,
            zwd_m=state.causal_zwd_m,
        )
