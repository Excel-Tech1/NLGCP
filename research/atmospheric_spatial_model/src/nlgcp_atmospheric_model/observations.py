"""RINEX observation extraction and common-observation discovery (Phase 6).

The 2024 NLGCP archive holds RINEX 2.11 mixed-constellation observation files.
RTKLIB ``.pos`` outputs carry no satellite-level fields, so Phase 6 extracts
satellite observables here, directly from the RINEX observations, with every
input traced to its source file and hash.

Scope: RINEX 2 observation files only. Geometry-free combinations are derived
for GPS L1/L2 exclusively, because GLONASS FDMA channel numbers are not
recorded in these headers and generic RINEX 2 codes for other constellations
have ambiguous band mappings. Exclusions always carry explicit reasons.
"""

from __future__ import annotations

import math
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .constants import (
    GPS_L1_HZ,
    GPS_L2_HZ,
    SPEED_OF_LIGHT_M_S,
)

GPS_L1_WAVELENGTH_M = SPEED_OF_LIGHT_M_S / GPS_L1_HZ
GPS_L2_WAVELENGTH_M = SPEED_OF_LIGHT_M_S / GPS_L2_HZ

MISSING_REASON_RINEX = "observation absent in RINEX record"
GPS_ONLY_GF_REASON = (
    "geometry-free combination restricted to GPS L1/L2: GLONASS FDMA channel "
    "numbers are not recorded in the RINEX 2 headers and non-GPS generic code "
    "band mappings are ambiguous"
)


@dataclass(frozen=True, slots=True)
class Rinex2Header:
    """Parsed RINEX 2 observation header."""

    path: str
    obs_types: tuple[str, ...]
    interval_s: float | None
    time_of_first_obs: str | None
    approx_xyz_m: tuple[float, float, float] | None
    time_system: str = "GPS"


@dataclass(slots=True)
class SatObs:
    """One satellite's raw observables at one epoch."""

    epoch_flag: int = 0
    values: dict[str, float | None] = field(default_factory=dict)
    lli: dict[str, int | None] = field(default_factory=dict)


@dataclass(slots=True)
class StationDataset:
    """Parsed observation content of one station-day file."""

    station_id: str
    header: Rinex2Header
    epochs: list[str] = field(default_factory=list)
    # epoch_iso -> satellite_id -> observables
    data: dict[str, dict[str, SatObs]] = field(default_factory=dict)
    skipped_epoch_records: int = 0
    skip_reasons: dict[str, int] = field(default_factory=dict)


def _full_year(yy: int) -> int:
    """Expand RINEX 2-digit epoch years; pass 4-digit header years through."""
    if yy > 1000:
        return yy
    return 2000 + yy if yy < 80 else 1900 + yy


def epoch_iso(year: int, month: int, day: int, hour: int, minute: int, sec: float) -> str:
    whole = int(sec)
    micro = int(round((sec - whole) * 1_000_000))
    return f"{year:04d}-{month:02d}-{day:02d}T{hour:02d}:{minute:02d}:{whole:02d}.{micro:06d}"


