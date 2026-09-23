import pytest

from gendertagger.domain.review_triage import (
    AUTHORITY_CONFLICT_TRIAGE_RANK,
    CERTAINTY_TIER_TRIAGE_RANKS,
    PREDICTION_ERROR_TRIAGE_RANK,
    RESIDUAL_TRIAGE_RANK,
    review_triage_rank,
)
from gendertagger.models.classification import CertaintyTier


def test_triage_ranks_order_uncertainty_before_confident_records() -> None:
    ranks = [
        review_triage_rank(
            certainty_tier=certainty_tier,
            has_authority_conflict=False,
            has_prediction_error=False,
        )
        for certainty_tier in (
            CertaintyTier.contested,
            CertaintyTier.low,
            CertaintyTier.uncertain,
            CertaintyTier.single,
            CertaintyTier.no_data,
            CertaintyTier.high,
        )
    ]

    assert ranks == sorted(ranks)
    assert len(set(ranks)) == len(ranks)
    assert ranks[-1] == RESIDUAL_TRIAGE_RANK


@pytest.mark.parametrize("certainty_tier", list(CertaintyTier))
def test_every_certainty_tier_has_a_defined_rank(certainty_tier: CertaintyTier) -> None:
    rank = review_triage_rank(
        certainty_tier=certainty_tier,
        has_authority_conflict=False,
        has_prediction_error=False,
    )

    if certainty_tier is CertaintyTier.high:
        assert certainty_tier not in CERTAINTY_TIER_TRIAGE_RANKS
        assert rank == RESIDUAL_TRIAGE_RANK
    else:
        assert rank == CERTAINTY_TIER_TRIAGE_RANKS[certainty_tier]


def test_flags_prioritize_confident_records_without_outranking_certainty_tiers() -> None:
    conflict_rank = review_triage_rank(
        certainty_tier=CertaintyTier.high,
        has_authority_conflict=True,
        has_prediction_error=False,
    )
    error_rank = review_triage_rank(
        certainty_tier=CertaintyTier.high,
        has_authority_conflict=False,
        has_prediction_error=True,
    )
    contested_with_error_rank = review_triage_rank(
        certainty_tier=CertaintyTier.contested,
        has_authority_conflict=True,
        has_prediction_error=True,
    )

    assert conflict_rank == AUTHORITY_CONFLICT_TRIAGE_RANK
    assert error_rank == PREDICTION_ERROR_TRIAGE_RANK
    assert conflict_rank < error_rank < RESIDUAL_TRIAGE_RANK
    assert contested_with_error_rank == CERTAINTY_TIER_TRIAGE_RANKS[CertaintyTier.contested]
