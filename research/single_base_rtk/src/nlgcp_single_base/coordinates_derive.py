"""Authoritative station coordinate derivation via PRIDE PPP-AR.

The preserved delivery only carries RINEX APPROX POSITION XYZ coordinates
with no declared reference frame or epoch.  To legitimately open the Phase 2
``coordinates_verified`` / ``reference_frame_verified`` /
``coordinate_epoch_verified`` gates, Phase 3 derives authoritative station
coordinates by static precise point positioning with ambiguity resolution
(PRIDE PPP-AR) over the real 24-hour observation, using WUM rapid precise
orbit/clock/attitude/bias/ERP products.

The resulting coordinate is an IGS20-frame station position at the
observation epoch.  All product and tool provenance is recorded so the
derivation is reproducible.
"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from nlgcp_single_base.coordinates import EcefCoordinate
from nlgcp_single_base.io import sha256_file

PDP3 = Path("/home/excellence/.PRIDE_PPPAR_BIN/pdp3")
PRIDE_LSQ = Path("/home/excellence/.PRIDE_PPPAR_BIN/lsq")
PRIDE_ARSIG = Path("/home/excellence/.PRIDE_PPPAR_BIN/arsig")
PRIDE_TABLE = Path("/home/excellence/PRIDE-PPPAR/table")
PRIDE_REPO = Path("/home/excellence/PRIDE-PPPAR")

# PRIDE solution parsing: fixed-width data row.
#   cols 0-6    name
#   cols 7-16   Mjd
#   cols 17-31  X
#   cols 32-46  Y
#   cols 47-61  Z
# followed by cofactor fields.
_POS_LINE_RE = re.compile(
    r"^\s*(?P<name>\S+)\s+"
    r"(?P<mjd>\d+\.\d+)\s+"
    r"(?P<x>-?\d+\.\d+)\s+"
    r"(?P<y>-?\d+\.\d+)\s+"
    r"(?P<z>-?\d+\.\d+)"
)


@dataclass(frozen=True)
class PrideSolution:
    """One parsed static PRIDE PPP-AR station position."""

    station: str
    mjd: float
    ecef: EcefCoordinate
    reference_frame: str
    coordinate_epoch: str
    product: str
    antfile: str


class PrideError(RuntimeError):
    """Raised when PRIDE PPP-AR fails to produce a usable static position."""


def parse_pride_pos(path: Path) -> PrideSolution:
    """Parse the single static result row from a PRIDE ``pos_YYYYDOY_site`` file."""
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    data_row: str | None = None
    sat_orbit = ""
    antfile = ""
    for line in lines:
        stripped = line.strip()
        if "WUM0MGXRAP" in line and len(sat_orbit) == 0:
            sat_orbit = line.strip()
        if "TABLE ANTEX" in line:
            antfile = line.strip()
        if stripped.startswith("*"):
            continue
        match = _POS_LINE_RE.match(stripped)
        if match and _is_station_name(match.group("name")):
            data_row = stripped

    if not data_row:
        raise PrideError(f"no static position row in {path}")
    match = _POS_LINE_RE.match(data_row)
    if not match:
        raise PrideError(f"cannot parse position row in {path}")

    frame = "IGS20"
    if "IGS14" in antfile or "igs14" in antfile.lower():
        frame = "IGS14"
    return PrideSolution(
        station=match.group("name"),
        mjd=float(match.group("mjd")),
        ecef=EcefCoordinate(
            x_m=float(match.group("x")),
            y_m=float(match.group("y")),
            z_m=float(match.group("z")),
        ),
        reference_frame=frame,
        coordinate_epoch=_epoch_from_mjd(float(match.group("mjd"))),
        product=sat_orbit,
        antfile=antfile,
    )


def _is_station_name(name: str) -> bool:
    return name.lower() in _STATION_NAMES


_STATION_NAMES = frozenset(
    {"abfc", "bike", "ekak", "ylad", "mgbo", "phri", "lgla", "enen", "unec"}
)


def _epoch_from_mjd(mjd: float) -> str:
    # MJD 60335.5 == 2024-01-26 12:00 UTC
    epoch = datetime(1858, 11, 17, tzinfo=UTC) + _mjd_timedelta(mjd)
    return epoch.isoformat(timespec="seconds").replace("+00:00", "Z")


def _mjd_timedelta(mjd: float) -> timedelta:
    return timedelta(days=mjd)


def build_authoritative_coordinate_registry(
    pride_pos_files: dict[str, Path],
    out_path: Path,
) -> dict[str, Any]:
    """Build and persist the authoritative station-coordinate registry.

    Each station's final static PRIDE PPP-AR position (the last ``pos_*_site``
    written by the completed run) is recorded with its IGS20 reference frame,
    the weighted observation-mean epoch, the WUM product and ANTEX table from
    the solution header, and a SHA-256 of the raw ``pos_*`` file so the
    derivation is reproducible.  Stations whose position is not scientifically
    usable (for example those with a poor variance factor or too few
    observations) are recorded with ``scientifically_valid=false`` rather than
    being silently dropped or substituted.
    """
    stations: dict[str, dict[str, object]] = {}
    for station_id, pos_path in sorted(pride_pos_files.items()):
        solution = parse_pride_pos(pos_path)
        valid = is_usable_pride_solution(pos_path)
        stations[station_id] = {
            "site": solution.station,
            "mjd": solution.mjd,
            "ecef": {
                "x_m": solution.ecef.x_m,
                "y_m": solution.ecef.y_m,
                "z_m": solution.ecef.z_m,
            },
            "reference_frame": solution.reference_frame,
            "coordinate_epoch": solution.coordinate_epoch,
            "pride_product": solution.product,
            "antex_table": solution.antfile,
            "pos_file_sha256": sha256_file(pos_path),
            "pos_file_path": str(pos_path),
            "scientifically_valid": valid,
        }
    registry = {
        "schema_version": "1.0",
        "source_method": (
            "PRIDE PPP-AR static daily solutions with WUM rapid products, "
            "IGS20 reference frame, observation-epoch coordinate"
        ),
        "stations": stations,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(registry, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return registry


def load_coordinate_registry(path: Path) -> dict[str, Any]:
    """Load the persisted authoritative coordinate registry from JSON."""
    if not path.is_file():
        return {}
    payload: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return payload.get("stations", {}) or {}


def is_usable_pride_solution(pos_path: Path) -> bool:
    """Return False when a PRIDE static solution is not scientifically usable.

    PRIDE writes, on the static result line, the square root of the variance
    factor (``Sig0``) and the number of observations (``Nobs``).  On the real
    Phase 3 2024/026 data the usable full-session stations have ``Sig0`` in the
    1.6-2.0 m range with roughly 60-70 000 observations, whereas a station with
    seriously degraded data quality (BKFP) shows ``Sig0`` of about 12.6 m with
    only 64 observations.

    The admission check therefore requires both a bounded variance factor
    (``Sig0 <= 5.0`` m) and a meaningful daily observation count
    (``Nobs >= 1000``).  A solution that fails either check is retained in the
    registry but flagged ``scientifically_valid`` false so it can never be
    silently used as an RTK control reference.
    """
    text = pos_path.read_text(encoding="utf-8", errors="replace")
    for line in text.splitlines():
        if not line.lstrip().lower().startswith(tuple(_STATION_NAMES)):
            continue
        if line.lstrip().startswith("*"):
            continue
        fields = line.split()
        if len(fields) >= 13:
            try:
                sig0 = float(fields[11])
                nobs = int(float(fields[12]))
            except ValueError:
                return False
            return sig0 <= 5.0 and nobs >= 1000
    return False


def pride_binary_hashes() -> dict[str, str]:
    """Record SHA-256 of the PRIDE PPP-AR binaries used for derivation."""
    result: dict[str, str] = {}
    for name, path in (("pdp3", PDP3), ("lsq", PRIDE_LSQ), ("arsig", PRIDE_ARSIG)):
        if path.exists():
            result[name] = sha256_file(path)
    return result


def run_pride_static(
    observation: Path,
    work_dir: Path,
    *,
    timeout_seconds: float = 1800.0,
) -> tuple[PrideSolution, Path]:
    """Run one PRIDE PPP-AR static daily solution and parse its position.

    Returns ``(solution, pos_path)`` where ``pos_path`` is the generated
    ``pos_*_<site>`` result file.
    """
    work_dir.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        [str(PDP3), "-m", "S", str(observation)],
        check=False,
        cwd=str(work_dir),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        timeout=timeout_seconds,
    )
    if result.returncode != 0:
        raise PrideError(f"PRIDE PPP-AR failed rc={result.returncode}\n{result.stdout[-4000:]}")

    site = observation.stem[:4].lower()
    pos_candidates = sorted(work_dir.rglob(f"pos_*_{site}"))
    if not pos_candidates:
        raise PrideError("PRIDE produced no pos_*_site output")
    pos_path = pos_candidates[-1]
    return parse_pride_pos(pos_path), pos_path
