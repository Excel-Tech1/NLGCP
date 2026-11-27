"""Causal epoch-by-epoch ionospheric filter, CODE DCB/SINEX BIAS, and IONEX GIM parser (B-05).

Upgrades Phase 6 atmospheric modelling from offline full-arc leveling to strictly causal
real-time-compatible epoch-by-epoch estimation while preserving complete scientific
traceability:

- **Strict Causality**: Every output at epoch ``k`` depends exclusively on observations
  at epochs ``<= k`` (verified by prefix-invariance tests).
- **External Bias Calibration**: Parses authentic CODE monthly ``P1P2``/``P1C1`` ``.DCB``
  files and SINEX BIAS 1.00 ``.BIA`` (``DSB``/``OSB``) files with SHA-256 provenance.
  Never fabricates unavailable biases.
- **IONEX GIM Validation**: Parses IONEX 1.0/1.1 ``TEC`` and ``RMS`` maps and applies
  Schaer et al. (1998) sun-fixed rotated-longitude bilinear + linear temporal interpolation.
- **Honest Uncertainty**: Tracks online carrier-to-code leveling variance and formal
  convergence sigma per satellite arc.
"""

from __future__ import annotations

import gzip
import math
import subprocess
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .constants import SPEED_OF_LIGHT_M_S
from .ionosphere_estimation import (
    DEFAULT_SLM_HEIGHT_M,
    GF_M_PER_TECU,
    L1_M_PER_TECU,
    melbourne_wubbena_m,
    slm_mapping_and_ipp,
)
from .observations import GPS_L1_WAVELENGTH_M, GPS_L2_WAVELENGTH_M, SatObs
from .provenance import sha256_file

CAUSAL_IONO_VERSION = "b05-causal-iono-v1.0"
NS_TO_M = 1e-9 * SPEED_OF_LIGHT_M_S
NS_TO_TECU = NS_TO_M / GF_M_PER_TECU


def _read_text_auto(path: Path) -> str:
    """Read plain text, .gz, or Unix-compress .Z file read-only."""
    if path.suffix == ".gz":
        with gzip.open(path, "rt", encoding="latin1", errors="replace") as f:
            return f.read()
    if path.suffix == ".Z":
        proc = subprocess.run(
            ["gzip", "-dc", str(path)], capture_output=True, check=False, timeout=30
        )
        if proc.returncode != 0:
            raise RuntimeError(f"Failed to decompress {path}")
        return proc.stdout.decode("latin1", errors="replace")
    return path.read_text(encoding="latin1", errors="replace")


@dataclass(frozen=True, slots=True)
class BiasProductTable:
    """Parsed external satellite differential code bias table with provenance."""

    product_type: str
    source_path: str
    sha256: str
    sat_bias_ns: dict[str, float]
    sat_rms_ns: dict[str, float]


def parse_code_monthly_dcb(path: Path, product_type: str) -> BiasProductTable:
    """Parse CODE monthly ``P1P2*.DCB`` or ``P1C1*.DCB`` satellite biases (ns)."""
    digest = sha256_file(path)
    text = _read_text_auto(path)
    biases: dict[str, float] = {}
    rms_map: dict[str, float] = {}
    in_table = False
    for line in text.splitlines():
        if line.startswith("***"):
            in_table = True
            continue
        if not in_table:
            continue
        s = line.strip()
        if not s:
            continue
        # Satellite rows have PRN in cols 0..3 and blank station name in cols 6..20
        prn = line[:3].strip()
        station = line[6:20].strip() if len(line) >= 20 else ""
        if not prn or station or len(prn) != 3 or prn[0] not in "GRECJ":
            continue
        parts = line[20:].split()
        if len(parts) >= 2:
            try:
                biases[prn] = float(parts[0])
                rms_map[prn] = float(parts[1])
            except ValueError:
                continue
    return BiasProductTable(
        product_type=product_type,
        source_path=str(path),
        sha256=digest,
        sat_bias_ns=biases,
        sat_rms_ns=rms_map,
    )


