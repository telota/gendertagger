from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from gendertagger.evaluation.report import EvaluationInputError, build_report
from gendertagger.models.aggregation import (
    AggregatedResult,
    AggregationOutcome,
    AggregationPersonPredictions,
    VoteCounts,
)
from gendertagger.models.classification import (
    AgreementTier,
    CanonicalLabel,
    CertaintyTier,
    PredictionResult,
    PredictionStatus,
)
from gendertagger.models.evaluation import EvaluationDefinition

pytestmark = [pytest.mark.unit, pytest.mark.scientific]


def _success(label: CanonicalLabel) -> PredictionResult:
    return PredictionResult(label=label, status=PredictionStatus.success)


def _complete_person(**overrides: PredictionResult) -> AggregationPersonPredictions:
    definition = EvaluationDefinition()
    predictions = {
        method_name: _success(CanonicalLabel.male) for method_name in definition.required_methods
    }
    predictions.update(overrides)
    return AggregationPersonPredictions(person_record_id=uuid4(), predictions=predictions)


def test_missing_required_prediction_raises_evaluation_input_error() -> None:
    definition = EvaluationDefinition()
    incomplete = AggregationPersonPredictions(
        person_record_id=uuid4(),
        predictions={
            method_name: _success(CanonicalLabel.male)
            for method_name in definition.required_methods
            if method_name != "gnd"
        },
    )

    with pytest.raises(EvaluationInputError, match="gnd"):
        build_report([incomplete], definition)


def test_builds_a_complete_report_without_aggregation_results() -> None:
    definition = EvaluationDefinition()
    corpus = [
        _complete_person(),
        _complete_person(
            gnd=_success(CanonicalLabel.female), gender_guesser=_success(CanonicalLabel.female)
        ),
        _complete_person(gnd=_success(CanonicalLabel.institution)),
    ]

    report = build_report(corpus, definition)

    assert report.definition == definition.id
    assert report.benchmark.size == 2
    assert report.benchmark.class_counts == {CanonicalLabel.male: 1, CanonicalLabel.female: 1}
    assert {c.method_name for c in report.coverage} == set(definition.required_methods)
    assert {a.method_name for a in report.accuracy} == set(definition.scored_methods)
    assert (
        len(report.kappa_matrix)
        == len(definition.kappa_methods) * (len(definition.kappa_methods) - 1) // 2
    )
    assert report.ensemble is None


def test_ensemble_is_populated_only_when_aggregated_results_supplied() -> None:
    definition = EvaluationDefinition()
    corpus = [_complete_person()]
    aggregated_results = [
        AggregatedResult(
            id=uuid4(),
            aggregation_execution_id=uuid4(),
            person_record_id=corpus[0].person_record_id,
            outcome=AggregationOutcome.decided,
            label=CanonicalLabel.male,
            pooled_vote_counts=VoteCounts(male=7),
            agreement_score=1.0,
            agreement_tier=AgreementTier.unanimous,
            certainty_tier=CertaintyTier.high,
            created_at=datetime.now(UTC),
        )
    ]

    report = build_report(
        corpus,
        definition,
        aggregated_results=aggregated_results,
        human_reviewed_count=1,
        human_correction_count=0,
    )

    assert report.ensemble is not None
    assert report.ensemble.canonical_label_distribution[CanonicalLabel.male] == 1
    assert report.ensemble.human_reviewed_count == 1
