"""SYNTHETIC TEST DATA — NOT VALID FOR SCIENTIFIC RESULTS."""

from __future__ import annotations

from nlgcp_scientific_expansion import expansion_report


def test_navigation_counts_use_validation_status() -> None:
    counts = expansion_report._count_nav(
        [
            {"validation_status": "ACCEPTED"},
            {"validation_status": "REJECTED"},
            {"validation_status": "BLOCKED"},
            {"validation_status": "UNVALIDATED"},
        ]
    )
    assert counts["validated"] == 1
    assert counts["rejected"] == 1
    assert counts["blocked"] == 1
    assert counts["unvalidated"] == 1


def test_empty_phase6_evidence_is_explicit(tmp_path: object) -> None:
    result = expansion_report._phase6_summary(tmp_path)  # type: ignore[arg-type]
    assert result["experiments"] == 0
    assert result["comparison_keys"] == 0
    assert result["aggregate_rmse"]["zero"] == "UNAVAILABLE (n=0)"