def parse_sinex_dsb(
    path: Path,
    *,
    obs1: str,
    obs2: str,
    constellation: str = "G",
) -> BiasProductTable:
    """Parse SINEX BIAS 1.00 ``DSB`` records matching ``(obs1, obs2)`` for satellites."""
    digest = sha256_file(path)
    text = _read_text_auto(path)
    biases: dict[str, float] = {}
    rms_map: dict[str, float] = {}
    in_sol = False
    for line in text.splitlines():
        if line.startswith("+BIAS/SOLUTION"):
            in_sol = True
            continue
        if line.startswith("-BIAS/SOLUTION"):
            break
        if not in_sol or line.startswith("*"):
            continue
        if not line.startswith(" DSB "):
            continue
        parts = line.split()
        # DSB SVN PRN [STATION] OBS1 OBS2 START END UNIT VALUE STD
        # Satellite rows have no STATION token -> len == 10
        if len(parts) != 10:
            continue
        prn, o1, o2, unit = parts[2], parts[3], parts[4], parts[7]
        if not prn.startswith(constellation) or unit.lower() != "ns":
            continue
        if o1 == obs1 and o2 == obs2:
            biases[prn] = float(parts[8])
            rms_map[prn] = float(parts[9])
        elif o1 == obs2 and o2 == obs1:
            biases[prn] = -float(parts[8])
            rms_map[prn] = float(parts[9])
    return BiasProductTable(
        product_type=f"SINEX_DSB_{obs1}_{obs2}",
        source_path=str(path),
        sha256=digest,
        sat_bias_ns=biases,
        sat_rms_ns=rms_map,
    )


def parse_sinex_osb_pair_diff(
    path: Path,
    *,
    obs1: str,
    obs2: str,
    constellation: str = "G",
) -> BiasProductTable:
    """Compute satellite ``DSB(obs1, obs2) = OSB(obs1) - OSB(obs2)`` from SINEX OSB."""
    digest = sha256_file(path)
    text = _read_text_auto(path)
    osb1: dict[str, tuple[float, float]] = {}
    osb2: dict[str, tuple[float, float]] = {}
    in_sol = False
    for line in text.splitlines():
        if line.startswith("+BIAS/SOLUTION"):
            in_sol = True
            continue
        if line.startswith("-BIAS/SOLUTION"):
            break
        if not in_sol or line.startswith("*") or not line.startswith(" OSB "):
            continue
        parts = line.split()
        # OSB SVN PRN OBS1 START END UNIT VALUE STD -> len == 9 for satellite rows
        if len(parts) != 9:
            continue
        prn, o1, unit = parts[2], parts[3], parts[6]
        if not prn.startswith(constellation) or unit.lower() != "ns":
            continue
        val, std_v = float(parts[7]), float(parts[8])
        if o1 == obs1:
            osb1[prn] = (val, std_v)
        elif o1 == obs2:
            osb2[prn] = (val, std_v)
    biases: dict[str, float] = {}
    rms_map: dict[str, float] = {}
    for prn in sorted(set(osb1) & set(osb2)):
        biases[prn] = osb1[prn][0] - osb2[prn][0]
        rms_map[prn] = math.hypot(osb1[prn][1], osb2[prn][1])
    return BiasProductTable(
        product_type=f"SINEX_OSB_DIFF_{obs1}_{obs2}",
        source_path=str(path),
        sha256=digest,
        sat_bias_ns=biases,
        sat_rms_ns=rms_map,
    )


def combine_code_p1p2_p1c1_to_c1p2(
    p1p2: BiasProductTable, p1c1: BiasProductTable
) -> dict[str, float]:
    """Compute satellite ``DSB(C1, P2) = DCB(P1-P2) - DCB(P1-C1)`` in nanoseconds."""
    out: dict[str, float] = {}
    for prn in sorted(set(p1p2.sat_bias_ns) & set(p1c1.sat_bias_ns)):
        out[prn] = p1p2.sat_bias_ns[prn] - p1c1.sat_bias_ns[prn]
    return out


@dataclass(frozen=True, slots=True)
class IonexMap:
    """Single IONEX epoch 2D grid (lat_idx x lon_idx) in TECU."""

    epoch_s: float
    epoch_iso: str
    values: tuple[tuple[float, ...], ...]


