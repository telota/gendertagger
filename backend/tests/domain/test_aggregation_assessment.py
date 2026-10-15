from __future__ import annotations

import pytest

from gendertagger.domain.aggregation import REFERENCE_REQUIRED_METHODS
from gendertagger.domain.aggregation_assessment import (
    ReferenceAssessmentError,
    assess_reference_predictions,
)
from gendertagger.models.aggregation import AggregationOutcome, OverrideSource, VoteCounts
from gendertagger.models.classification import (
    AgreementTier,
    CanonicalLabel,
    CertaintyTier,
    LlmSelfReportedCertainty,
    PredictionResult,
    PredictionStatus,
)

pytestmark = [pytest.mark.unit, pytest.mark.scientific]


def _success(
    label: CanonicalLabel,
    *,
    self_reported_certainty: LlmSelfReportedCertainty | None = None,
) -> PredictionResult:
    metadata = (
        {"self_reported_certainty": self_reported_certainty.value}
        if self_reported_certainty is not None
        else {}
    )
    return PredictionResult(
        label=label,
        status=PredictionStatus.success,
        metadata=metadata,
    )


def _complete_predictions(
    **overrides: PredictionResult,
) -> dict[str, PredictionResult]:
    predictions = {
        method_name: PredictionResult(label=None, status=PredictionStatus.abstain)
        for method_name in REFERENCE_REQUIRED_METHODS
    }
    predictions.update(overrides)
    return predictions


@pytest.mark.parametrize(
    (
        "agreeing_labels",
        "disagreeing_labels",
        "expected_score",
        "expected_agreement",
        "expected_certainty",
    ),
    [
        (4, 0, 1.0, AgreementTier.unanimous, CertaintyTier.high),
        (3, 1, 0.75, AgreementTier.strong_majority, CertaintyTier.high),
        (2, 1, 0.667, AgreementTier.weak_majority, CertaintyTier.low),
    ],
)
def test_pooled_agreement_and_certainty_boundaries(
    agreeing_labels: int,
    disagreeing_labels: int,
    expected_score: float,
    expected_agreement: AgreementTier,
    expected_certainty: CertaintyTier,
) -> None:
    method_names = (
        "gender_guesser",
        "wiki_gendersort",
        "hivoto",
        "nomquamgender",
    )
    predictions = _complete_predictions()
    for method_name in method_names[:agreeing_labels]:
        predictions[method_name] = _success(CanonicalLabel.female)
    for method_name in method_names[agreeing_labels : agreeing_labels + disagreeing_labels]:
        predictions[method_name] = _success(CanonicalLabel.male)

    result = assess_reference_predictions(predictions)

    assert result.agreement_score == expected_score
    assert result.agreement_tier is expected_agreement
    assert result.certainty_tier is expected_certainty


def test_unique_half_plurality_is_weak_majority_and_low_certainty() -> None:
    predictions = _complete_predictions(
        gender_guesser=_success(CanonicalLabel.female),
        wiki_gendersort=_success(CanonicalLabel.female),
        hivoto=_success(CanonicalLabel.male),
        nomquamgender=_success(CanonicalLabel.unknown),
    )

    result = assess_reference_predictions(predictions)

    assert result.label is CanonicalLabel.female
    assert result.agreement_score == 0.5
    assert result.agreement_tier is AgreementTier.weak_majority
    assert result.certainty_tier is CertaintyTier.low


def test_unique_plurality_below_half_has_no_consensus_and_is_contested() -> None:
    predictions = _complete_predictions(
        gender_guesser=_success(CanonicalLabel.female),
        wiki_gendersort=_success(CanonicalLabel.female),
        hivoto=_success(CanonicalLabel.male),
        nomquamgender=_success(CanonicalLabel.unknown),
        local_llm=_success(
            CanonicalLabel.institution,
            self_reported_certainty=LlmSelfReportedCertainty.high,
        ),
    )

    result = assess_reference_predictions(predictions)

    assert result.label is CanonicalLabel.female
    assert result.agreement_score == 0.4
    assert result.agreement_tier is AgreementTier.no_consensus
    assert result.certainty_tier is CertaintyTier.contested


def test_unresolved_tie_keeps_top_share_but_forces_contested_assessment() -> None:
    predictions = _complete_predictions(
        gender_guesser=_success(CanonicalLabel.male),
        wiki_gendersort=_success(CanonicalLabel.female),
    )

    result = assess_reference_predictions(predictions)

    assert result.outcome is AggregationOutcome.unresolved_tie
    assert result.label is None
    assert result.tied_labels == (CanonicalLabel.male, CanonicalLabel.female)
    assert result.agreement_score == 0.5
    assert result.agreement_tier is AgreementTier.no_consensus
    assert result.certainty_tier is CertaintyTier.contested


def test_three_way_unresolved_tie_has_one_third_agreement() -> None:
    predictions = _complete_predictions(
        gender_guesser=_success(CanonicalLabel.male),
        wiki_gendersort=_success(CanonicalLabel.female),
        local_llm=_success(
            CanonicalLabel.institution,
            self_reported_certainty=LlmSelfReportedCertainty.high,
        ),
    )

    result = assess_reference_predictions(predictions)

    assert result.agreement_score == 0.333
    assert result.agreement_tier is AgreementTier.no_consensus
    assert result.certainty_tier is CertaintyTier.contested


