"""Station identity resolution against the authoritative Phase 2 registry.

Folder names in the preserved delivery do not equal RINEX marker names.
This module resolves a canonical NLGCP station id (``ABFC00NGA``) to and from
the RINEX marker seen in headers/filenames (``ABFC``, ``BIKE``, ``EKAK``,
``YLAD``, ``MGBO``, ``PHRI``, ``LGLA``, ``ENEN``/``UNEC``) using the
Phase 2 header registry.

It never invents identity: if a marker is not in the authoritative map the
resolution fails closed.
"""

from __future__ import annotations

from pathlib import Path

from nlgcp_single_base.rinrex import parse_rinex_filename

# Authoritative canonical station id -> RINEX marker(s) observed in the
# preserved 2024 delivery header registry.  Maintained as code so tests can
# pin it, but derived from the Phase 2 rinex-header-registry.csv.
CANONICAL_STATIONS: dict[str, tuple[str, ...]] = {
    "ABFC00NGA": ("ABFC",),
    "BKFP00NGA": ("BIKE",),
    "EKAK00NGA": ("EKAK",),
    "FUTY00NGA": ("YLAD",),
    "MGBO00NGA": ("MGBO",),
    "PHRI00NGA": ("PHRI",),
    "ULAG00NGA": ("LGLA",),
    "UNEC00NGA": ("ENEN", "UNEC"),
}

MARKER_TO_CANONICAL: dict[str, str] = {
    marker: station for station, markers in CANONICAL_STATIONS.items() for marker in markers
}


class StationIdentityError(ValueError):
    """Raised when a marker/filename cannot be attributed to a known station."""


def canonical_station_id_for_marker(marker: str) -> str:
    """Return the canonical NLGCP station id for a RINEX marker name."""
    key = marker.upper()
    try:
        return MARKER_TO_CANONICAL[key]
    except KeyError as exc:
        raise StationIdentityError(f"unknown RINEX marker: {marker}") from exc


def station_id_from_observation_filename(filename: str | Path) -> str:
    """Return the canonical station id for a RINEX observation filename."""
    name = filename.name if isinstance(filename, Path) else filename
    parsed = parse_rinex_filename(name)
    if parsed.file_type not in ("O", "D"):
        raise StationIdentityError(f"not an observation filename: {name}")
    return canonical_station_id_for_marker(parsed.marker)


def markers_for_canonical_station(station_id: str) -> tuple[str, ...]:
    """Return the known RINEX marker(s) for a canonical station id."""
    try:
        return CANONICAL_STATIONS[station_id]
    except KeyError as exc:
        raise StationIdentityError(f"unknown canonical station: {station_id}") from exc
