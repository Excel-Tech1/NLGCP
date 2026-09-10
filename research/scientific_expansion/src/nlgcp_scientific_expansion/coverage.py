"""Station x DOY coverage matrix construction (pure functions over parsed rows).

Inputs are plain row dicts so tests run on synthetic fixtures without touching
the data root. Real-data loaders live in ``loaders.py``.
"""

from __future__ import annotations

from nlgcp_scientific_expansion.models import StationDayCoverage

_CANONICAL_STATIONS = (
    "ABFC00NGA",
    "BKFP00NGA",
    "EKAK00NGA",
    "FUTY00NGA",
    "MGBO00NGA",
    "PHRI00NGA",
    "ULAG00NGA",
    "UNEC00NGA",
)

# Stations with scientifically valid PRIDE PPP-AR coordinates at DOY 2024/026.
COORDINATED_STATIONS = frozenset(
    {"ABFC00NGA", "EKAK00NGA", "MGBO00NGA", "PHRI00NGA"}
)


def canonical_station_ids() -> tuple[str, ...]:
    """Return the eight canonical 2024 OSGoF station identities."""
    return _CANONICAL_STATIONS


def build_coverage_matrix(
    manifest_records: list[dict[str, object]],
    qc_rows: list[dict[str, str]],
    nav_by_day: dict[int, str],
    coordinate_days: dict[str, set[int]],
    year: int,
) -> list[StationDayCoverage]:
    """Join canonical manifest + QC session table + nav inventory + coordinates.

    ``manifest_records`` carry ``station_id``/``day_of_year``/path/sha keys.
    ``qc_rows`` carry the Phase 4 ``session-qc-summary.csv`` columns.
    ``nav_by_day`` maps DOY to the accepted navigation product filename.
    ``coordinate_days`` maps station id to admitted coordinate DOYs.
    """
    qc_by_key: dict[tuple[str, int], dict[str, str]] = {}
    for row in qc_rows:
        try:
            key = (str(row["station_id"]), int(str(row["day_of_year"])))
        except (KeyError, ValueError):
            continue
        qc_by_key[key] = row

    observed: dict[tuple[str, int], dict[str, object]] = {}
    for record in manifest_records:
        try:
            station = str(record["station_id"])
            doy = int(str(record["day_of_year"]))
        except (KeyError, TypeError, ValueError):
            continue
        if station not in _CANONICAL_STATIONS:
            continue
        observed[(station, doy)] = record

    cells: list[StationDayCoverage] = []
    for (station, doy), record in sorted(observed.items()):
        qc = qc_by_key.get((station, doy), {})
        findings = tuple(
            code for code in str(qc.get("finding_codes", "")).split(";") if code
        )
        classification = str(qc.get("classification", "UNKNOWN")) or "UNKNOWN"
        nav_product = nav_by_day.get(doy, "")
        coordinate_eligible = doy in coordinate_days.get(station, set())
        availability = _parse_float(qc.get("availability_percent", ""))
        epochs = _parse_int(qc.get("epochs_observed", ""))
        block_reason = _block_reason(
            classification, findings, nav_product, coordinate_eligible
        )
        processable = (
            classification == "ACCEPT"
            and bool(nav_product)
            and coordinate_eligible
            and "FULL_SESSION" in findings
        )
        cells.append(
            StationDayCoverage(
                station_id=station,
                year=year,
                doy=doy,
                observation_available=True,
                observation_path=str(record.get("canonical_relative_path", "")),
                observation_sha256=str(record.get("sha256", "")),
                qc_classification=classification,
                qc_findings=findings,
                availability_percent=availability,
                epochs_observed=epochs,
                navigation_available=bool(nav_product),
                navigation_product=nav_product,
                coordinate_eligible=coordinate_eligible,
                processable_single_base=processable,
                block_reason=block_reason,
            )
        )
    return cells


def _block_reason(
    classification: str,
    findings: tuple[str, ...],
    nav_product: str,
    coordinate_eligible: bool,
) -> str:
    if classification == "ACCEPT" and nav_product and coordinate_eligible:
        return ""
    reasons: list[str] = []
    if classification == "REJECT":
        reasons.append("BLOCKED_QC_REJECT")
    elif classification == "BLOCKED":
        if "NAVIGATION_PRODUCT_MISSING" in findings:
            reasons.append("BLOCKED_NAVIGATION")
        if not coordinate_eligible:
            reasons.append("BLOCKED_COORDINATE_INTERVAL")
        if "SEVERE_SESSION_TRUNCATION" in findings:
            reasons.append("BLOCKED_QC_TRUNCATION")
        if "MAJOR_OBSERVATION_GAP" in findings:
            reasons.append("BLOCKED_QC_GAP")
        if not reasons:
            reasons.append("BLOCKED_QC")
    elif classification == "WARN":
        reasons.append("BLOCKED_QC_WARN")
    else:
        reasons.append("BLOCKED_UNKNOWN_QC_STATE")
    return ";".join(reasons)


def _parse_float(value: object) -> float:
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return 0.0


def _parse_int(value: object) -> int:
    try:
        return int(float(str(value)))
    except (TypeError, ValueError):
        return 0
