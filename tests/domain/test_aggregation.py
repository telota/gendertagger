from __future__ import annotations

import pytest

from gendertagger.domain.aggregation import (
    REFERENCE_AUTHORITY_METHODS,
    REFERENCE_IGNORED_METHODS,
    REFERENCE_POOLED_METHODS,
    REFERENCE_REQUIRED_METHODS,
    ReferenceAggregationError,
    aggregate_reference_predictions,
)
from gendertagger.models.aggregation import AggregationOutcome, OverrideSource, VoteCounts
from gendertagger.models.classification import (
    CanonicalLabel,
    PredictionResult,
    PredictionStatus,
)

pytestmark = [pytest.mark.unit, pytest.mark.scientific]


def _success(
    label: CanonicalLabel,
    *,
    method_confidence: float | None = None,
) -> PredictionResult:
    return PredictionResult(
        label=label,
        status=PredictionStatus.success,
        method_confidence=method_confidence,
    )


def _no_vote(status: PredictionStatus = PredictionStatus.abstain) -> PredictionResult:
    return PredictionResult(label=None, status=status)


def _complete_predictions(
    **overrides: PredictionResult,
) -> dict[str, PredictionResult]:
    predictions = {method_name: _no_vote() for method_name in REFERENCE_REQUIRED_METHODS}
    predictions.update(overrides)
    return predictions


def test_reference_method_sets_are_exact_and_exclude_experimental_vote() -> None:
    assert REFERENCE_AUTHORITY_METHODS == ("parenthetical_qualifier", "gnd")
    assert REFERENCE_POOLED_METHODS == (
        "gender_guesser",
        "wiki_gendersort",
        "hivoto",
        "nomquamgender",
        "hf_distilbert",
        "hf_genderize",
        "local_llm",
    )
    assert REFERENCE_IGNORED_METHODS == ("hivoto_xgboost",)
    assert REFERENCE_REQUIRED_METHODS == REFERENCE_AUTHORITY_METHODS + REFERENCE_POOLED_METHODS


def test_parenthetical_override_has_first_priority_and_records_support() -> None:
    predictions = _complete_predictions(
        parenthetical_qualifier=_success(CanonicalLabel.female),
        gnd=_success(CanonicalLabel.female),
        gender_guesser=_success(CanonicalLabel.female),
        wiki_gendersort=_success(CanonicalLabel.male),
        hivoto=_success(CanonicalLabel.unknown),
    )

    decision = aggregate_reference_predictions(predictions)

    assert decision.outcome is AggregationOutcome.decided
    assert decision.label is CanonicalLabel.female
    assert decision.override_source is OverrideSource.parenthetical_qualifier
    assert decision.override_agreeing_count == 2
    assert decision.override_comparison_count == 4
    assert decision.pooled_vote_counts == VoteCounts(male=1, female=1, unknown=1)


def test_parenthetical_successful_unknown_is_an_override() -> None:
    predictions = _complete_predictions(
        parenthetical_qualifier=_success(CanonicalLabel.unknown),
        gnd=_success(CanonicalLabel.male),
        gender_guesser=_success(CanonicalLabel.male),
    )

    decision = aggregate_reference_predictions(predictions)

    assert decision.label is CanonicalLabel.unknown
    assert decision.override_source is OverrideSource.parenthetical_qualifier
    assert decision.override_agreeing_count == 0
    assert decision.override_comparison_count == 2


def test_parenthetical_support_excludes_non_substantive_gnd_unknown() -> None:
    predictions = _complete_predictions(
        parenthetical_qualifier=_success(CanonicalLabel.male),
        gnd=_success(CanonicalLabel.unknown),
        gender_guesser=_success(CanonicalLabel.male),
    )

    decision = aggregate_reference_predictions(predictions)

    assert decision.override_agreeing_count == 1
    assert decision.override_comparison_count == 1


def test_gnd_substantive_result_overrides_pooled_majority() -> None:
    predictions = _complete_predictions(
        gnd=_success(CanonicalLabel.male),
        gender_guesser=_success(CanonicalLabel.female),
        wiki_gendersort=_success(CanonicalLabel.female),
        hivoto=_success(CanonicalLabel.male),
        nomquamgender=_success(CanonicalLabel.unknown),
    )

    decision = aggregate_reference_predictions(predictions)

    assert decision.outcome is AggregationOutcome.decided
    assert decision.label is CanonicalLabel.male
    assert decision.override_source is OverrideSource.gnd
    assert decision.override_agreeing_count == 1
    assert decision.override_comparison_count == 4
    assert decision.pooled_vote_counts == VoteCounts(male=1, female=2, unknown=1)


