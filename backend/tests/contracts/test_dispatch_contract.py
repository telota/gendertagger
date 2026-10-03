from datetime import UTC, datetime, timedelta, timezone
from uuid import uuid4

import pytest
from pydantic import TypeAdapter, ValidationError

from gendertagger.models.aggregation import AggregationTaskMessage
from gendertagger.models.dispatch import (
    AggregationDispatchCreate,
    BatchDispatch,
    BatchDispatchCreate,
    DispatchCreate,
    DispatchStatus,
    DispatchTarget,
    PublicClassificationDispatchCreate,
    SnapshotDispatchCreate,
)
from gendertagger.models.project import SnapshotImportTaskMessage
from gendertagger.models.public_classification import PublicClassificationTaskMessage
from gendertagger.models.run import TaskBatchMessage


def test_dispatch_create_requires_matching_task_batch_identity() -> None:
    with pytest.raises(ValidationError, match="task_batch_id must match"):
        BatchDispatchCreate(
            task_batch_id=uuid4(),
            queue_name="cpu",
            payload=TaskBatchMessage(
                method_execution_id=uuid4(),
                task_batch_id=uuid4(),
            ),
            available_at=datetime.now(UTC),
        )


def test_aggregation_dispatch_requires_matching_execution_identity() -> None:
    with pytest.raises(ValidationError, match="aggregation_execution_id must match"):
        AggregationDispatchCreate(
            aggregation_execution_id=uuid4(),
            queue_name="cpu",
            payload=AggregationTaskMessage(aggregation_execution_id=uuid4()),
            available_at=datetime.now(UTC),
        )


def test_snapshot_dispatch_requires_matching_snapshot_identity() -> None:
    with pytest.raises(ValidationError, match="dataset_snapshot_id must match"):
        SnapshotDispatchCreate(
            dataset_snapshot_id=uuid4(),
            queue_name="cpu",
            payload=SnapshotImportTaskMessage(dataset_snapshot_id=uuid4()),
            available_at=datetime.now(UTC),
        )


def test_dispatch_create_union_is_discriminated_by_target() -> None:
    aggregation_execution_id = uuid4()

    command: DispatchCreate = TypeAdapter(DispatchCreate).validate_python(
        {
            "target": DispatchTarget.aggregation_execution,
            "aggregation_execution_id": aggregation_execution_id,
            "queue_name": "cpu",
            "payload": {"aggregation_execution_id": aggregation_execution_id},
            "available_at": datetime.now(UTC),
        }
    )

    assert isinstance(command, AggregationDispatchCreate)
    assert command.target_id == aggregation_execution_id


def test_dispatch_create_union_supports_dataset_snapshot_target() -> None:
    dataset_snapshot_id = uuid4()

    command: DispatchCreate = TypeAdapter(DispatchCreate).validate_python(
        {
            "target": DispatchTarget.dataset_snapshot,
            "dataset_snapshot_id": dataset_snapshot_id,
            "queue_name": "cpu",
            "payload": {"dataset_snapshot_id": dataset_snapshot_id},
            "available_at": datetime.now(UTC),
        }
    )

    assert isinstance(command, SnapshotDispatchCreate)
    assert command.target_id == dataset_snapshot_id


def test_public_classification_dispatch_requires_matching_job_identity() -> None:
    with pytest.raises(ValidationError, match="classification_job_id must match"):
        PublicClassificationDispatchCreate(
            classification_job_id=uuid4(),
            queue_name="cpu",
            payload=PublicClassificationTaskMessage(classification_job_id=uuid4()),
            available_at=datetime.now(UTC),
        )


def test_dispatch_create_union_supports_public_classification_job_target() -> None:
    job_id = uuid4()

    command: DispatchCreate = TypeAdapter(DispatchCreate).validate_python(
        {
            "target": DispatchTarget.public_classification_job,
            "classification_job_id": job_id,
            "queue_name": "cpu",
            "payload": {"classification_job_id": job_id},
            "available_at": datetime.now(UTC),
        }
    )

    assert isinstance(command, PublicClassificationDispatchCreate)
    assert command.target_id == job_id


def test_dispatch_create_normalizes_available_time_to_utc() -> None:
    task_batch_id = uuid4()
    command = BatchDispatchCreate(
        task_batch_id=task_batch_id,
        queue_name="cpu",
        payload=TaskBatchMessage(
            method_execution_id=uuid4(),
            task_batch_id=task_batch_id,
        ),
        available_at=datetime(2026, 8, 14, 14, tzinfo=timezone(timedelta(hours=2))),
    )

    assert command.available_at == datetime(2026, 8, 14, 12, tzinfo=UTC)


def test_dispatch_create_rejects_naive_available_time() -> None:
    task_batch_id = uuid4()
    with pytest.raises(ValidationError, match="timezone-aware"):
        BatchDispatchCreate(
            task_batch_id=task_batch_id,
            queue_name="cpu",
            payload=TaskBatchMessage(
                method_execution_id=uuid4(),
                task_batch_id=task_batch_id,
            ),
            available_at=datetime(2026, 8, 14, 12),  # noqa: DTZ001 - Invalid input.
        )


def test_pending_dispatch_rejects_publication_timestamp() -> None:
    now = datetime.now(UTC)
    task_batch_id = uuid4()
    with pytest.raises(ValidationError, match="pending dispatch"):
        BatchDispatch(
            id=uuid4(),
            task_batch_id=task_batch_id,
            queue_name="cpu",
            payload=TaskBatchMessage(
                method_execution_id=uuid4(),
                task_batch_id=task_batch_id,
            ),
            available_at=now,
            status=DispatchStatus.pending,
            attempt_count=1,
            published_at=now,
            created_at=now,
            updated_at=now,
        )


def test_published_dispatch_requires_timestamp_and_released_lease() -> None:
    now = datetime.now(UTC)
    task_batch_id = uuid4()
    common = {
        "id": uuid4(),
        "task_batch_id": task_batch_id,
        "queue_name": "cpu",
        "payload": TaskBatchMessage(
            method_execution_id=uuid4(),
            task_batch_id=task_batch_id,
        ),
        "available_at": now,
        "status": DispatchStatus.published,
        "attempt_count": 1,
        "created_at": now,
        "updated_at": now,
    }

    with pytest.raises(ValidationError, match="requires published_at"):
        BatchDispatch.model_validate(common)

    with pytest.raises(ValidationError, match="must not retain"):
        BatchDispatch.model_validate(
            {
                **common,
                "published_at": now,
                "lease_owner": "relay-1",
                "lease_until": now + timedelta(seconds=30),
            }
        )