def test_authority_override_with_comparators_uses_support_share_and_high_certainty() -> None:
    predictions = _complete_predictions(
        gnd=_success(CanonicalLabel.female),
        gender_guesser=_success(CanonicalLabel.female),
        wiki_gendersort=_success(CanonicalLabel.male),
        hivoto=_success(CanonicalLabel.male),
        nomquamgender=_success(CanonicalLabel.male),
    )

    result = assess_reference_predictions(predictions)

    assert result.override_source is OverrideSource.gnd
    assert result.override_agreeing_count == 1
    assert result.override_comparison_count == 4
    assert result.agreement_score == 0.25
    assert result.agreement_tier is AgreementTier.no_consensus
    assert result.certainty_tier is CertaintyTier.high


def test_authority_override_without_comparator_is_single_rater_but_high_certainty() -> None:
    result = assess_reference_predictions(
        _complete_predictions(parenthetical_qualifier=_success(CanonicalLabel.female))
    )

    assert result.override_source is OverrideSource.parenthetical_qualifier
    assert result.agreement_score == 1.0
    assert result.agreement_tier is AgreementTier.single_rater
    assert result.certainty_tier is CertaintyTier.high


def test_authority_override_with_all_comparators_agreeing_is_unanimous() -> None:
    predictions = _complete_predictions(
        gnd=_success(CanonicalLabel.male),
        gender_guesser=_success(CanonicalLabel.male),
        wiki_gendersort=_success(CanonicalLabel.male),
    )

    result = assess_reference_predictions(predictions)

    assert result.agreement_score == 1.0
    assert result.agreement_tier is AgreementTier.unanimous
    assert result.certainty_tier is CertaintyTier.high


@pytest.mark.parametrize(
    ("self_reported_certainty", "expected_certainty"),
    [
        (LlmSelfReportedCertainty.high, CertaintyTier.single),
        (LlmSelfReportedCertainty.low, CertaintyTier.uncertain),
        (LlmSelfReportedCertainty.uncertain, CertaintyTier.uncertain),
    ],
)
def test_lone_llm_certainty_uses_typed_self_report(
    self_reported_certainty: LlmSelfReportedCertainty,
    expected_certainty: CertaintyTier,
) -> None:
    result = assess_reference_predictions(
        _complete_predictions(
            local_llm=_success(
                CanonicalLabel.unknown,
                self_reported_certainty=self_reported_certainty,
            )
        )
    )

    assert result.pooled_vote_counts == VoteCounts(unknown=1)
    assert result.agreement_score == 1.0
    assert result.agreement_tier is AgreementTier.single_rater
    assert result.certainty_tier is expected_certainty


def test_lone_non_llm_voter_is_conservatively_uncertain() -> None:
    result = assess_reference_predictions(
        _complete_predictions(gender_guesser=_success(CanonicalLabel.male))
    )

    assert result.agreement_score == 1.0
    assert result.agreement_tier is AgreementTier.single_rater
    assert result.certainty_tier is CertaintyTier.uncertain


@pytest.mark.parametrize(
    "metadata", [{}, {"self_reported_certainty": 1}, {"self_reported_certainty": "HIGH"}]
)
def test_lone_llm_requires_valid_typed_self_report(metadata: dict[str, object]) -> None:
    prediction = PredictionResult(
        label=CanonicalLabel.female,
        status=PredictionStatus.success,
        metadata=metadata,
    )

    with pytest.raises(ReferenceAssessmentError, match="self_reported_certainty"):
        assess_reference_predictions(_complete_predictions(local_llm=prediction))


def test_no_vote_has_no_score_and_no_data_tiers() -> None:
    result = assess_reference_predictions(_complete_predictions())

    assert result.outcome is AggregationOutcome.no_data
    assert result.label is None
    assert result.agreement_score is None
    assert result.agreement_tier is AgreementTier.no_answer
    assert result.certainty_tier is CertaintyTier.no_data


def test_partial_strategy_lone_voter_is_found_without_the_other_eight_present() -> None:
    # ADR-0051: unlike `_complete_predictions()`, nothing pads the other eight reference methods
    # in as an abstain here — a `reference_partial_v1` selection simply never has entries for
    # method it did not select, and finding the lone voter must not assume otherwise.
    result = assess_reference_predictions(
        {"gender_guesser": _success(CanonicalLabel.male)},
        require_full_set=False,
    )

    assert result.agreement_score == 1.0
    assert result.agreement_tier is AgreementTier.single_rater
    assert result.certainty_tier is CertaintyTier.uncertain


def test_partial_strategy_lone_llm_voter_still_requires_its_self_report() -> None:
    prediction = PredictionResult(label=CanonicalLabel.female, status=PredictionStatus.success)

    with pytest.raises(ReferenceAssessmentError, match="self_reported_certainty"):
        assess_reference_predictions({"local_llm": prediction}, require_full_set=False)
