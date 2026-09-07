"""Broadcast navigation (ephemeris) association for Phase 3 experiments.

Real single-base RTK requires navigation inputs validated for temporal
compatibility with the observation window.  The preserved delivery contains
no navigation files, so Phase 3 selects global broadcast navigation from the
IGS BRDC archive and records full provenance (source, product type, SHA-256,
coverage).

Navigation association is deterministic.  The product key embeds the year and
day-of-year so that a navigation file intended for another epoch cannot be
silently reused.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from nlgcp_single_base.io import sha256_file

# IGS nightly merged broadcast navigation, RINEX 3.04 mixed constellation.
# Released once per day with >99% coverage; local source pinned to the IGS
# BKG archive used for reproducible acquisition.
BRDC_PRODUCT_TEMPLATE = "BRDC00IGS_R_{year}{doy:03d}0000_01D_MN.rnx.gz"
BRDC_PRODUCT_TYPE = "igs_broadcast_navigation_mixed"
BRDC_SOURCE = "https://igs.bkg.bund.de/root_ftp/IGS/BRDC/{year}/{doy:03d}/{name}"

# BRDC00IGS_R_20240260000_01D_MN.rnx.gz
_BRDC_RE = re.compile(r"BRDC00IGS_R_(?P<year>\d{4})(?P<doy>\d{3})\d{4}_(?P<tail>.+)")


@dataclass(frozen=True)
class NavigationProduct:
    """A broadcast navigation product with provenance."""

    path: Path
    sha256: str
    product_type: str
    source_url: str
    year: int
    day_of_year: int

    def key(self) -> str:
        """Deterministic product key embedding the intended epoch."""
        return f"{self.product_type}:{self.year}-{self.day_of_year:03d}"


def brdc_filename(year: int, doy: int) -> str:
    """Name of the IGS merged broadcast navigation file for a given epoch."""
    return BRDC_PRODUCT_TEMPLATE.format(year=year, doy=doy)


def brdc_source_url(year: int, doy: int) -> str:
    """Source URL for the IGS merged broadcast navigation for an epoch."""
    name = brdc_filename(year, doy)
    return BRDC_SOURCE.format(year=year, doy=doy, name=name)


def parse_brdc_epoch(path: Path) -> tuple[int, int]:
    """Return (year, doy) embedded in an IGS BRDC filename."""
    match = _BRDC_RE.fullmatch(path.name)
    if not match:
        raise ValueError(f"not an IGS BRDC navigation filename: {path.name}")
    return int(match.group("year")), int(match.group("doy"))


def verify_navigation_product(path: Path, year: int, doy: int) -> NavigationProduct:
    """Validate an existing navigation file against its expected epoch.

    The navigation file must already exist on disk.  Its SHA-256 is recorded
    and the epoch embedded in the deterministic filename is checked against
    the requested ``(year, doy)`` so a product for another date cannot be
    passed as the right one for an experiment.
    """
    if not path.is_file():
        raise FileNotFoundError(f"navigation file not found: {path}")
    actual_year, actual_doy = parse_brdc_epoch(path)
    if (actual_year, actual_doy) != (year, doy):
        raise ValueError(
            f"navigation product epoch mismatch: {path.name} is "
            f"{actual_year}-{actual_doy:03d}, expected {year}-{doy:03d}"
        )
    return NavigationProduct(
        path=path.resolve(),
        sha256=sha256_file(path),
        product_type=BRDC_PRODUCT_TYPE,
        source_url=brdc_source_url(year, doy),
        year=year,
        day_of_year=doy,
    )
