"""Transparent station-health, network-overlap, tables, figures, and report outputs."""

from __future__ import annotations

import csv
import json
import statistics
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from nlgcp_gnss_qc.dataset import inventory_navigation_products


def load_profile_results(data_root: Path, profile: str) -> list[dict[str, Any]]:
    root = data_root / "processed" / "qc" / "profiles" / profile / "sessions"
    results = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(root.rglob("qc-result.json"))
    ]
    if not results:
        raise ValueError(f"no QC results found for profile {profile!r} under {root}")
    return results


def summarize_profile(data_root: Path, profile: str) -> dict[str, Any]:
    """Generate all Phase 4 summaries from stored measured session results."""

    results = load_profile_results(data_root, profile)
    output = data_root / "processed" / "qc" / "profiles" / profile
    tables = output / "tables"
    figures = output / "figures"
    summaries = output / "summaries"
    reports = output / "reports"
    for directory in (tables, figures, summaries, reports):
        directory.mkdir(parents=True, exist_ok=True)

    session_rows = [_session_row(result) for result in results]
    station_rows = _station_health(session_rows)
    overlap_rows, overlap_windows = _network_overlap(session_rows)
    equipment_rows, equipment_change_count = _equipment_history(results)
    aliases = _alias_rows(results)
    duplicates = _duplicate_rows(results)
    navigation_rows = _navigation_rows(results)
    rejected = [row for row in session_rows if row["classification"] == "REJECT"]
    blocked = [row for row in session_rows if row["classification"] == "BLOCKED"]

    table_paths = {
        "session_qc_summary": tables / "session-qc-summary.csv",
        "station_health_summary": tables / "station-health-summary.csv",
        "network_overlap_summary": tables / "network-overlap-summary.csv",
        "equipment_history": tables / "equipment-history.csv",
        "navigation_coverage": tables / "navigation-coverage.csv",
        "rejected_sessions": tables / "rejected-sessions.csv",
        "blocked_sessions": tables / "blocked-sessions.csv",
        "known_aliases": tables / "known-aliases.csv",
        "known_duplicates": tables / "known-duplicates.csv",
    }
    _write_csv(table_paths["session_qc_summary"], session_rows)
    _write_csv(table_paths["station_health_summary"], station_rows)
    _write_csv(table_paths["network_overlap_summary"], overlap_rows)
    _write_csv(table_paths["equipment_history"], equipment_rows)
    _write_csv(table_paths["navigation_coverage"], navigation_rows)
    _write_csv(table_paths["rejected_sessions"], rejected, fallback_fields=_session_fields())
    _write_csv(table_paths["blocked_sessions"], blocked, fallback_fields=_session_fields())
    _write_csv(
        table_paths["known_aliases"],
        aliases,
        fallback_fields=["station_id", "marker", "session_count"],
    )
    _write_csv(
        table_paths["known_duplicates"],
        duplicates,
        fallback_fields=["station_id", "year", "day_of_year", "retained", "excluded", "sha256"],
    )

    counts = Counter(row["classification"] for row in session_rows)
    finding_counts = Counter(
        finding["finding_code"] for result in results for finding in result.get("findings", [])
    )
    products = inventory_navigation_products(data_root)
    summary = {
        "profile": profile,
        "profile_version": results[0]["qc_profile"]["version"],
        "profile_status": results[0]["qc_profile"]["status"],
        "sessions_processed": len(session_rows),
        "stations_processed": sorted({row["station_id"] for row in session_rows}),
        "classification_counts": {
            key: counts.get(key, 0) for key in ("ACCEPT", "WARN", "REJECT", "BLOCKED")
        },
        "duplicate_findings": finding_counts.get("EXACT_DUPLICATE", 0),
        "partial_sessions": finding_counts.get("PARTIAL_SESSION", 0)
        + finding_counts.get("SEVERE_SESSION_TRUNCATION", 0),
        "sampling_anomalies": finding_counts.get("UNEXPECTED_SAMPLING_INTERVAL", 0)
        + finding_counts.get("MALFORMED_EPOCH_SEQUENCE", 0),
        "major_gaps": finding_counts.get("MAJOR_OBSERVATION_GAP", 0),
        "potential_cycle_slip_indicators": sum(
            int((result.get("rinex") or {}).get("potential_cycle_slip_indicators", 0))
            for result in results
        ),
        "aliases_resolved": aliases,
        "equipment_changes": equipment_change_count,
        "navigation_covered_sessions": sum(row["navigation_available"] for row in session_rows),
        "navigation_blocked_sessions": finding_counts.get("NAVIGATION_PRODUCT_MISSING", 0),
        "external_product_inventory": [product.as_dict() for product in products],
        "network_overlap_windows": overlap_windows,
        "station_health": station_rows,
        "tables": {name: str(path) for name, path in table_paths.items()},
    }
    _atomic_json(summaries / "phase4-summary.json", summary)
    _atomic_json(summaries / "network-overlap-windows.json", {"windows": overlap_windows})
    _atomic_json(
        summaries / "external-product-inventory.json",
        {"schema_version": "1.0", "products": [product.as_dict() for product in products]},
    )
    figure_paths = _figures(figures, station_rows, overlap_rows)
    summary["figures"] = [str(path) for path in figure_paths]
    canonical_report = data_root / "validation" / "reports" / "phase4-gnss-qc-validation-report.md"
    canonical_report.parent.mkdir(parents=True, exist_ok=True)
    summary["validation_report"] = str(canonical_report)
    _atomic_json(summaries / "phase4-summary.json", summary)
    report_text = _report(summary, results)
    (reports / "phase4-gnss-qc-validation-report.md").write_text(report_text, encoding="utf-8")
    canonical_report.write_text(report_text, encoding="utf-8")
    return summary


