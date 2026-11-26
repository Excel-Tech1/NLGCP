"""Command-line interface for NLGCP Research Archive (`nlgcp archive ...`)."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from nlgcp_research_archive.hash_verifier import scan_unregistered_outputs
from nlgcp_research_archive.models import ExitCode, IntegrityStatus
from nlgcp_research_archive.provenance import (
    build_provenance_lineage,
    capture_environment_snapshot,
)
from nlgcp_research_archive.registry import (
    load_archive,
    render_markdown_report,
    render_status_text,
    verify_archive,
)


def _default_repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _default_archive_root(repo_root: Path) -> Path:
    return repo_root / "research" / "archive"


def _default_data_root() -> Path:
    return Path(os.environ.get("NLGCP_DATA_ROOT", "/home/excellence/nlgcp-data"))


def _print_json(payload: Any) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def _build_archive_parser(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    # status
    p_stat = sub.add_parser("status", help="Show archive integrity and completeness summary")
    p_stat.add_argument("--format", choices=("text", "json"), default="text")
    p_stat.add_argument("--skip-hashes", action="store_true")
    p_stat.add_argument("--max-hash-mb", type=float, default=None)

    # datasets {list,verify}
    p_ds = sub.add_parser("datasets", help="List or verify registered datasets")
    ds_sub = p_ds.add_subparsers(dest="datasets_cmd", required=True)
    p_ds_ls = ds_sub.add_parser("list", help="List registered datasets")
    p_ds_ls.add_argument("--format", choices=("text", "json"), default="text")
    p_ds_v = ds_sub.add_parser("verify", help="Verify dataset SHA-256 hashes read-only")
    p_ds_v.add_argument("--dataset-id", default=None)
    p_ds_v.add_argument("--format", choices=("text", "json"), default="text")
    p_ds_v.add_argument("--max-hash-mb", type=float, default=None)

    # experiments {list,validate}
    p_exp = sub.add_parser("experiments", help="List or validate registered experiments")
    exp_sub = p_exp.add_subparsers(dest="experiments_cmd", required=True)
    p_exp_ls = exp_sub.add_parser("list", help="List registered experiments")
    p_exp_ls.add_argument("--format", choices=("text", "json"), default="text")
    p_exp_v = exp_sub.add_parser("validate", help="Validate experiment manifests & provenance")
    p_exp_v.add_argument("--experiment-id", default=None)
    p_exp_v.add_argument("--format", choices=("text", "json"), default="text")

    # artifacts {verify}
    p_art = sub.add_parser("artifacts", help="Verify registered artifacts")
    art_sub = p_art.add_subparsers(dest="artifacts_cmd", required=True)
    p_art_v = art_sub.add_parser("verify", help="Verify artifact SHA-256 hashes read-only")
    p_art_v.add_argument("--artifact-id", default=None)
    p_art_v.add_argument("--format", choices=("text", "json"), default="text")
    p_art_v.add_argument("--max-hash-mb", type=float, default=None)
    p_art_v.add_argument("--verify-nested", action="store_true")
    p_art_v.add_argument("--scan-dir", type=Path, default=None)

    # provenance {report,capture-env}
    p_prov = sub.add_parser("provenance", help="Inspect software provenance and lineage")
    prov_sub = p_prov.add_subparsers(dest="provenance_cmd", required=True)
    p_prov_r = prov_sub.add_parser("report", help="Emit dataset->experiment->claim lineage")
    p_prov_r.add_argument("--format", choices=("text", "json"), default="text")
    p_prov_e = prov_sub.add_parser("capture-env", help="Capture redacted environment snapshot")
    p_prov_e.add_argument("--out", type=Path, default=None)

    # verify
    p_ver = sub.add_parser("verify", help="Run all archive checks read-only")
    p_ver.add_argument("--format", choices=("text", "json"), default="text")
    p_ver.add_argument("--skip-hashes", action="store_true")
    p_ver.add_argument("--max-hash-mb", type=float, default=None)
    p_ver.add_argument("--verify-nested", action="store_true")
    p_ver.add_argument("--out-dir", type=Path, default=None)

    # report
    p_rep = sub.add_parser("report", help="Generate Markdown or JSON completeness report")
    p_rep.add_argument("--format", choices=("markdown", "json"), default="markdown")
    p_rep.add_argument("--skip-hashes", action="store_true")
    p_rep.add_argument("--max-hash-mb", type=float, default=None)
    p_rep.add_argument("--out", type=Path, default=None)


def _max_bytes(mb: float | None) -> int | None:
    if mb is None:
        return None
    if mb <= 0:
        raise ValueError("--max-hash-mb must be positive")
    return int(mb * 1024 * 1024)


def main(argv: list[str] | None = None) -> int:
    """CLI entry point supporting both ``nlgcp archive <cmd>`` and direct ``<cmd>``."""
    raw_args = list(sys.argv[1:] if argv is None else argv)
    # Allow optional leading "archive" namespace so `nlgcp archive status` and
    # `run_research_archive.py status` both work identically.
    if raw_args and raw_args[0] == "archive":
        raw_args = raw_args[1:]

    default_repo = _default_repo_root()
    parser = argparse.ArgumentParser(
        prog="nlgcp archive",
        description="NLGCP Research Archive, Data Provenance and Reproducibility CLI (B-00)",
    )
    parser.add_argument("--repo-root", type=Path, default=default_repo)
    parser.add_argument("--archive-root", type=Path, default=None)
    parser.add_argument("--data-root", type=Path, default=_default_data_root())
    sub = parser.add_subparsers(dest="command", required=True)
    _build_archive_parser(sub)

    try:
        args = parser.parse_args(raw_args)
    except SystemExit as exc:
        code = exc.code if isinstance(exc.code, int) else int(ExitCode.INVALID_ARGUMENTS_OR_CONFIG)
        return code

    repo_root: Path = args.repo_root.resolve()
    archive_root: Path = (
        args.archive_root.resolve() if args.archive_root else _default_archive_root(repo_root)
    )
    data_root: Path = args.data_root
    if not archive_root.is_dir():
        print(f"error: archive root does not exist: {archive_root}", file=sys.stderr)
        return int(ExitCode.INVALID_ARGUMENTS_OR_CONFIG)

    try:
        max_b = _max_bytes(getattr(args, "max_hash_mb", None))
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return int(ExitCode.INVALID_ARGUMENTS_OR_CONFIG)

    cmd = args.command

    if cmd == "status":
        rep = verify_archive(
            archive_root,
            repo_root=repo_root,
            data_root=data_root,
            verify_hashes=not args.skip_hashes,
            max_hash_bytes=max_b,
        )
        if args.format == "json":
            _print_json(rep.summary.as_dict())
        else:
            print(render_status_text(rep))
        return rep.summary.exit_code

    if cmd == "datasets":
        loaded = load_archive(archive_root)
        if args.datasets_cmd == "list":
            rows = [
                {
                    "dataset_id": did,
                    "name": loaded.datasets[did].get("name"),
                    "classification": loaded.datasets[did].get("source_classification"),
                    "storage_type": loaded.datasets[did].get("storage", {}).get("storage_type"),
                    "location": loaded.datasets[did].get("storage", {}).get("location"),
                    "coordinate_status": loaded.datasets[did]
                    .get("metadata", {})
                    .get("coordinate_reference_status"),
                }
                for did in sorted(loaded.datasets)
            ]
            if args.format == "json":
                _print_json(rows)
            else:
                for r in rows:
                    print(
                        f"{r['dataset_id']}  {str(r['classification']):28s}  "
                        f"{str(r['coordinate_status']):24s}  {r['name']}"
                    )
            return int(ExitCode.OK)

        rep = verify_archive(
            archive_root,
            repo_root=repo_root,
            data_root=data_root,
            verify_hashes=True,
            max_hash_bytes=max_b,
        )
        checks = list(rep.dataset_integrity)
        if args.dataset_id:
            checks = [c for c in checks if c.record_id == args.dataset_id]
            if not checks:
                print(f"error: unknown dataset_id '{args.dataset_id}'", file=sys.stderr)
                return int(ExitCode.INVALID_ARGUMENTS_OR_CONFIG)
        if args.format == "json":
            _print_json([c.as_dict() for c in checks])
        else:
            for c in checks:
                print(f"{c.record_id}  {str(c.status):16s}  {c.detail}")
        if any(
            c.status
            in (
                IntegrityStatus.MISSING,
                IntegrityStatus.HASH_MISMATCH,
                IntegrityStatus.INVALID_MANIFEST,
            )
            for c in checks
        ) or bool(rep.dataset_schema_errors or rep.duplicate_id_errors or rep.parse_errors):
            return int(ExitCode.INTEGRITY_OR_VALIDATION_FAILURE)
        if any(c.status is IntegrityStatus.ACCESS_DENIED for c in checks):
            return int(ExitCode.EXTERNAL_STORAGE_OR_DEPENDENCY_UNAVAILABLE)
        return int(ExitCode.OK)

    if cmd == "experiments":
        loaded = load_archive(archive_root)
        if args.experiments_cmd == "list":
            rows = [
                {
                    "experiment_id": eid,
                    "milestone": loaded.experiments[eid].get("milestone"),
                    "status": loaded.experiments[eid].get("status"),
                    "validation_level": loaded.experiments[eid]
                    .get("validation", {})
                    .get("highest_level"),
                    "reproducibility": loaded.experiments[eid]
                    .get("reproducibility", {})
                    .get("status"),
                    "title": loaded.experiments[eid].get("title"),
                }
                for eid in sorted(loaded.experiments)
            ]
            if args.format == "json":
                _print_json(rows)
            else:
                for r in rows:
                    print(
                        f"{r['experiment_id']}  {str(r['milestone']):10s}  "
                        f"{str(r['status']):12s}  {str(r['validation_level']):24s}  {r['title']}"
                    )
            return int(ExitCode.OK)

        rep = verify_archive(
            archive_root,
            repo_root=repo_root,
            data_root=data_root,
            verify_hashes=False,
        )
        exps = list(rep.experiment_validations)
        if args.experiment_id:
            exps = [e for e in exps if e.experiment_id == args.experiment_id]
            if not exps:
                print(f"error: unknown experiment_id '{args.experiment_id}'", file=sys.stderr)
                return int(ExitCode.INVALID_ARGUMENTS_OR_CONFIG)
        if args.format == "json":
            _print_json([e.as_dict() for e in exps])
        else:
            for e in exps:
                prov_lbl = "COMPLETE" if e.provenance_complete else "INCOMPLETE"
                print(
                    f"{e.experiment_id}  valid={e.valid!s:5s}  prov={prov_lbl:10s}  "
                    f"errors={len(e.errors)} gaps={len(e.provenance_gaps)}"
                )
        if any(not e.valid for e in exps) or bool(rep.duplicate_id_errors or rep.parse_errors):
            return int(ExitCode.INTEGRITY_OR_VALIDATION_FAILURE)
        return int(ExitCode.OK)

    if cmd == "artifacts":
        rep = verify_archive(
            archive_root,
            repo_root=repo_root,
            data_root=data_root,
            verify_hashes=True,
            max_hash_bytes=max_b,
            verify_nested=args.verify_nested,
        )
        checks = list(rep.artifact_integrity)
        if args.artifact_id:
            checks = [c for c in checks if c.record_id == args.artifact_id]
            if not checks:
                print(f"error: unknown artifact_id '{args.artifact_id}'", file=sys.stderr)
                return int(ExitCode.INVALID_ARGUMENTS_OR_CONFIG)
        unregistered: list[str] = []
        if args.scan_dir is not None:
            reg_paths = {Path(c.resolved_path) for c in rep.artifact_integrity if c.resolved_path}
            unregistered = scan_unregistered_outputs(args.scan_dir, reg_paths)
        if args.format == "json":
            payload: dict[str, Any] = {
                "artifacts": [c.as_dict() for c in checks],
                "nested_checks": rep.nested_artifact_checks,
            }
            if args.scan_dir is not None:
                payload["unregistered_outputs"] = unregistered
            _print_json(payload)
        else:
            for c in checks:
                print(f"{c.record_id}  {str(c.status):16s}  {c.detail}")
            for aid, nc in rep.nested_artifact_checks.items():
                print(
                    f"{aid} [nested]  {nc['status']:16s}  "
                    f"{nc['verified']}/{nc['total']} verified"
                )
            if args.scan_dir is not None:
                print(f"Unregistered outputs in {args.scan_dir}: {len(unregistered)}")
        nested_bad = any(
            nc.get("status") != str(IntegrityStatus.VERIFIED)
            for nc in rep.nested_artifact_checks.values()
        )
        if (
            any(
                c.status
                in (
                    IntegrityStatus.MISSING,
                    IntegrityStatus.HASH_MISMATCH,
                    IntegrityStatus.INVALID_MANIFEST,
                )
                for c in checks
            )
            or nested_bad
            or bool(rep.artifact_schema_errors or rep.duplicate_id_errors or rep.parse_errors)
        ):
            return int(ExitCode.INTEGRITY_OR_VALIDATION_FAILURE)
        if any(c.status is IntegrityStatus.ACCESS_DENIED for c in checks):
            return int(ExitCode.EXTERNAL_STORAGE_OR_DEPENDENCY_UNAVAILABLE)
        return int(ExitCode.OK)

    if cmd == "provenance":
        if args.provenance_cmd == "capture-env":
            snap = capture_environment_snapshot(repo_root, data_root)
            if args.out is not None:
                args.out.parent.mkdir(parents=True, exist_ok=True)
                args.out.write_text(json.dumps(snap, indent=2, sort_keys=True) + "\n", "utf-8")
            _print_json(snap)
            return int(ExitCode.OK)

        loaded = load_archive(archive_root)
        lineage = build_provenance_lineage(
            datasets=loaded.datasets,
            experiments=loaded.experiments,
            artifacts=loaded.artifacts,
            software=loaded.software,
            findings=loaded.findings,
            limitations=loaded.limitations,
            claims=loaded.claims,
            reproductions=loaded.reproductions,
        )
        if args.format == "json":
            _print_json(lineage)
        else:
            print("NLGCP Provenance Lineage Summary:")
            for k, v in lineage["counts"].items():
                print(f"  {k:16s}: {v}")
            print("Publication Claim Evidence Chains:")
            for c in lineage["publication_claim_chains"]:
                print(
                    f"  {c['claim_id']} [{c['status']}] -> findings={c['supporting_findings']} "
                    f"exps={c['supporting_experiments']}"
                )
        return int(ExitCode.OK)

    if cmd == "verify":
        rep = verify_archive(
            archive_root,
            repo_root=repo_root,
            data_root=data_root,
            verify_hashes=not args.skip_hashes,
            max_hash_bytes=max_b,
            verify_nested=args.verify_nested,
        )
        if args.out_dir is not None:
            loaded = load_archive(archive_root)
            try:
                args.out_dir.mkdir(parents=True, exist_ok=True)
                (args.out_dir / "archive_verification_report.json").write_text(
                    json.dumps(rep.as_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8"
                )
                (args.out_dir / "archive_verification_report.md").write_text(
                    render_markdown_report(rep, loaded), encoding="utf-8"
                )
            except OSError as exc:
                print(
                    f"ERROR: cannot write verification report to {args.out_dir}: {exc}",
                    file=sys.stderr,
                )
                return int(ExitCode.EXTERNAL_STORAGE_OR_DEPENDENCY_UNAVAILABLE)
        if args.format == "json":
            _print_json(rep.as_dict())
        else:
            print(render_status_text(rep))
        return rep.summary.exit_code

    if cmd == "report":
        loaded = load_archive(archive_root)
        rep = verify_archive(
            archive_root,
            repo_root=repo_root,
            data_root=data_root,
            verify_hashes=not args.skip_hashes,
            max_hash_bytes=max_b,
        )
        text = (
            json.dumps(rep.as_dict(), indent=2, sort_keys=True) + "\n"
            if args.format == "json"
            else render_markdown_report(rep, loaded)
        )
        if args.out is not None:
            try:
                args.out.parent.mkdir(parents=True, exist_ok=True)
                args.out.write_text(text, encoding="utf-8")
            except OSError as exc:
                print(
                    f"ERROR: cannot write report to {args.out}: {exc}",
                    file=sys.stderr,
                )
                return int(ExitCode.EXTERNAL_STORAGE_OR_DEPENDENCY_UNAVAILABLE)
        else:
            print(text)
        return rep.summary.exit_code

    return int(ExitCode.INVALID_ARGUMENTS_OR_CONFIG)
