"""Satellite geometry: elevation/azimuth from verified ephemerides (Phase 6).

Elevation/azimuth are derived from verified station coordinates and satellite
positions — never approximated with static satellite coordinates. The
supported ephemeris source is GPS broadcast navigation (RINEX 3 merged BRDC)
propagated with the IS-GPS-200 Kepler solution; every position records the
navigation file hash. All other constellations, and epochs without a usable
broadcast record, fail closed with explicit reasons.

References: IS-GPS-200 (Navstar GPS Space Segment/Navigation User Segment
Interfaces), Table 20-IV orbital equations; Hofmann-Wellenhof et al. (2008)
for the topocentric transformation.
"""

from __future__ import annotations

import gzip
import math
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .constants import EARTH_GM_M3_S2, EARTH_ROT_RATE_RAD_S
from .spatial import _geodetic_lat_lon

GPS_EPOCH = datetime(1980, 1, 6, tzinfo=UTC)
LEAP_SECONDS_2024 = 18
"""GPS minus UTC offset valid for 2024 (informational only).

RINEX 2 observation epochs and RINEX 3 navigation epochs in this archive
carry GPS-time labels (headers declare ``GPS`` in TIME OF FIRST OBS), and
the pipeline stores them as ISO-8601 wall times. They must be interpreted
as GPST directly: no leap-second offset is added in conversions. A previous
revision added these 18 s, biasing every broadcast propagation by ~70 km
of along-track error. Retained as a named constant for documentation only.
"""

WEEK_SECONDS = 604_800.0
HALF_WEEK = 302_400.0
MU = EARTH_GM_M3_S2
OMEGA_E = EARTH_ROT_RATE_RAD_S


@dataclass(frozen=True, slots=True)
class BroadcastEphemeris:
    """One GPS broadcast ephemeris record (SI units, radians)."""

    satellite_id: str  # e.g. "G03"
    toc_week: int
    toc_tow_s: float
    af0_s: float
    af1_s_s: float
    af2_s_s2: float
    iode: float
    crs_m: float
    delta_n_rad_s: float
    m0_rad: float
    cuc_rad: float
    e: float
    cus_rad: float
    sqrt_a_m_sqrt: float
    toe_tow_s: float
    toe_week: int
    cic_rad: float
    omega0_rad: float
    cis_rad: float
    i0_rad: float
    crc_m: float
    omega_rad: float
    omega_dot_rad_s: float
    idot_rad_s: float
    health: int = 0


@dataclass(frozen=True, slots=True)
class Topocentric:
    """Elevation/azimuth observation geometry with provenance."""

    epoch_iso: str
    station_id: str
    satellite_id: str
    elevation_deg: float
    azimuth_deg: float
    nav_hash: str
    method: str = "IS-GPS-200 broadcast Kepler + topocentric ENU"


def _rinex_rad(value: float) -> float:
    """RINEX broadcast angles/rates are stored in radians (identity).

    The ICD (IS-GPS-200) uses semicircles, but RINEX navigation files
    record M0, Delta-n, OMEGA0, i0, omega, OMEGADOT and IDOT converted to
    radians / radians/second. The pinned RTKLIB ``decode_eph`` stores these
    fields without any pi scaling, and the real DOY 026 product confirms it:
    raw i0 = 0.9905 rad = 56.7 deg (correct GPS inclination), whereas
    ``* pi`` would give 178.3 deg. A previous revision multiplied seven
    fields by pi; that is removed here. Cuc/Cus/Crc/Crs/Cic/Cis were and
    remain unscaled (radians/metres).
    """
    return value