def parse_rinex2_header(path: Path) -> Rinex2Header:
    obs_types: list[str] = []
    pending_count = 0
    interval: float | None = None
    first_obs: str | None = None
    approx: tuple[float, float, float] | None = None
    time_system = ""
    with path.open(encoding="utf-8", errors="replace") as handle:
        for line in handle:
            if pending_count > 0:
                for k in range(0, len(line.rstrip("\n")), 6):
                    token = line[k : k + 6].strip()
                    if token:
                        obs_types.append(token)
                        if len(obs_types) >= pending_count:
                            break
                if len(obs_types) >= pending_count:
                    pending_count = 0
                continue
            label = line[60:]
            if "# / TYPES OF OBSERV" in label:
                try:
                    pending_count = int(line[0:6].strip())
                except ValueError:
                    pending_count = 0
                for k in range(0, 54, 6):
                    token = line[6 + k : 12 + k].strip()
                    if token:
                        obs_types.append(token)
                if len(obs_types) >= pending_count:
                    pending_count = 0
            elif "INTERVAL" in label:
                try:
                    interval = float(line[0:10].strip())
                except ValueError:
                    interval = None
            elif "TIME OF FIRST OBS" in label:
                time_system = line[48:51].strip()
                try:
                    first_obs = epoch_iso(
                        _full_year(int(line[0:6])),
                        int(line[6:12]),
                        int(line[12:18]),
                        int(line[18:24]),
                        int(line[24:30]),
                        float(line[30:43]),
                    )
                except ValueError:
                    first_obs = None
            elif "APPROX POSITION XYZ" in label:
                try:
                    approx = (
                        float(line[0:14]),
                        float(line[14:28]),
                        float(line[28:42]),
                    )
                except ValueError:
                    approx = None
            elif "END OF HEADER" in label:
                break
    return Rinex2Header(
        path=str(path),
        obs_types=tuple(obs_types),
        interval_s=interval,
        time_of_first_obs=first_obs,
        approx_xyz_m=approx,
        time_system=time_system,
    )


def _parse_epoch_line(line: str) -> tuple[str, int, list[str]] | None:
    try:
        iso = epoch_iso(
            _full_year(int(line[0:3])),
            int(line[3:6]),
            int(line[6:9]),
            int(line[9:12]),
            int(line[12:15]),
            float(line[15:26]),
        )
        flag = int(line[26:29])
        nsat = int(line[29:32])
    except (ValueError, IndexError):
        return None
    sats: list[str] = []
    body = line[32:].rstrip("\n")
    for k in range(0, len(body), 3):
        token = body[k : k + 3].strip()
        if token:
            sats.append(token)
    return iso, flag, sats[:nsat] if nsat >= 0 else sats


def _parse_obs_value(field16: str) -> tuple[float | None, int | None]:
    text = field16[:14].strip()
    value: float | None = None
    if text:
        try:
            value = float(text)
            if not math.isfinite(value):
                raise ValueError("non-finite RINEX observation")
        except ValueError:
            value = None
    lli: int | None = None
    if len(field16) > 14 and field16[14].strip():
        try:
            lli = int(field16[14])
        except ValueError:
            lli = None
    return value, lli


