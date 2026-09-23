from datetime import UTC, datetime
from uuid import UUID

import pytest
from pydantic import ValidationError

from gendertagger.models.aggregation import (
    AggregatedResult,
    AggregationCreateRequest,
    AggregationExecution,
    AggregationExecutionCreate,
    AggregationOutcome,
    AggregationResultWrite,
    ReferenceAggregationResult,
    VoteCounts,
)
from gendertagger.models.classification import AgreementTier, CanonicalLabel, CertaintyTier
from gendertagger.models.lifecycle import AggregationExecutionStatus

RUN_ID = UUID("50000000-0000-0000-0000-000000000001")
EXECUTION_ID = UUID("60000000-0000-0000-0000-000000000001")
SECOND_EXECUTION_ID = UUID("60000000-0000-0000-0000-000000000002")
AGGREGATION_ID = UUID("80000000-0000-0000-0000-000000000001")
RESULT_ID = UUID("90000000-0000-0000-0000-000000000001")
PERSON_ID = UUID("40000000-0000-0000-0000-000000000001")
CREATED_AT = datetime(2026, 8, 13, 10, 0, tzinfo=UTC)


def execution_payload(**overrides: object) -> dict[str, object]:
    command = AggregationExecutionCreate(
        run_id=RUN_ID,
        resolved_config={"minimum_methods": 1},
        method_execution_ids=(EXECUTION_ID, SECOND_EXECUTION_ID),
    )
    payload: dict[str, object] = {
        **command.model_dump(),
        "id": AGGREGATION_ID,
        "config_sha256": command.canonical_config_sha256(),
        "status": AggregationExecutionStatus.pending,
        "started_at": None,
        "finished_at": None,
        "failure_class": None,
        "failure_diagnostic": None,
        "created_at": CREATED_AT,
    }
    payload.update(overrides)
    return payload


def decided_result() -> ReferenceAggregationResult:
    return ReferenceAggregationResult(
        outcome=AggregationOutcome.decided,
        label=CanonicalLabel.female,
        pooled_vote_counts=VoteCounts(female=2),
        tied_labels=(),
        override_source=None,
        override_agreeing_count=None,
        override_comparison_count=None,
        agreement_score=1.0,
        agreement_tier=AgreementTier.unanimous,
        certainty_tier=CertaintyTier.high,
    )


def test_aggregation_create_request_uses_exact_unique_execution_ids() -> None:
    command = AggregationCreateRequest(method_execution_ids=(EXECUTION_ID, SECOND_EXECUTION_ID))

    assert command.model_dump(mode="json") == {
        "strategy": "reference_v1",
        "method_execution_ids": [str(EXECUTION_ID), str(SECOND_EXECUTION_ID)],
    }
    with pytest.raises(ValidationError, match="must not contain duplicates"):
        AggregationCreateRequest(method_execution_ids=(EXECUTION_ID, EXECUTION_ID))


def test_aggregation_execution_requires_unique_method_selection() -> None:
    with pytest.raises(ValidationError, match="must not contain duplicates"):
        AggregationExecutionCreate(
            run_id=RUN_ID,
            method_execution_ids=(EXECUTION_ID, EXECUTION_ID),
        )


def test_aggregation_config_hash_is_key_order_independent() -> None:
    first = AggregationExecutionCreate(
        run_id=RUN_ID,
        resolved_config={"a": 1, "nested": {"enabled": True}},
        method_execution_ids=(EXECUTION_ID,),
    )
    second = AggregationExecutionCreate(
        run_id=RUN_ID,
        resolved_config={"nested": {"enabled": True}, "a": 1},
        method_execution_ids=(EXECUTION_ID,),
    )

    assert first.canonical_config_sha256() == second.canonical_config_sha256()


def test_aggregation_execution_accepts_pending_and_completed_shapes() -> None:
    pending = AggregationExecution.model_validate(execution_payload())
    completed = AggregationExecution.model_validate(
        execution_payload(
            status=AggregationExecutionStatus.completed,
            started_at=CREATED_AT,
            finished_at=CREATED_AT,
        )
    )

    assert pending.status is AggregationExecutionStatus.pending
    assert completed.finished_at == CREATED_AT


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        (
            {"status": AggregationExecutionStatus.completed},
            "terminal aggregation requires finished_at",
        ),
        (
            {"finished_at": CREATED_AT},
            "non-terminal aggregation must not have finished_at",
        ),
        (
            {
                "status": AggregationExecutionStatus.failed,
                "finished_at": CREATED_AT,
            },
            "failed aggregation requires a failure diagnostic",
        ),
        (
            {"failure_class": "ValueError"},
            "only a failed aggregation may have failure details",
        ),
    ],
)
def test_aggregation_execution_rejects_inconsistent_lifecycle_fields(
    overrides: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(ValidationError, match=message):
        AggregationExecution.model_validate(execution_payload(**overrides))


def test_aggregated_result_extends_scientific_result_without_mutation() -> None:
    scientific_result = decided_result()
    write = AggregationResultWrite(
        person_record_id=PERSON_ID,
        result=scientific_result,
        has_prediction_error=True,
        metadata={"strategy": "reference_v1"},
    )
    persisted = AggregatedResult(
        id=RESULT_ID,
        aggregation_execution_id=AGGREGATION_ID,
        person_record_id=PERSON_ID,
        has_prediction_error=write.has_prediction_error,
        metadata=write.metadata,
        created_at=CREATED_AT,
        **scientific_result.model_dump(),
    )

    assert write.result == scientific_result
    assert persisted.label is CanonicalLabel.female
    assert persisted.pooled_vote_counts == VoteCounts(female=2)
    assert persisted.metadata == {"strategy": "reference_v1"}
    assert persisted.has_prediction_error is True
    assert "has_prediction_error" not in scientific_result.model_dump()
