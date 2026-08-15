"""Pure benchmark-subset selection for evaluation."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from gendertagger.models.classification import CanonicalLabel, PredictionResult, PredictionStatus
from gendertagger.models.evaluation import EvaluationDefinition


def select_benchmark_subset(
    corpus: Sequence[Mapping[str, PredictionResult]],
    definition: EvaluationDefinition,
) -> list[tuple[CanonicalLabel, Mapping[str, PredictionResult]]]:
    """Select the persons whose benchmark-method result is a filtered label.

    Reproduces the published study's "gendered GND benchmark": a person
    enters the subset only when the configured benchmark method (``gnd`` by
    default) returned a successful result whose label is in
    ``definition.benchmark_label_filter`` (male/female by default, excluding
    institution and unknown/abstained records).

    Args:
        corpus: One prediction mapping per person, each already containing a
            result for every method in ``definition.required_methods``.
        definition: The evaluation's benchmark and metric configuration.

    Returns:
        ``(truth_label, predictions)`` pairs for every person in the
        benchmark subset, in corpus order.
    """
    subset: list[tuple[CanonicalLabel, Mapping[str, PredictionResult]]] = []
    for person in corpus:
        label = _successful_label(person[definition.benchmark_method])
        if label is not None and label in definition.benchmark_label_filter:
            subset.append((label, person))
    return subset


def _successful_label(prediction: PredictionResult) -> CanonicalLabel | None:
    return prediction.label if prediction.status is PredictionStatus.success else None