@dataclass(frozen=True, slots=True)
class IonexGrid:
    """Parsed IONEX 1.0/1.1 Global Ionosphere Map with Schaer (1998) interpolation."""

    source_path: str
    sha256: str
    base_radius_km: float
    shell_height_km: float
    lat1: float
    lat2: float
    dlat: float
    lon1: float
    lon2: float
    dlon: float
    exponent: int
    tec_maps: tuple[IonexMap, ...]
    rms_maps: tuple[IonexMap, ...]

    def _bilinear_single_map(self, grid: IonexMap, lat_deg: float, lon_deg: float) -> float | None:
        # Wrap longitude into [lon1, lon2]
        lon = lon_deg
        while lon < self.lon1:
            lon += 360.0
        while lon > self.lon2:
            lon -= 360.0
        n_lat = len(grid.values)
        n_lon = len(grid.values[0])
        fi = (lat_deg - self.lat1) / self.dlat
        fj = (lon - self.lon1) / self.dlon
        if fi < 0.0 or fi > n_lat - 1 or fj < 0.0 or fj > n_lon - 1:
            return None
        i0 = min(n_lat - 2, max(0, int(math.floor(fi))))
        j0 = min(n_lon - 2, max(0, int(math.floor(fj))))
        p = fi - i0
        q = fj - j0
        v00 = grid.values[i0][j0]
        v01 = grid.values[i0][j0 + 1]
        v10 = grid.values[i0 + 1][j0]
        v11 = grid.values[i0 + 1][j0 + 1]
        if any(math.isnan(v) for v in (v00, v01, v10, v11)):
            return None
        return (
            (1.0 - p) * (1.0 - q) * v00
            + (1.0 - p) * q * v01
            + p * (1.0 - q) * v10
            + p * q * v11
        )

    def interpolate_vtec(
        self, lat_deg: float, lon_deg: float, epoch_iso: str
    ) -> tuple[float | None, float | None]:
        """Interpolate VTEC (TECU) and optional RMS using sun-fixed rotated longitude."""
        if not self.tec_maps:
            return None, None
        t_s = datetime.fromisoformat(epoch_iso).timestamp()
        # Find bracketing maps
        idx = 0
        for i in range(len(self.tec_maps) - 1):
            if self.tec_maps[i].epoch_s <= t_s <= self.tec_maps[i + 1].epoch_s:
                idx = i
                break
        else:
            if t_s < self.tec_maps[0].epoch_s:
                v = self._bilinear_single_map(self.tec_maps[0], lat_deg, lon_deg)
                r = (
                    self._bilinear_single_map(self.rms_maps[0], lat_deg, lon_deg)
                    if self.rms_maps
                    else None
                )
                return v, r
            v = self._bilinear_single_map(self.tec_maps[-1], lat_deg, lon_deg)
            r = (
                self._bilinear_single_map(self.rms_maps[-1], lat_deg, lon_deg)
                if self.rms_maps
                else None
            )
            return v, r

        m0 = self.tec_maps[idx]
        m1 = self.tec_maps[idx + 1]
        dt = m1.epoch_s - m0.epoch_s
        if dt <= 0.0:
            return self._bilinear_single_map(m0, lat_deg, lon_deg), None
        w1 = (t_s - m0.epoch_s) / dt
        w0 = 1.0 - w1
        if w1 <= 1e-12:
            v = self._bilinear_single_map(m0, lat_deg, lon_deg)
            r = (
                self._bilinear_single_map(self.rms_maps[idx], lat_deg, lon_deg)
                if len(self.rms_maps) == len(self.tec_maps)
                else None
            )
            return v, r
        if w0 <= 1e-12:
            v = self._bilinear_single_map(m1, lat_deg, lon_deg)
            r = (
                self._bilinear_single_map(self.rms_maps[idx + 1], lat_deg, lon_deg)
                if len(self.rms_maps) == len(self.tec_maps)
                else None
            )
            return v, r
        # Sun-fixed longitude rotation (Schaer et al. 1998, Section 3): 360 deg / 86400 s
        lon0 = lon_deg + (t_s - m0.epoch_s) * (360.0 / 86400.0)
        lon1 = lon_deg + (t_s - m1.epoch_s) * (360.0 / 86400.0)
        v0 = self._bilinear_single_map(m0, lat_deg, lon0)
        v1 = self._bilinear_single_map(m1, lat_deg, lon1)
        if v0 is None or v1 is None:
            return None, None
        vtec = w0 * v0 + w1 * v1
        rms_val: float | None = None
        if len(self.rms_maps) == len(self.tec_maps):
            r0 = self._bilinear_single_map(self.rms_maps[idx], lat_deg, lon0)
            r1 = self._bilinear_single_map(self.rms_maps[idx + 1], lat_deg, lon1)
            if r0 is not None and r1 is not None:
                rms_val = w0 * r0 + w1 * r1
        return vtec, rms_val