def _session_row(result: dict[str, Any]) -> dict[str, Any]:
    identity = result["station_identity"]
    rinex = result.get("rinex") or {}
    findings = result.get("findings", [])
    return {
        "station_id": identity["canonical_station_id"],
        "year": identity["year"],
        "day_of_year": identity["day_of_year"],
        "classification": result["overall_classification"],
        "source_path": result["source"]["relative_path"],
        "source_sha256": result["source"].get("observed_sha256"),
        "first_epoch": rinex.get("first_epoch"),
        "last_epoch": rinex.get("last_epoch"),
        "availability_percent": rinex.get("availability_percent"),
        "epochs_observed": rinex.get("epochs_observed"),
        "epochs_expected": rinex.get("epochs_expected"),
        "gap_count": rinex.get("gap_count"),
        "largest_gap_seconds": rinex.get("largest_gap_seconds"),
        "satellites_median": rinex.get("satellites_median"),
        "navigation_available": result.get("navigation") is not None,
        "identity_resolution": identity.get("resolution"),
        "finding_codes": ";".join(finding["finding_code"] for finding in findings),
    }


def _station_health(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[row["station_id"]].append(row)
    output: list[dict[str, Any]] = []
    for station_id, station_rows in sorted(grouped.items()):
        counts = Counter(row["classification"] for row in station_rows)
        completeness = [
            float(row["availability_percent"])
            for row in station_rows
            if row["availability_percent"] is not None
        ]
        accepted_or_warned = counts["ACCEPT"] + counts["WARN"]
        output.append(
            {
                "station_id": station_id,
                "days_available": len(station_rows),
                "days_accepted": counts["ACCEPT"],
                "days_warned": counts["WARN"],
                "days_rejected": counts["REJECT"],
                "days_blocked": counts["BLOCKED"],
                "calendar_availability_rate": len(station_rows) / 366,
                "qc_usable_rate_of_available_days": accepted_or_warned / len(station_rows),
                "full_session_rate": sum(value >= 99.0 for value in completeness)
                / len(completeness)
                if completeness
                else None,
                "mean_completeness_percent": statistics.mean(completeness)
                if completeness
                else None,
                "median_completeness_percent": statistics.median(completeness)
                if completeness
                else None,
                "sessions_with_major_gaps": sum(
                    "MAJOR_OBSERVATION_GAP" in row["finding_codes"] for row in station_rows
                ),
                "navigation_covered_days": sum(row["navigation_available"] for row in station_rows),
            }
        )
    return output


def _network_overlap(
    rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    by_day: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_day[int(row["day_of_year"])].append(row)
    output: list[dict[str, Any]] = []
    for doy in range(1, 367):
        day_rows = by_day.get(doy, [])
        accepted = sorted(
            row["station_id"] for row in day_rows if row["classification"] == "ACCEPT"
        )
        warned = sorted(row["station_id"] for row in day_rows if row["classification"] == "WARN")
        output.append(
            {
                "year": 2024,
                "day_of_year": doy,
                "date": (date(2024, 1, 1) + timedelta(days=doy - 1)).isoformat(),
                "files_present": len(day_rows),
                "accepted_station_count": len(accepted),
                "warned_station_count": len(warned),
                "qc_qualified_station_count": len(accepted),
                "qc_qualified_stations": ";".join(accepted),
                "navigation_covered_sessions": sum(row["navigation_available"] for row in day_rows),
            }
        )
    windows: list[dict[str, Any]] = []
    for minimum in range(1, 9):
        active_start: int | None = None
        for doy in range(1, 368):
            qualifies = doy <= 366 and output[doy - 1]["qc_qualified_station_count"] >= minimum
            if qualifies and active_start is None:
                active_start = doy
            if not qualifies and active_start is not None:
                end = doy - 1
                windows.append(
                    {
                        "minimum_station_count": minimum,
                        "start_doy": active_start,
                        "end_doy": end,
                        "duration_days": end - active_start + 1,
                    }
                )
                active_start = None
    windows.sort(
        key=lambda row: (row["minimum_station_count"], -row["duration_days"], row["start_doy"])
    )
    return output, windows


def _equipment_history(
    results: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], int]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for result in results:
        grouped[result["station_identity"]["canonical_station_id"]].append(result)
    rows: list[dict[str, Any]] = []
    changes = 0
    for station_id, station_results in sorted(grouped.items()):
        station_results.sort(key=lambda result: result["station_identity"]["day_of_year"])
        previous: tuple[Any, ...] | None = None
        segment: dict[str, Any] | None = None
        for result in station_results:
            header = (result.get("rinex") or {}).get("header", {})
            equipment = (
                header.get("receiver_number"),
                header.get("receiver_type"),
                header.get("receiver_version"),
                header.get("antenna_number"),
                header.get("antenna_type"),
                json.dumps(header.get("antenna_delta_hen_m")),
            )
            doy = result["station_identity"]["day_of_year"]
            if previous != equipment:
                if segment is not None:
                    rows.append(segment)
                    changes += 1
                segment = {
                    "station_id": station_id,
                    "start_doy": doy,
                    "end_doy": doy,
                    "receiver_number": equipment[0],
                    "receiver_type": equipment[1],
                    "receiver_version": equipment[2],
                    "antenna_number": equipment[3],
                    "antenna_type": equipment[4],
                    "antenna_delta_hen_m": equipment[5],
                    "change_status": "RINEX_HEADER_OBSERVED; authoritative effective-date metadata unavailable",
                }
                previous = equipment
            elif segment is not None:
                segment["end_doy"] = doy
        if segment is not None:
            rows.append(segment)
    return rows, changes


def _alias_rows(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts: Counter[tuple[str, str]] = Counter()
    for result in results:
        if result["station_identity"].get("resolution") != "KNOWN_ALIAS":
            continue
        header = (result.get("rinex") or {}).get("header", {})
        counts[
            (result["station_identity"]["canonical_station_id"], header.get("marker_name", ""))
        ] += 1
    return [
        {"station_id": station, "marker": marker, "session_count": count}
        for (station, marker), count in sorted(counts.items())
    ]


def _duplicate_rows(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for result in results:
        source = result["source"]
        identity = result["station_identity"]
        for excluded in source.get("exact_duplicate_sources", []):
            rows.append(
                {
                    "station_id": identity["canonical_station_id"],
                    "year": identity["year"],
                    "day_of_year": identity["day_of_year"],
                    "retained": source["relative_path"],
                    "excluded": excluded,
                    "sha256": source["manifest_sha256"],
                }
            )
    return rows


def _navigation_rows(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "station_id": result["station_identity"]["canonical_station_id"],
            "year": result["station_identity"]["year"],
            "day_of_year": result["station_identity"]["day_of_year"],
            "available": result.get("navigation") is not None,
            "path": (result.get("navigation") or {}).get("relative_path"),
            "sha256": (result.get("navigation") or {}).get("sha256"),
            "acquisition_provenance": (result.get("navigation") or {}).get(
                "acquisition_provenance"
            ),
        }
        for result in results
    ]


def _figures(
    directory: Path,
    station_rows: list[dict[str, Any]],
    overlap_rows: list[dict[str, Any]],
) -> list[Path]:
    paths = [
        directory / "station-classification-counts.svg",
        directory / "station-mean-completeness.svg",
        directory / "network-qualified-availability.svg",
        directory / "navigation-coverage.svg",
    ]
    _stacked_station_svg(paths[0], station_rows)
    _bar_svg(
        paths[1],
        "Mean session completeness by station (%)",
        [(row["station_id"], float(row["mean_completeness_percent"] or 0)) for row in station_rows],
        100.0,
    )
    _line_svg(
        paths[2],
        "QC-qualified station availability by 2024 day-of-year",
        [(int(row["day_of_year"]), int(row["qc_qualified_station_count"])) for row in overlap_rows],
        8,
    )
    _line_svg(
        paths[3],
        "Sessions with catalogued broadcast navigation by 2024 day-of-year",
        [
            (
                int(row["day_of_year"]),
                int(row["navigation_covered_sessions"]),
            )
            for row in overlap_rows
        ],
        8,
    )
    return paths


def _stacked_station_svg(path: Path, rows: list[dict[str, Any]]) -> None:
    colours = {"ACCEPT": "#1b9e77", "WARN": "#e6ab02", "REJECT": "#d95f02", "BLOCKED": "#7570b3"}
    width, height, margin = 900, 480, 70
    maximum = max((row["days_available"] for row in rows), default=1)
    parts = [_svg_start(width, height, "Session classifications by station")]
    bar_width = (width - 2 * margin) / max(len(rows), 1) * 0.7
    for index, row in enumerate(rows):
        x = margin + index * ((width - 2 * margin) / len(rows))
        y = height - margin
        for classification in ("ACCEPT", "WARN", "REJECT", "BLOCKED"):
            key = {
                "ACCEPT": "days_accepted",
                "WARN": "days_warned",
                "REJECT": "days_rejected",
                "BLOCKED": "days_blocked",
            }[classification]
            count = row[key]
            segment = count / maximum * (height - 2 * margin)
            y -= segment
            parts.append(
                f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_width:.1f}" height="{segment:.1f}" fill="{colours[classification]}"/>'
            )
        parts.append(
            f'<text x="{x + bar_width / 2:.1f}" y="{height - 40}" text-anchor="middle" font-size="11">{row["station_id"][:4]}</text>'
        )
    parts.append("</svg>\n")
    path.write_text("".join(parts), encoding="utf-8")


def _bar_svg(path: Path, title: str, values: list[tuple[str, float]], maximum: float) -> None:
    width, height, margin = 900, 480, 70
    parts = [_svg_start(width, height, title)]
    step = (width - 2 * margin) / max(len(values), 1)
    for index, (label, value) in enumerate(values):
        bar_height = value / maximum * (height - 2 * margin)
        x = margin + index * step + step * 0.15
        y = height - margin - bar_height
        parts.append(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{step * 0.7:.1f}" height="{bar_height:.1f}" fill="#377eb8"/>'
        )
        parts.append(
            f'<text x="{x + step * 0.35:.1f}" y="{height - 40}" text-anchor="middle" font-size="11">{label[:4]}</text>'
        )
        parts.append(
            f'<text x="{x + step * 0.35:.1f}" y="{max(y - 5, 25):.1f}" text-anchor="middle" font-size="10">{value:.1f}</text>'
        )
    parts.append("</svg>\n")
    path.write_text("".join(parts), encoding="utf-8")


def _line_svg(path: Path, title: str, values: list[tuple[int, int]], maximum: int) -> None:
    width, height, margin = 1000, 420, 60
    points = " ".join(
        f"{margin + (x - 1) / 365 * (width - 2 * margin):.1f},{height - margin - y / maximum * (height - 2 * margin):.1f}"
        for x, y in values
    )
    content = [
        _svg_start(width, height, title),
        f'<polyline points="{points}" fill="none" stroke="#1f78b4" stroke-width="2"/>',
        f'<line x1="{margin}" y1="{height - margin}" x2="{width - margin}" y2="{height - margin}" stroke="#333"/>',
        "</svg>\n",
    ]
    path.write_text("".join(content), encoding="utf-8")


def _svg_start(width: int, height: int, title: str) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}"><rect width="100%" height="100%" fill="white"/>'
        f'<text x="{width / 2}" y="24" text-anchor="middle" font-family="sans-serif" font-size="16">{title}</text>'
    )


