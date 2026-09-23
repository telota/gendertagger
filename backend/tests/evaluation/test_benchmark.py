from __future__ import annotations

import pytest

from gendertagger.evaluation.benchmark import select_benchmark_subset
from gendertagger.models.classification import CanonicalLabel, PredictionResult, PredictionStatus
from gendertagger.models.evaluation import EvaluationDefinition

pytestmark = [pytest.mark.unit, pytest.mark.scientific]


def _success(label: CanonicalLabel) -> PredictionResult:
    return PredictionResult(label=label, status=PredictionStatus.success)


def _abstain() -> PredictionResult:
    return PredictionResult(label=None, status=PredictionStatus.abstain)


def test_selects_only_gendered_successful_gnd_results_by_default() -> None:
    definition = EvaluationDefinition()
    corpus = [
        {"gnd": _success(CanonicalLabel.male)},
        {"gnd": _success(CanonicalLabel.female)},
        {"gnd": _success(CanonicalLabel.institution)},
        {"gnd": _success(CanonicalLabel.unknown)},
        {"gnd": _abstain()},
    ]

    subset = select_benchmark_subset(corpus, definition)

    assert [label for label, _ in subset] == [CanonicalLabel.male, CanonicalLabel.female]
    assert [person for _, person in subset] == [corpus[0], corpus[1]]


def test_preserves_corpus_order() -> None:
    definition = EvaluationDefinition()
    corpus = [
        {"gnd": _success(CanonicalLabel.female)},
        {"gnd": _success(CanonicalLabel.male)},
    ]

    subset = select_benchmark_subset(corpus, definition)

    assert [label for label, _ in subset] == [CanonicalLabel.female, CanonicalLabel.male]


def test_custom_benchmark_method_and_label_filter_are_honored() -> None:
    definition = EvaluationDefinition(
        benchmark_method="hivoto",
        benchmark_label_filter=(CanonicalLabel.institution,),
        scored_methods=("gender_guesser",),
        kappa_extra_methods=(),
    )
    corpus = [
        {"hivoto": _success(CanonicalLabel.institution)},
        {"hivoto": _success(CanonicalLabel.male)},
    ]

    subset = select_benchmark_subset(corpus, definition)

    assert [label for label, _ in subset] == [CanonicalLabel.institution]


def test_empty_corpus_yields_empty_subset() -> None:
    definition = EvaluationDefinition()

    assert select_benchmark_subset([], definition) == []