def gps_datetime_to_tow(moment: datetime) -> tuple[int, float]:
    """Convert a GPST calendar label to (GPS week, time-of-week in seconds).

    The input wall time is GPS time (RINEX headers declare GPS); no
    UTC leap-second offset is applied.
    """
    if moment.utcoffset() not in (None, __import__("datetime").timedelta(0)):
        raise ValueError("GPST label cannot carry a nonzero UTC offset")
    gps_time = moment.replace(tzinfo=UTC).timestamp()
    epoch_s = GPS_EPOCH.timestamp()
    elapsed = gps_time - epoch_s
    week = int(elapsed // WEEK_SECONDS)
    return week, elapsed - week * WEEK_SECONDS


def broadcast_position(
    eph: BroadcastEphemeris, week: int, tow_s: float
) -> tuple[float, float, float]:
    """Propagate a broadcast record to ECEF metres (IS-GPS-200 Table 20-IV).

    Signal-travel-time Earth-rotation correction is omitted (documented
    first-order simplification: ~3 m position effect, negligible for the
    elevation-mask and mapping-function use here).
    """
    if not (0 <= eph.e < 1) or not math.isfinite(eph.sqrt_a_m_sqrt) or eph.sqrt_a_m_sqrt <= 0:
        raise ValueError("invalid broadcast eccentricity/semimajor axis")
    a = eph.sqrt_a_m_sqrt * eph.sqrt_a_m_sqrt
    tk = tow_s - eph.toe_tow_s + (week - eph.toe_week) * WEEK_SECONDS
    if tk > HALF_WEEK:
        tk -= WEEK_SECONDS
    elif tk < -HALF_WEEK:
        tk += WEEK_SECONDS
    n0 = math.sqrt(MU / (a * a * a))
    n = n0 + eph.delta_n_rad_s
    m_k = eph.m0_rad + n * tk
    e_k = m_k
    for _ in range(12):
        delta = (m_k - e_k + eph.e * math.sin(e_k)) / (1.0 - eph.e * math.cos(e_k))
        e_k += delta
        if abs(delta) < 1e-13:
            break
    else:
        raise ValueError("broadcast Kepler iteration did not converge")
    cos_e = math.cos(e_k)
    sin_e = math.sin(e_k)
    v_k = math.atan2(math.sqrt(1.0 - eph.e * eph.e) * sin_e, cos_e - eph.e)
    phi_k = v_k + eph.omega_rad
    sin2, cos2 = math.sin(2.0 * phi_k), math.cos(2.0 * phi_k)
    u_k = phi_k + eph.cus_rad * sin2 + eph.cuc_rad * cos2
    r_k = a * (1.0 - eph.e * cos_e) + eph.crs_m * sin2 + eph.crc_m * cos2
    i_k = eph.i0_rad + eph.idot_rad_s * tk + eph.cis_rad * sin2 + eph.cic_rad * cos2
    x_p = r_k * math.cos(u_k)
    y_p = r_k * math.sin(u_k)
    omega_k = eph.omega0_rad + (eph.omega_dot_rad_s - OMEGA_E) * tk - OMEGA_E * eph.toe_tow_s
    cos_o, sin_o = math.cos(omega_k), math.sin(omega_k)
    cos_i, sin_i = math.cos(i_k), math.sin(i_k)
    return (
        x_p * cos_o - y_p * cos_i * sin_o,
        x_p * sin_o + y_p * cos_i * cos_o,
        y_p * sin_i,
    )


def elevation_azimuth_deg(
    station_ecef_m: tuple[float, float, float],
    satellite_ecef_m: tuple[float, float, float],
) -> tuple[float, float]:
    """Topocentric elevation/azimuth (degrees) for verified coordinates."""
    sx, sy, sz = station_ecef_m
    dx = satellite_ecef_m[0] - sx
    dy = satellite_ecef_m[1] - sy
    dz = satellite_ecef_m[2] - sz
    # Geodetic (ellipsoidal) latitude is required for the ENU rotation. A
    # previous revision used geocentric latitude atan2(z, hypot(x, y)),
    # tilting the frame by up to ~0.08 deg over Nigeria (km-level ENU bias).
    lat, lon = _geodetic_lat_lon(station_ecef_m)
    sin_lat, cos_lat = math.sin(lat), math.cos(lat)
    sin_lon, cos_lon = math.sin(lon), math.cos(lon)
    east = -sin_lon * dx + cos_lon * dy
    north = -sin_lat * cos_lon * dx - sin_lat * sin_lon * dy + cos_lat * dz
    up = cos_lat * cos_lon * dx + cos_lat * sin_lon * dy + sin_lat * dz
    rng = math.hypot(east, north, up)
    if not math.isfinite(rng) or rng <= 0:
        raise ValueError("invalid topocentric range")
    elevation = math.degrees(math.asin(max(-1.0, min(1.0, up / rng))))
    azimuth = math.degrees(math.atan2(east, north)) % 360.0
    return elevation, azimuth


def _fortran_float(text: str) -> float:
    return float(text.replace("D", "E").strip() or "nan")


FLOAT_TOKEN = re.compile(r"[+-]?\d\.\d+[EDed][+-]?\d+")


def _orbit_values(block: list[str]) -> list[float] | None:
    """Read RINEX 3 GPS D19.12 fields; blank fit/spare fields are optional.

    Adjacent signed fields are valid fixed columns. Regex requiring 28
    numeric tokens silently discarded records with blank trailing spares.
    """
    values: list[float] = []
    for row, line in enumerate(block):
        for col in range(4):
            field = line[4 + 19 * col : 4 + 19 * (col + 1)].strip()
            if not field and row * 4 + col >= 25:
                values.append(0.0)  # unused optional fit interval / spares only
                continue
            try:
                value = _fortran_float(field)
            except ValueError:
                return None
            if not math.isfinite(value):
                return None
            values.append(value)
    return values if len(values) == 28 else None


def parse_rinex3_gps_nav(path: Path) -> dict[str, list[BroadcastEphemeris]]:
    """Parse GPS broadcast records from a (possibly gzipped) RINEX 3 nav file.

    Only ``Gnn`` records are parsed; all other systems are ignored with the
    caller recording the exclusion reason. Raises ``ModelBlocked``-style
    ``ValueError`` is avoided: an empty mapping means BLOCKED downstream.
    """
    if path.suffix == ".gz":
        with gzip.open(path, "rt", encoding="utf-8", errors="replace") as gz_handle:
            lines = gz_handle.readlines()
    else:
        with open(path, encoding="utf-8", errors="replace") as txt_handle:
            lines = txt_handle.readlines()
    records: dict[str, list[BroadcastEphemeris]] = {}
    idx = 0
    # Skip header.
    while idx < len(lines) and "END OF HEADER" not in lines[idx]:
        idx += 1
    idx += 1
    while idx < len(lines):
        line = lines[idx]
        idx += 1
        if len(line) < 23 or not (line[0] == "G" and line[1:3].strip().isdigit()):
            continue
        try:
            sat = f"G{int(line[1:3]):02d}"
            toc = datetime(
                int(line[4:8]),
                int(line[9:11]),
                int(line[12:14]),
                int(line[15:17]),
                int(line[18:20]),
                int(line[21:23]),
                tzinfo=UTC,
            )
            af_tokens = FLOAT_TOKEN.findall(line[22:])
            if len(af_tokens) < 3:
                continue
            af0 = _fortran_float(af_tokens[0])
            af1 = _fortran_float(af_tokens[1])
            af2 = _fortran_float(af_tokens[2])
            block = lines[idx : idx + 7]
            idx += 7
            if len(block) < 7:
                break
            # RINEX 3.04 Table A20 (GPS NAV): 7 orbit lines x 4 D19 fields.
            # Line 1: IODE, Crs, Delta n, M0; line 2: Cuc, e, Cus, sqrtA;
            # line 3: Toe, Cic, OMEGA, CIS; line 4: i0, Crc, omega,
            # OMEGA DOT; line 5: IDOT, codes-on-L2, GPS week, L2P flag;
            # line 6: SV accuracy, SV health, TGD, IODC; line 7: trans
            # time, fit interval, spare, spare.
            vals_opt = _orbit_values(block)
            if vals_opt is None:
                continue
            vals = vals_opt
            week, tow = gps_datetime_to_tow(toc)
            toe_tow = vals[8]
            toe_week = int(vals[18])
            eph = BroadcastEphemeris(
                satellite_id=sat,
                toc_week=week,
                toc_tow_s=tow,
                af0_s=af0,
                af1_s_s=af1,
                af2_s_s2=af2,
                iode=vals[0],
                crs_m=vals[1],
                delta_n_rad_s=_rinex_rad(vals[2]),
                m0_rad=_rinex_rad(vals[3]),
                cuc_rad=vals[4],
                e=vals[5],
                cus_rad=vals[6],
                sqrt_a_m_sqrt=vals[7],
                toe_tow_s=toe_tow,
                toe_week=toe_week,
                cic_rad=vals[9],
                omega0_rad=_rinex_rad(vals[10]),
                cis_rad=vals[11],
                i0_rad=_rinex_rad(vals[12]),
                crc_m=vals[13],
                omega_rad=_rinex_rad(vals[14]),
                omega_dot_rad_s=_rinex_rad(vals[15]),
                idot_rad_s=_rinex_rad(vals[16]),
                health=int(vals[21]),
            )
            records.setdefault(sat, []).append(eph)
        except (ValueError, IndexError):
            continue
    return records


def select_ephemeris(
    records: list[BroadcastEphemeris], week: int, tow_s: float
) -> BroadcastEphemeris | None:
    """Select the record with the smallest |t - toe| (documented rule)."""
    best: BroadcastEphemeris | None = None
    best_dt = float("inf")
    for eph in records:
        dt = abs((tow_s + (week - eph.toe_week) * WEEK_SECONDS) - eph.toe_tow_s)
        if eph.health != 0 or dt > 7201.0:
            continue
        if dt <= best_dt:
            best_dt = dt
            best = eph
    return best


def geometry_table(
    *,
    epochs: list[str],
    satellites: list[str],
    station_coords: dict[str, tuple[float, float, float]],
    nav_records: dict[str, list[BroadcastEphemeris]],
    nav_hash: str,
) -> tuple[list[Topocentric], list[dict[str, Any]]]:
    """Compute elevation/azimuth for station/satellite/epoch triples.

    Returns ``(rows, exclusions)``; exclusions carry explicit reasons and no
    geometry is approximated when ephemeris is absent.
    """
    rows: list[Topocentric] = []
    exclusions: list[dict[str, Any]] = []
    for epoch_iso_value in epochs:
        try:
            moment = datetime.fromisoformat(epoch_iso_value)
        except ValueError:
            exclusions.append({"epoch": epoch_iso_value, "reason": "unparsable epoch"})
            continue
        week, tow = gps_datetime_to_tow(moment)
        for sat in satellites:
            if not sat.startswith("G"):
                exclusions.append(
                    {
                        "epoch": epoch_iso_value,
                        "satellite": sat,
                        "reason": "non-GPS broadcast propagation not implemented",
                    }
                )
                continue
            eph = select_ephemeris(nav_records.get(sat, []), week, tow)
            if eph is None:
                exclusions.append(
                    {
                        "epoch": epoch_iso_value,
                        "satellite": sat,
                        "reason": "no GPS broadcast record available",
                    }
                )
                continue
            sat_ecef = broadcast_position(eph, week, tow)
            for station_id, coord in station_coords.items():
                elev, azim = elevation_azimuth_deg(coord, sat_ecef)
                rows.append(
                    Topocentric(
                        epoch_iso=epoch_iso_value,
                        station_id=station_id,
                        satellite_id=sat,
                        elevation_deg=elev,
                        azimuth_deg=azim,
                        nav_hash=nav_hash,
                    )
                )
    return rows, exclusions
