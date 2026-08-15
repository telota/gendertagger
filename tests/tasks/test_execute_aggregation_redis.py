from __future__ import annotations

import time
from contextlib import AbstractContextManager
from datetime import UTC, datetime
from functools import partial
from typing import cast
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine

from gendertagger.config.run import MethodRunConfig, RunConfig
from gendertagger.db.session import create_session_factory
from gendertagger.db.unit_of_work import SqlAlchemyUnitOfWork
from gendertagger.domain.aggregation import REFERENCE_REQUIRED_METHODS
from gendertagger.ingestion.registry import version_for_snapshot_import
from gendertagger.models.aggregation import AggregationCreateRequest
from gendertagger.models.artifact import ArtifactCreate
from gendertagger.models.classification import (
    CanonicalLabel,
    PredictionResult,
    PredictionStatus,
)
from gendertagger.models.lifecycle import (
    AggregationExecutionStatus,
    TaskBatchStatus,
)
from gendertagger.models.method import MethodDescriptor
from gendertagger.models.person import ImportedPerson, PersonInput
from gendertagger.models.project import (
    DatasetSnapshotCreate,
    ProjectCreate,
    SnapshotImportConfig,
    SnapshotImportLimits,
    SnapshotSourceMemberCreate,
)
from gendertagger.models.run import (
    MethodExecutionCreate,
    PredictionWrite,
    RunCreate,
    TaskBatchCreate,
)
from gendertagger.services.aggregations import AggregationService
from gendertagger.services.dispatch import OutboxRelay
from gendertagger.services.pagination import CursorCodec
from gendertagger.services.unit_of_work import UnitOfWorkFactory
from gendertagger.tasks import aggregation as aggregation_module
from gendertagger.tasks.celery_app import create_celery_app
from gendertagger.tasks.dispatch import CeleryMessagePublisher

pytestmark = [pytest.mark.integration, pytest.mark.postgres, pytest.mark.redis]

_TERMINAL = {
    AggregationExecutionStatus.completed,
    AggregationExecutionStatus.failed,
}

REFERENCE_PREDICTIONS = {
    "baseline_lookup": (CanonicalLabel.female, 0.90),
    "first_name_dictionary": (CanonicalLabel.female, 0.85),
    "surname_rule": (CanonicalLabel.female, 0.70),
    "name_frequency": (CanonicalLabel.female, 0.80),
    "character_ngram": (CanonicalLabel.female, 0.75),
}


