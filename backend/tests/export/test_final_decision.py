from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from gendertagger.export.final_decision import resolve_final_decision
from gendertagger.models.aggregation import AggregatedResult, AggregationOutcome, VoteCounts
from gendertagger.models.classification import AgreementTier, CanonicalLabel, CertaintyTier
from gendertagger.models.export import LabelSourcePolicy
from gendertagger.models.review import Annotation, ReviewAction

pytestmark = [pytest.mark.unit, pytest.mark.scientific]

NOW = datetime(2026, 8, 15, 12, 0, tzinfo=UTC)
HUMAN_RESP_ID = "#editor"


def _aggregated_result(
    *,
    label: CanonicalLabel | None,
    certainty_tier: CertaintyTier = CertaintyTier.high,
) -> AggregatedResult:
    outcome = AggregationOutcome.no_data if label is None else AggregationOutcome.decided
    return AggregatedResult(
        id=uuid4(),
        aggregation_execution_id=uuid4(),
        person_record_id=uuid4(),
        outcome=outcome,
        label=label,
        pooled_vote_counts=VoteCounts() if label is None else VoteCounts(male=7),
        agreement_score=None if label is None else 1.0,
        agreement_tier=AgreementTier.no_answer if label is None else AgreementTier.unanimous,
        certainty_tier=CertaintyTier.no_data if label is None else certainty_tier,
        created_at=NOW,
    )


def _annotation(*, action: ReviewAction, label: CanonicalLabel | None) -> Annotation:
    return Annotation(
        id=uuid4(),
        snapshot_id=uuid4(),
        person_record_id=uuid4(),
        tei_id="p1",
        action=action,
        label=label,
        reviewer_user_id=uuid4(),
        resulting_revision=1,
        created_at=NOW,
    )


def test_machine_policy_ignores_annotations_even_when_present() -> None:
    result = _aggregated_result(label=CanonicalLabel.male)
    annotation = _annotation(action=ReviewAction.correct, label=CanonicalLabel.female)

    record = resolve_final_decision(
        tei_id="p1",
        source_member_name=None,
        aggregated_result=result,
        annotation=annotation,
        label_source_policy=LabelSourcePolicy.machine_aggregation,
        human_resp_id=HUMAN_RESP_ID,
    )

    assert record.label is CanonicalLabel.male
    assert record.is_human_reviewed is False
    assert record.resp == "#gendertagger"
    assert record.cert == "high"


def test_human_overrides_policy_prefers_a_correction() -> None:
    result = _aggregated_result(label=CanonicalLabel.male, certainty_tier=CertaintyTier.low)
    annotation = _annotation(action=ReviewAction.correct, label=CanonicalLabel.female)

    record = resolve_final_decision(
        tei_id="p1",
        source_member_name=None,
        aggregated_result=result,
        annotation=annotation,
        label_source_policy=LabelSourcePolicy.human_overrides,
        human_resp_id=HUMAN_RESP_ID,
    )

    assert record.label is CanonicalLabel.female
    assert record.is_human_reviewed is True
    assert record.resp == HUMAN_RESP_ID
    assert record.cert == "high"
    # The machine's own tier is preserved unmodified alongside the override.
    assert record.certainty_tier is CertaintyTier.low


def test_a_deferred_annotation_never_overrides_the_machine_label() -> None:
    result = _aggregated_result(label=CanonicalLabel.male)
    annotation = _annotation(action=ReviewAction.defer, label=None)

    record = resolve_final_decision(
        tei_id="p1",
        source_member_name=None,
        aggregated_result=result,
        annotation=annotation,
        label_source_policy=LabelSourcePolicy.human_overrides,
        human_resp_id=HUMAN_RESP_ID,
    )

    assert record.label is CanonicalLabel.male
    assert record.is_human_reviewed is False
    assert record.resp == "#gendertagger"


def test_no_annotation_falls_back_to_the_aggregated_result() -> None:
    result = _aggregated_result(label=CanonicalLabel.female)

    record = resolve_final_decision(
        tei_id="p1",
        source_member_name=None,
        aggregated_result=result,
        annotation=None,
        label_source_policy=LabelSourcePolicy.human_overrides,
        human_resp_id=HUMAN_RESP_ID,
    )

    assert record.label is CanonicalLabel.female
    assert record.is_human_reviewed is False


def test_a_no_data_result_has_no_evidence_resp_or_cert() -> None:
    result = _aggregated_result(label=None)

    record = resolve_final_decision(
        tei_id="p1",
        source_member_name=None,
        aggregated_result=result,
        annotation=None,
        label_source_policy=LabelSourcePolicy.machine_aggregation,
        human_resp_id=HUMAN_RESP_ID,
    )

    assert record.label is None
    assert record.evidence is None
    assert record.resp is None
    assert record.cert is None
    assert record.is_human_reviewed is False
