"""Versioned uncertainty-first ordering policy for the review queue.

The policy assigns one small integer rank to a review candidate so that the
records needing editorial attention first appear first. Every input is
immutable for a completed aggregation, which keeps keyset pagination stable
while reviewers annotate concurrently. Mutable review state, in particular the
workflow state, must never enter this rank.
"""

from collections.abc import Mapping

from gendertagger.models.classification import CertaintyTier

REVIEW_TRIAGE_POLICY = "review_triage_v1"

CERTAINTY_TIER_TRIAGE_RANKS: Mapping[CertaintyTier, int] = {
    CertaintyTier.contested: 0,
    CertaintyTier.low: 1,
    CertaintyTier.uncertain: 2,
    CertaintyTier.single: 3,
    CertaintyTier.no_data: 4,
}
"""Ranks for the certainty tiers that carry their own triage priority.

``CertaintyTier.high`` deliberately has no entry: a high-certainty record is
only prioritized through the authority-conflict or prediction-error ranks.
"""

AUTHORITY_CONFLICT_TRIAGE_RANK = 5
PREDICTION_ERROR_TRIAGE_RANK = 6
RESIDUAL_TRIAGE_RANK = 7


def review_triage_rank(
    *,
    certainty_tier: CertaintyTier,
    has_authority_conflict: bool,
    has_prediction_error: bool,
) -> int:
    """Return the ``review_triage_v1`` rank of one review candidate.

    A certainty tier that carries its own priority wins over both flags, so a
    contested record with a failed method still sorts as contested.

    Args:
        certainty_tier: Reference certainty assigned to the aggregated result.
        has_authority_conflict: Whether an authority override disagrees with at
            least one compared method.
        has_prediction_error: Whether any selected method failed technically for
            this person.

    Returns:
        The rank, where a lower value is reviewed earlier.
    """
    tier_rank = CERTAINTY_TIER_TRIAGE_RANKS.get(certainty_tier)
    if tier_rank is not None:
        return tier_rank
    if has_authority_conflict:
        return AUTHORITY_CONFLICT_TRIAGE_RANK
    if has_prediction_error:
        return PREDICTION_ERROR_TRIAGE_RANK
    return RESIDUAL_TRIAGE_RANK
