"""Pure implementation of the published reference aggregation priority chain."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping

from gendertagger.models.aggregation import (
    AggregationOutcome,
    OverrideSource,
    ReferenceAggregationDecision,
    VoteCounts,
)
from gendertagger.models.classification import (
    CanonicalLabel,
    PredictionResult,
    PredictionStatus,
)

REFERENCE_AUTHORITY_METHODS = ("parenthetical_qualifier", "gnd")
REFERENCE_POOLED_METHODS = (
    "gender_guesser",
    "wiki_gendersort",
    "hivoto",
    "nomquamgender",
    "hf_distilbert",
    "hf_genderize",
    "local_llm",
)
REFERENCE_IGNORED_METHODS = ("hivoto_xgboost",)
REFERENCE_REQUIRED_METHODS = REFERENCE_AUTHORITY_METHODS + REFERENCE_POOLED_METHODS
_ALLOWED_METHODS = frozenset(REFERENCE_REQUIRED_METHODS + REFERENCE_IGNORED_METHODS)


class ReferenceAggregationError(ValueError):
    """Raised when inputs cannot represent a reproducible reference aggregation."""


def aggregate_reference_predictions(
    predictions: Mapping[str, PredictionResult],
    *,
    require_full_set: bool = True,
) -> ReferenceAggregationDecision:
    """Aggregate one person's reference prediction set (ADR-0051).

    The parenthetical-qualifier result has first priority, including a
    substantive ``unknown`` result. A substantive non-unknown GND result has
    second priority. Otherwise, the pooled methods present cast an unweighted
    vote. HIVOTO-XGBoost is accepted as provenance but never enters the vote.

    Args:
        predictions: One result per reference method present, keyed by stable
            method identifier. Under ``require_full_set``, every required
            method must be present; otherwise any non-empty subset of the
            allowed methods is accepted, and an absent method simply does not
            vote — never treated as abstaining, which it did not do.
        require_full_set: ``reference_v1``'s own completeness requirement.
            ``False`` is ``reference_partial_v1`` (ADR-0051).

    Returns:
        An immutable decision with complete pooled vote and override evidence.

    Raises:
        ReferenceAggregationError: If a required method is absent while
            ``require_full_set``, or an unknown method is supplied.
    """
    supplied_methods = set(predictions)
    missing_methods = (
        sorted(set(REFERENCE_REQUIRED_METHODS) - supplied_methods) if require_full_set else []
    )
    unknown_methods = sorted(supplied_methods - _ALLOWED_METHODS)
    if missing_methods or unknown_methods:
        problems: list[str] = []
        if missing_methods:
            problems.append(f"missing required methods: {', '.join(missing_methods)}")
        if unknown_methods:
            problems.append(f"unknown methods: {', '.join(unknown_methods)}")
        raise ReferenceAggregationError("; ".join(problems))

    pooled_labels = [
        label
        for method_name in REFERENCE_POOLED_METHODS
        if (prediction := predictions.get(method_name)) is not None
        and (label := _successful_label(prediction)) is not None
    ]
    pooled_vote_counts = _count_votes(pooled_labels)
    parenthetical_prediction = predictions.get("parenthetical_qualifier")
    parenthetical_label = (
        _successful_label(parenthetical_prediction)
        if parenthetical_prediction is not None
        else None
    )
    gnd_prediction = predictions.get("gnd")
    gnd_label = _successful_label(gnd_prediction) if gnd_prediction is not None else None
    substantive_gnd_label = gnd_label if gnd_label is not CanonicalLabel.unknown else None

    if parenthetical_label is not None:
        comparison_count = len(pooled_labels) + int(substantive_gnd_label is not None)
        agreeing_count = sum(label is parenthetical_label for label in pooled_labels)
        agreeing_count += int(substantive_gnd_label is parenthetical_label)
        return ReferenceAggregationDecision(
            outcome=AggregationOutcome.decided,
            label=parenthetical_label,
            pooled_vote_counts=pooled_vote_counts,
            override_source=OverrideSource.parenthetical_qualifier,
            override_agreeing_count=agreeing_count,
            override_comparison_count=comparison_count,
        )

    if substantive_gnd_label is not None:
        return ReferenceAggregationDecision(
            outcome=AggregationOutcome.decided,
            label=substantive_gnd_label,
            pooled_vote_counts=pooled_vote_counts,
            override_source=OverrideSource.gnd,
            override_agreeing_count=sum(label is substantive_gnd_label for label in pooled_labels),
            override_comparison_count=len(pooled_labels),
        )

    if not pooled_labels:
        return ReferenceAggregationDecision(
            outcome=AggregationOutcome.no_data,
            label=None,
            pooled_vote_counts=pooled_vote_counts,
        )

    maximum_count = max(pooled_vote_counts.for_label(label) for label in CanonicalLabel)
    top_labels = tuple(
        label for label in CanonicalLabel if pooled_vote_counts.for_label(label) == maximum_count
    )
    if len(top_labels) == 1:
        return ReferenceAggregationDecision(
            outcome=AggregationOutcome.decided,
            label=top_labels[0],
            pooled_vote_counts=pooled_vote_counts,
        )

    substantive_top_labels = tuple(
        label for label in top_labels if label is not CanonicalLabel.unknown
    )
    if CanonicalLabel.unknown in top_labels and len(substantive_top_labels) == 1:
        return ReferenceAggregationDecision(
            outcome=AggregationOutcome.decided,
            label=substantive_top_labels[0],
            pooled_vote_counts=pooled_vote_counts,
        )

    tied_labels = substantive_top_labels if substantive_top_labels else top_labels
    return ReferenceAggregationDecision(
        outcome=AggregationOutcome.unresolved_tie,
        label=None,
        pooled_vote_counts=pooled_vote_counts,
        tied_labels=tied_labels,
    )


def _successful_label(prediction: PredictionResult) -> CanonicalLabel | None:
    if prediction.status is PredictionStatus.success:
        return prediction.label
    return None


def _count_votes(labels: list[CanonicalLabel]) -> VoteCounts:
    counts = Counter(labels)
    return VoteCounts(
        male=counts[CanonicalLabel.male],
        female=counts[CanonicalLabel.female],
        unknown=counts[CanonicalLabel.unknown],
        institution=counts[CanonicalLabel.institution],
    )
