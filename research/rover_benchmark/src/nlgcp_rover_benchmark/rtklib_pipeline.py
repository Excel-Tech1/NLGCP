"""Provenance-checked RTKLIB convbin + rnx2rtkp execution pipeline for B-02.

Enforces fail-closed checks on:
- pinned RTKLIB v2.4.2-p13 binary SHA-256 provenance;
- RTCM 3.x stream framing & CRC-24Q integrity before convbin conversion;
- RINEX observation integrity after convbin conversion;
- comparable RTKLIB configuration generation with explicit SHA-256 hashing;
- timeout and non-zero return-code capture without synthetic fallback.
"""

from __future__ import annotations

import hashlib
import shutil
import subprocess
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from nlgcp_rtcm_generation.independent_decoder import (
    convbin_provenance,
    locate_convbin,
    sha256_file,
)
from nlgcp_rtcm_replay.framing import parse_stream
from nlgcp_rtcm_replay.models import CRCStatus
from nlgcp_single_base.rtklib import (
    RECORDED_RNX2RTKP_SHA256,
    RECORDED_RTKLIB_COMMIT,
    RECORDED_RTKLIB_TAG,
)
from nlgcp_single_base.solution import ParsedSolution, parse_solution_pos

from nlgcp_rover_benchmark.models import (
    BenchmarkFailure,
    BenchmarkOutcome,
    ProcessingProfile,
)


def locate_rnx2rtkp(binary: Path | None = None) -> Path:
    """Locate rnx2rtkp binary without substituting or modifying it."""
    if binary is not None:
        if not binary.is_file():
            raise BenchmarkFailure(f"rnx2rtkp binary not found at {binary}")
        return binary.resolve()
    found = shutil.which("rnx2rtkp")
    if found:
        return Path(found).resolve()
    fallback = Path.home() / ".local" / "bin" / "rnx2rtkp"
    if fallback.is_file():
        return fallback.resolve()
    raise BenchmarkFailure("RTKLIB rnx2rtkp binary is not installed")


def rtklib_tool_provenance(
    *, rnx2rtkp_bin: Path | None = None, convbin_bin: Path | None = None
) -> dict[str, Any]:
    """Capture and verify pinned RTKLIB v2.4.2-p13 executable provenance."""
    rnx_path = locate_rnx2rtkp(rnx2rtkp_bin)
    rnx_sha = sha256_file(rnx_path)
    if rnx_sha != RECORDED_RNX2RTKP_SHA256:
        raise BenchmarkFailure(
            f"rnx2rtkp SHA-256 mismatch: observed {rnx_sha}, pinned {RECORDED_RNX2RTKP_SHA256}"
        )
    conv_prov = convbin_provenance(convbin_bin)
    return {
        "rtklib_tag": RECORDED_RTKLIB_TAG,
        "rtklib_commit": RECORDED_RTKLIB_COMMIT,
        "rnx2rtkp_path": str(rnx_path),
        "rnx2rtkp_sha256": rnx_sha,
        "rnx2rtkp_matches_pinned": True,
        "convbin_path": conv_prov["binary_path"],
        "convbin_sha256": conv_prov["binary_sha256"],
    }


def validate_rtcm_stream_integrity(
    rtcm_bytes: bytes,
) -> tuple[BenchmarkOutcome | None, dict[str, Any]]:
    """Verify RTCM 3.x framing, CRC-24Q, and zero truncation prior to convbin."""
    if not rtcm_bytes:
        return BenchmarkOutcome.FAILED_TRUNCATED_RTCM, {"error": "empty RTCM stream"}
    parsed = parse_stream(rtcm_bytes)
    crc_fails = [f for f in parsed.frames if f.record.crc_status != CRCStatus.PASS]
    trunc_findings = [fn for fn in parsed.findings if "TRUNCATED" in fn.upper()]
    stray_findings = [fn for fn in parsed.findings if "STRAY" in fn.upper()]
    msg_nums = sorted({f.record.message_number for f in parsed.frames if f.record.message_number})
    summary: dict[str, Any] = {
        "bytes_len": len(rtcm_bytes),
        "frame_count": len(parsed.frames),
        "crc_fail_count": len(crc_fails),
        "message_numbers": msg_nums,
        "findings": list(parsed.findings),
    }
    if crc_fails:
        return BenchmarkOutcome.FAILED_INVALID_RTCM, summary
    if trunc_findings or stray_findings or not parsed.frames:
        return BenchmarkOutcome.FAILED_TRUNCATED_RTCM, summary
    if 1005 not in msg_nums or 1074 not in msg_nums:
        return BenchmarkOutcome.FAILED_INVALID_RTCM, {
            **summary,
            "error": "RTCM stream missing required 1005 or 1074 messages",
        }
    return None, summary


