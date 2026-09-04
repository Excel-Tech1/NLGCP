#!/usr/bin/env python3
"""Build and QC the canonical archive for the preserved OSGoF 2024 dataset."""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

from nlgcp_api.config import Settings, resolve_data_root
from nlgcp_api.phase2_dataset import (
    ArchiveRecord,
    EpochGap,
    Phase2DatasetError,
    SessionQC,
    analyse_crinex_file,
    build_canonical_archive,
    discover_delivery,
    write_phase2_outputs,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build the preserved 2024 canonical raw archive and Phase 2 QC report."
    )
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="Do not create missing canonical files; verify files already present.",
    )
    args = parser.parse_args(argv)
    try:
        data_root = resolve_data_root(Settings())
        if shutil.which("uncompress") is None or shutil.which("CRX2RNX") is None:
            raise Phase2DatasetError("uncompress and CRX2RNX are required for CRINEX QC")
        delivery_root = data_root / "00-deliveries" / "osgof-2024" / "batch-001"
        delivery = discover_delivery(delivery_root)
        place_names = {item.station_id: item.place_name for item in delivery}
        print(f"discovered {len(delivery)} delivered files", flush=True)
        archive = build_canonical_archive(
            delivery_root,
            data_root,
            copy_files=not args.verify_only,
            delivery_files=delivery,
        )
        print(
            f"verified {len(archive.records)} canonical files; "
            f"excluded {len(archive.exact_duplicates)} exact duplicates",
            flush=True,
        )
        sessions: list[SessionQC] = []
        gaps: list[EpochGap] = []
        observations = [
            record for record in archive.records if record.artifact_type == "observation"
        ]
        worker_count = min(8, os.cpu_count() or 1)
        with ProcessPoolExecutor(max_workers=worker_count) as executor:
            futures = [
                executor.submit(_analyse_one, data_root, record)
                for record in observations
            ]
            for index, future in enumerate(as_completed(futures), start=1):
                session, session_gaps = future.result()
                sessions.append(session)
                gaps.extend(session_gaps)
                if index % 50 == 0 or index == len(observations):
                    print(
                        f"analysed {index}/{len(observations)} observation sessions",
                        flush=True,
                    )
        sessions.sort(key=lambda item: item.canonical_relative_path)
        gaps.sort(key=lambda item: (item.station_id, item.day_of_year, item.previous_epoch))
        outputs = write_phase2_outputs(
            data_root,
            archive,
            sessions,
            gaps,
            place_names,
        )
    except (OSError, Phase2DatasetError) as exc:
        print(f"Phase 2 dataset processing failed: {exc}", file=sys.stderr)
        return 1

    print(f"Phase 2 report: {outputs['report']}")
    print("Phase 3 was not started.")
    return 0


def _analyse_one(
    data_root: Path,
    record: ArchiveRecord,
) -> tuple[SessionQC, list[EpochGap]]:
    return analyse_crinex_file(data_root / record.canonical_relative_path, record)


if __name__ == "__main__":
    raise SystemExit(main())
