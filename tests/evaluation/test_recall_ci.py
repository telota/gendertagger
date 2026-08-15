from __future__ import annotations

import pytest

from gendertagger.evaluation.recall_ci import wilson_recall_interval

pytestmark = [pytest.mark.unit, pytest.mark.scientific]


def test_zero_class_size_returns_degenerate_zero_interval() -> None:
    assert wilson_recall_interval(0, 0, confidence_level=0.95) == {
        "recall": 0.0,
        "ci_low": 0.0,
        "ci_high": 0.0,
    }


def test_perfect_recall_matches_published_wilson_interval() -> None:
    # docs/paper/article.tex reports the local LLM's female recall on the GND
    # benchmark as 100.0% with a 95% Wilson CI of [98.2, 100.0] over n=205.
    result = wilson_recall_interval(205, 205, confidence_level=0.95)

    assert result == {"recall": 1.0, "ci_low": 0.982, "ci_high": 1.0}


def test_zero_recall_has_a_bounded_nonzero_upper_interval() -> None:
    result = wilson_recall_interval(0, 5, confidence_level=0.95)

    assert result["recall"] == 0.0
    assert result["ci_low"] == 0.0
    assert 0.0 < result["ci_high"] < 1.0


def test_interval_narrows_at_a_lower_confidence_level() -> None:
    wide = wilson_recall_interval(3, 4, confidence_level=0.99)
    narrow = wilson_recall_interval(3, 4, confidence_level=0.80)

    assert narrow["ci_low"] > wide["ci_low"]
    assert narrow["ci_high"] < wide["ci_high"]


def test_interval_bounds_are_never_outside_unit_range() -> None:
    result = wilson_recall_interval(1, 1, confidence_level=0.95)

    assert 0.0 <= result["ci_low"] <= result["ci_high"] <= 1.0
