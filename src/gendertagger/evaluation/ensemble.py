"""Pure record-level ensemble and human-review metrics."""

from __future__ import annotations

from collections.abc import Sequence

from gendertagger.models.aggregation import AggregatedResult
from gendertagger.models.classification import AgreementTier, CanonicalLabel, CertaintyTier
from gendertagger.models.evaluation import EnsembleMetrics


def compute_ensemble_metrics(
    aggregated_results: Sequence[AggregatedResult],
    *,
    human_reviewed_count: int = 0,
    human_correction_count: int = 0,
) -> EnsembleMetrics:
    """Canonical-label, agreement-tier, and certainty-tier distributions.

    ``canonical_label_distribution`` counts only decided results; an
    unresolved tie or a no-data outcome has no canonical label and is not
    counted there, though it is still counted in the agreement/certainty
    tier distributions (every result has exactly one of each).

    Args:
        aggregated_results: The run's complete AggregatedResult set.
        human_reviewed_count: Reviewed-person count, supplied by the caller
            (derived from ReviewState/Annotation, which this pure function
            does not read).
        human_correction_count: Corrected-person count, supplied by the
            caller.

    Returns:
        The immutable ensemble metrics summary.
    """
    label_distribution: dict[CanonicalLabel, int] = dict.fromkeys(CanonicalLabel, 0)
    agreement_distribution: dict[AgreementTier, int] = dict.fromkeys(AgreementTier, 0)
    certainty_distribution: dict[CertaintyTier, int] = dict.fromkeys(CertaintyTier, 0)

    for result in aggregated_results:
        if result.label is not None:
            label_distribution[result.label] += 1
        agreement_distribution[result.agreement_tier] += 1
        certainty_distribution[result.certainty_tier] += 1

    return EnsembleMetrics(
        canonical_label_distribution=label_distribution,
        agreement_tier_distribution=agreement_distribution,
        certainty_tier_distribution=certainty_distribution,
        human_reviewed_count=human_reviewed_count,
        human_correction_count=human_correction_count,
    )