def _seed_completed_reference_run(
    factory: UnitOfWorkFactory,
    _postgres_engine: Engine,
) -> tuple[UUID, tuple[UUID, ...]]:
    now = datetime.now(UTC)
    with factory() as unit_of_work:
        project = unit_of_work.projects.add_project(
            ProjectCreate(
                slug=f"aggregation-redis-{uuid4().hex}",
                display_name="Aggregation Redis e2e project",
            )
        )
        source = unit_of_work.artifacts.add_artifact(
            ArtifactCreate(
                logical_type="source_tei",
                storage_uri="file:///synthetic/aggregation-source.xml",
                sha256="a" * 64,
                byte_size=1,
                media_type="application/xml",
                project_id=project.id,
            )
        )
        import_config = SnapshotImportConfig(limits=SnapshotImportLimits())
        snapshot = unit_of_work.projects.add_snapshot(
            DatasetSnapshotCreate(
                project_id=project.id,
                source_artifact_id=source.id,
                source_sha256=source.sha256,
                parser_version=version_for_snapshot_import(import_config),
                import_config=import_config.model_dump(mode="json"),
            )
        )
        unit_of_work.projects.add_snapshot_source_members(
            snapshot.id,
            [
                SnapshotSourceMemberCreate(
                    artifact_id=source.id,
                    ordinal=0,
                    logical_name="source.xml",
                    sha256=source.sha256,
                    byte_size=source.byte_size,
                    media_type=source.media_type,
                )
            ],
        )
        unit_of_work.projects.begin_snapshot_import(snapshot.id)
        unit_of_work.projects.add_imported_person_records(
            snapshot.id,
            [
                ImportedPerson(
                    person=PersonInput(tei_id="p01", surname="Example"),
                    source_member_name="source.xml",
                    source_record_locator="1",
                )
            ],
        )
        unit_of_work.projects.complete_snapshot_import(snapshot.id, ready_at=now)
        person = unit_of_work.projects.get_person_record_by_tei_id(snapshot.id, "p01")
        assert person is not None
        run = unit_of_work.runs.add_run(
            RunCreate(
                dataset_snapshot_id=snapshot.id,
                resolved_config=RunConfig(
                    methods=[
                        MethodRunConfig(name=method_name)
                        for method_name in REFERENCE_REQUIRED_METHODS
                    ]
                ),
                code_git_commit="abc123",
                application_version="0.0.0",
                python_version="3.11.0",
                dependency_lock_sha256="b" * 64,
            )
        )
        unit_of_work.runs.mark_run_queued(run.id)
        unit_of_work.runs.mark_run_started(run.id, started_at=now)
        execution_ids: list[UUID] = []
        for method_name in REFERENCE_REQUIRED_METHODS:
            execution = unit_of_work.runs.add_method_execution(
                MethodExecutionCreate(
                    run_id=run.id,
                    descriptor=MethodDescriptor(
                        name=method_name,
                        implementation_version=f"{method_name}_v1",
                        normalization_version=f"{method_name}_v1",
                    ),
                    queue_name="cpu",
                    total_count=1,
                )
            )
            execution_ids.append(execution.id)
            batch = unit_of_work.runs.add_task_batch(
                TaskBatchCreate(
                    method_execution_id=execution.id,
                    batch_index=0,
                    queue_name="cpu",
                    record_offset=0,
                    record_count=1,
                )
            )
            unit_of_work.runs.mark_execution_queued(execution.id)
            unit_of_work.runs.mark_execution_started(execution.id, started_at=now)
            claimed_batch = unit_of_work.runs.claim_batch(
                batch.id,
                method_execution_id=execution.id,
                worker_task_id=f"fixture-{method_name}",
                started_at=now,
                attempt_count=1,
            )
            assert claimed_batch is not None
            result = (
                PredictionResult(
                    label=CanonicalLabel.female,
                    status=PredictionStatus.success,
                    raw_label="female",
                )
                if method_name == "gender_guesser"
                else PredictionResult(
                    label=None,
                    status=PredictionStatus.abstain,
                )
            )
            unit_of_work.runs.add_predictions(
                execution.id,
                [
                    PredictionWrite(
                        person_record_id=person.id,
                        task_batch_id=batch.id,
                        input_fingerprint="c" * 64,
                        result=result,
                    )
                ],
            )
            unit_of_work.runs.mark_batch_finished(
                batch.id,
                status=TaskBatchStatus.completed,
                finished_at=now,
                success_count=int(result.status is PredictionStatus.success),
                abstain_count=int(result.status is PredictionStatus.abstain),
            )
            unit_of_work.runs.finalize_execution_if_complete(execution.id, finished_at=now)
        unit_of_work.runs.finalize_run_if_complete(run.id, finished_at=now)
        unit_of_work.commit()
    return run.id, tuple(execution_ids)


def test_reference_aggregation_runs_through_relay_and_real_worker(
    repository_database_url: str,
    postgres_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from celery.contrib.testing.worker import start_worker

    monkeypatch.setenv("GENDERTAGGER_DATABASE_URL", repository_database_url)
    aggregation_module._aggregation_executor.cache_clear()
    factory: UnitOfWorkFactory = partial(
        SqlAlchemyUnitOfWork,
        create_session_factory(postgres_engine),
    )
    run_id, execution_ids = _seed_completed_reference_run(factory, postgres_engine)
    aggregation = AggregationService(
        unit_of_work_factory=factory,
        cursor_codec=CursorCodec(),
        clock=partial(datetime.now, UTC),
    ).create_aggregation(
        run_id=run_id,
        command=AggregationCreateRequest(method_execution_ids=execution_ids),
    )
    assert aggregation.status is AggregationExecutionStatus.queued

    app = create_celery_app()
    relay = OutboxRelay(
        unit_of_work_factory=factory,
        publisher=CeleryMessagePublisher(app),
        relay_id="aggregation-redis-e2e-relay",
        clock=partial(datetime.now, UTC),
    )
    terminal_status: AggregationExecutionStatus | None = None
    try:
        worker_context = cast(
            AbstractContextManager[object],
            start_worker(app, queues=["cpu"], perform_ping_check=False, shutdown_timeout=30),
        )
        with worker_context:
            relay_result = relay.run_once()
            assert relay_result.published == 1
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                with factory() as unit_of_work:
                    current = unit_of_work.aggregations.get_aggregation(aggregation.id)
                assert current is not None
                terminal_status = current.status
                if terminal_status in _TERMINAL:
                    break
                time.sleep(0.25)

        assert terminal_status is AggregationExecutionStatus.completed
        with factory() as unit_of_work:
            results = unit_of_work.aggregations.list_results(aggregation.id, limit=10)
            dispatch = unit_of_work.dispatches.get_dispatch_for_aggregation(aggregation.id)
        assert len(results) == 1
        assert results[0].label is CanonicalLabel.female
        assert dispatch is not None
    finally:
        app.close()
        aggregation_module._aggregation_executor.cache_clear()
