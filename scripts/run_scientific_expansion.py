"""CLI for the interim scientific-expansion sprint (Stages A–G)."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(
    0,
    os.path.join(
        os.path.dirname(__file__), "..", "research", "scientific_expansion", "src"
    ),
)


def _data_root(explicit: str) -> str:
    from nlgcp_scientific_expansion.loaders import data_root_from_env

    return data_root_from_env(explicit)


def cmd_coverage(args: argparse.Namespace) -> int:
    """Build the station x DOY coverage matrix from real manifests."""
    from nlgcp_scientific_expansion import coverage as coverage_mod
    from nlgcp_scientific_expansion import loaders

    root = _data_root(args.data_root)
    manifest = os.path.join(root, "manifests", "canonical-raw-archive-2024.json")
    qc_table = os.path.join(
        root, "processed", "qc", "profiles", "single_base_rtk", "tables",
        "session-qc-summary.csv",
    )
    nav_dir = os.path.join(root, "external-products", "brdc", "2024")
    records = loaders.load_manifest_records(manifest)
    qc_rows = loaders.load_qc_session_table(qc_table)
    nav_by_day = loaders.nav_inventory_by_day(
        nav_dir,
        os.path.join(
            root, "validation", "scientific-expansion-2024", "inventory",
            "navigation-products.csv",
        ),
    )
    coord_path = os.path.join(
        root, "processed", "single-base", "derived-coordinates.json"
    )
    with open(coord_path, encoding="utf-8") as handle:
        registry = json.load(handle).get("stations", {})
    coordinate_days: dict[str, set[int]] = {}
    for station_id, entry in registry.items():
        epoch = str(entry.get("coordinate_epoch", ""))
        if epoch.startswith("2024-01-26") and entry.get("scientifically_valid"):
            coordinate_days.setdefault(station_id, set()).add(26)
    cells = coverage_mod.build_coverage_matrix(
        records, qc_rows, nav_by_day, coordinate_days, year=2024
    )
    out_dir = os.path.join(root, "validation", "scientific-expansion-2024", "inventory")
    os.makedirs(out_dir, exist_ok=True)
    from nlgcp_scientific_expansion import reporting

    rows = [
        {
            "station_id": cell.station_id,
            "year": cell.year,
            "doy": cell.doy,
            "observation_available": cell.observation_available,
            "observation_path": cell.observation_path,
            "observation_sha256": cell.observation_sha256,
            "qc_classification": cell.qc_classification,
            "availability_percent": cell.availability_percent,
            "epochs_observed": cell.epochs_observed,
            "navigation_available": cell.navigation_available,
            "navigation_product": cell.navigation_product,
            "coordinate_eligible": cell.coordinate_eligible,
            "processable_single_base": cell.processable_single_base,
            "block_reason": cell.block_reason,
        }
        for cell in cells
    ]
    digest = reporting.write_csv(
        os.path.join(out_dir, "observation-coverage.csv"),
        [
            "station_id", "year", "doy", "observation_available",
            "observation_path", "observation_sha256", "qc_classification",
            "availability_percent", "epochs_observed", "navigation_available",
            "navigation_product", "coordinate_eligible",
            "processable_single_base", "block_reason",
        ],
        rows,
    )
    print(f"cells={len(cells)} sha256={digest}")
    return 0


def cmd_overlap(args: argparse.Namespace) -> int:
    """Compute multi-station overlap from the coverage matrix CSV."""
    import csv

    from nlgcp_scientific_expansion import overlap as overlap_mod
    from nlgcp_scientific_expansion.models import StationDayCoverage

    root = _data_root(args.data_root)
    inv = os.path.join(root, "validation", "scientific-expansion-2024", "inventory")
    coverage_csv = os.path.join(inv, "observation-coverage.csv")
    cells: list[StationDayCoverage] = []
    with open(coverage_csv, newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            findings = tuple(
                code for code in str(row.get("qc_classification", "")).split(";") if code
            )
            cells.append(
                StationDayCoverage(
                    station_id=row["station_id"],
                    year=int(row["year"]),
                    doy=int(row["doy"]),
                    observation_available=row["observation_available"] == "True",
                    observation_path=row.get("observation_path", ""),
                    observation_sha256=row.get("observation_sha256", ""),
                    qc_classification=row.get("qc_classification", ""),
                    qc_findings=findings,
                    availability_percent=float(row.get("availability_percent") or 0.0),
                    epochs_observed=int(float(row.get("epochs_observed") or 0)),
                    navigation_available=row.get("navigation_available") == "True",
                    navigation_product=row.get("navigation_product", ""),
                    coordinate_eligible=row.get("coordinate_eligible") == "True",
                    processable_single_base=row.get("processable_single_base") == "True",
                    block_reason=row.get("block_reason", ""),
                )
            )
    # NOTE: CSV round-trip drops raw finding codes; recompute FULL flags from
    # the QC session table so overlap filtering stays faithful.
    from nlgcp_scientific_expansion import loaders

    qc_table = os.path.join(
        root, "processed", "qc", "profiles", "single_base_rtk", "tables",
        "session-qc-summary.csv",
    )
    full_keys = {
        (row["station_id"], int(row["day_of_year"]))
        for row in loaders.load_qc_session_table(qc_table)
        if "FULL_SESSION" in row.get("finding_codes", "")
    }
    enriched = [
        StationDayCoverage(
            station_id=cell.station_id, year=cell.year, doy=cell.doy,
            observation_available=cell.observation_available,
            observation_path=cell.observation_path,
            observation_sha256=cell.observation_sha256,
            qc_classification=cell.qc_classification,
            qc_findings=(("FULL_SESSION",) if (cell.station_id, cell.doy) in full_keys else ()),
            availability_percent=cell.availability_percent,
            epochs_observed=cell.epochs_observed,
            navigation_available=cell.navigation_available,
            navigation_product=cell.navigation_product,
            coordinate_eligible=cell.coordinate_eligible,
            processable_single_base=cell.processable_single_base,
            block_reason=cell.block_reason,
        )
        for cell in cells
    ]
    days = overlap_mod.overlap_by_day(enriched)
    coord_days = overlap_mod.overlap_by_day(
        enriched, coordinated_only=True, require_full_session=True
    )
    from nlgcp_scientific_expansion import reporting

    reporting.write_csv(
        os.path.join(inv, "overlap-by-doy.csv"),
        ["year", "doy", "stations", "station_count", "candidate_experiment_type"],
        [
            {
                "year": day.year, "doy": day.doy,
                "stations": "+".join(day.stations),
                "station_count": day.station_count,
                "candidate_experiment_type": day.candidate_experiment_type,
            }
            for day in days
        ],
    )
    reporting.write_csv(
        os.path.join(inv, "overlap-coordinated-full.csv"),
        ["year", "doy", "stations", "station_count", "candidate_experiment_type"],
        [
            {
                "year": day.year, "doy": day.doy,
                "stations": "+".join(day.stations),
                "station_count": day.station_count,
                "candidate_experiment_type": day.candidate_experiment_type,
            }
            for day in coord_days
        ],
    )
    print(f"all_days={len(days)} coordinated_full_days={len(coord_days)}")
    print(f"all_counts={overlap_mod.count_days_by_overlap(days)}")
    print(f"coordinated_full_counts={overlap_mod.count_days_by_overlap(coord_days)}")
    return 0


def cmd_plan_nav(args: argparse.Namespace) -> int:
    """Write a deterministic BRDC acquisition plan for candidate days."""
    import csv

    from nlgcp_scientific_expansion import nav_acquisition, reporting

    root = _data_root(args.data_root)
    inv = os.path.join(root, "validation", "scientific-expansion-2024", "inventory")
    overlap_csv = os.path.join(inv, "overlap-coordinated-full.csv")
    doys: set[int] = set()
    with open(overlap_csv, newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if int(row["station_count"]) >= int(args.min_stations):
                doys.add(int(row["doy"]))
    plans = nav_acquisition.plan_products(sorted(doys), 2024)
    reporting.write_csv(
        os.path.join(inv, "navigation-plan.csv"),
        ["year", "doy", "provider", "source_url", "product_type",
         "expected_filename", "download_status"],
        [
            {
                "year": plan.year, "doy": plan.doy, "provider": plan.provider,
                "source_url": plan.source_url, "product_type": plan.product_type,
                "expected_filename": plan.expected_filename,
                "download_status": plan.download_status,
            }
            for plan in plans
        ],
    )
    print(f"planned={len(plans)}")
    return 0


def cmd_fetch_nav(args: argparse.Namespace) -> int:
    """Download planned BRDC products (only network-touching command)."""
    import csv

    from nlgcp_scientific_expansion import nav_acquisition, reporting
    from nlgcp_scientific_expansion.models import NavProductRecord

    root = _data_root(args.data_root)
    inv = os.path.join(root, "validation", "scientific-expansion-2024", "inventory")
    dest = os.path.join(root, "external-products", "brdc", "2024")
    plans: list[NavProductRecord] = []
    with open(os.path.join(inv, "navigation-plan.csv"), newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            plans.append(
                NavProductRecord(
                    year=int(row["year"]), doy=int(row["doy"]),
                    provider=row["provider"], source_url=row["source_url"],
                    product_type=row["product_type"],
                    expected_filename=row["expected_filename"],
                    download_status=row.get("download_status", "PLANNED"),
                )
            )
    if args.limit > 0:
        plans = plans[: args.limit]
    if args.doys:
        wanted = set(args.doys)
        plans = [plan for plan in plans if plan.doy in wanted]
    config = nav_acquisition.FetchConfig(
        timeout_seconds=args.timeout, max_retries=args.retries,
        retry_backoff_seconds=args.backoff,
    )
    results = nav_acquisition.fetch_products(plans, dest, config)
    # Targeted retries must not discard provenance for the other planned days.
    # Merge the returned records with the previous inventory before writing.
    if args.doys and os.path.exists(os.path.join(inv, "navigation-products.csv")):
        with open(
            os.path.join(inv, "navigation-products.csv"),
            newline="",
            encoding="utf-8",
        ) as handle:
            previous = list(csv.DictReader(handle))
        fetched_doys = {record.doy for record in results}
        for row in previous:
            doy = int(row["doy"])
            if doy in fetched_doys:
                continue
            results.append(
                NavProductRecord(
                    year=int(row["year"]), doy=doy,
                    provider=row["provider"], source_url=row["source_url"],
                    product_type=row["product_type"],
                    expected_filename=row["expected_filename"],
                    stored_path=row["stored_path"], sha256=row["sha256"],
                    size_bytes=int(row["size_bytes"] or 0),
                    download_status=row["download_status"],
                    http_status=int(row["http_status"] or 0),
                    retrieval_utc=row["retrieval_utc"],
                    validation_status=row["validation_status"],
                    validation_detail=row["validation_detail"],
                    ephemeris_records=int(row["ephemeris_records"] or 0),
                )
            )
        results.sort(key=lambda record: (record.year, record.doy))
    reporting.write_csv(
        os.path.join(inv, "navigation-products.csv"),
        ["year", "doy", "provider", "source_url", "product_type",
         "expected_filename", "stored_path", "sha256", "size_bytes",
         "download_status", "http_status", "retrieval_utc",
         "validation_status", "validation_detail", "ephemeris_records"],
        [
            {
                "year": record.year, "doy": record.doy,
                "provider": record.provider, "source_url": record.source_url,
                "product_type": record.product_type,
                "expected_filename": record.expected_filename,
                "stored_path": record.stored_path, "sha256": record.sha256,
                "size_bytes": record.size_bytes,
                "download_status": record.download_status,
                "http_status": record.http_status,
                "retrieval_utc": record.retrieval_utc,
                "validation_status": record.validation_status,
                "validation_detail": record.validation_detail,
                "ephemeris_records": record.ephemeris_records,
            }
            for record in results
        ],
    )
    from collections import Counter

    print(dict(Counter(record.download_status for record in results)))
    return 0


def cmd_verify_nav(args: argparse.Namespace) -> int:
    """Validate downloaded BRDC products (no network)."""
    import csv

    from nlgcp_scientific_expansion import nav_acquisition, reporting
    from nlgcp_scientific_expansion.models import NavProductRecord

    root = _data_root(args.data_root)
    inv = os.path.join(root, "validation", "scientific-expansion-2024", "inventory")
    src = os.path.join(inv, "navigation-products.csv")
    plan_path = os.path.join(inv, "navigation-plan.csv")
    existing_rows: dict[int, dict[str, str]] = {}
    if os.path.exists(src):
        with open(src, newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                try:
                    existing_rows[int(row["doy"])] = row
                except (KeyError, ValueError):
                    continue
    records: list[NavProductRecord] = []
    # Always iterate the complete plan. A targeted fetch may have replaced
    # the inventory with a subset, so verification must restore all rows.
    with open(plan_path, newline="", encoding="utf-8") as handle:
        for plan_row in csv.DictReader(handle):
            doy = int(plan_row["doy"])
            row = existing_rows.get(doy, plan_row)
            stored = row.get("stored_path", "") or os.path.join(
                root, "external-products", "brdc", "2024", plan_row["expected_filename"]
            )
            download_status = row.get("download_status", "")
            if download_status in {"", "PLANNED"} and os.path.exists(stored):
                download_status = "CACHED"
            records.append(
                NavProductRecord(
                    year=int(plan_row["year"]), doy=doy,
                    provider=plan_row["provider"], source_url=plan_row["source_url"],
                    product_type=plan_row["product_type"],
                    expected_filename=plan_row["expected_filename"], stored_path=stored,
                    sha256=row.get("sha256", ""),
                    size_bytes=int(row.get("size_bytes", 0) or 0),
                    download_status=download_status or "NOT_FOUND",
                    http_status=int(row.get("http_status", 0) or 0),
                    retrieval_utc=row.get("retrieval_utc", ""),
                    validation_status=row.get("validation_status", "UNVALIDATED"),
                    validation_detail=row.get("validation_detail", ""),
                    ephemeris_records=int(row.get("ephemeris_records", 0) or 0),
                )
            )
    verified = [
        nav_acquisition.verify_product(record, record.year, record.doy)
        for record in records
    ]
    reporting.write_csv(
        src,
        ["year", "doy", "provider", "source_url", "product_type",
         "expected_filename", "stored_path", "sha256", "size_bytes",
         "download_status", "http_status", "retrieval_utc",
         "validation_status", "validation_detail", "ephemeris_records"],
        [
            {
                "year": record.year, "doy": record.doy,
                "provider": record.provider, "source_url": record.source_url,
                "product_type": record.product_type,
                "expected_filename": record.expected_filename,
                "stored_path": record.stored_path, "sha256": record.sha256,
                "size_bytes": record.size_bytes,
                "download_status": record.download_status,
                "http_status": record.http_status,
                "retrieval_utc": record.retrieval_utc,
                "validation_status": record.validation_status,
                "validation_detail": record.validation_detail,
                "ephemeris_records": record.ephemeris_records,
            }
            for record in verified
        ],
    )
    from collections import Counter

    print(dict(Counter(record.validation_status for record in verified)))
    return 0


def cmd_catalog(args: argparse.Namespace) -> int:
    """Build the processable-day catalog with preregistered prioritization."""
    from nlgcp_scientific_expansion import catalog as catalog_mod
    from nlgcp_scientific_expansion import coverage as coverage_mod
    from nlgcp_scientific_expansion import loaders, reporting
    from nlgcp_scientific_expansion import overlap as overlap_mod

    root = _data_root(args.data_root)
    inv = os.path.join(root, "validation", "scientific-expansion-2024", "inventory")
    records = loaders.load_manifest_records(
        os.path.join(root, "manifests", "canonical-raw-archive-2024.json")
    )
    qc_rows = loaders.load_qc_session_table(
        os.path.join(
            root, "processed", "qc", "profiles", "single_base_rtk", "tables",
            "session-qc-summary.csv",
        )
    )
    nav_by_day = loaders.nav_inventory_by_day(
        os.path.join(root, "external-products", "brdc", "2024"),
        os.path.join(inv, "navigation-products.csv"),
    )
    coord_path = os.path.join(
        root, "processed", "single-base", "derived-coordinates.json"
    )
    with open(coord_path, encoding="utf-8") as handle:
        registry = json.load(handle).get("stations", {})
    coordinate_days = {
        station_id: {26}
        for station_id, entry in registry.items()
        if entry.get("scientifically_valid")
    }
    cells = coverage_mod.build_coverage_matrix(
        records, qc_rows, nav_by_day, coordinate_days, year=2024
    )
    days = overlap_mod.overlap_by_day(cells)
    catalog = catalog_mod.build_processable_catalog(cells, days, nav_by_day)
    reporting.write_csv(
        os.path.join(inv, "processable-days.csv"),
        ["year", "doy", "stations", "station_count", "nav_product",
         "single_base_possible", "network_possible", "phase6_loocv_possible",
         "reason_if_blocked"],
        [
            {
                "year": day.year, "doy": day.doy,
                "stations": "+".join(day.stations),
                "station_count": day.station_count,
                "nav_product": day.nav_product,
                "single_base_possible": day.single_base_possible,
                "network_possible": day.network_possible,
                "phase6_loocv_possible": day.phase6_loocv_possible,
                "reason_if_blocked": day.reason_if_blocked,
            }
            for day in catalog
        ],
    )
    prioritized = catalog_mod.prioritize_days(catalog, max_days=args.max_days)
    reporting.write_csv(
        os.path.join(inv, "prioritized-days.csv"),
        ["year", "doy", "stations", "station_count", "nav_product",
         "priority_score", "selection_reason"],
        [
            {
                "year": day.year, "doy": day.doy,
                "stations": "+".join(day.stations),
                "station_count": day.station_count,
                "nav_product": day.nav_product,
                "priority_score": day.priority_score,
                "selection_reason": day.selection_reason,
            }
            for day in prioritized
        ],
    )
    single = sum(1 for day in catalog if day.single_base_possible)
    network = sum(1 for day in catalog if day.network_possible)
    print(f"catalog={len(catalog)} single_base_days={single} network_days={network}")
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    """Write the final evidence-derived sprint report."""
    import subprocess

    from nlgcp_scientific_expansion.expansion_report import write_report

    root = _data_root(args.data_root)
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=False
    ).stdout.strip() or "UNKNOWN"
    output = write_report(Path(root), branch=args.branch, commit=commit)
    print(output)
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Build the sprint CLI parser."""
    parser = argparse.ArgumentParser(description="NLGCP scientific-expansion sprint")
    parser.add_argument("--data-root", default="", help="Override NLGCP_DATA_ROOT")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("coverage", help="Build station x DOY coverage matrix")
    sub.add_parser("overlap", help="Compute multi-station overlap")
    plan = sub.add_parser("plan-nav", help="Plan BRDC acquisition")
    plan.add_argument("--min-stations", type=int, default=2)
    fetch = sub.add_parser("fetch-nav", help="Download planned BRDC products")
    fetch.add_argument("--limit", type=int, default=0)
    fetch.add_argument("--timeout", type=float, default=60.0)
    fetch.add_argument("--retries", type=int, default=3)
    fetch.add_argument("--backoff", type=float, default=5.0)
    fetch.add_argument(
        "--doy", dest="doys", action="append", type=int, default=[],
        help="Fetch only this DOY; repeat for multiple products",
    )
    sub.add_parser("verify-nav", help="Validate downloaded BRDC products")
    cat = sub.add_parser("catalog", help="Build processable-day catalog")
    cat.add_argument("--max-days", type=int, default=12)
    report = sub.add_parser("report", help="Write the final scientific report")
    report.add_argument("--branch", default="interim/scientific-expansion")
    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    parser = build_parser()
    args = parser.parse_args(argv)
    handlers = {
        "coverage": cmd_coverage,
        "overlap": cmd_overlap,
        "plan-nav": cmd_plan_nav,
        "fetch-nav": cmd_fetch_nav,
        "verify-nav": cmd_verify_nav,
        "catalog": cmd_catalog,
        "report": cmd_report,
    }
    return handlers[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())
