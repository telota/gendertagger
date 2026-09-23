"""Pure per-method coverage, benchmark accuracy, and confusion-matrix metrics."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from gendertagger.evaluation.recall_ci import wilson_recall_interval
from gendertagger.models.classification import CanonicalLabel, PredictionResult, PredictionStatus
from gendertagger.models.evaluation import (
    BenchmarkSummary,
    EvaluationDefinition,
    MethodAccuracy,
    MethodCoverage,
    RecallWithCI,
)

_ROUNDING_DECIMAL_PLACES = 3


def compute_method_coverage(
    method_name: str,
    corpus: Sequence[Mapping[str, PredictionResult]],
    *,
    total: int,
) -> MethodCoverage:
    """Corpus-wide coverage and label distribution for one method.

    Coverage counts every successful, non-abstained, non-error result,
    including a substantive ``unknown`` label -- the method evaluated the
    input and returned an ambiguous classification, which is scientifically
    distinct from abstaining.
    """
    label_counts: dict[CanonicalLabel, int] = dict.fromkeys(CanonicalLabel, 0)
    abstain_count = 0
    error_count = 0
    for person in corpus:
        prediction = person[method_name]
        label = _successful_label(prediction)
        if label is not None:
            label_counts[label] += 1
        elif prediction.status is PredictionStatus.abstain:
            abstain_count += 1
        else:
            error_count += 1

    coverage_count = sum(label_counts.values())
    coverage_share = round(coverage_count / total, _ROUNDING_DECIMAL_PLACES) if total else 0.0
    return MethodCoverage(
        method_name=method_name,
        total=total,
        coverage_count=coverage_count,
        coverage_share=coverage_share,
        label_distribution=label_counts,
        abstain_count=abstain_count,
        error_count=error_count,
    )


def compute_benchmark_summary(
    definition: EvaluationDefinition,
    benchmark_subset: Sequence[tuple[CanonicalLabel, Mapping[str, PredictionResult]]],
) -> BenchmarkSummary:
    """Size and per-label composition of the resolved benchmark subset."""
    class_counts: dict[CanonicalLabel, int] = dict.fromkeys(definition.benchmark_label_filter, 0)
    for truth_label, _ in benchmark_subset:
        class_counts[truth_label] += 1
    return BenchmarkSummary(
        method_name=definition.benchmark_method,
        labels=definition.benchmark_label_filter,
        size=len(benchmark_subset),
        class_counts=class_counts,
    )


def compute_method_accuracy(
    method_name: str,
    definition: EvaluationDefinition,
    benchmark_subset: Sequence[tuple[CanonicalLabel, Mapping[str, PredictionResult]]],
) -> MethodAccuracy:
    """Benchmark-scoped accuracy, recall, and confusion matrix for one scored method.

    ``accuracy`` divides correct labels by answered entries only.
    ``effective_accuracy`` divides by the full benchmark size, so abstentions
    count against the method -- matching the published study's definition.
    """
    benchmark_labels = definition.benchmark_label_filter
    confusion: dict[CanonicalLabel, dict[CanonicalLabel, int]] = {
        truth_label: dict.fromkeys(CanonicalLabel, 0) for truth_label in benchmark_labels
    }
    class_totals: dict[CanonicalLabel, int] = dict.fromkeys(benchmark_labels, 0)
    class_correct: dict[CanonicalLabel, int] = dict.fromkeys(benchmark_labels, 0)
    answered_count = 0
    correct_count = 0

    for truth_label, person in benchmark_subset:
        class_totals[truth_label] += 1
        predicted_label = _successful_label(person[method_name])
        if predicted_label is None:
            continue
        answered_count += 1
        confusion[truth_label][predicted_label] += 1
        if predicted_label == truth_label:
            correct_count += 1
            class_correct[truth_label] += 1

    benchmark_size = len(benchmark_subset)
    accuracy = (
        round(correct_count / answered_count, _ROUNDING_DECIMAL_PLACES) if answered_count else 0.0
    )
    effective_accuracy = (
        round(correct_count / benchmark_size, _ROUNDING_DECIMAL_PLACES) if benchmark_size else 0.0
    )
    recall = tuple(
        RecallWithCI(
            label=label,
            class_size=class_totals[label],
            correct=class_correct[label],
            **wilson_recall_interval(
                class_correct[label],
                class_totals[label],
                confidence_level=definition.confidence_level,
            ),
        )
        for label in benchmark_labels
    )

    return MethodAccuracy(
        method_name=method_name,
        answered_count=answered_count,
        correct_count=correct_count,
        accuracy=accuracy,
        effective_accuracy=effective_accuracy,
        confusion_matrix=confusion,
        recall=recall,
    )


def _successful_label(prediction: PredictionResult) -> CanonicalLabel | None:
    return prediction.label if prediction.status is PredictionStatus.success else None
