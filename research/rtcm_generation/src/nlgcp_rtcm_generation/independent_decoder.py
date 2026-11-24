"""Independent RTCM 3.x decoder harness using unmodified RTKLIB v2.4.2-p13.

Provides two external C decoding paths that share ZERO code with the Python
Phase 11 encoders or Phase 9 CRC-24Q implementation:

1. ``convbin``: the installed unmodified RTKLIB ``convbin`` CLI binary,
   decoding RTCM 3.x streams into RINEX 3.02 observation files.
2. Native ``input_rtcm3`` adapter: a read-only C harness compiled directly
   against the pinned unmodified RTKLIB v2.4.2-p13 source tree.

Honest provenance note:
RTKLIB v2.4.2-p13 was also used as the Day 2 bit-layout reference.  Passing
RTKLIB decoding therefore confirms byte/bit/CRC/semantic agreement against an
unmodified third-party C GNSS implementation, but does NOT constitute
validation by a second non-RTKLIB decoder, receiver interoperability testing,
or scientific/operational approval.  Synthetic fixtures remain labelled
SYNTHETIC TEST DATA — NOT VALID FOR SCIENTIFIC RESULTS.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from nlgcp_rtcm_generation.provenance import fingerprint

RTKLIB_COMMIT = "71db0ffa0d9735697c6adfd06fdf766d0e5ce807"
RTKLIB_DECODER_SOURCES = ("rtcm.c", "rtcm2.c", "rtcm3.c", "rtcm3e.c", "rtkcmn.c")

CLIGHT = 299_792_458.0
GPS_FREQ_HZ: dict[int, float] = {
    1: 1_575_420_000.0,
    2: 1_227_600_000.0,
    3: 1_176_450_000.0,
}
GLONASS_FREQ1_HZ = 1_602_000_000.0
GLONASS_DFREQ1_HZ = 562_500.0
GLONASS_FREQ2_HZ = 1_246_000_000.0
GLONASS_DFREQ2_HZ = 437_500.0
GLONASS_FREQ3_HZ = 1_202_025_000.0


class IndependentDecoderUnavailable(RuntimeError):
    """Raised when an external independent RTCM decoder is unavailable."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def gps_wavelength_m(freq_index: int) -> float:
    return CLIGHT / GPS_FREQ_HZ[freq_index]


def glonass_wavelength_m(freq_index: int, fcn: int) -> float:
    if freq_index == 1:
        return CLIGHT / (GLONASS_FREQ1_HZ + GLONASS_DFREQ1_HZ * fcn)
    if freq_index == 2:
        return CLIGHT / (GLONASS_FREQ2_HZ + GLONASS_DFREQ2_HZ * fcn)
    if freq_index == 3:
        return CLIGHT / GLONASS_FREQ3_HZ
    raise ValueError(f"unsupported GLONASS frequency index: {freq_index}")


def locate_convbin(binary: Path | None = None) -> Path:
    if binary is not None:
        if not binary.is_file():
            raise IndependentDecoderUnavailable(f"convbin not found at {binary}")
        return binary
    found = shutil.which("convbin")
    if found:
        return Path(found)
    fallback = Path.home() / ".local" / "bin" / "convbin"
    if fallback.is_file():
        return fallback
    raise IndependentDecoderUnavailable("RTKLIB convbin binary is not installed")


def convbin_provenance(binary: Path | None = None) -> dict[str, Any]:
    path = locate_convbin(binary)
    return {
        "decoder_name": "RTKLIB convbin",
        "binary_path": str(path),
        "binary_sha256": sha256_file(path),
        "pinned_rtklib_commit": RTKLIB_COMMIT,
        "non_rtklib_decoder_available": False,
    }


@dataclass(frozen=True, slots=True)
class ConvbinObservation:
    value: float
    lli: int | None


@dataclass(frozen=True, slots=True)
class ConvbinEpoch:
    epoch_header: str
    satellites: dict[str, dict[str, ConvbinObservation]]


@dataclass(frozen=True, slots=True)
class ConvbinResult:
    returncode: int
    stderr: str
    rinex_text: str | None
    station_id: int | None
    approx_position_xyz: tuple[float, float, float] | None
    sys_obs_types: dict[str, tuple[str, ...]]
    time_of_first_obs: str | None
    epochs: tuple[ConvbinEpoch, ...]


