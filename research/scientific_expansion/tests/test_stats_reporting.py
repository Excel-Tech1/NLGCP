"""SYNTHETIC TEST DATA — NOT VALID FOR SCIENTIFIC RESULTS."""

from __future__ import annotations

import math

from nlgcp_scientific_expansion import reporting, stats


def test_summarize_basic() -> None:
    result = stats.summarize([1.0, 2.0, 3.0, 4.0])
    assert result.n == 4
    assert result.mean == 2.5
    assert result.median == 2.5
    assert result.minimum == 1.0
    assert result.maximum == 4.0


def test_summarize_empty_never_invents() -> None:
    result = stats.summarize([])
    assert result.n == 0
    assert math.isnan(result.mean)


def test_pearson_perfect_correlation() -> None:
    result = stats.pearson_with_ci([1.0, 2.0, 3.0, 4.0], [2.0, 4.0, 6.0, 8.0])
    assert result.n == 4
    assert abs(result.coefficient - 1.0) < 1e-9
    assert result.ci_low <= result.coefficient <= result.ci_high


def test_pearson_insufficient_sample() -> None:
    result = stats.pearson_with_ci([1.0], [1.0])
    assert result.n == 1
    assert math.isnan(result.coefficient)


def test_fix_rate_zero_denominator() -> None:
    outcome = stats.fix_rate_summary(0, 0)
    assert outcome["total_epochs"] == 0
    assert math.isnan(float(outcome["fix_rate"]))


def test_fix_rate_fraction() -> None:
    outcome = stats.fix_rate_summary(2, 2880)
    assert abs(float(outcome["fix_rate"]) - 2 / 2880) < 1e-12


def test_write_csv_deterministic(tmp_path: object) -> None:
    from pathlib import Path

    path = str(Path(str(tmp_path)) / "table.csv")
    rows = [{"a": 1, "b": "x"}, {"a": 2, "b": "y"}]
    first = reporting.write_csv(path, ["a", "b"], rows)
    second = reporting.write_csv(path, ["a", "b"], rows)
    assert first == second
    assert len(first) == 64


def test_fingerprint_mapping_sorted() -> None:
    first = reporting.fingerprint_mapping({"b": "2", "a": "1"})
    second = reporting.fingerprint_mapping({"a": "1", "b": "2"})
    assert first == second