@dataclass(frozen=True, slots=True)
class ConvbinConversion:
    """Verified outcome of converting a preserved RTCM 3.x stream to RINEX 3.02."""

    ok: bool
    outcome: BenchmarkOutcome
    rtcm_path: Path
    rtcm_sha256: str
    rinex_path: Path | None
    rinex_sha256: str | None
    returncode: int
    stderr: str
    summary: dict[str, Any]


def convert_rtcm_to_rinex(
    rtcm_path: Path,
    rinex_out_path: Path,
    *,
    ref_date_slash: str,
    ref_time_hms: str = "00:00:00",
    convbin_bin: Path | None = None,
    timeout_s: float = 120.0,
) -> ConvbinConversion:
    """Validate an RTCM 3.x stream and decode it to RINEX 3.02 via unmodified convbin."""
    if not rtcm_path.is_file():
        return ConvbinConversion(
            ok=False,
            outcome=BenchmarkOutcome.FAILED_MISSING_REFERENCE_OBS,
            rtcm_path=rtcm_path,
            rtcm_sha256="",
            rinex_path=None,
            rinex_sha256=None,
            returncode=-1,
            stderr=f"missing RTCM file: {rtcm_path}",
            summary={},
        )
    raw = rtcm_path.read_bytes()
    rtcm_sha = hashlib.sha256(raw).hexdigest()
    fail_outcome, integrity = validate_rtcm_stream_integrity(raw)
    if fail_outcome is not None:
        return ConvbinConversion(
            ok=False,
            outcome=fail_outcome,
            rtcm_path=rtcm_path,
            rtcm_sha256=rtcm_sha,
            rinex_path=None,
            rinex_sha256=None,
            returncode=-1,
            stderr=f"RTCM stream failed pre-conversion integrity check: {fail_outcome}",
            summary=integrity,
        )

    exe = locate_convbin(convbin_bin)
    rinex_out_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        str(exe),
        "-r",
        "rtcm3",
        "-tr",
        ref_date_slash,
        ref_time_hms,
        "-v",
        "3.02",
        "-f",
        "3",
        "-os",
        "-scan",
        "-o",
        str(rinex_out_path),
        str(rtcm_path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=timeout_s)
    if proc.returncode != 0 or not rinex_out_path.is_file():
        return ConvbinConversion(
            ok=False,
            outcome=BenchmarkOutcome.FAILED_INVALID_RTCM,
            rtcm_path=rtcm_path,
            rtcm_sha256=rtcm_sha,
            rinex_path=None,
            rinex_sha256=None,
            returncode=proc.returncode,
            stderr=proc.stderr,
            summary=integrity,
        )

    # Audit converted RINEX 3.02 header & epoch count
    text = rinex_out_path.read_text(encoding="ascii", errors="replace")
    lines = text.splitlines()
    epoch_lines = [ln for ln in lines if ln.startswith(">")]
    approx_xyz: list[float] | None = None
    obs_types: dict[str, list[str]] = {}
    for ln in lines:
        lbl = ln[60:].strip()
        if lbl == "APPROX POSITION XYZ":
            parts = ln[:60].split()
            if len(parts) == 3:
                approx_xyz = [float(p) for p in parts]
        elif lbl == "SYS / # / OBS TYPES" and ln[0].strip():
            obs_types[ln[0].strip()] = ln[7:60].split()
        elif lbl == "END OF HEADER":
            break

    if not epoch_lines:
        return ConvbinConversion(
            ok=False,
            outcome=BenchmarkOutcome.FAILED_INVALID_RTCM,
            rtcm_path=rtcm_path,
            rtcm_sha256=rtcm_sha,
            rinex_path=rinex_out_path,
            rinex_sha256=sha256_file(rinex_out_path),
            returncode=proc.returncode,
            stderr="convbin produced RINEX with zero observation epochs",
            summary=integrity,
        )

    return ConvbinConversion(
        ok=True,
        outcome=BenchmarkOutcome.COMPLETED,
        rtcm_path=rtcm_path,
        rtcm_sha256=rtcm_sha,
        rinex_path=rinex_out_path,
        rinex_sha256=sha256_file(rinex_out_path),
        returncode=proc.returncode,
        stderr=proc.stderr,
        summary={
            **integrity,
            "rinex_epoch_count": len(epoch_lines),
            "rinex_approx_xyz_m": approx_xyz,
            "rinex_sys_obs_types": obs_types,
            "first_epoch": epoch_lines[0].strip() if epoch_lines else None,
            "last_epoch": epoch_lines[-1].strip() if epoch_lines else None,
        },
    )


