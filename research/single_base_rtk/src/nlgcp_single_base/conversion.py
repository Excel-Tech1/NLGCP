"""Deterministic RINEX observation conversion for Phase 3.

The preserved 2024 delivery stores observations as Hatanaka-compressed,
Unix-compressed RINEX 2.11 files (``*.24D.Z``).  RTKLIB and PRIDE PPP-AR need
plain RINEX observations (``*.24O``).

This module provides the reproducible two-stage conversion:

    *.24D.Z  --uncompress-->  *.24D  --CRX2RNX-->  *.24O

Source bytes are never modified.  Every input and output is hashed with
SHA-256 and a conversion record is returned so experiments can record full
provenance.
"""

from __future__ import annotations

import shutil
import subprocess
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from nlgcp_single_base.io import sha256_file

CRX2RNX = "/usr/local/bin/CRX2RNX"
CRX2RNX_VERSION_PROBE = [CRX2RNX, "-h"]


class ConversionError(RuntimeError):
    """Raised when a Hatanaka/Unix observation conversion fails."""


def _tool_version() -> str:
    """Return a best-effort CRX2RNX version string or 'unknown'."""
    try:
        result = subprocess.run(
            CRX2RNX_VERSION_PROBE,
            check=False,
            text=True,
            capture_output=True,
            timeout=30,
        )
        return (result.stdout or result.stderr).strip()[:200] or "unknown"
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def uncompress_tool_path() -> str:
    """Return the resolvable path of the Unix ``uncompress`` utility."""
    path = shutil.which("uncompress")
    if not path:
        raise ConversionError("uncompress utility not found on PATH")
    return path


@dataclass(frozen=True)
class ObservationConversion:
    """Provenance record for one source-to-RINEX observation conversion."""

    source_path: Path
    source_sha256: str
    decompressed_path: Path
    decompressed_sha256: str
    converted_path: Path
    converted_sha256: str
    crx2rnx_version: str
    uncompress_tool: str
    started_at: str
    duration_seconds: float
    crx2rnx_rc: int

    def as_dict(self) -> dict[str, str | int | float | None]:
        """JSON-safe conversion provenance."""
        return {
            "source_path": str(self.source_path),
            "source_sha256": self.source_sha256,
            "decompressed_path": str(self.decompressed_path),
            "decompressed_sha256": self.decompressed_sha256,
            "converted_path": str(self.converted_path),
            "converted_sha256": self.converted_sha256,
            "crx2rnx_version": self.crx2rnx_version,
            "uncompress_tool": self.uncompress_tool,
            "started_at": self.started_at,
            "duration_seconds": self.duration_seconds,
            "crx2rnx_rc": self.crx2rnx_rc,
        }


def _decompressed_name(source: Path, output_dir: Path) -> Path:
    """Return the staged ``*.24D`` path for a ``*.24D.Z`` source."""
    return output_dir / source.name[:-2]


def _converted_name(source: Path, output_dir: Path) -> Path:
    """Return the staged plain-RINEX ``*.24O`` path for a source."""
    decompressed = _decompressed_name(source, output_dir)
    return output_dir / (decompressed.name[:-1] + "O")


def convert_observation(
    source: Path,
    output_dir: Path,
    *,
    force: bool = False,
) -> ObservationConversion:
    """Convert a ``*.24D.Z`` source into a plain RINEX ``*.24O`` observation.

    The conversion is deterministic given identical source bytes and tools.
    It never touches the source archive.

    Parameters
    ----------
    source : Path
        The preserved ``*.24D.Z`` Hatanaka/Unix-compressed archive.
    output_dir : Path
        Working staging directory for the decompressed and converted files.
        Will be created if missing.
    force : bool
        Re-run the conversion even if the target already exists.

    Returns
    -------
    ObservationConversion
        Full provenance for the conversion.
    """
    source = source.resolve()
    output_dir = output_dir.resolve()
    if not source.is_file():
        raise ConversionError(f"source observation is not a file: {source}")
    if not source.name.endswith(".Z"):
        raise ConversionError(f"expected Unix-compressed (*.Z) source: {source}")
    if source.name.count(".24D") != 1 and source.name.count(".24O") != 1:
        raise ConversionError(f"unrecognised observation source name: {source.name}")

    output_dir.mkdir(parents=True, exist_ok=True)

    source_sha256 = sha256_file(source)
    decompressed_path = _decompressed_name(source, output_dir)
    converted_path = _converted_name(source, output_dir)

    uncompress_tool = uncompress_tool_path()
    started_iso = datetime.now(UTC).isoformat(timespec="seconds")
    started = time.monotonic()

    if not decompressed_path.exists() or force:
        _run_uncompress(source, decompressed_path, uncompress_tool)

    decompressed_sha256 = sha256_file(decompressed_path)

    crx2rnx_rc = 0
    if not converted_path.exists() or force:
        crx2rnx_rc = _run_crx2rnx(decompressed_path, output_dir)

    converted_sha256 = sha256_file(converted_path)

    return ObservationConversion(
        source_path=source,
        source_sha256=source_sha256,
        decompressed_path=decompressed_path,
        decompressed_sha256=decompressed_sha256,
        converted_path=converted_path,
        converted_sha256=converted_sha256,
        crx2rnx_version=_tool_version(),
        uncompress_tool=uncompress_tool,
        started_at=started_iso,
        duration_seconds=time.monotonic() - started,
        crx2rnx_rc=crx2rnx_rc,
    )


def _run_uncompress(source: Path, target: Path, tool: str) -> None:
    """Unix-decompress a ``*.Z`` archive to ``target`` without touching source."""
    scratch_dir = target.parent / ".unc-tmp"
    scratch_dir.mkdir(parents=True, exist_ok=True)
    scratch_archive = scratch_dir / source.name
    scratch_archive.write_bytes(source.read_bytes())
    try:
        result = subprocess.run(
            [tool, str(scratch_archive)],
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise ConversionError(
                f"uncompress failed rc={result.returncode}: {(result.stderr or '').strip()}"
            )
        decompressed_scratch = scratch_dir / (source.name[:-2])
        if not decompressed_scratch.exists() or decompressed_scratch.stat().st_size == 0:
            raise ConversionError("uncompress produced no output")
        target.write_bytes(decompressed_scratch.read_bytes())
    finally:
        shutil.rmtree(scratch_dir, ignore_errors=True)


def _run_crx2rnx(source: Path, output_dir: Path) -> int:
    """Convert a Hatanaka-compressed RINEX into plain RINEX with CRX2RNX."""
    result = subprocess.run(
        [CRX2RNX, str(source)],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        cwd=str(output_dir),
    )
    if result.returncode != 0:
        raise ConversionError(f"CRX2RNX failed rc={result.returncode}: {result.stdout.strip()}")
    return result.returncode
