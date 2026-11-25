#!/usr/bin/env python3
"""Reproducible local Phase 11 -> Phase 12 NTRIP -> RTKLIB synthetic demo CLI.

SYNTHETIC TEST DATA — NOT VALID FOR NAVIGATION OR SCIENTIFIC POSITIONING RESULTS.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

_SERVICE_SRC = Path(__file__).resolve().parents[1] / "services" / "correction-service" / "src"
if str(_SERVICE_SRC) not in sys.path:
    sys.path.insert(0, str(_SERVICE_SRC))

from nlgcp_correction_service import SYNTHETIC_MOUNTPOINT_LABEL  # noqa: E402
from nlgcp_correction_service.pipeline import (  # noqa: E402
    EndToEndDemoReport,
    run_local_end_to_end_demo,
)


def _format_human_summary(report: EndToEndDemoReport) -> str:
    stages = report.stages
    msg_id_ok = "PASS" if stages["message_type_identification"]["ok"] else "FAIL"
    convbin_status = "PASS" if report.rtklib_validation.get("convbin_performed") else "NOT_RUN"
    native_status = (
        "PASS" if report.rtklib_validation.get("native_input_rtcm3_performed") else "NOT_RUN"
    )
    lines = [
        "=== NLGCP Phase 12 Local Synthetic Loopback Demonstration ===",
        f"NOTICE: {SYNTHETIC_MOUNTPOINT_LABEL}",
        f"Overall Status:        {'PASS' if report.ok else 'FAIL'}",
        f"Mountpoint:            {report.mountpoint}",
        f"Caster Startup:        {'PASS' if stages['caster_startup']['ok'] else 'FAIL'} "
        f"({stages['caster_startup']['bind_host']}:{stages['caster_startup']['bind_port']})",
        f"Mountpoint Available:  {'PASS' if stages['mountpoint_availability']['ok'] else 'FAIL'} "
        f"(HTTP {stages['mountpoint_availability']['sourcetable_status']})",
        f"Authentication:        {'PASS' if stages['authentication']['ok'] else 'FAIL'} "
        f"(NTRIP {stages['authentication']['ntrip_version']}, "
        f"HTTP {stages['authentication']['status_code']})",
        f"RTCM Publication:      {'PASS' if stages['rtcm_publication']['ok'] else 'FAIL'} "
        f"({stages['rtcm_publication']['published_frames']} frames: "
        f"{stages['rtcm_publication']['message_numbers']})",
        f"Client Reception:      {'PASS' if stages['client_reception']['ok'] else 'FAIL'} "
        f"({stages['client_reception']['received_frames']} frames, "
        f"{stages['client_reception']['bytes_received']} bytes)",
        f"Byte-Exact Match:      {'PASS' if report.byte_exact_match else 'FAIL'} "
        f"({stages['byte_exact_comparison']['received_bytes']}/"
        f"{stages['byte_exact_comparison']['sent_bytes']} bytes)",
        f"CRC-24Q Validation:    {'PASS' if stages['crc_validation']['ok'] else 'FAIL'} "
        f"(caster_failures={stages['crc_validation']['caster_crc_failures']}, "
        f"client_failures={stages['crc_validation']['client_crc_failures']})",
        f"Message Identification: {msg_id_ok} ({list(report.received_message_numbers)})",
        f"RTKLIB convbin:        {convbin_status}",
        f"RTKLIB input_rtcm3:    {native_status}",
        f"Clean Shutdown:        {'PASS' if stages['clean_shutdown']['ok'] else 'FAIL'} "
        f"(status={stages['clean_shutdown']['caster_status']}, "
        f"active_clients={stages['clean_shutdown']['active_clients']})",
        f"Scientific Readiness:  {report.scientific_readiness}",
        "Operational Readiness: NOT APPROVED (loopback synthetic lab only)",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run the local loopback-only Phase 12 synthetic NTRIP integration demo "
            "(SYNTHETIC TEST DATA — NOT VALID FOR NAVIGATION OR SCIENTIFIC POSITIONING)."
        )
    )
    parser.add_argument(
        "--ntrip-version",
        choices=("1.0", "2.0"),
        default="2.0",
        help="NTRIP protocol version for the local loopback client (default: 2.0).",
    )
    parser.add_argument(
        "--mountpoint",
        default="NLGCP_TEST",
        help="Synthetic mountpoint name (default: NLGCP_TEST).",
    )
    parser.add_argument(
        "--format",
        choices=("both", "json", "text"),
        default="both",
        help=(
            "Output format: 'both' writes human-readable summary to stderr and "
            "JSON to stdout (default); 'json' writes JSON only; 'text' writes "
            "human-readable summary only."
        ),
    )
    args = parser.parse_args()

    rtklib_env = os.environ.get("RTKLIB_SOURCE")
    rtklib_source = Path(rtklib_env) if rtklib_env else None
    repo_root = Path(__file__).resolve().parents[1]

    report = run_local_end_to_end_demo(
        ntrip_version=args.ntrip_version,
        mountpoint=args.mountpoint,
        rtklib_source=rtklib_source,
        repo_root=repo_root,
    )
    payload = {
        "data_notice": SYNTHETIC_MOUNTPOINT_LABEL,
        "ok": report.ok,
        "mountpoint": report.mountpoint,
        "sent_message_numbers": list(report.sent_message_numbers),
        "received_message_numbers": list(report.received_message_numbers),
        "byte_exact_match": report.byte_exact_match,
        "stages": report.stages,
        "caster_diagnostics": report.caster_diagnostics,
        "client_diagnostics": report.client_result.diagnostics,
        "rtklib_validation": report.rtklib_validation,
        "scientific_readiness": report.scientific_readiness,
        "operational_readiness": "NOT_APPROVED",
    }
    if args.format == "text":
        print(_format_human_summary(report))
    elif args.format == "json":
        print(json.dumps(payload, indent=2, sort_keys=True, default=str))
    else:
        print(_format_human_summary(report), file=sys.stderr)
        print(json.dumps(payload, indent=2, sort_keys=True, default=str))
    return 0 if report.ok else 1


if __name__ == "__main__":
    sys.exit(main())