def render_profile_config(
    profile: ProcessingProfile,
    *,
    base_ecef_m: tuple[float, float, float] | None,
    elevation_mask_deg: float = 15.0,
) -> str:
    """Render deterministic, comparable RTKLIB v2.4.2-p13 config for a B-02 profile."""
    if profile is ProcessingProfile.SPP_SINGLE:
        posmode, iono, tropo, armode = "single", "brdc", "saas", "off"
    elif profile is ProcessingProfile.DGPS_CODE_DIFF:
        posmode, iono, tropo, armode = "dgps", "off", "off", "off"
    elif profile is ProcessingProfile.KINEMATIC_BRDC_SAAS:
        posmode, iono, tropo, armode = "kinematic", "brdc", "saas", "continuous"
    elif profile is ProcessingProfile.STATIC_BRDC_SAAS:
        posmode, iono, tropo, armode = "static", "brdc", "saas", "continuous"
    elif profile is ProcessingProfile.KINEMATIC_VRS_IONO_OFF:
        posmode, iono, tropo, armode = "kinematic", "off", "off", "continuous"
    else:
        raise BenchmarkFailure(f"unsupported processing profile: {profile}")

    lines = [
        f"# NLGCP B-02 Offline Rover Benchmark RTKLIB config ({profile})",
        "# Pinned RTKLIB v2.4.2-p13 options verified in src/options.c.",
        "# Identical settings applied across Physical Anchor, Geometry-Only VRS, and Atmo VRS.",
        f"pos1-posmode       ={posmode}",
        "pos1-frequency     =l1+l2",
        "pos1-soltype       =forward",
        f"pos1-elmask        ={elevation_mask_deg:g}",
        f"pos1-ionoopt       ={iono}",
        f"pos1-tropopt       ={tropo}",
        "pos1-navsys        =1",
        f"pos2-armode        ={armode}",
        "pos2-arthres       =3.0",
        "pos2-maxage        =30",
        "out-solformat      =llh",
        "out-outhead        =on",
        "out-outopt         =on",
        "out-timesys        =gpst",
        "out-timeform       =hms",
        "out-timendec       =3",
        "out-degform        =deg",
        "out-height         =ellipsoidal",
        "stats-eratio1      =100",
    ]
    if base_ecef_m is not None and profile is not ProcessingProfile.SPP_SINGLE:
        lines.extend(
            [
                "ant2-postype       =xyz",
                f"ant2-pos1          ={base_ecef_m[0]:.4f}",
                f"ant2-pos2          ={base_ecef_m[1]:.4f}",
                f"ant2-pos3          ={base_ecef_m[2]:.4f}",
            ]
        )
    return "\n".join(lines) + "\n"


def _rtklib_epoch_args(timestamp: str) -> tuple[str, str]:
    parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    parsed = parsed.astimezone(UTC)
    return parsed.strftime("%Y/%m/%d"), parsed.strftime("%H:%M:%S")


def build_rnx2rtkp_command(
    *,
    executable: Path,
    profile: ProcessingProfile,
    config_path: Path,
    output_pos_path: Path,
    rover_obs_path: Path,
    base_obs_path: Path | None,
    nav_paths: list[Path],
    base_ecef_m: tuple[float, float, float] | None,
    start_time_utc: str,
    end_time_utc: str,
) -> list[str]:
    """Construct a deterministic rnx2rtkp CLI invocation for a given profile."""
    cmd = [
        str(executable),
        "-k",
        str(config_path),
        "-ts",
        *_rtklib_epoch_args(start_time_utc),
        "-te",
        *_rtklib_epoch_args(end_time_utc),
        "-ti",
        "0",
    ]
    if profile is not ProcessingProfile.SPP_SINGLE and base_ecef_m is not None:
        cmd.extend(
            [
                "-r",
                f"{base_ecef_m[0]:.4f}",
                f"{base_ecef_m[1]:.4f}",
                f"{base_ecef_m[2]:.4f}",
            ]
        )
    cmd.extend(["-o", str(output_pos_path), str(rover_obs_path)])
    if profile is not ProcessingProfile.SPP_SINGLE and base_obs_path is not None:
        cmd.append(str(base_obs_path))
    cmd.extend(str(p) for p in nav_paths)
    return cmd


