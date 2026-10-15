"""Pure agreement and certainty assessment for reference aggregation."""

from __future__ import annotations

from collections.abc import Mapping
from typing import cast

from gendertagger.domain.aggregation import (
    REFERENCE_POOLED_METHODS,
    aggregate_reference_predictions,
)
from gendertagger.models.aggregation import (
    AggregationOutcome,
    ReferenceAggregationDecision,
    ReferenceAggregationResult,
)
from gendertagger.models.classification import (
    AgreementTier,
    CanonicalLabel,
    CertaintyTier,
    LlmSelfReportedCertainty,
    PredictionResult,
    PredictionStatus,
)

_AGREEMENT_DECIMAL_PLACES = 3
# ADR-0009: agreement tiers and pooled-vote certainty share these score thresholds.
_STRONG_MAJORITY_THRESHOLD = 0.75
_WEAK_MAJORITY_THRESHOLD = 0.50


class ReferenceAssessmentError(ValueError):
    """Raised when evidence required for certainty assignment is invalid."""


def assess_reference_predictions(
    predictions: Mapping[str, PredictionResult],
    *,
    require_full_set: bool = True,
) -> ReferenceAggregationResult:
    """Run reference aggregation and derive its agreement and certainty.

    Args:
        predictions: Per-person reference method results accepted by
            :func:`aggregate_reference_predictions`.
        require_full_set: Forwarded to :func:`aggregate_reference_predictions`
            (ADR-0051).

    Returns:
        A fully assessed immutable reference aggregation result.

    Raises:
        ReferenceAssessmentError: If a lone local-LLM vote lacks its required
            typed self-reported certainty metadata.
        ReferenceAggregationError: If the reference prediction set is invalid.
    """
    prediction_snapshot = dict(predictions)
    decision = aggregate_reference_predictions(
        prediction_snapshot, require_full_set=require_full_set
    )
    agreement_score, agreement_tier = calculate_reference_agreement(decision)
    certainty_tier = _assign_reference_certainty(
        decision,
        prediction_snapshot,
        agreement_score,
    )
    return ReferenceAggregationResult(
        outcome=decision.outcome,
        label=decision.label,
        pooled_vote_counts=decision.pooled_vote_counts,
        tied_labels=decision.tied_labels,
        override_source=decision.override_source,
        override_agreeing_count=decision.override_agreeing_count,
        override_comparison_count=decision.override_comparison_count,
        agreement_score=agreement_score,
        agreement_tier=agreement_tier,
        certainty_tier=certainty_tier,
    )


def calculate_reference_agreement(
    decision: ReferenceAggregationDecision,
) -> tuple[float | None, AgreementTier]:
    """Derive the versioned per-record agreement score and tier.

    Scores are rounded to three decimal places to reproduce the reference
    output. An unresolved tie retains its maximum vote share but is always
    categorized as no consensus.
    """
    if decision.outcome is AggregationOutcome.no_data:
        return None, AgreementTier.no_answer

    if decision.override_source is not None:
        agreeing_count = cast(int, decision.override_agreeing_count)
        comparison_count = cast(int, decision.override_comparison_count)
        if comparison_count == 0:
            return 1.0, AgreementTier.single_rater
        score = _rounded_share(agreeing_count, comparison_count)
        return score, _agreement_tier_for_score(score)

    pooled_vote_count = decision.pooled_vote_counts.total
    if pooled_vote_count == 1:
        return 1.0, AgreementTier.single_rater

    if decision.outcome is AggregationOutcome.unresolved_tie:
        highest_count = max(
            decision.pooled_vote_counts.for_label(label) for label in decision.tied_labels
        )
        return (
            _rounded_share(highest_count, pooled_vote_count),
            AgreementTier.no_consensus,
        )

    label = cast(CanonicalLabel, decision.label)
    score = _rounded_share(
        decision.pooled_vote_counts.for_label(label),
        pooled_vote_count,
    )
    return score, _agreement_tier_for_score(score)


def _assign_reference_certainty(
    decision: ReferenceAggregationDecision,
    predictions: Mapping[str, PredictionResult],
    agreement_score: float | None,
) -> CertaintyTier:
    if decision.outcome is AggregationOutcome.no_data:
        return CertaintyTier.no_data
    if decision.override_source is not None:
        return CertaintyTier.high
    if decision.outcome is AggregationOutcome.unresolved_tie:
        return CertaintyTier.contested

    pooled_vote_count = decision.pooled_vote_counts.total
    if pooled_vote_count == 1:
        lone_method_name = _find_lone_pooled_voter(predictions)
        if lone_method_name != "local_llm":
            return CertaintyTier.uncertain
        self_reported_certainty = _parse_llm_self_reported_certainty(predictions[lone_method_name])
        if self_reported_certainty is LlmSelfReportedCertainty.high:
            return CertaintyTier.single
        return CertaintyTier.uncertain

    score = cast(float, agreement_score)
    if score >= _STRONG_MAJORITY_THRESHOLD:
        return CertaintyTier.high
    if score >= _WEAK_MAJORITY_THRESHOLD:
        return CertaintyTier.low
    return CertaintyTier.contested


def _find_lone_pooled_voter(predictions: Mapping[str, PredictionResult]) -> str:
    return next(
        method_name
        for method_name in REFERENCE_POOLED_METHODS
        if (prediction := predictions.get(method_name)) is not None
        and prediction.status is PredictionStatus.success
    )


def _parse_llm_self_reported_certainty(
    prediction: PredictionResult,
) -> LlmSelfReportedCertainty:
    raw_certainty = prediction.metadata.get("self_reported_certainty")
    if not isinstance(raw_certainty, str):
        msg = "lone local_llm prediction requires string self_reported_certainty metadata"
        raise ReferenceAssessmentError(msg)
    try:
        return LlmSelfReportedCertainty(raw_certainty)
    except ValueError as error:
        msg = f"invalid local_llm self_reported_certainty: {raw_certainty!r}"
        raise ReferenceAssessmentError(msg) from error


def _rounded_share(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, _AGREEMENT_DECIMAL_PLACES)


def _agreement_tier_for_score(score: float) -> AgreementTier:
    if score == 1.0:
        return AgreementTier.unanimous
    if score >= _STRONG_MAJORITY_THRESHOLD:
        return AgreementTier.strong_majority
    if score >= _WEAK_MAJORITY_THRESHOLD:
        return AgreementTier.weak_majority
    return AgreementTier.no_consensus