def read_rinex2_observations(path: Path, station_id: str, *, stride: int = 1) -> StationDataset:
    """Parse a RINEX 2 observation file into a station dataset.

    ``stride`` keeps every Nth epoch (deterministic decimation for expensive
    pilots); stride=1 keeps all epochs. No interpolation across missing
    observations is performed.
    """
    if stride < 1:
        raise ValueError("stride must be >= 1")
    header = parse_rinex2_header(path)
    dataset = StationDataset(station_id=station_id, header=header)
    ntypes = len(header.obs_types)
    if ntypes == 0:
        dataset.skip_reasons["no observation types in header"] = 1
        return dataset
    if header.time_system != "GPS":
        raise ValueError("explicit GPS observation time system required")
    lines_per_sat = (ntypes + 4) // 5
    epoch_index = 0
    with path.open(encoding="utf-8", errors="replace") as handle:
        raw_lines = handle.read().splitlines()
    # Skip header.
    body_start = 0
    for pos, line in enumerate(raw_lines):
        if "END OF HEADER" in line[60:]:
            body_start = pos + 1
            break
    pos = body_start
    total = len(raw_lines)

    def note_skip(reason: str) -> None:
        dataset.skipped_epoch_records += 1
        dataset.skip_reasons[reason] = dataset.skip_reasons.get(reason, 0) + 1

    while pos < total:
        line = raw_lines[pos]
        pos += 1
        # Blank lines and receiver-clock special records are only ever
        # skipped while an epoch record is expected. Inside a satellite
        # observation block every line (including blank lines for absent
        # observables) is structural and is consumed exactly below, so
        # skipping here can never desynchronise the record layout.
        if not line.strip():
            continue
        if line.startswith("%"):
            note_skip("special/event record (%)")
            continue
        parsed = _parse_epoch_line(line)
        if parsed is None:
            note_skip("malformed epoch line")
            continue
        iso, flag, sats = parsed
        if flag in (2, 3, 5):
            note_skip(f"epoch flag {flag} excluded")
            pos += int(line[29:32])  # event count is special records, NOT satellites
            continue
        if flag not in (0, 1):
            raise ValueError(f"unsupported RINEX header/slip event {flag}")
        # Satellite-id continuation lines (more than 12 satellites listed).
        for _ in range(_satellite_overflow_count(line)):
            if pos >= total:
                break
            cont = raw_lines[pos]
            pos += 1
            for k in range(32, len(cont), 3):
                token = cont[k : k + 3].strip()
                if token:
                    sats.append(token)
        if flag not in (0, 1):
            note_skip(f"epoch flag {flag} excluded")
            # Still must consume the satellite data lines exactly so the
            # next epoch record starts at the correct line.
            pos += len(sats) * lines_per_sat
            continue
        keep = epoch_index % stride == 0
        epoch_index += 1
        truncated = False
        for sat_id in sats:
            block = raw_lines[pos : pos + lines_per_sat]
            if len(block) < lines_per_sat:
                truncated = True
                pos = total
                break
            pos += lines_per_sat
            obs = SatObs(epoch_flag=flag)
            for idx, code in enumerate(header.obs_types):
                row = idx // 5
                col = idx % 5
                segment = block[row]
                seg = segment[col * 16 : (col + 1) * 16]
                value, lli = _parse_obs_value(seg + " " * (16 - len(seg)))
                obs.values[code] = value
                obs.lli[code] = lli
            if keep and sat_id:
                bucket = dataset.data.setdefault(iso, {})
                bucket[sat_id] = obs
                if iso not in dataset.epochs:
                    dataset.epochs.append(iso)
        if truncated:
            note_skip("truncated epoch record at end of file")
            break
    dataset.epochs.sort()
    return dataset


