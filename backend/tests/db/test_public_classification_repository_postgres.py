from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine, select, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from gendertagger.db.repositories.dispatch_repository import SqlAlchemyDispatchRepository
from gendertagger.db.repositories.public_classification_repository import (
    SqlAlchemyPublicClassificationRepository,
)
from gendertagger.db.rows.public_classification import PublicClassificationJobRow
from gendertagger.models.aggregation import AggregationOutcome, VoteCounts
from gendertagger.models.classification import CanonicalLabel, PredictionResult, PredictionStatus
from gendertagger.models.dispatch import (
    DispatchStatus,
    PublicClassificationDispatchCreate,
)
from gendertagger.models.method import MethodDescriptor
from gendertagger.models.public_classification import (
    PublicClassificationJobRecord,
    PublicClassificationProvenance,
    PublicClassificationStatus,
    PublicClassificationTaskMessage,
)
from gendertagger.models.synchronous_classification import (
    AggregatedClassification,
    ClassifyNamesResponse,
    MethodClassification,
    NameClassificationResult,
)
from gendertagger.services.ports.persistence_errors import (
    InvalidResourceStateError,
    ResourceNotFoundError,
)

pytestmark = [pytest.mark.integration, pytest.mark.postgres]

NOW = datetime(2026, 10, 3, 12, tzinfo=UTC)


def _job() -> PublicClassificationJobRecord:
    return PublicClassificationJobRecord(
        id=uuid4(),
        retrieval_token_sha256="a" * 64,
        names=["Ada"],
        methods=["fixture"],
        resolved_method_configs={"fixture": {"scientific_option": "fixed"}},
        provenance=PublicClassificationProvenance(
            methods=[
                MethodDescriptor(
                    name="fixture",
                    implementation_version="1",
                    normalization_version="1",
                )
            ],
            method_configs={"fixture": {"scientific_option": "fixed"}},
            resolved_config_sha256="b" * 64,
            code_git_commit="test-revision",
            application_version="0.0.0",
            python_version="3.11.0",
            dependency_lock_sha256="c" * 64,
            dependency_versions={"gendertagger": "0.0.0"},
        ),
        created_at=NOW,
    )


def _response() -> ClassifyNamesResponse:
    return ClassifyNamesResponse(
        results=[
            NameClassificationResult(
                name="Ada",
                classifications={
                    "fixture": MethodClassification(
                        label=CanonicalLabel.female,
                        status=PredictionStatus.success,
                        raw_label="f",
                    )
                },
                aggregated=AggregatedClassification(
                    label=CanonicalLabel.female,
                    outcome=AggregationOutcome.decided,
                    vote_counts=VoteCounts(female=1),
                ),
            )
        ]
    )


def _predictions() -> list[dict[str, PredictionResult]]:
    return [
        {
            "fixture": PredictionResult(
                label=CanonicalLabel.female,
                status=PredictionStatus.success,
                raw_label="f",
                raw_output={"label": "f", "source": "synthetic"},
                metadata={"normalization_version": "1"},
            )
        }
    ]


def _dispatch(job_id: UUID) -> PublicClassificationDispatchCreate:
    return PublicClassificationDispatchCreate(
        classification_job_id=job_id,
        queue_name="cpu",
        payload=PublicClassificationTaskMessage(classification_job_id=job_id),
        available_at=NOW,
    )


def test_public_job_preserves_inputs_config_provenance_and_identifier_only_dispatch(
    db_session: Session,
) -> None:
    repository = SqlAlchemyPublicClassificationRepository(db_session)
    dispatches = SqlAlchemyDispatchRepository(db_session)
    job = _job()

    assert repository.add_job(job) == job
    assert repository.get_job(job.id) == job
    assert repository.get_job(uuid4()) is None
    dispatch = dispatches.ensure_dispatch(_dispatch(job.id))
    assert dispatches.ensure_dispatch(_dispatch(job.id)) == dispatch
    assert dispatches.get_dispatch_for_classification(job.id) == dispatch
    assert dispatches.get_dispatch(dispatch.id) == dispatch
    assert dispatch.payload.model_dump(mode="json") == {"classification_job_id": str(job.id)}