def _provenance_limitation_sentence(products: list[dict[str, Any]]) -> str:
    """Evidence-based Known Limitations wording derived from the product inventory.

    The sentence reflects the catalogued external-product inventory instead of
    asserting a fixed provenance state. Missing provenance stays explicit: no
    provenance value is invented here.
    """

    if not products:
        return (
            "Only catalogued external navigation is counted; no external "
            "navigation products are currently catalogued, so acquisition "
            "provenance cannot be assessed from the inventory."
        )
    missing = sum(1 for product in products if not product.get("acquisition_provenance"))
    if missing == 0:
        if len(products) == 1:
            return (
                "Only catalogued external navigation is counted. Acquisition "
                "provenance and product hashes are recorded for the currently "
                "catalogued broadcast-navigation product."
            )
        return (
            f"Only catalogued external navigation is counted. Acquisition "
            f"provenance and product hashes are recorded for all {len(products)} "
            f"currently catalogued broadcast-navigation products."
        )
    return (
        f"Only catalogued external navigation is counted. Product hashes are "
        f"recorded; missing acquisition provenance remains explicit for "
        f"{missing} of {len(products)} catalogued product(s)."
    )


def _report(summary: dict[str, Any], results: list[dict[str, Any]]) -> str:
    counts = summary["classification_counts"]
    stations = summary["stations_processed"]
    windows = summary["network_overlap_windows"]
    longest = next((row for row in windows if row["minimum_station_count"] == 4), None)
    provenance_sentence = _provenance_limitation_sentence(
        summary.get("external_product_inventory", [])
    )
    observation_types = sorted(
        {
            value
            for result in results
            for value in (
                (result.get("rinex") or {}).get("header", {}).get("observation_types", [])
            )
        }
    )
    return f"""# NLGCP Phase 4 GNSS QC Validation Report

## 1. Objective

Determine, with structured evidence, whether each canonical 2024 station-day is ACCEPT, WARN, REJECT, or BLOCKED before later scientific processing.

## 2. Data scope

Processed {summary["sessions_processed"]} canonical observation sessions from {len(stations)} stations: {", ".join(stations)}. Raw delivery and canonical raw files were not modified.

## 3. QC architecture

The engine verifies canonical-manifest hashes, converts immutable Hatanaka/Unix-compressed inputs into a derivative working corpus, streams RINEX observations, records structured findings, then aggregates station and network health. Profile outputs are isolated to avoid overwrites.

## 4. QC profiles

This report uses `{summary["profile"]}` profile version {summary["profile_version"]}. Status: {summary["profile_status"]}. Thresholds are centralized, versioned, and provisional; no uncalibrated C/N0, residual, satellite-count, or cycle-slip rejection threshold is claimed.

## 5. File integrity and conversion

All decisions retain manifest and observed hashes. {summary["duplicate_findings"]} canonical session(s) reference an excluded exact delivery duplicate. Converted observations are derivative files under `working/qc-converted`; originals remain preserved.

## 6. Station identity and RINEX metadata

Explicit aliases resolved: {len(summary["aliases_resolved"])}. Header fields include marker, observer/agency, receiver, antenna, approximate XYZ (frame not inferred), antenna delta, declared interval, observation types, first/last observation, and leap seconds. Observed types across the corpus: {", ".join(observation_types)}.

## 7. Temporal completeness, sampling, and gaps

Partial/severely truncated sessions: {summary["partial_sessions"]}. Sampling anomalies: {summary["sampling_anomalies"]}. Sessions exceeding the provisional major-gap criterion: {summary["major_gaps"]}. Exact gap intervals are in per-session `gaps.csv` files.

## 8. Satellites, constellations, observation types, and continuity

Per-session minimum/median/maximum satellite counts and per-constellation continuity are stored in JSON and CSV. Non-zero LLI values are reported only as potential cycle-slip indicators ({summary["potential_cycle_slip_indicators"]} observed); they are not asserted to be confirmed cycle slips.

## 9. Receiver and antenna continuity

Observed RINEX-header equipment transitions: {summary["equipment_changes"]}. Because authoritative effective-dated equipment records are unavailable, these are labelled observed transitions rather than automatically classified as faults.

## 10. Navigation and coordinate eligibility

Sessions with temporally compatible catalogued navigation: {summary["navigation_covered_sessions"]}. Navigation-blocked profile decisions: {summary["navigation_blocked_sessions"]}. Product hashes are recorded; missing acquisition provenance remains explicit. Positioning eligibility is separate from observation quality and requires verified frame/coordinate evidence for the station-day.

## 11. Station health and network availability

Classification totals: ACCEPT={counts["ACCEPT"]}, WARN={counts["WARN"]}, REJECT={counts["REJECT"]}, BLOCKED={counts["BLOCKED"]}. The longest ACCEPT-only window supporting at least four stations is {json.dumps(longest, sort_keys=True) if longest else "not available"}.

## 12. Rejected and blocked data

Rejected and blocked sessions are enumerated in separate machine-readable tables. REJECT denotes an observed-data failure; BLOCKED denotes missing external evidence or dependency.

## 13. Known limitations

- Scientific profile thresholds remain provisional pending Level 3 review/calibration.
- Coordinate eligibility is limited to the explicitly admitted Phase 3 coordinate epoch; no effective interval is invented.
- {provenance_sentence}
- LLI events are continuity indicators, not independently validated cycle-slip detections.
- This phase performs QC only; no NRTK, atmospheric interpolation, VRS, RTCM, NTRIP, or accuracy claim is implemented.

## 14. Reproducibility

Every result records input hash, profile version/hash, engine version, Git commit, working-tree state, conversion tool provenance, and execution timestamp. Tables and figures are generated from stored QC JSON rather than manually edited values.

## 15. Phase 5 implications and exit decision

Only ACCEPT sessions in the network-overlap table are automatically QC-qualified. WARN sessions require review; REJECT and BLOCKED sessions are excluded. Phase 4 remains in VALIDATION until provisional thresholds and external-product provenance receive scientific review. Phase 5 must not begin automatically.
"""


def _session_fields() -> list[str]:
    return [
        "station_id",
        "year",
        "day_of_year",
        "classification",
        "source_path",
        "source_sha256",
        "first_epoch",
        "last_epoch",
        "availability_percent",
        "epochs_observed",
        "epochs_expected",
        "gap_count",
        "largest_gap_seconds",
        "satellites_median",
        "navigation_available",
        "identity_resolution",
        "finding_codes",
    ]


def _write_csv(
    path: Path, rows: list[dict[str, Any]], fallback_fields: list[str] | None = None
) -> None:
    fields = list(rows[0]) if rows else (fallback_fields or [])
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        if fields:
            writer.writeheader()
            writer.writerows(rows)
    temporary.replace(path)


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)