def test_gnd_unknown_falls_through_to_pooled_vote() -> None:
    predictions = _complete_predictions(
        gnd=_success(CanonicalLabel.unknown),
        gender_guesser=_success(CanonicalLabel.female),
        wiki_gendersort=_success(CanonicalLabel.female),
        hivoto=_success(CanonicalLabel.male),
    )

    decision = aggregate_reference_predictions(predictions)

    assert decision.label is CanonicalLabel.female
    assert decision.override_source is None
    assert decision.pooled_vote_counts == VoteCounts(male=1, female=2)


def test_unweighted_vote_ignores_method_confidence() -> None:
    predictions = _complete_predictions(
        gender_guesser=_success(CanonicalLabel.male, method_confidence=0.01),
        wiki_gendersort=_success(CanonicalLabel.male, method_confidence=0.01),
        hivoto=_success(CanonicalLabel.female, method_confidence=1.0),
    )

    decision = aggregate_reference_predictions(predictions)

    assert decision.label is CanonicalLabel.male
    assert decision.pooled_vote_counts == VoteCounts(male=2, female=1)


def test_unknown_tied_with_one_substantive_label_loses_tie() -> None:
    predictions = _complete_predictions(
        gender_guesser=_success(CanonicalLabel.unknown),
        wiki_gendersort=_success(CanonicalLabel.unknown),
        hivoto=_success(CanonicalLabel.institution),
        local_llm=_success(CanonicalLabel.institution),
    )

    decision = aggregate_reference_predictions(predictions)

    assert decision.outcome is AggregationOutcome.decided
    assert decision.label is CanonicalLabel.institution
    assert decision.tied_labels == ()


def test_unknown_is_removed_from_multi_substantive_top_tie() -> None:
    predictions = _complete_predictions(
        gender_guesser=_success(CanonicalLabel.unknown),
        wiki_gendersort=_success(CanonicalLabel.unknown),
        hivoto=_success(CanonicalLabel.male),
        nomquamgender=_success(CanonicalLabel.male),
        hf_distilbert=_success(CanonicalLabel.female),
        hf_genderize=_success(CanonicalLabel.female),
    )

    decision = aggregate_reference_predictions(predictions)

    assert decision.outcome is AggregationOutcome.unresolved_tie
    assert decision.label is None
    assert decision.tied_labels == (CanonicalLabel.male, CanonicalLabel.female)
    assert decision.pooled_vote_counts == VoteCounts(male=2, female=2, unknown=2)


def test_substantive_tie_is_transparent_and_deterministic() -> None:
    predictions = _complete_predictions(
        gender_guesser=_success(CanonicalLabel.female),
        wiki_gendersort=_success(CanonicalLabel.male),
    )

    decision = aggregate_reference_predictions(predictions)

    assert decision.outcome is AggregationOutcome.unresolved_tie
    assert decision.label is None
    assert decision.tied_labels == (CanonicalLabel.male, CanonicalLabel.female)


def test_single_unknown_vote_is_a_substantive_unknown_decision() -> None:
    decision = aggregate_reference_predictions(
        _complete_predictions(local_llm=_success(CanonicalLabel.unknown))
    )

    assert decision.outcome is AggregationOutcome.decided
    assert decision.label is CanonicalLabel.unknown
    assert decision.pooled_vote_counts == VoteCounts(unknown=1)


def test_abstentions_and_errors_do_not_cast_votes() -> None:
    predictions = _complete_predictions(
        gender_guesser=_no_vote(PredictionStatus.error),
        wiki_gendersort=_no_vote(PredictionStatus.abstain),
    )

    decision = aggregate_reference_predictions(predictions)

    assert decision.outcome is AggregationOutcome.no_data
    assert decision.label is None
    assert decision.pooled_vote_counts.total == 0


def test_experimental_hivoto_xgboost_is_accepted_but_ignored() -> None:
    predictions = _complete_predictions(
        gender_guesser=_success(CanonicalLabel.female),
        hivoto_xgboost=_success(CanonicalLabel.male),
    )

    decision = aggregate_reference_predictions(predictions)

    assert decision.label is CanonicalLabel.female
    assert decision.pooled_vote_counts == VoteCounts(female=1)


def test_missing_reference_method_fails_clearly() -> None:
    predictions = _complete_predictions()
    del predictions["local_llm"]

    with pytest.raises(ReferenceAggregationError, match="missing required methods: local_llm"):
        aggregate_reference_predictions(predictions)


def test_unknown_method_fails_clearly() -> None:
    predictions = _complete_predictions(typo_method=_no_vote())

    with pytest.raises(ReferenceAggregationError, match="unknown methods: typo_method"):
        aggregate_reference_predictions(predictions)