def _parse_rinex3(text: str) -> tuple[
    int | None,
    tuple[float, float, float] | None,
    dict[str, tuple[str, ...]],
    str | None,
    tuple[ConvbinEpoch, ...],
]:
    lines = text.splitlines()
    station_id: int | None = None
    approx_pos: tuple[float, float, float] | None = None
    obs_types: dict[str, list[str]] = {}
    first_obs: str | None = None
    current_sys: str | None = None
    body_start = len(lines)

    for idx, line in enumerate(lines):
        label = line[60:].strip()
        content = line[:60]
        if label == "COMMENT" and "station ID:" in content:
            tail = content.split("station ID:", 1)[1].strip()
            with contextlib.suppress(IndexError, ValueError):
                station_id = int(tail.split()[0])
        elif label == "APPROX POSITION XYZ":
            parts = content.split()
            if len(parts) == 3:
                approx_pos = (float(parts[0]), float(parts[1]), float(parts[2]))
        elif label == "SYS / # / OBS TYPES":
            sys_char = line[0].strip()
            if sys_char:
                current_sys = sys_char
                obs_types.setdefault(current_sys, [])
            if current_sys is not None:
                obs_types[current_sys].extend(line[7:60].split())
        elif label == "TIME OF FIRST OBS":
            first_obs = content.strip()
        elif label == "END OF HEADER":
            body_start = idx + 1
            break

    epochs: list[ConvbinEpoch] = []
    idx = body_start
    while idx < len(lines):
        line = lines[idx]
        if not line.startswith(">"):
            idx += 1
            continue
        header = line.strip()
        parts = header.split()
        nsat = int(parts[8]) if len(parts) >= 9 else 0
        sat_map: dict[str, dict[str, ConvbinObservation]] = {}
        idx += 1
        for _ in range(nsat):
            if idx >= len(lines):
                break
            sat_line = lines[idx]
            idx += 1
            sat_id = sat_line[:3].replace(" ", "0")
            sys_char = sat_id[0]
            types = obs_types.get(sys_char, [])
            measurements: dict[str, ConvbinObservation] = {}
            for col, obs_code in enumerate(types):
                start = 3 + col * 16
                field = sat_line[start : start + 16]
                val_text = field[:14].strip()
                if not val_text:
                    continue
                lli_char = field[14:15].strip() if len(field) >= 15 else ""
                lli = int(lli_char) if lli_char.isdigit() else None
                measurements[obs_code] = ConvbinObservation(
                    value=float(val_text), lli=lli
                )
            sat_map[sat_id] = measurements
        epochs.append(ConvbinEpoch(epoch_header=header, satellites=sat_map))

    return (
        station_id,
        approx_pos,
        {k: tuple(v) for k, v in obs_types.items()},
        first_obs,
        tuple(epochs),
    )


def decode_with_convbin(
    rtcm_bytes: bytes,
    *,
    ref_date: str = "2026/01/01",
    ref_time: str = "00:00:00",
    binary: Path | None = None,
) -> ConvbinResult:
    exe = locate_convbin(binary)
    with tempfile.TemporaryDirectory(prefix="nlgcp-convbin-") as tmpdir:
        tmp = Path(tmpdir)
        inp = tmp / "synthetic.rtcm3"
        out = tmp / "decoded.obs"
        inp.write_bytes(rtcm_bytes)
        proc = subprocess.run(
            [
                str(exe),
                "-r",
                "rtcm3",
                "-tr",
                ref_date,
                ref_time,
                "-v",
                "3.02",
                "-f",
                "3",
                "-os",
                "-scan",
                "-o",
                str(out),
                str(inp),
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=60,
        )
        rinex_text = out.read_text(encoding="ascii", errors="replace") if out.is_file() else None
    if rinex_text is None:
        return ConvbinResult(
            returncode=proc.returncode,
            stderr=proc.stderr,
            rinex_text=None,
            station_id=None,
            approx_position_xyz=None,
            sys_obs_types={},
            time_of_first_obs=None,
            epochs=(),
        )
    station_id, approx_pos, sys_obs, first_obs, epochs = _parse_rinex3(rinex_text)
    return ConvbinResult(
        returncode=proc.returncode,
        stderr=proc.stderr,
        rinex_text=rinex_text,
        station_id=station_id,
        approx_position_xyz=approx_pos,
        sys_obs_types=sys_obs,
        time_of_first_obs=first_obs,
        epochs=epochs,
    )


def rtklib_decoder_provenance(source: Path) -> dict[str, Any]:
    if not source.is_dir():
        raise IndependentDecoderUnavailable(f"RTKLIB source directory not found: {source}")
    commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=source, text=True
    ).strip()
    if commit != RTKLIB_COMMIT:
        raise IndependentDecoderUnavailable(
            f"RTKLIB source commit {commit} does not match pinned {RTKLIB_COMMIT}"
        )
    hashes: dict[str, str] = {}
    for name in (*RTKLIB_DECODER_SOURCES, "rtklib.h"):
        path = source / "src" / name
        blob = subprocess.check_output(
            ["git", "show", f"{RTKLIB_COMMIT}:src/{name}"], cwd=source
        )
        if path.read_bytes() != blob:
            raise IndependentDecoderUnavailable(f"modified RTKLIB source file: {name}")
        hashes[name] = sha256_file(path)
    compiler = subprocess.check_output(["cc", "--version"], text=True).splitlines()[0]
    return {
        "decoder_name": "RTKLIB v2.4.2-p13 input_rtcm3",
        "commit": commit,
        "source_sha256": hashes,
        "compiler": compiler,
        "flags": (
            "-O2 -ffunction-sections -fdata-sections -Wl,--gc-sections "
            "-DENAGLO -DENAQZS -DENAGAL -DNFREQ=3 -DNEXOBS=3 -lm -lrt"
        ),
        "non_rtklib_decoder_available": False,
    }