def _satellite_overflow_count(line: str) -> int:
    """Number of continuation lines holding further satellite ids."""
    try:
        nsat = int(line[29:32])
    except (ValueError, IndexError):
        return 0
    listed = max(0, (len(line.rstrip("\n")) - 32 + 2) // 3)
    remaining = nsat - listed
    if remaining <= 0:
        return 0
    return (remaining + 11) // 12


def discover_observables(datasets: dict[str, StationDataset]) -> dict[str, Any]:
    """Deterministic discovery of observables across stations.

    Records per-station constellations, observation codes, satellites and
    epochs, plus the cross-station compatible subset usable for dual-frequency
    combinations. Never substitutes frequencies.
    """
    stations: dict[str, Any] = {}
    for station_id in sorted(datasets):
        dataset = datasets[station_id]
        constellations: set[str] = set()
        sats: set[str] = set()
        codes: set[str] = set(dataset.header.obs_types)
        for sats_at_epoch in dataset.data.values():
            for sat_id in sats_at_epoch:
                if sat_id:
                    constellations.add(sat_id[0])
                    sats.add(sat_id)
        stations[station_id] = {
            "station_id": station_id,
            "source_path": dataset.header.path,
            "observation_codes": sorted(codes),
            "constellations": sorted(constellations),
            "satellite_count": len(sats),
            "epoch_count": len(dataset.epochs),
            "skipped_epoch_records": dataset.skipped_epoch_records,
            "skip_reasons": dict(dataset.skip_reasons),
        }
    common_codes: set[str] | None = None
    for dataset in datasets.values():
        codes = set(dataset.header.obs_types)
        common_codes = codes if common_codes is None else (common_codes & codes)
    gps_dual = common_codes is not None and {"L1", "L2"} <= common_codes
    return {
        "stations": stations,
        "common_observation_codes": sorted(common_codes or []),
        "gps_l1_l2_compatible": bool(gps_dual),
        "gps_only_gf_reason": None
        if gps_dual
        else (
            "L1 and L2 not simultaneously present in every station header; " + GPS_ONLY_GF_REASON
            if gps_dual is False and common_codes is not None and {"L1", "L2"} & common_codes
            else GPS_ONLY_GF_REASON
        ),
    }


def common_epochs(datasets: dict[str, StationDataset]) -> list[str]:
    """Epochs present in every station dataset (no interpolation)."""
    common: set[str] | None = None
    for dataset in datasets.values():
        epochs = set(dataset.data)
        common = epochs if common is None else (common & epochs)
    return sorted(common or [])


def common_satellites(
    datasets: dict[str, StationDataset],
    epoch_iso_value: str,
    *,
    stations: list[str] | None = None,
    require_l1_l2: bool = True,
) -> dict[str, list[str]]:
    """Map satellite -> observing stations at one epoch.

    With ``require_l1_l2`` only GPS satellites with both L1 and L2 phase
    present at every requested station are returned; exclusions are reported
    via :func:`common_satellite_summary`.
    """
    wanted = stations or sorted(datasets)
    per_station = {name: datasets[name].data.get(epoch_iso_value, {}) for name in wanted}
    candidates: set[str] | None = None
    for sats in per_station.values():
        keys = set(sats)
        candidates = keys if candidates is None else (candidates & keys)
    result: dict[str, list[str]] = {}
    for sat in sorted(candidates or []):
        if require_l1_l2:
            if not sat.startswith("G"):
                continue
            ok = True
            for name in wanted:
                obs = per_station[name].get(sat)
                if obs is None or obs.values.get("L1") is None or obs.values.get("L2") is None:
                    ok = False
                    break
            if not ok:
                continue
        result[sat] = [name for name in wanted if sat in per_station.get(name, {})]
    return result


def common_satellite_summary(
    datasets: dict[str, StationDataset],
    epochs: list[str],
    *,
    stations: list[str] | None = None,
) -> dict[str, Any]:
    """Summary statistics of common-satellite availability."""
    wanted = stations or sorted(datasets)
    per_epoch: list[int] = []
    constellation_counts: dict[str, int] = {}
    gps_l1l2_counts: list[int] = []
    for epoch in epochs:
        common = common_satellites(datasets, epoch, stations=wanted)
        gps_l1l2_counts.append(len(common))
        all_sats: set[str] | None = None
        for name in wanted:
            keys = set(datasets[name].data.get(epoch, {}))
            all_sats = keys if all_sats is None else (all_sats & keys)
        per_epoch.append(len(all_sats or []))
        for sat in all_sats or []:
            constellation_counts[sat[0]] = constellation_counts.get(sat[0], 0) + 1
    usable = sum(1 for c in gps_l1l2_counts if c > 0)
    return {
        "epoch_count": len(epochs),
        "common_satellites_per_epoch": per_epoch,
        "median_common_satellites": _median(per_epoch),
        "minimum_common_satellites": min(per_epoch) if per_epoch else 0,
        "gps_l1l2_common_per_epoch": gps_l1l2_counts,
        "median_gps_l1l2_common": _median(gps_l1l2_counts),
        "minimum_gps_l1l2_common": min(gps_l1l2_counts) if gps_l1l2_counts else 0,
        "constellation_appearances": constellation_counts,
        "usable_epoch_count": usable,
        "usable_epoch_fraction": (usable / len(epochs)) if epochs else 0.0,
    }


def _median(values: list[int]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2 == 1:
        return float(ordered[mid])
    return (ordered[mid - 1] + ordered[mid]) / 2.0


def iter_station_epochs(dataset: StationDataset) -> Iterator[tuple[str, dict[str, SatObs]]]:
    for epoch in dataset.epochs:
        yield epoch, dataset.data[epoch]
