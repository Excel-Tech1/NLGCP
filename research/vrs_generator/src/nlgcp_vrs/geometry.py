"""Reproducibly build/run the pinned external RTKLIB geometry adapter."""

from __future__ import annotations

import gzip
import math
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

from nlgcp_atmospheric_model.provenance import fingerprint, sha256_file

from .models import Blocked

RTKLIB_COMMIT = "71db0ffa0d9735697c6adfd06fdf766d0e5ce807"
SOURCES = ("rtkcmn.c", "rinex.c", "ephemeris.c", "preceph.c", "sbas.c", "qzslex.c")
FIELDS = (
    "range_anchor_m",
    "range_target_m",
    "satellite_clock_translation_m",
    "satellite_anchor_x_m",
    "satellite_anchor_y_m",
    "satellite_anchor_z_m",
    "satellite_target_x_m",
    "satellite_target_y_m",
    "satellite_target_z_m",
    "anchor_elevation_deg",
    "target_elevation_deg",
)


def source_provenance(source: Path) -> dict[str, Any]:
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=source, text=True).strip()
    if commit != RTKLIB_COMMIT:
        raise Blocked("RTKLIB source must match the documented v2.4.2-p13 commit")
    hashes = {}
    for name in (*SOURCES, "rtklib.h"):
        path = source / "src" / name
        blob = subprocess.check_output(["git", "show", f"{RTKLIB_COMMIT}:src/{name}"], cwd=source)
        if path.read_bytes() != blob:
            raise Blocked(f"modified RTKLIB dependency: {name}")
        hashes[name] = sha256_file(path)
    return {
        "commit": commit,
        "source_sha256": hashes,
        "compiler": subprocess.check_output(["cc", "--version"], text=True).splitlines()[0],
        "flags": (
            "-O2 -ffunction-sections -fdata-sections -Wl,--gc-sections "
            "-DENAGLO -DENAQZS -DENAGAL -DNFREQ=3 -lm -lrt"
        ),
    }


def build_adapter(repo: Path, source: Path) -> tuple[Path, dict[str, Any]]:
    provenance = source_provenance(source)
    adapter = repo / "research/vrs_generator/native/geometry.c"
    provenance["adapter_sha256"] = sha256_file(adapter)
    build = repo / "build/vrs" / fingerprint(provenance)
    build.mkdir(parents=True, exist_ok=True)
    executable = build / "geometry"
    # Always compile before generation; do not trust a mutable cached executable.
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
        "-I",
        str(source / "src"),
        str(adapter),
        *(str(source / "src" / n) for n in SOURCES),
        "-lm",
        "-lrt",
        "-o",
        str(executable),
    ]
    with tempfile.TemporaryDirectory(prefix=".compile-", dir=build) as temporary:
        staged = Path(temporary) / "geometry"
        command[-1] = str(staged)
        result = subprocess.run(command, capture_output=True, text=True, check=False, timeout=120)
        if result.returncode:
            raise Blocked("RTKLIB adapter compilation failed: " + result.stderr[-3000:])
        staged.replace(executable)

    provenance["executable_sha256"] = sha256_file(executable)
    return executable, provenance


def geometry_batch(
    executable: Path,
    navigation: Path,
    anchor: tuple[float, float, float],
    target: tuple[float, float, float],
    requests: list[tuple[str, str, float]],
    work: Path,
) -> list[dict[str, Any]]:
    text = []
    for epoch, satellite, pseudorange in requests:
        t = datetime.fromisoformat(epoch)
        text.append(
            f"{t.year} {t.month} {t.day} {t.hour} {t.minute} "
            f"{t.second + t.microsecond / 1e6:.6f} {int(satellite[1:])} {pseudorange:.9f}"
        )
    # Decompress a verified navigation product to an isolated derived temporary
    # location; never let RTKLIB uncompress beside an immutable input.
    with tempfile.TemporaryDirectory(dir=work) as temporary:
        nav = Path(temporary) / "broadcast.rnx"
        if navigation.suffix == ".gz":
            with gzip.open(navigation, "rb") as handle:
                nav.write_bytes(handle.read())
        else:
            nav.write_bytes(navigation.read_bytes())
        result = subprocess.run(
            [str(executable), str(nav), *(str(x) for x in (*anchor, *target))],
            input="\n".join(text) + "\n",
            capture_output=True,
            text=True,
            check=False,
            timeout=300,
        )
    if result.returncode:
        raise Blocked(f"RTKLIB geometry failed with exit {result.returncode}")
    lines = result.stdout.splitlines()
    if len(lines) != len(requests):
        raise Blocked("RTKLIB geometry row count mismatch")
    output = []
    for line in lines:
        values = line.split()
        if values == ["1"]:
            output.append({"reason": "missing/stale/unhealthy ephemeris"})
        elif values == ["2"]:
            output.append({"reason": "light-time iteration or range invalid"})
        elif len(values) == 12 and values[0] == "0":
            numbers = [float(x) for x in values[1:]]
            if not all(math.isfinite(x) for x in numbers):
                raise Blocked("non-finite satellite geometry")
            row: dict[str, Any] = dict(zip(FIELDS, numbers, strict=True))
            row["geometric_transformation_m"] = numbers[1] - numbers[0]
            if min(numbers[-2:]) <= 0:
                row["reason"] = "satellite at/below geometric horizon at anchor or target"
            output.append(row)
        else:
            raise Blocked("malformed adapter output")
    return output