def build_rtklib_decoder(repo: Path, source: Path) -> tuple[Path, dict[str, Any]]:
    provenance = rtklib_decoder_provenance(source)
    adapter = repo / "research/rtcm_generation/native/rtklib_rtcm_decode.c"
    provenance["adapter_sha256"] = sha256_file(adapter)
    build_dir = repo / "build/rtcm-decoder" / fingerprint(provenance)
    build_dir.mkdir(parents=True, exist_ok=True)
    executable = build_dir / "rtklib_rtcm_decode"
    command = [
        "cc",
        "-O2",
        "-ffunction-sections",
        "-fdata-sections",
        "-Wl,--gc-sections",
        "-DENAGLO",
        "-DENAQZS",
        "-DENAGAL",
        "-DNFREQ=3",
        "-DNEXOBS=3",
        "-I",
        str(source / "src"),
        str(adapter),
        *(str(source / "src" / name) for name in RTKLIB_DECODER_SOURCES),
        "-lm",
        "-lrt",
        "-o",
        str(executable),
    ]
    with tempfile.TemporaryDirectory(prefix=".compile-", dir=build_dir) as tmpdir:
        staged = Path(tmpdir) / "rtklib_rtcm_decode"
        command[-1] = str(staged)
        proc = subprocess.run(
            command, capture_output=True, text=True, check=False, timeout=120
        )
        if proc.returncode:
            raise IndependentDecoderUnavailable(
                "RTKLIB native RTCM decoder build failed: " + proc.stderr[-2000:]
            )
        staged.replace(executable)
    provenance["executable_sha256"] = sha256_file(executable)
    return executable, provenance


def decode_with_rtklib_native(
    executable: Path,
    rtcm_bytes: bytes,
    *,
    ref_epoch: tuple[int, int, int, int, int, float] = (2026, 1, 1, 0, 0, 0.0),
    glo_fcns: dict[int, int] | None = None,
) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="nlgcp-rtklib-dec-") as tmpdir:
        inp = Path(tmpdir) / "synthetic.rtcm3"
        inp.write_bytes(rtcm_bytes)
        args = [
            str(executable),
            str(inp),
            str(ref_epoch[0]),
            str(ref_epoch[1]),
            str(ref_epoch[2]),
            str(ref_epoch[3]),
            str(ref_epoch[4]),
            f"{ref_epoch[5]:.6f}",
        ]
        if glo_fcns:
            for slot in sorted(glo_fcns):
                args.extend(["--glo-fcn", f"{slot}:{glo_fcns[slot]}"])
        proc = subprocess.run(
            args, capture_output=True, text=True, check=False, timeout=60
        )
    if proc.returncode != 0:
        raise RuntimeError(
            f"native RTKLIB decoder failed (rc={proc.returncode}): {proc.stderr}"
        )
    parsed: dict[str, Any] = json.loads(proc.stdout)
    return parsed
