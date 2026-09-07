"""RINEX filename and header parsing for Phase 3 station identity and QC.

The preserved delivery uses RINEX 2.11 ``*.24D.Z`` files whose **filename
prefix does not always equal the folder name** (e.g. folder ``BKFP00NGA``
contains files named ``BIKE...``).  Authoritative station identity must be
resolved from RINEX headers, not folder names.

This module provides deterministic filename parsing and lightweight header
parsing used to attribute an observation to a canonical NLGCP station.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

# Folder marker names from the preserved delivery (mapping to canonical ids
# is done by the caller using authoritative station metadata).

FILE_TYPE_BY_SUFFIX = {
    "O": "observation",
    "D": "observation_hatanaka",
    "N": "navigation_gps",
    "G": "navigation_glonass",
    "P": "navigation_mixed",
    "E": "navigation_galileo",
    "C": "navigation_bds",
    "L": "navigation_qzss",
    "S": "navigation_sbas",
}


@dataclass(frozen=True)
class RinexFilename:
    """Fields parsed from a RINEX 2.x compressed filename."""

    marker: str
    doy: int
    session: str
    year_2digit: int
    file_type: str
    compress_flag: str


def parse_rinex_filename(name: str) -> RinexFilename:
    """Parse a RINEX 2.11-style filename (e.g. ``ABFC0260.24D.Z``).

    The RINEX 2.x filename format is ``ssssdddf.yyt`` where ``ssss`` is the
    four-character station marker, ``ddd`` the day-of-year, ``f`` the session
    flag, ``yy`` the two-digit year, and ``t`` the file type character.
    A trailing ``.Z`` denotes Unix compression; a preceding ``.gz`` a gzip
    compression.  We accept a trailing ``.Z``/``.gz``.

    Raises ``ValueError`` if the name is not a plausible RINEX 2.x filename.
    """
    base = name
    compress_flag = ""
    if base.endswith(".Z"):
        compress_flag = "Z"
        base = base[:-2]
    elif base.endswith(".gz"):
        compress_flag = "gz"
        base = base[:-3]

    match = re.fullmatch(
        r"(?P<marker>[A-Za-z0-9]{4})(?P<doy>\d{3})(?P<session>[0-9A-Z])\.(?P<year>\d{2})(?P<type>[A-Za-z])",
        base,
    )
    if not match:
        raise ValueError(f"not a RINEX 2.x filename: {name}")
    file_type = match.group("type").upper()
    if file_type not in FILE_TYPE_BY_SUFFIX:
        raise ValueError(f"unrecognised RINEX file type {file_type!r} in {name}")
    doy = int(match.group("doy"))
    if not 1 <= doy <= 366:
        raise ValueError(f"day-of-year out of range in {name}")
    return RinexFilename(
        marker=match.group("marker").upper(),
        doy=doy,
        session=match.group("session"),
        year_2digit=int(match.group("year")),
        file_type=file_type,
        compress_flag=compress_flag,
    )


@dataclass(frozen=True)
class RinexHeader:
    """Key RINEX 2.x observation header fields relevant to station identity."""

    rinex_version: str
    file_type: str
    marker_name: str | None
    marker_number: str | None
    approx_position_xyz: tuple[float, float, float] | None


def read_rinex2_header(path: Path, max_lines: int = 500) -> RinexHeader:
    """Read a plain (non-Hatanaka) RINEX 2.x observation header.

    The header is the block of lines before the first ``END OF HEADER``
    marker.  Marker name and number and APPROX POSITION XYZ are returned
    where present.
    """
    rinex_version = ""
    file_type = ""
    marker_name: str | None = None
    marker_number: str | None = None
    approx: tuple[float, float, float] | None = None

    with path.open(encoding="utf-8", errors="replace") as handle:
        for _ in range(max_lines):
            line = handle.readline()
            if not line:
                break
            if len(line) < 60:
                continue
            label = line[60:80].strip()
            if label == "RINEX VERSION / TYPE":
                rinex_version = line[0:9].strip()
                file_type = line[20:21].strip()
            elif label == "MARKER NAME":
                marker_name = line[0:60].strip()
            elif label == "MARKER NUMBER":
                marker_number = line[0:20].strip()
            elif label == "APPROX POSITION XYZ":
                try:
                    approx = (
                        float(line[0:14]),
                        float(line[14:28]),
                        float(line[28:42]),
                    )
                except ValueError:
                    approx = None
            elif label == "END OF HEADER":
                break
    return RinexHeader(
        rinex_version=rinex_version,
        file_type=file_type,
        marker_name=marker_name,
        marker_number=marker_number,
        approx_position_xyz=approx,
    )


def resolve_year(four_digit_year: int, two_digit_year: int) -> int:
    """Resolve a two-digit year to a four-digit year near a reference year."""
    modulus = (two_digit_year - (four_digit_year % 100)) % 100
    return (
        four_digit_year - (100 - modulus)
        if modulus > 50
        else four_digit_year + modulus
    )
