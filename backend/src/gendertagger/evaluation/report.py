"""Pure orchestration assembling one complete EvaluationReport."""

from __future__ import annotations

from collections.abc import Sequence

from gendertagger.evaluation.benchmark import select_benchmark_subset
from gendertagger.evaluation.ensemble import compute_ensemble_metrics
from gendertagger.evaluation.kappa import compute_kappa_matrix
from gendertagger.evaluation.metrics import (
    compute_benchmark_summary,
    compute_method_accuracy,
    compute_method_coverage,
)
from gendertagger.models.aggregation import AggregatedResult, AggregationPersonPredictions
from gendertagger.models.evaluation import EvaluationDefinition, EvaluationReport


class EvaluationInputError(ValueError):
    """Raised when persisted evidence cannot produce a reproducible evaluation."""


def build_report(
    corpus: Sequence[AggregationPersonPredictions],
    definition: EvaluationDefinition,
    *,
    aggregated_results: Sequence[AggregatedResult] | None = None,
    human_reviewed_count: int = 0,
    human_correction_count: int = 0,
) -> EvaluationReport:
    """Assemble one complete, immutable evaluation report.

    Args:
        corpus: One prediction mapping per person in the evaluated run
            snapshot. Every person must carry a Prediction from every method
            in ``definition.required_methods``; presence, not scientific
            outcome, satisfies completeness -- ``success``/``abstain``/
            ``error`` all count.
        definition: The versioned benchmark and metric configuration.
        aggregated_results: The run's complete AggregatedResult set, if an
            aggregation execution was supplied. Enables the ensemble metrics
            block; omitted (``None``) leaves it unset.
        human_reviewed_count: Reviewed-person count for the ensemble summary,
            supplied by the caller (derived from ReviewState/Annotation,
            which this pure function does not read). Ignored when
            ``aggregated_results`` is ``None``.
        human_correction_count: Corrected-person count for the ensemble
            summary, supplied by the caller. Ignored when
            ``aggregated_results`` is ``None``.

    Returns:
        The complete, immutable computed evaluation report.

    Raises:
        EvaluationInputError: If any person is missing a required method's
            Prediction.
    """
    required_methods = set(definition.required_methods)
    for person in corpus:
        missing_methods = sorted(required_methods - person.predictions.keys())
        if missing_methods:
            msg = (
                f"person record {person.person_record_id} is missing required "
                f"predictions: {', '.join(missing_methods)}"
            )
            raise EvaluationInputError(msg)

    per_person = [person.predictions for person in corpus]
    total = len(per_person)

    coverage = tuple(
        compute_method_coverage(method_name, per_person, total=total)
        for method_name in definition.required_methods
    )

    benchmark_subset = select_benchmark_subset(per_person, definition)
    benchmark_summary = compute_benchmark_summary(definition, benchmark_subset)
    accuracy = tuple(
        compute_method_accuracy(method_name, definition, benchmark_subset)
        for method_name in definition.scored_methods
    )
    kappa_matrix = compute_kappa_matrix(definition.kappa_methods, per_person)

    ensemble = None
    if aggregated_results is not None:
        ensemble = compute_ensemble_metrics(
            aggregated_results,
            human_reviewed_count=human_reviewed_count,
            human_correction_count=human_correction_count,
        )

    return EvaluationReport(
        definition=definition.id,
        benchmark=benchmark_summary,
        coverage=coverage,
        accuracy=accuracy,
        kappa_matrix=kappa_matrix,
        ensemble=ensemble,
    )
