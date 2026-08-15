from __future__ import annotations

import pytest

from gendertagger.evaluation.metrics import (
    compute_benchmark_summary,
    compute_method_accuracy,
    compute_method_coverage,
)
from gendertagger.models.classification import CanonicalLabel, PredictionResult, PredictionStatus
from gendertagger.models.evaluation import EvaluationDefinition

pytestmark = [pytest.mark.unit, pytest.mark.scientific]


def _success(label: CanonicalLabel) -> PredictionResult:
    return PredictionResult(label=label, status=PredictionStatus.success)


def _abstain() -> PredictionResult:
    return PredictionResult(label=None, status=PredictionStatus.abstain)


def _error() -> PredictionResult:
    return PredictionResult(label=None, status=PredictionStatus.error)


class TestMethodCoverage:
    def test_counts_labels_abstentions_and_errors_separately(self) -> None:
        corpus = [
            {"method": _success(CanonicalLabel.male)},
            {"method": _success(CanonicalLabel.male)},
            {"method": _success(CanonicalLabel.female)},
            {"method": _abstain()},
            {"method": _error()},
        ]

        coverage = compute_method_coverage("method", corpus, total=5)

        assert coverage.total == 5
        assert coverage.coverage_count == 3
        assert coverage.coverage_share == 0.6
        assert coverage.label_distribution == {
            CanonicalLabel.male: 2,
            CanonicalLabel.female: 1,
            CanonicalLabel.unknown: 0,
            CanonicalLabel.institution: 0,
        }
        assert coverage.abstain_count == 1
        assert coverage.error_count == 1

    def test_substantive_unknown_counts_as_coverage_not_abstention(self) -> None:
        coverage = compute_method_coverage(
            "method", [{"method": _success(CanonicalLabel.unknown)}], total=1
        )

        assert coverage.coverage_count == 1
        assert coverage.abstain_count == 0
        assert coverage.label_distribution[CanonicalLabel.unknown] == 1

    def test_empty_corpus_has_zero_share_without_dividing_by_zero(self) -> None:
        coverage = compute_method_coverage("method", [], total=0)

        assert coverage.coverage_count == 0
        assert coverage.coverage_share == 0.0


class TestBenchmarkSummary:
    def test_counts_each_benchmark_label(self) -> None:
        definition = EvaluationDefinition()
        subset = [
            (CanonicalLabel.male, {"gnd": _success(CanonicalLabel.male)}),
            (CanonicalLabel.male, {"gnd": _success(CanonicalLabel.male)}),
            (CanonicalLabel.female, {"gnd": _success(CanonicalLabel.female)}),
        ]

        summary = compute_benchmark_summary(definition, subset)

        assert summary.method_name == "gnd"
        assert summary.size == 3
        assert summary.class_counts == {CanonicalLabel.male: 2, CanonicalLabel.female: 1}


class TestMethodAccuracy:
    def test_matches_hand_computed_accuracy_and_recall(self) -> None:
        definition = EvaluationDefinition()
        # truth=male, pred=male (correct); truth=male, pred=female (wrong);
        # truth=female, pred=female (correct); truth=female, pred=abstain (unanswered).
        subset = [
            (CanonicalLabel.male, {"gender_guesser": _success(CanonicalLabel.male)}),
            (CanonicalLabel.male, {"gender_guesser": _success(CanonicalLabel.female)}),
            (CanonicalLabel.female, {"gender_guesser": _success(CanonicalLabel.female)}),
            (CanonicalLabel.female, {"gender_guesser": _abstain()}),
        ]

        accuracy = compute_method_accuracy("gender_guesser", definition, subset)

        assert accuracy.answered_count == 3
        assert accuracy.correct_count == 2
        assert accuracy.accuracy == pytest.approx(2 / 3, abs=1e-3)
        assert accuracy.effective_accuracy == 0.5
        assert accuracy.confusion_matrix[CanonicalLabel.male][CanonicalLabel.male] == 1
        assert accuracy.confusion_matrix[CanonicalLabel.male][CanonicalLabel.female] == 1
        assert accuracy.confusion_matrix[CanonicalLabel.female][CanonicalLabel.female] == 1

        recall_by_label = {r.label: r for r in accuracy.recall}
        assert recall_by_label[CanonicalLabel.male].class_size == 2
        assert recall_by_label[CanonicalLabel.male].correct == 1
        assert recall_by_label[CanonicalLabel.male].recall == 0.5
        assert recall_by_label[CanonicalLabel.female].class_size == 2
        assert recall_by_label[CanonicalLabel.female].correct == 1
        assert recall_by_label[CanonicalLabel.female].recall == 0.5

    def test_empty_benchmark_subset_has_zero_accuracy_without_dividing_by_zero(self) -> None:
        definition = EvaluationDefinition()

        accuracy = compute_method_accuracy("gender_guesser", definition, [])

        assert accuracy.answered_count == 0
        assert accuracy.correct_count == 0
        assert accuracy.accuracy == 0.0
        assert accuracy.effective_accuracy == 0.0
