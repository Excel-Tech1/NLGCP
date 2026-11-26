#!/usr/bin/env python3
"""Reproducible CLI runner for B-02 Offline Rover Positioning Benchmark.

Evaluates Physical Anchor vs. Geometry-Only VRS vs. Atmospheric-Model VRS
using authentic Nigerian GNSS observations and pinned RTKLIB v2.4.2-p13
(``convbin`` + ``rnx2rtkp``), writing machine-readable evidence outside Git
under ``${NLGCP_DATA_ROOT}/processed/rover-benchmark/b02/``.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

_ROVER_SRC = Path(__file__).resolve().parents[1] / "research" / "rover_benchmark" / "src"
if str(_ROVER_SRC) not in sys.path:
    sys.path.insert(0, str(_ROVER_SRC))

from nlgcp_rover_benchmark.benchmark import run_b02_benchmark  # noqa: E402
from nlgcp_rover_benchmark.models import ProcessingProfile  # noqa: E402


def _print_dataset_table(label: str, ds_res: dict[str, object]) -> None:
    print(f"\n=== {label} ===")
    profiles = ds_res["profiles"]
    assert isinstance(profiles, dict)
    for prof in (
        str(ProcessingProfile.KINEMATIC_BRDC_SAAS),
        str(ProcessingProfile.STATIC_BRDC_SAAS),
        str(ProcessingProfile.KINEMATIC_VRS_IONO_OFF),
        str(ProcessingProfile.DGPS_CODE_DIFF),
    ):
        if prof not in profiles:
            continue
        print(f"  [{prof}]")
        for vid, rec in profiles[prof].items():
            m = rec.get("metrics", {})
            h_rmse = m.get("horizontal_rmse_m")
            v_rmse = m.get("vertical_rmse_m")
            d3_rmse = m.get("three_d_rmse_m")
            fix_r = m.get("fix_rate", 0.0)
            flt_r = m.get("float_rate", 0.0)
            val = m.get("valid_epochs", 0)
            h_s = f"{h_rmse:.4f}" if isinstance(h_rmse, float) else "None"
            v_s = f"{v_rmse:.4f}" if isinstance(v_rmse, float) else "None"
            d3_s = f"{d3_rmse:.4f}" if isinstance(d3_rmse, float) else "None"
            print(
                f"    {vid:32s} valid={val:4d} H={h_s:>7s}m V={v_s:>7s}m "
                f"3D={d3_s:>7s}m FIX={fix_r * 100:5.1f}% FLT={flt_r * 100:5.1f}%"
            )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="NLGCP B-02 Offline Rover Positioning Benchmark")
    parser.add_argument(
        "--data-root",
        type=Path,
        default=Path(os.environ.get("NLGCP_DATA_ROOT", "/home/excellence/nlgcp-data")),
    )
    parser.add_argument("--out-dir", type=Path, default=None)
    parser.add_argument("--stride", type=int, default=1, help="Epoch stride (1=30s native cadence)")
    parser.add_argument(
        "--max-epochs", type=int, default=None, help="Optional cap on epochs (default: full 24h)"
    )
    args = parser.parse_args(argv)

    summary = run_b02_benchmark(
        data_root=args.data_root,
        out_dir=args.out_dir,
        stride=args.stride,
        max_epochs=args.max_epochs,
    )
    _print_dataset_table(
        "DATASET B: 2024-01-26 PHRI00NGA (VERIFIED IGS20 TRUTH, EXTRAPOLATED)",
        summary["dataset_2024_phri_verified"],
    )
    _print_dataset_table(
        "DATASET A: 2011-03-20 OSGF (PROVISIONAL TRUTH ONLY, INTERIOR HULL)",
        summary["dataset_2011_osgf_interior"],
    )
    fs = summary["failure_and_robustness_suite"]
    print(f"\nFailure suite: {fs['total_scenarios']} scenarios, all_passed={fs['all_passed']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