def test_public_job_claim_requires_available_lease_and_terminal_result_is_preserved(
    db_session: Session,
) -> None:
    repository = SqlAlchemyPublicClassificationRepository(db_session)
    job = repository.add_job(_job())
    lease_id = uuid4()
    expiry = NOW + timedelta(minutes=5)

    claimed = repository.claim_job(job.id, now=NOW, lease_until=expiry, lease_id=lease_id)

    assert claimed is not None
    assert claimed.status is PublicClassificationStatus.running
    assert claimed.started_at == NOW
    assert repository.claim_job(job.id, now=NOW, lease_until=expiry, lease_id=uuid4()) is None
    assert repository.claim_job(uuid4(), now=NOW, lease_until=expiry, lease_id=uuid4()) is None
    assert not repository.fail_job(job.id, lease_id=uuid4(), completed_at=NOW)
    assert repository.complete_job(
        job.id,
        lease_id=lease_id,
        response=_response(),
        raw_predictions=_predictions(),
        completed_at=NOW + timedelta(seconds=1),
    )
    completed = repository.get_job(job.id)
    assert completed is not None
    assert completed.status is PublicClassificationStatus.completed
    assert completed.response == _response()
    assert completed.raw_predictions == _predictions()
    assert completed.lease_id is None
    assert completed.lease_until is None
    assert not repository.fail_job(job.id, lease_id=lease_id, completed_at=expiry)
    assert (
        repository.claim_job(
            job.id, now=expiry, lease_until=expiry + timedelta(minutes=1), lease_id=uuid4()
        )
        is None
    )


def test_public_job_expired_lease_fences_previous_worker_and_failure_is_sanitized(
    db_session: Session,
) -> None:
    repository = SqlAlchemyPublicClassificationRepository(db_session)
    job = repository.add_job(_job())
    old_token, new_token = uuid4(), uuid4()
    expiry = NOW + timedelta(minutes=5)
    assert repository.claim_job(job.id, now=NOW, lease_until=expiry, lease_id=old_token)
    assert repository.claim_job(job.id, now=NOW, lease_until=expiry, lease_id=uuid4()) is None

    reclaimed = repository.claim_job(
        job.id, now=expiry, lease_until=expiry + timedelta(minutes=5), lease_id=new_token
    )

    assert reclaimed is not None
    assert reclaimed.started_at == NOW
    assert not repository.complete_job(
        job.id,
        lease_id=old_token,
        response=_response(),
        raw_predictions=_predictions(),
        completed_at=expiry,
    )
    assert repository.fail_job(job.id, lease_id=new_token, completed_at=expiry)
    failed = repository.get_job(job.id)
    assert failed is not None
    assert failed.status is PublicClassificationStatus.failed
    assert failed.failure_code == "classification_failed"
    assert failed.raw_predictions is None
    assert (
        repository.claim_job(
            job.id, now=expiry, lease_until=expiry + timedelta(minutes=1), lease_id=uuid4()
        )
        is None
    )


@pytest.mark.parametrize("field_name", ["names", "resolved_method_configs", "provenance"])
def test_public_job_database_rejects_input_and_provenance_mutation(
    db_session: Session,
    field_name: str,
) -> None:
    repository = SqlAlchemyPublicClassificationRepository(db_session)
    job = repository.add_job(_job())

    with (
        pytest.raises(DBAPIError, match="inputs and provenance are immutable"),
        db_session.begin_nested(),
    ):
        db_session.execute(
            update(PublicClassificationJobRow)
            .where(PublicClassificationJobRow.id == job.id)
            .values({field_name: {"mutated": True}})
        )


def test_public_job_database_rejects_terminal_result_mutation(db_session: Session) -> None:
    repository = SqlAlchemyPublicClassificationRepository(db_session)
    job = repository.add_job(_job())
    token = uuid4()
    assert repository.claim_job(
        job.id, now=NOW, lease_until=NOW + timedelta(minutes=5), lease_id=token
    )
    assert repository.complete_job(
        job.id,
        lease_id=token,
        response=_response(),
        raw_predictions=_predictions(),
        completed_at=NOW,
    )

    with (
        pytest.raises(DBAPIError, match="terminal public classification jobs are immutable"),
        db_session.begin_nested(),
    ):
        db_session.execute(
            update(PublicClassificationJobRow)
            .where(PublicClassificationJobRow.id == job.id)
            .values(response={"results": []})
        )


def test_public_job_claim_skips_concurrent_transaction_row_lock(postgres_engine: Engine) -> None:
    with Session(postgres_engine) as setup:
        job = SqlAlchemyPublicClassificationRepository(setup).add_job(_job())
        setup.commit()
    with Session(postgres_engine) as first, Session(postgres_engine) as second:
        first.scalar(
            select(PublicClassificationJobRow)
            .where(PublicClassificationJobRow.id == job.id)
            .with_for_update()
        )
        assert (
            SqlAlchemyPublicClassificationRepository(second).claim_job(
                job.id, now=NOW, lease_until=NOW + timedelta(minutes=5), lease_id=uuid4()
            )
            is None
        )


