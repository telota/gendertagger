from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from gendertagger.evaluation.ensemble import compute_ensemble_metrics
from gendertagger.models.aggregation import AggregatedResult, AggregationOutcome, VoteCounts
from gendertagger.models.classification import AgreementTier, CanonicalLabel, CertaintyTier

pytestmark = [pytest.mark.unit, pytest.mark.scientific]


def _decided(label: CanonicalLabel, *, certainty_tier: CertaintyTier) -> AggregatedResult:
    return AggregatedResult(
        id=uuid4(),
        aggregation_execution_id=uuid4(),
        person_record_id=uuid4(),
        outcome=AggregationOutcome.decided,
        label=label,
        pooled_vote_counts=VoteCounts(**{label.value: 7}),
        agreement_score=1.0,
        agreement_tier=AgreementTier.unanimous,
        certainty_tier=certainty_tier,
        created_at=datetime.now(UTC),
    )


def _unresolved_tie() -> AggregatedResult:
    return AggregatedResult(
        id=uuid4(),
        aggregation_execution_id=uuid4(),
        person_record_id=uuid4(),
        outcome=AggregationOutcome.unresolved_tie,
        label=None,
        pooled_vote_counts=VoteCounts(male=2, female=2),
        tied_labels=(CanonicalLabel.male, CanonicalLabel.female),
        agreement_score=0.5,
        agreement_tier=AgreementTier.no_consensus,
        certainty_tier=CertaintyTier.contested,
        created_at=datetime.now(UTC),
    )


def _no_data() -> AggregatedResult:
    return AggregatedResult(
        id=uuid4(),
        aggregation_execution_id=uuid4(),
        person_record_id=uuid4(),
        outcome=AggregationOutcome.no_data,
        label=None,
        pooled_vote_counts=VoteCounts(),
        agreement_score=None,
        agreement_tier=AgreementTier.no_answer,
        certainty_tier=CertaintyTier.no_data,
        created_at=datetime.now(UTC),
    )


def test_counts_decided_labels_and_every_tier() -> None:
    results = [
        _decided(CanonicalLabel.male, certainty_tier=CertaintyTier.high),
        _decided(CanonicalLabel.male, certainty_tier=CertaintyTier.high),
        _decided(CanonicalLabel.female, certainty_tier=CertaintyTier.high),
        _unresolved_tie(),
        _no_data(),
    ]

    metrics = compute_ensemble_metrics(results)

    assert metrics.canonical_label_distribution == {
        CanonicalLabel.male: 2,
        CanonicalLabel.female: 1,
        CanonicalLabel.unknown: 0,
        CanonicalLabel.institution: 0,
    }
    assert metrics.agreement_tier_distribution[AgreementTier.unanimous] == 3
    assert metrics.agreement_tier_distribution[AgreementTier.no_consensus] == 1
    assert metrics.agreement_tier_distribution[AgreementTier.no_answer] == 1
    assert metrics.certainty_tier_distribution[CertaintyTier.high] == 3
    assert metrics.certainty_tier_distribution[CertaintyTier.contested] == 1
    assert metrics.certainty_tier_distribution[CertaintyTier.no_data] == 1


def test_unresolved_and_no_data_results_are_not_in_the_label_distribution() -> None:
    results = [_unresolved_tie(), _no_data()]

    metrics = compute_ensemble_metrics(results)

    assert sum(metrics.canonical_label_distribution.values()) == 0
    # Every result still lands in exactly one agreement/certainty tier, so the
    # total corpus size remains recoverable even though no label was decided.
    assert sum(metrics.agreement_tier_distribution.values()) == 2
    assert sum(metrics.certainty_tier_distribution.values()) == 2


def test_human_review_counts_pass_through_unmodified() -> None:
    metrics = compute_ensemble_metrics(
        [_decided(CanonicalLabel.male, certainty_tier=CertaintyTier.high)],
        human_reviewed_count=10,
        human_correction_count=3,
    )

    assert metrics.human_reviewed_count == 10
    assert metrics.human_correction_count == 3


def test_empty_results_yield_all_zero_metrics() -> None:
    metrics = compute_ensemble_metrics([])

    assert sum(metrics.canonical_label_distribution.values()) == 0
    assert sum(metrics.agreement_tier_distribution.values()) == 0
    assert sum(metrics.certainty_tier_distribution.values()) == 0
    assert metrics.human_reviewed_count == 0
    assert metrics.human_correction_count == 0
