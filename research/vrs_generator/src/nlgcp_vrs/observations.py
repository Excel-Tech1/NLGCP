"""Bounded strict RINEX 2 reader; GPST labels, original codes, LLI and SSI retained.

Phase 6's atmospheric reader remains unchanged. This adapter rejects malformed
records, unknown time systems and header-changing events instead of recovering
scientifically ambiguous record alignment.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from .models import Blocked

C = 299792458.0
WAVELENGTHS = {"L1": C / 1575420000.0, "L2": C / 1227600000.0}
SUPPORTED = ("C1", "P1", "P2", "L1", "L2")


@dataclass(frozen=True)
class Measurement:
    value: float
    lli: int | None
    ssi: int | None
    epoch_flag: int


@dataclass
class Dataset:
    codes: tuple[str, ...]
    interval: float
    data: dict[str, dict[str, dict[str, Measurement]]]


def read_observations(path: Path) -> Dataset:
    lines = path.read_text(encoding="ascii").splitlines()
    if not lines or lines[0][:9].strip() != "2.11" or lines[0][20:21] != "O":
        raise Blocked("only RINEX 2.11 observation files supported")
    codes: list[str] = []
    ntypes = 0
    interval = 0.0
    gps = False
    end = None
    for i, line in enumerate(lines):
        label = line[60:].strip()
        if label == "# / TYPES OF OBSERV":
            if line[:6].strip():
                ntypes = int(line[:6])
            codes.extend(
                line[j : j + 6].strip() for j in range(6, 60, 6) if line[j : j + 6].strip()
            )
        elif label == "INTERVAL":
            interval = float(line[:10])
        elif label == "TIME OF FIRST OBS":
            gps = line[48:51].strip() == "GPS"
        elif label == "WAVELENGTH FACT L1/2":
            if line[:6].strip() != "1" or line[6:12].strip() != "1" or line[12:18].strip():
                raise Blocked("non-default wavelength factors are unsupported")
        elif label == "END OF HEADER":
            end = i + 1
            break
    if (
        end is None
        or not gps
        or interval <= 0
        or not math.isfinite(interval)
        or not ntypes
        or len(codes) != ntypes
        or len(set(codes)) != ntypes
    ):
        raise Blocked("incomplete/incompatible RINEX header")
    dataset = Dataset(tuple(codes), interval, {})
    pos = end
    previous: datetime | None = None
    while pos < len(lines):
        line = lines[pos]
        pos += 1
        if not line.strip():
            continue
        try:
            yy, month, day, hour, minute = (
                int(line[a:b]) for a, b in ((0, 3), (3, 6), (6, 9), (9, 12), (12, 15))
            )
            sec = float(line[15:26])
            if not 0 <= sec < 60:
                raise ValueError("invalid GPST seconds")
            moment = datetime(2000 + yy if yy < 80 else 1900 + yy, month, day, hour, minute)
            moment += timedelta(seconds=sec)
            flag, nsat = int(line[28:29]), int(line[29:32])
            if flag not in (0, 1) or not 0 <= nsat <= 99:
                raise Blocked("event/header update unsupported; explicit preprocessing required")
            if line[68:80].strip() and float(line[68:80]) != 0:
                raise Blocked("nonzero epoch receiver-clock field unsupported")
            if previous is not None and moment <= previous:
                raise Blocked("duplicate or non-monotonic epoch")
            previous = moment
            ids = line[32:68]
            for _ in range((max(0, nsat - 12) + 11) // 12):
                continuation = lines[pos]
                pos += 1
                if continuation[:32].strip():
                    raise Blocked("invalid satellite continuation")
                ids += continuation[32:68]
            satellites = [ids[j * 3 : j * 3 + 3].strip() for j in range(nsat)]
            if len(set(satellites)) != nsat or any(len(s) != 3 for s in satellites):
                raise Blocked("invalid/duplicate satellite IDs")
            bucket: dict[str, dict[str, Measurement]] = {}
            for sat in satellites:
                fields = ""
                for _ in range((ntypes + 4) // 5):
                    block = lines[pos]
                    pos += 1
                    if len(block) > 80:
                        raise Blocked("overlong observation record")
                    fields += block.ljust(80)
                measures: dict[str, Measurement] = {}
                for j, code in enumerate(codes):
                    field = fields[j * 16 : (j + 1) * 16]
                    if not field[:14].strip():
                        continue
                    value = float(field[:14].replace("D", "E"))
                    lli = int(field[14]) if field[14].strip() else None
                    ssi = int(field[15]) if field[15].strip() else None
                    if not math.isfinite(value) or (lli is not None and not 0 <= lli <= 7):
                        raise Blocked("non-finite observation or invalid LLI")
                    measures[code] = Measurement(value, lli, ssi, flag)
                bucket[sat] = measures
            dataset.data[moment.isoformat(timespec="microseconds")] = bucket
        except (ValueError, IndexError) as exc:
            raise Blocked(f"malformed RINEX near line {pos}: {exc}") from exc
    if not dataset.data:
        raise Blocked("no observation epochs")
    return dataset


def transform(code: str, observation: float, geometric_m: float, clock_m: float) -> float:
    if code not in SUPPORTED or not all(
        math.isfinite(x) for x in (observation, geometric_m, clock_m)
    ):
        raise Blocked("unsupported code or non-finite transformation")
    return observation + (geometric_m + clock_m) / WAVELENGTHS.get(code, 1.0)