def parse_ionex(path: Path) -> IonexGrid:
    """Parse an IONEX 1.0/1.1 file (.11I.Z, .INX.gz, or plain) into ``IonexGrid``."""
    digest = sha256_file(path)
    lines = _read_text_auto(path).splitlines()
    base_radius_km = 6371.0
    shell_height_km = 450.0
    lat1, lat2, dlat = 87.5, -87.5, -2.5
    lon1, lon2, dlon = -180.0, 180.0, 5.0
    exponent = -1

    idx = 0
    while idx < len(lines):
        line = lines[idx]
        lbl = line[60:].strip()
        if lbl == "BASE RADIUS":
            base_radius_km = float(line[:60].split()[0])
        elif lbl == "HGT1 / HGT2 / DHGT":
            shell_height_km = float(line[:60].split()[0])
        elif lbl == "LAT1 / LAT2 / DLAT":
            p = line[:60].split()
            lat1, lat2, dlat = float(p[0]), float(p[1]), float(p[2])
        elif lbl == "LON1 / LON2 / DLON":
            p = line[:60].split()
            lon1, lon2, dlon = float(p[0]), float(p[1]), float(p[2])
        elif lbl == "EXPONENT":
            exponent = int(line[:60].split()[0])
        elif lbl == "END OF HEADER":
            idx += 1
            break
        idx += 1

    scale = 10.0**exponent
    n_lon = int(round((lon2 - lon1) / dlon)) + 1
    tec_maps: list[IonexMap] = []
    rms_maps: list[IonexMap] = []

    while idx < len(lines):
        line = lines[idx]
        lbl = line[60:].strip()
        if lbl in ("START OF TEC MAP", "START OF RMS MAP"):
            is_tec = lbl == "START OF TEC MAP"
            idx += 1
            ep_iso = ""
            ep_s = 0.0
            rows: list[tuple[float, ...]] = []
            while idx < len(lines):
                ln = lines[idx]
                sub_lbl = ln[60:].strip()
                if sub_lbl in ("END OF TEC MAP", "END OF RMS MAP"):
                    idx += 1
                    break
                if sub_lbl == "EPOCH OF CURRENT MAP":
                    parts = [int(float(x)) for x in ln[:60].split()[:6]]
                    yr, mo, dy, hr, mn, sc = parts
                    # Handle 24:00:00 if ever present
                    if hr == 24:
                        dt_obj = datetime(yr, mo, dy, 0, mn, sc)
                        ep_s = dt_obj.timestamp() + 86400.0
                    else:
                        dt_obj = datetime(yr, mo, dy, hr, mn, sc)
                        ep_s = dt_obj.timestamp()
                    ep_iso = f"{yr:04d}-{mo:02d}-{dy:02d}T{hr:02d}:{mn:02d}:{sc:02d}"
                    idx += 1
                elif sub_lbl == "LAT/LON1/LON2/DLON/H":
                    idx += 1
                    vals: list[float] = []
                    while len(vals) < n_lon and idx < len(lines):
                        for tok in lines[idx].split():
                            iv = int(tok)
                            vals.append(math.nan if iv == 9999 else iv * scale)
                        idx += 1
                    rows.append(tuple(vals[:n_lon]))
                else:
                    idx += 1
            imap = IonexMap(epoch_s=ep_s, epoch_iso=ep_iso, values=tuple(rows))
            if is_tec:
                tec_maps.append(imap)
            else:
                rms_maps.append(imap)
        else:
            idx += 1

    return IonexGrid(
        source_path=str(path),
        sha256=digest,
        base_radius_km=base_radius_km,
        shell_height_km=shell_height_km,
        lat1=lat1,
        lat2=lat2,
        dlat=dlat,
        lon1=lon1,
        lon2=lon2,
        dlon=dlon,
        exponent=exponent,
        tec_maps=tuple(tec_maps),
        rms_maps=tuple(rms_maps),
    )


@dataclass
class _CausalSatState:
    arc_id: int = 0
    arc_epochs: int = 0
    prev_t_s: float | None = None
    prev_gf_m: float | None = None
    mw_n: int = 0
    mw_mean: float = 0.0
    mw_m2: float = 0.0
    # Recursive elevation-weighted leveling: offset = weighted_mean(stec_code - stec_phase_rel)
    w_sum: float = 0.0
    w2_sum: float = 0.0
    level_mean_tecu: float = 0.0
    level_m2_tecu2: float = 0.0
    rot_history: deque[tuple[float, float]] = field(default_factory=deque)


@dataclass(frozen=True, slots=True)
class CausalIonoEstimate:
    """Single strictly causal ionospheric estimate produced at epoch k (using <= k only)."""

    station_id: str
    satellite_id: str
    epoch_iso: str
    arc_id: int
    arc_epoch_count: int
    elevation_deg: float
    azimuth_deg: float
    ipp_lat_deg: float
    ipp_lon_deg: float
    slm_mf: float
    gf_phase_m: float
    gf_code_m: float
    code_pair: tuple[str, str]
    causal_raw_stec_tecu: float
    causal_sat_debiased_stec_tecu: float | None
    causal_calibrated_stec_tecu: float | None
    causal_calibrated_vtec_tecu: float | None
    causal_l1_delay_m: float
    leveling_sigma_tecu: float
    rx_dcb_est_tecu: float | None
    rot_tecu_per_min: float | None
    roti_tecu_per_min: float | None
    cycle_slip_detected: bool
    sat_dcb_applied_ns: float | None


