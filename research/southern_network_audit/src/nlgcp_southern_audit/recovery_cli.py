"""Command line entry point for Southern Nigeria navigation recovery."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from .archive_access import Credentials, DownloadConfig
from .navigation_recovery import DEFAULT_PROVIDERS, run_recovery

DEFAULT_OUTPUT_ROOT = Path(
    "/home/excellence/nlgcp-data/validation/southern-nignet/coordinate-navigation-recovery"
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit-run", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--run-id")
    parser.add_argument("--year", type=int)
    parser.add_argument("--include-secondary", action="store_true")
    parser.add_argument("--constellation-evidence", type=Path)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--timeout-seconds", type=float, default=60.0)
    parser.add_argument("--max-retries", type=int, default=3)
    parser.add_argument("--retry-backoff-seconds", type=float, default=1.0)
    parser.add_argument("--max-bytes", type=int, default=64 * 1024 * 1024)
    parser.add_argument(
        "--providers",
        default=",".join(DEFAULT_PROVIDERS),
        help="Comma-separated provider priority: CDDIS,BKG,IGN,GSSC,SIO",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Perform downloads; without this flag only the dry-run plan is written.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    providers = tuple(
        provider.strip().upper() for provider in args.providers.split(",") if provider.strip()
    )
    unknown = sorted(set(providers) - set(DEFAULT_PROVIDERS))
    if unknown:
        raise SystemExit(f"unknown providers: {', '.join(unknown)}")
    repo_root = Path(__file__).resolve().parents[4]
    try:
        args.output_root.resolve().relative_to(repo_root)
    except ValueError:
        pass
    else:
        raise SystemExit("output root must be outside the Git repository")
    summary = run_recovery(
        args.audit_run,
        args.output_root,
        run_id=args.run_id,
        dry_run=not args.execute,
        year=args.year,
        include_secondary=args.include_secondary,
        constellation_evidence=args.constellation_evidence,
        workers=args.workers,
        providers=providers,
        download_config=DownloadConfig(
            timeout_seconds=args.timeout_seconds,
            max_retries=args.max_retries,
            retry_backoff_seconds=args.retry_backoff_seconds,
            max_bytes=args.max_bytes,
        ),
        credentials=Credentials.from_environment(),
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