def execute_rnx2rtkp(
    *,
    profile: ProcessingProfile,
    rover_obs_path: Path,
    base_obs_path: Path | None,
    nav_paths: list[Path],
    base_ecef_m: tuple[float, float, float] | None,
    start_time_utc: str,
    end_time_utc: str,
    run_dir: Path,
    rnx2rtkp_bin: Path | None = None,
    timeout_s: float = 120.0,
) -> tuple[BenchmarkOutcome, ParsedSolution | None, dict[str, Any]]:
    """Run rnx2rtkp fail-closed and return parsed solution + full execution provenance."""
    if not rover_obs_path.is_file():
        return (
            BenchmarkOutcome.FAILED_MISSING_ROVER_OBS,
            None,
            {"error": f"missing rover observation file: {rover_obs_path}"},
        )
    if profile is not ProcessingProfile.SPP_SINGLE and (
        base_obs_path is None or not base_obs_path.is_file()
    ):
        return (
            BenchmarkOutcome.FAILED_MISSING_REFERENCE_OBS,
            None,
            {"error": f"missing base/VRS observation file: {base_obs_path}"},
        )
    if not nav_paths or any(not p.is_file() for p in nav_paths):
        return (
            BenchmarkOutcome.FAILED_MISSING_NAVIGATION,
            None,
            {"error": f"missing navigation product(s): {[str(p) for p in nav_paths]}"},
        )

    exe = locate_rnx2rtkp(rnx2rtkp_bin)
    run_dir.mkdir(parents=True, exist_ok=True)
    cfg_path = run_dir / "rtklib.conf"
    pos_path = run_dir / "solution.pos"
    stdout_path = run_dir / "stdout.log"
    stderr_path = run_dir / "stderr.log"

    cfg_text = render_profile_config(profile, base_ecef_m=base_ecef_m)
    cfg_path.write_text(cfg_text, encoding="utf-8")
    cfg_sha = hashlib.sha256(cfg_text.encode("utf-8")).hexdigest()

    cmd = build_rnx2rtkp_command(
        executable=exe,
        profile=profile,
        config_path=cfg_path,
        output_pos_path=pos_path,
        rover_obs_path=rover_obs_path,
        base_obs_path=base_obs_path,
        nav_paths=nav_paths,
        base_ecef_m=base_ecef_m,
        start_time_utc=start_time_utc,
        end_time_utc=end_time_utc,
    )

    t0 = time.monotonic()
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout_s,
        )
    except subprocess.TimeoutExpired as exc:
        return (
            BenchmarkOutcome.FAILED_RTKLIB_EXECUTION,
            None,
            {
                "command": cmd,
                "config_path": str(cfg_path),
                "config_sha256": cfg_sha,
                "error": f"rnx2rtkp timed out after {timeout_s} s",
                "duration_s": round(time.monotonic() - t0, 3),
                "timeout": True,
                "partial_stderr": str(exc.stderr or "")[-500:],
            },
        )

    duration = round(time.monotonic() - t0, 3)
    stdout_path.write_text(proc.stdout, encoding="utf-8")
    stderr_path.write_text(proc.stderr, encoding="utf-8")

    exec_info: dict[str, Any] = {
        "command": cmd,
        "return_code": proc.returncode,
        "duration_s": duration,
        "config_path": str(cfg_path),
        "config_sha256": cfg_sha,
        "solution_pos_path": str(pos_path) if pos_path.is_file() else None,
        "solution_pos_sha256": sha256_file(pos_path) if pos_path.is_file() else None,
        "stdout_path": str(stdout_path),
        "stderr_path": str(stderr_path),
    }

    if proc.returncode != 0 or not pos_path.is_file():
        if proc.returncode == 0 and not pos_path.is_file() and "no obs data" in proc.stderr.lower():
            return (
                BenchmarkOutcome.FAILED_EPOCH_MISMATCH,
                None,
                {
                    **exec_info,
                    "error": (
                        "rnx2rtkp reported no overlapping observation data in requested window"
                    ),
                },
            )
        return (
            BenchmarkOutcome.FAILED_RTKLIB_EXECUTION,
            None,
            {**exec_info, "error": f"rnx2rtkp exit code {proc.returncode}"},
        )

    parsed = parse_solution_pos(pos_path, strict=False)
    if parsed.diagnostics.structural_mismatch or parsed.diagnostics.malformed_rows:
        return (
            BenchmarkOutcome.FAILED_RTKLIB_EXECUTION,
            parsed,
            {
                **exec_info,
                "error": (
                    parsed.diagnostics.structural_mismatch
                    or "; ".join(parsed.diagnostics.malformed_rows[:3])
                ),
            },
        )
    if not parsed.epochs:
        return (
            BenchmarkOutcome.FAILED_INSUFFICIENT_SATELLITES,
            parsed,
            {**exec_info, "error": "rnx2rtkp produced zero valid positioning epochs"},
        )
    return BenchmarkOutcome.COMPLETED, parsed, exec_info