class CausalIonoFilter:
    """Strictly causal epoch-by-epoch dual-frequency GPS ionospheric estimator.

    Guarantees that ``process_epoch(ep_k, ...)`` never inspects epochs ``> k``.
    Optionally applies external satellite DCBs (``sat_dsb_c1_p2_ns`` / ``sat_dsb_p1_p2_ns``)
    and tracks the station receiver DCB causally against an IONEX GIM prior (or leaves
    receiver DCB uncalibrated if no GIM is provided).
    """

    def __init__(
        self,
        *,
        station_id: str,
        station_ecef_m: tuple[float, float, float],
        nominal_step_s: float = 30.0,
        min_elevation_deg: float = 15.0,
        gf_slip_threshold_m: float = 0.25,
        mw_slip_sigma: float = 4.0,
        mw_slip_floor_m: float = 0.75,
        roti_window_s: float = 300.0,
        shell_height_m: float = DEFAULT_SLM_HEIGHT_M,
        sat_dsb_c1_p2_ns: dict[str, float] | None = None,
        sat_dsb_p1_p2_ns: dict[str, float] | None = None,
        ionex_grid: IonexGrid | None = None,
        code_noise_tecu_at_zenith: float = 3.0,
        rx_dcb_forgetting: float = 0.995,
    ) -> None:
        self.station_id = station_id
        self.station_ecef_m = station_ecef_m
        self.nominal_step_s = nominal_step_s
        self.min_elevation_deg = min_elevation_deg
        self.gf_slip_threshold_m = gf_slip_threshold_m
        self.mw_slip_sigma = mw_slip_sigma
        self.mw_slip_floor_m = mw_slip_floor_m
        self.roti_window_s = roti_window_s
        self.shell_height_m = shell_height_m
        self.sat_dsb_c1_p2_ns = sat_dsb_c1_p2_ns or {}
        self.sat_dsb_p1_p2_ns = sat_dsb_p1_p2_ns or {}
        self.ionex_grid = ionex_grid
        self.code_noise_tecu_at_zenith = code_noise_tecu_at_zenith
        self.rx_dcb_forgetting = rx_dcb_forgetting

        self._sats: dict[str, _CausalSatState] = {}
        # Causal exponentially weighted receiver DCB tracker (TECU, relative to IONEX)
        self._rx_dcb_w_sum: float = 0.0
        self._rx_dcb_est_tecu: float | None = None
        self.slip_counts: dict[str, int] = {"gf": 0, "mw": 0, "lli_or_gap": 0}

    def _reset_arc(self, st: _CausalSatState) -> None:
        st.arc_id += 1
        st.arc_epochs = 0
        st.mw_n = 0
        st.mw_mean = 0.0
        st.mw_m2 = 0.0
        st.w_sum = 0.0
        st.w2_sum = 0.0
        st.level_mean_tecu = 0.0
        st.level_m2_tecu2 = 0.0
        st.rot_history.clear()

    def process_epoch(
        self,
        epoch_iso: str,
        obs_by_sat: dict[str, SatObs],
        topo_by_sat: dict[str, tuple[float, float]],
    ) -> list[CausalIonoEstimate]:
        """Process one epoch strictly causally and return per-satellite iono estimates."""
        t_s = datetime.fromisoformat(epoch_iso).timestamp()
        out: list[CausalIonoEstimate] = []
        pending_rx_samples: list[tuple[float, float]] = []

        for sat in sorted(obs_by_sat):
            if not sat.startswith("G"):
                continue
            obs = obs_by_sat[sat]
            topo = topo_by_sat.get(sat)
            if topo is None:
                continue
            el_deg, az_deg = topo
            if el_deg < self.min_elevation_deg:
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
                continue

            gf_phase = l1 * GPS_L1_WAVELENGTH_M - l2 * GPS_L2_WAVELENGTH_M
            gf_code = p2 - code1_val
            mw_val = melbourne_wubbena_m(l1, l2, code1_val, p2)
            lli = (obs.lli.get("L1") or 0, obs.lli.get("L2") or 0)

            st = self._sats.setdefault(sat, _CausalSatState())
            slip = False
            if st.prev_t_s is not None and st.prev_gf_m is not None:
                dt = t_s - st.prev_t_s
                if (
                    dt <= 0.0
                    or dt > 1.5 * self.nominal_step_s + 1e-6
                    or obs.epoch_flag != 0
                    or any(f & 1 for f in lli)
                ):
                    slip = True
                    self.slip_counts["lli_or_gap"] += 1
                elif abs(gf_phase - st.prev_gf_m) > self.gf_slip_threshold_m:
                    slip = True
                    self.slip_counts["gf"] += 1
                elif st.mw_n >= 3:
                    mw_std = math.sqrt(st.mw_m2 / max(1, st.mw_n - 1))
                    thresh = max(self.mw_slip_floor_m, self.mw_slip_sigma * mw_std)
                    if abs(mw_val - st.mw_mean) > thresh:
                        slip = True
                        self.slip_counts["mw"] += 1

            if slip or st.arc_epochs == 0:
                if slip:
                    self._reset_arc(st)
                elif st.arc_id == 0:
                    st.arc_id = 1

            # Update causal MW Welford detector
            st.mw_n += 1
            d_mw = mw_val - st.mw_mean
            st.mw_mean += d_mw / st.mw_n
            st.mw_m2 += d_mw * (mw_val - st.mw_mean)

            # Causal elevation-weighted recursive carrier-to-code leveling
            w = math.sin(math.radians(el_deg)) ** 2
            stec_code_raw = gf_code / GF_M_PER_TECU
            stec_phase_rel = gf_phase / GF_M_PER_TECU
            sample_offset = stec_code_raw - stec_phase_rel
            st.w_sum += w
            st.w2_sum += w * w
            diff_l = sample_offset - st.level_mean_tecu
            st.level_mean_tecu += (w / st.w_sum) * diff_l
            st.level_m2_tecu2 += w * diff_l * (sample_offset - st.level_mean_tecu)
            st.arc_epochs += 1

            raw_stec = stec_phase_rel + st.level_mean_tecu
            eff_n = (st.w_sum * st.w_sum) / max(1e-12, st.w2_sum)
            level_sigma = self.code_noise_tecu_at_zenith / math.sqrt(max(1.0, eff_n))

            # Causal ROT and sliding-window ROTI
            rot_val: float | None = None
            if not slip and st.prev_t_s is not None and st.prev_gf_m is not None:
                dt_min = (t_s - st.prev_t_s) / 60.0
                if dt_min > 0.0:
                    rot_val = ((gf_phase - st.prev_gf_m) / GF_M_PER_TECU) / dt_min
                    st.rot_history.append((t_s, rot_val))
            while st.rot_history and (t_s - st.rot_history[0][0]) > self.roti_window_s + 1e-6:
                st.rot_history.popleft()
            roti_val: float | None = None
            if len(st.rot_history) >= 5:
                rvals = [rv for _, rv in st.rot_history]
                mr = sum(rvals) / len(rvals)
                roti_val = math.sqrt(sum((r - mr) ** 2 for r in rvals) / (len(rvals) - 1))

            st.prev_t_s = t_s
            st.prev_gf_m = gf_phase

            mf, ipp_lat, ipp_lon = slm_mapping_and_ipp(
                self.station_ecef_m, el_deg, az_deg, shell_height_m=self.shell_height_m
            )

            # Satellite DCB removal (exact sign: GF_code = alpha_GF*STEC - c*DSB(code1, P2))
            dsb_ns: float | None = None
            if code1_name == "C1" and sat in self.sat_dsb_c1_p2_ns:
                dsb_ns = self.sat_dsb_c1_p2_ns[sat]
            elif code1_name == "P1" and sat in self.sat_dsb_p1_p2_ns:
                dsb_ns = self.sat_dsb_p1_p2_ns[sat]

            sat_debiased_stec = (raw_stec + dsb_ns * NS_TO_TECU) if dsb_ns is not None else None

            # Optional causal receiver DCB sample against IONEX GIM (strictly current epoch!)
            if (
                sat_debiased_stec is not None
                and self.ionex_grid is not None
                and el_deg >= 25.0
                and st.arc_epochs >= 4
            ):
                # Use IONEX shell height for consistent IPP lookup
                mf_ionex, lat_ix, lon_ix = slm_mapping_and_ipp(
                    self.station_ecef_m,
                    el_deg,
                    az_deg,
                    shell_height_m=self.ionex_grid.shell_height_km * 1000.0,
                )
                vtec_gim, _ = self.ionex_grid.interpolate_vtec(lat_ix, lon_ix, epoch_iso)
                if vtec_gim is not None:
                    rx_sample = sat_debiased_stec - mf_ionex * vtec_gim
                    pending_rx_samples.append((w, rx_sample))

            # Apply current causal rx_dcb estimate (will be updated right after loop or inline)
            out.append(
                CausalIonoEstimate(
                    station_id=self.station_id,
                    satellite_id=sat,
                    epoch_iso=epoch_iso,
                    arc_id=st.arc_id,
                    arc_epoch_count=st.arc_epochs,
                    elevation_deg=el_deg,
                    azimuth_deg=az_deg,
                    ipp_lat_deg=ipp_lat,
                    ipp_lon_deg=ipp_lon,
                    slm_mf=mf,
                    gf_phase_m=gf_phase,
                    gf_code_m=gf_code,
                    code_pair=(code1_name, "P2"),
                    causal_raw_stec_tecu=raw_stec,
                    causal_sat_debiased_stec_tecu=sat_debiased_stec,
                    causal_calibrated_stec_tecu=None,
                    causal_calibrated_vtec_tecu=None,
                    causal_l1_delay_m=raw_stec * L1_M_PER_TECU,
                    leveling_sigma_tecu=level_sigma,
                    rx_dcb_est_tecu=self._rx_dcb_est_tecu,
                    rot_tecu_per_min=rot_val,
                    roti_tecu_per_min=roti_val,
                    cycle_slip_detected=slip,
                    sat_dcb_applied_ns=dsb_ns,
                )
            )

        # Update causal station receiver DCB tracker using ONLY current-epoch IONEX residuals
        if pending_rx_samples:
            self._rx_dcb_w_sum *= self.rx_dcb_forgetting
            for w_s, rx_val in pending_rx_samples:
                self._rx_dcb_w_sum += w_s
                if self._rx_dcb_est_tecu is None:
                    self._rx_dcb_est_tecu = rx_val
                else:
                    self._rx_dcb_est_tecu += (w_s / self._rx_dcb_w_sum) * (
                        rx_val - self._rx_dcb_est_tecu
                    )

        # Populate causal_calibrated_stec_tecu / vtec using the updated <=k rx_dcb estimate
        if self._rx_dcb_est_tecu is not None:
            updated: list[CausalIonoEstimate] = []
            for e in out:
                if e.causal_sat_debiased_stec_tecu is not None:
                    cal_stec = e.causal_sat_debiased_stec_tecu - self._rx_dcb_est_tecu
                    cal_vtec = cal_stec / e.slm_mf
                    updated.append(
                        CausalIonoEstimate(
                            station_id=e.station_id,
                            satellite_id=e.satellite_id,
                            epoch_iso=e.epoch_iso,
                            arc_id=e.arc_id,
                            arc_epoch_count=e.arc_epoch_count,
                            elevation_deg=e.elevation_deg,
                            azimuth_deg=e.azimuth_deg,
                            ipp_lat_deg=e.ipp_lat_deg,
                            ipp_lon_deg=e.ipp_lon_deg,
                            slm_mf=e.slm_mf,
                            gf_phase_m=e.gf_phase_m,
                            gf_code_m=e.gf_code_m,
                            code_pair=e.code_pair,
                            causal_raw_stec_tecu=e.causal_raw_stec_tecu,
                            causal_sat_debiased_stec_tecu=e.causal_sat_debiased_stec_tecu,
                            causal_calibrated_stec_tecu=cal_stec,
                            causal_calibrated_vtec_tecu=cal_vtec,
                            causal_l1_delay_m=cal_stec * L1_M_PER_TECU,
                            leveling_sigma_tecu=e.leveling_sigma_tecu,
                            rx_dcb_est_tecu=self._rx_dcb_est_tecu,
                            rot_tecu_per_min=e.rot_tecu_per_min,
                            roti_tecu_per_min=e.roti_tecu_per_min,
                            cycle_slip_detected=e.cycle_slip_detected,
                            sat_dcb_applied_ns=e.sat_dcb_applied_ns,
                        )
                    )
                else:
                    updated.append(e)
            return updated
        return out


