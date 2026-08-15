from __future__ import annotations

import pytest

from gendertagger.evaluation.kappa import compute_kappa_matrix
from gendertagger.models.classification import CanonicalLabel, PredictionResult, PredictionStatus

pytestmark = [pytest.mark.unit, pytest.mark.scientific]


def _success(label: CanonicalLabel) -> PredictionResult:
    return PredictionResult(label=label, status=PredictionStatus.success)


def _abstain() -> PredictionResult:
    return PredictionResult(label=None, status=PredictionStatus.abstain)


def test_two_by_two_kappa_matches_hand_computed_value() -> None:
    # method_a: male, male, female, female
    # method_b: male, female, female, female
    # po = 3/4; pe = 0.5*0.25 + 0.5*0.75 = 0.5; kappa = (po-pe)/(1-pe) = 0.5.
    corpus = [
        {"method_a": _success(CanonicalLabel.male), "method_b": _success(CanonicalLabel.male)},
        {"method_a": _success(CanonicalLabel.male), "method_b": _success(CanonicalLabel.female)},
        {
            "method_a": _success(CanonicalLabel.female),
            "method_b": _success(CanonicalLabel.female),
        },
        {
            "method_a": _success(CanonicalLabel.female),
            "method_b": _success(CanonicalLabel.female),
        },
    ]

    matrix = compute_kappa_matrix(("method_a", "method_b"), corpus)

    assert len(matrix) == 1
    cell = matrix[0]
    assert cell.method_a == "method_a"
    assert cell.method_b == "method_b"
    assert cell.co_answered_count == 4
    assert cell.kappa == 0.5


def test_perfect_agreement_has_kappa_one() -> None:
    corpus = [
        {"method_a": _success(CanonicalLabel.male), "method_b": _success(CanonicalLabel.male)},
        {
            "method_a": _success(CanonicalLabel.female),
            "method_b": _success(CanonicalLabel.female),
        },
    ]

    matrix = compute_kappa_matrix(("method_a", "method_b"), corpus)

    assert matrix[0].kappa == 1.0


def test_fewer_than_two_co_answered_entries_reports_no_kappa() -> None:
    corpus = [
        {"method_a": _success(CanonicalLabel.male), "method_b": _abstain()},
        {"method_a": _success(CanonicalLabel.male), "method_b": _success(CanonicalLabel.male)},
    ]

    matrix = compute_kappa_matrix(("method_a", "method_b"), corpus)

    assert matrix[0].co_answered_count == 1
    assert matrix[0].kappa is None


def test_both_raters_constant_reports_no_kappa() -> None:
    corpus = [
        {"method_a": _success(CanonicalLabel.male), "method_b": _success(CanonicalLabel.male)},
        {"method_a": _success(CanonicalLabel.male), "method_b": _success(CanonicalLabel.male)},
        {"method_a": _success(CanonicalLabel.male), "method_b": _success(CanonicalLabel.male)},
    ]

    matrix = compute_kappa_matrix(("method_a", "method_b"), corpus)

    assert matrix[0].co_answered_count == 3
    assert matrix[0].kappa is None


def test_three_methods_produce_all_unordered_pairs_in_combination_order() -> None:
    corpus = [
        {
            "a": _success(CanonicalLabel.male),
            "b": _success(CanonicalLabel.female),
            "c": _success(CanonicalLabel.male),
        },
        {
            "a": _success(CanonicalLabel.female),
            "b": _success(CanonicalLabel.male),
            "c": _success(CanonicalLabel.female),
        },
    ]

    matrix = compute_kappa_matrix(("a", "b", "c"), corpus)

    assert [(cell.method_a, cell.method_b) for cell in matrix] == [
        ("a", "b"),
        ("a", "c"),
        ("b", "c"),
    ]


def test_error_status_never_counts_as_co_answered() -> None:
    corpus = [
        {
            "method_a": _success(CanonicalLabel.male),
            "method_b": PredictionResult(label=None, status=PredictionStatus.error),
        },
        {"method_a": _success(CanonicalLabel.male), "method_b": _success(CanonicalLabel.female)},
        {
            "method_a": _success(CanonicalLabel.female),
            "method_b": _success(CanonicalLabel.female),
        },
    ]

    matrix = compute_kappa_matrix(("method_a", "method_b"), corpus)

    assert matrix[0].co_answered_count == 2
