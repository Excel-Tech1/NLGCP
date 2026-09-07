"""Phase 3 validation report generation.

Produces the consolidated Phase 3 validation report and a concise
thesis-ready evidence summary, both derived from stored result files.  No
conclusions are written before the measured results exist.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


def write_validation_report(
    out_path: Path,
    *,
    objective: str,
    research_question: str,
    dataset: str,
    stations: list[str],
    station_metadata_provenance: str,
    experimental_window: str,
    session_qc: str,
    baseline_selection: str,
    rtklib_provenance: str,
    rtklib_config: str,
    processing_methodology: str,
    experiment_matrix: str,
    results: str,
    fix_float_behaviour: str,
    ttff: str,
    coordinate_residuals: str,
    rmse: str,
    baseline_length_relationship: str,
    temporal_variability: str,
    failed_blocked: str,
    limitations: str,
    implications_single_base: str,
    implications_network_rtk: str,
    reproducibility: str,
    exit_decision: str,
) -> Path:
    """Write the 25-section Phase 3 validation report."""
    sections = [
        ("Objective", objective),
        ("Research question", research_question),
        ("Dataset", dataset),
        ("Stations", stations),
        ("Station metadata provenance", station_metadata_provenance),
        ("Experimental window", experimental_window),
        ("Session QC", session_qc),
        ("Baseline-selection methodology", baseline_selection),
        ("RTKLIB provenance", rtklib_provenance),
        ("RTKLIB configuration", rtklib_config),
        ("Processing methodology", processing_methodology),
        ("Experiment matrix", experiment_matrix),
        ("Results", results),
        ("FIX/FLOAT behaviour", fix_float_behaviour),
        ("TTFF", ttff),
        ("Coordinate residuals", coordinate_residuals),
        ("RMSE", rmse),
        ("Baseline-length relationship", baseline_length_relationship),
        ("Temporal variability", temporal_variability),
        ("Failed/blocked experiments", failed_blocked),
        ("Limitations", limitations),
        ("Implications for Nigerian single-base RTK", implications_single_base),
        ("Implications for NLGCP network RTK/VRS", implications_network_rtk),
        ("Reproducibility information", reproducibility),
        ("Phase 3 exit decision", exit_decision),
    ]
    lines = ["# NLGCP Phase 3 Validation Report", ""]
    for index, (title, body) in enumerate(sections, start=1):
        lines.append(f"## {index}. {title}")
        lines.append("")
        lines.append(_wrap(body))
        lines.append("")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")
    return out_path


def write_thesis_evidence(
    out_path: Path,
    *,
    header: str,
    findings: list[str],
) -> Path:
    """Write a concise thesis-ready evidence summary."""
    lines = [
        header,
        "",
        "The findings below are derived from the measured Phase 3 results.",
        "",
    ]
    for item in findings:
        lines.append(f"- {item}")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out_path


def _wrap(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "\n".join(f"- {item}" for item in value)
    return str(value)