class CausalNetworkDiffIonoTracker:
    """Strictly causal datum-relative differential L1 slant ionosphere tracker.

    Tracks the differential receiver DCB between each reference station and the datum
    station causally (satellite DCBs cancel identically in single differences), using
    ONLY observations at epochs ``<= k`` (zero future-arc median leakage).
    """

    def __init__(
        self,
        *,
        datum_station: str,
        forgetting_factor: float = 0.998,
        min_pair_epochs: int = 3,
    ) -> None:
        self.datum_station = datum_station
        self.forgetting_factor = forgetting_factor
        self.min_pair_epochs = min_pair_epochs
        # Per-station causal differential receiver DCB (TECU): rx_bias(st) - rx_bias(datum)
        self._rx_diff_w: dict[str, float] = {}
        self._rx_diff_tecu: dict[str, float] = {}
        # Per-(station, sat, arc_st, arc_dat) causal phase-smoothed offset
        self._pair_arc_count: dict[tuple[str, str, int, int], int] = {}
        self._pair_arc_mean_gf: dict[tuple[str, str, int, int], float] = {}

    def process_epoch(
        self,
        epoch_iso: str,
        estimates_by_station: dict[str, list[CausalIonoEstimate]],
    ) -> tuple[dict[tuple[str, str, str], float], dict[tuple[str, str, str], float]]:
        """Process one epoch across stations; returns (causal_sd_leveled, causal_sd_pair_arc).

        - ``causal_sd_leveled``: preserves diurnal spatial gradients via causal DCB-aligned
          STEC difference ``(STEC_cal(st) - STEC_cal(datum)) * L1_M_PER_TECU`` (if IONEX
          calibrated, or causal online rx-bias tracked otherwise).
        - ``causal_sd_pair_arc``: strictly causal online pair-arc running-mean-removed GF
          differential L1 delay (real-time analogue of Phase 6 ``common_arc_sd_l1_iono``).
        """
        datum_ests = {e.satellite_id: e for e in estimates_by_station.get(self.datum_station, [])}
        sd_leveled: dict[tuple[str, str, str], float] = {}
        sd_pair_arc: dict[tuple[str, str, str], float] = {}

        for sat in datum_ests:
            sd_leveled[(epoch_iso, sat, self.datum_station)] = 0.0
            sd_pair_arc[(epoch_iso, sat, self.datum_station)] = 0.0

        for sid, ests in sorted(estimates_by_station.items()):
            if sid == self.datum_station:
                continue
            for e in ests:
                d_est = datum_ests.get(e.satellite_id)
                if d_est is None:
                    continue
                # 1. Causal pair-arc running mean removal (zero future leakage)
                pkey = (sid, e.satellite_id, e.arc_id, d_est.arc_id)
                sd_gf = e.gf_phase_m - d_est.gf_phase_m
                cnt = self._pair_arc_count.get(pkey, 0) + 1
                self._pair_arc_count[pkey] = cnt
                prev_m = self._pair_arc_mean_gf.get(pkey, sd_gf)
                new_m = prev_m + (sd_gf - prev_m) / cnt
                self._pair_arc_mean_gf[pkey] = new_m
                if cnt >= self.min_pair_epochs:
                    # GF_TO_L1_FACTOR = L1_M_PER_TECU / GF_M_PER_TECU
                    sd_pair_arc[(epoch_iso, e.satellite_id, sid)] = (
                        (sd_gf - new_m) * (L1_M_PER_TECU / GF_M_PER_TECU)
                    )

                # 2. Causal leveled / calibrated differential L1 ionosphere
                if (
                    e.causal_calibrated_stec_tecu is not None
                    and d_est.causal_calibrated_stec_tecu is not None
                ):
                    sd_tecu = e.causal_calibrated_stec_tecu - d_est.causal_calibrated_stec_tecu
                    sd_leveled[(epoch_iso, e.satellite_id, sid)] = sd_tecu * L1_M_PER_TECU
                else:
                    # Causal differential receiver bias tracking (satellite DCB cancels)
                    raw_diff = e.causal_raw_stec_tecu - d_est.causal_raw_stec_tecu
                    w_el = min(
                        math.sin(math.radians(e.elevation_deg)) ** 2,
                        math.sin(math.radians(d_est.elevation_deg)) ** 2,
                    )
                    w_prev = self._rx_diff_w.get(sid, 0.0) * self.forgetting_factor
                    w_new = w_prev + w_el
                    self._rx_diff_w[sid] = w_new
                    est_prev = self._rx_diff_tecu.get(sid, raw_diff)
                    est_new = est_prev + (w_el / max(1e-12, w_new)) * (raw_diff - est_prev)
                    self._rx_diff_tecu[sid] = est_new
                    sd_leveled[(epoch_iso, e.satellite_id, sid)] = (
                        (raw_diff - est_new) * L1_M_PER_TECU
                    )

        return sd_leveled, sd_pair_arc