def test_public_job_outbox_recovers_missing_and_expired_work_without_rearming_live_jobs(
    db_session: Session,
) -> None:
    repository = SqlAlchemyPublicClassificationRepository(db_session)
    dispatches = SqlAlchemyDispatchRepository(db_session)
    job = repository.add_job(_job())
    assert dispatches.ensure_missing(now=NOW, limit=10) == 1
    assert dispatches.ensure_missing(now=NOW, limit=10) == 0
    dispatch = dispatches.get_dispatch_for_classification(job.id)
    assert dispatch is not None
    claimed_dispatches = dispatches.claim_available(
        now=NOW, lease_owner="relay", lease_until=NOW + timedelta(seconds=30), limit=10
    )
    assert len(claimed_dispatches) == 1
    assert claimed_dispatches[0].id == dispatch.id
    assert claimed_dispatches[0].lease_owner == "relay"
    dispatches.mark_published(dispatch.id, lease_owner="relay", published_at=NOW)
    assert repository.claim_job(
        job.id, now=NOW, lease_until=NOW + timedelta(minutes=5), lease_id=uuid4()
    )
    assert (
        dispatches.rearm_stale_published(
            now=NOW + timedelta(minutes=1), published_before=NOW, limit=10
        )
        == 0
    )
    assert (
        dispatches.rearm_stale_published(
            now=NOW + timedelta(minutes=5), published_before=NOW, limit=10
        )
        == 1
    )
    rearmed = dispatches.get_dispatch(dispatch.id)
    assert rearmed is not None
    assert rearmed.status is DispatchStatus.pending
    assert rearmed.published_at is None


def test_public_job_dispatch_rejects_invalid_resource_state_queue_and_payload(
    db_session: Session,
) -> None:
    repository = SqlAlchemyPublicClassificationRepository(db_session)
    dispatches = SqlAlchemyDispatchRepository(db_session)
    with pytest.raises(ResourceNotFoundError):
        dispatches.ensure_dispatch(_dispatch(uuid4()))
    job = repository.add_job(_job())
    with pytest.raises(InvalidResourceStateError, match="persisted job queue"):
        dispatches.ensure_dispatch(_dispatch(job.id).model_copy(update={"queue_name": "llm"}))
    dispatches.ensure_dispatch(_dispatch(job.id))
    with pytest.raises(InvalidResourceStateError, match="different dispatch intent"):
        dispatches.ensure_dispatch(
            _dispatch(job.id).model_copy(
                update={"payload": PublicClassificationTaskMessage(classification_job_id=uuid4())}
            )
        )
    token = uuid4()
    assert repository.claim_job(
        job.id, now=NOW, lease_until=NOW + timedelta(minutes=5), lease_id=token
    )
    assert repository.fail_job(job.id, lease_id=token, completed_at=NOW)
    with pytest.raises(InvalidResourceStateError, match="not dispatchable"):
        dispatches.ensure_dispatch(_dispatch(job.id))


def test_public_job_repository_rejects_invalid_lease_expiry(
    db_session: Session,
) -> None:
    repository = SqlAlchemyPublicClassificationRepository(db_session)
    with pytest.raises(ValueError, match="later than now"):
        repository.claim_job(uuid4(), now=NOW, lease_until=NOW, lease_id=uuid4())


def test_public_job_heartbeat_extends_only_the_current_lease(db_session: Session) -> None:
    repository = SqlAlchemyPublicClassificationRepository(db_session)
    job = repository.add_job(_job())
    lease_id = uuid4()
    expiry = NOW + timedelta(minutes=5)
    assert repository.claim_job(job.id, now=NOW, lease_until=expiry, lease_id=lease_id)
    extended = expiry + timedelta(minutes=5)

    assert not repository.renew_job_lease(job.id, lease_id=uuid4(), lease_until=extended)
    assert repository.renew_job_lease(job.id, lease_id=lease_id, lease_until=extended)

    assert repository.claim_job(job.id, now=expiry, lease_until=extended, lease_id=uuid4()) is None
    current = repository.get_job(job.id)
    assert current is not None
    assert current.lease_until == extended
    assert current.started_at == NOW


def test_public_job_missing_dispatch_recovery_preserves_persisted_worker_queue(
    db_session: Session,
) -> None:
    repository = SqlAlchemyPublicClassificationRepository(db_session)
    job = repository.add_job(_job().model_copy(update={"queue_name": "llm"}))
    dispatches = SqlAlchemyDispatchRepository(db_session)

    assert dispatches.ensure_missing(now=NOW, limit=10) == 1

    dispatch = dispatches.get_dispatch_for_classification(job.id)
    assert dispatch is not None
    assert dispatch.queue_name == "llm"
