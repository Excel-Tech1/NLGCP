"""Read-only independent reference build; pins external RTKLIB provenance."""

import subprocess
from pathlib import Path

from nlgcp_atmospheric_model.provenance import sha256_file
from nlgcp_vrs.geometry import SOURCES, source_provenance


def build_reference(repo: Path, source: Path) -> tuple[Path, dict]:
    provenance = source_provenance(source)
    adapter = repo / "research/scientific_validation/native/reference.c"
    out = repo / "build/scientific-validation/reference"
    out.parent.mkdir(parents=True, exist_ok=True)
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
        *[str(source / "src" / n) for n in SOURCES],
        "-lm",
        "-lrt",
        "-o",
        str(out),
    ]
    subprocess.run(command, check=True, capture_output=True)
    provenance.update(
        adapter_sha256=sha256_file(adapter), executable_sha256=sha256_file(out), command=command
    )
    return out, provenance
