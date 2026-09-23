"""Shared persistence seeds that follow the production write path.

Each function makes the repository calls that the application services and workers make for the
same step, in the same order, so every seeded row is in a state production can reach. Tests
that need a snapshot, run, or aggregation in a given state compose these functions instead of
writing their own setup. Seeds record completed work but not its delivery, so they create no
dispatch-outbox rows.

The functions take any object exposing the repositories they use: a ``UnitOfWork`` or, for
tests that work on a bare ``Session``, :func:`session_repositories`. Callers own the
transaction and commit it themselves.
"""

from __future__ import annotations

import hashlib
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from gendertagger.config.run import MethodRunConfig, RunConfig
from gendertagger.db.aggregation_repository import SqlAlchemyAggregationRepository
from gendertagger.db.artifact_repository import SqlAlchemyArtifactRepository
from gendertagger.db.project_repository import SqlAlchemyProjectRepository
from gendertagger.db.run_repository import SqlAlchemyRunRepository
from gendertagger.domain.aggregation_assessment import assess_reference_predictions
from gendertagger.ingestion.registry import version_for_snapshot_import
from gendertagger.models.aggregation import (
    AggregationExecution,
    AggregationExecutionCreate,
    AggregationResultWrite,
)
from gendertagger.models.artifact import Artifact, ArtifactCreate
from gendertagger.models.classification import PredictionResult, PredictionStatus
from gendertagger.models.lifecycle import AggregationExecutionStatus, TaskBatchStatus
from gendertagger.models.method import MethodDescriptor
from gendertagger.models.person import ImportedPerson, PersonInput, PersonRecord
from gendertagger.models.project import (
    DatasetSnapshot,
    DatasetSnapshotCreate,
    Project,
    ProjectCreate,
    SnapshotImportConfig,
    SnapshotImportLimits,
    SnapshotSourceMemberCreate,
    TeiImportProfile,
)
from gendertagger.models.run import MethodExecutionCreate, PredictionWrite, Run, RunCreate
from gendertagger.models.user import ProjectRole, User, UserCreate
from gendertagger.services.aggregation_repository import AggregationRepository
from gendertagger.services.artifact_repository import ArtifactRepository
from gendertagger.services.project_repository import ProjectRepository
from gendertagger.services.run_repository import RunRepository
from gendertagger.services.task_batches import plan_task_batches
from gendertagger.services.unit_of_work import UnitOfWork

SEED_TIME = datetime(2026, 8, 14, 18, 0, tzinfo=UTC)
SEED_CODE_GIT_COMMIT = "c" * 40
SEED_DEPENDENCY_LOCK_SHA256 = "d" * 64
SEED_SOURCE_SHA256 = "a" * 64
SEED_BATCH_SIZE = 100

PredictionFactory = Callable[[str, PersonRecord], PredictionResult]
"""Return the prediction one method makes for one person, keyed by method name."""


class SeedRepositories(Protocol):
    """The repositories the seeds write through.

    ``UnitOfWork`` and :class:`SessionRepositories` both satisfy it.
    """

    @property
    def projects(self) -> ProjectRepository:
        """Return project persistence."""
        ...

    @property
    def artifacts(self) -> ArtifactRepository:
        """Return artifact persistence."""
        ...

    @property
    def runs(self) -> RunRepository:
        """Return run and execution persistence."""
        ...

    @property
    def aggregations(self) -> AggregationRepository:
        """Return aggregation persistence."""
        ...


@dataclass(frozen=True, slots=True)
class SessionRepositories:
    """The seed repositories bound to one caller-managed ``Session``."""

    projects: SqlAlchemyProjectRepository
    artifacts: SqlAlchemyArtifactRepository
    runs: SqlAlchemyRunRepository
    aggregations: SqlAlchemyAggregationRepository


def session_repositories(session: Session) -> SessionRepositories:
    """Bind the seed repositories to a session, for tests that bypass the unit of work."""
    return SessionRepositories(
        projects=SqlAlchemyProjectRepository(session),
        artifacts=SqlAlchemyArtifactRepository(session),
        runs=SqlAlchemyRunRepository(session),
        aggregations=SqlAlchemyAggregationRepository(session),
    )


@dataclass(frozen=True, slots=True)
class CompletedRun:
    """A finished run with one completed execution per method."""

    run: Run
    execution_ids: tuple[UUID, ...]
    people: Mapping[str, PersonRecord]
    """The snapshot's person records, keyed by TEI ``xml:id``."""


def seed_project(repositories: SeedRepositories, *, slug_prefix: str = "seed") -> Project:
    """Create a project with a unique slug."""
    return repositories.projects.add_project(
        ProjectCreate(slug=f"{slug_prefix}-{uuid4().hex}", display_name="Seeded project")
    )


def seed_member(
    unit_of_work: UnitOfWork,
    project_id: UUID,
    *,
    role: ProjectRole = ProjectRole.operator,
    display_name: str = "Seeded member",
) -> User:
    """Create a local user without global roles and grant them one project role."""
    user = unit_of_work.users.add_user(UserCreate(display_name=display_name, roles=set()))
    unit_of_work.access.set_member_role(project_id, user.id, role)
    return user


def seed_artifact(
    repositories: SeedRepositories,
    project_id: UUID,
    *,
    logical_type: str = "source_tei",
    sha256: str = SEED_SOURCE_SHA256,
    byte_size: int = 1,
    media_type: str = "application/tei+xml",
    storage_uri: str | None = None,
) -> Artifact:
    """Register a project-scoped artifact; the bytes need not exist unless a test reads them."""
    return repositories.artifacts.add_artifact(
        ArtifactCreate(
            logical_type=logical_type,
            storage_uri=storage_uri or f"local-sha256:{sha256}",
            sha256=sha256,
            byte_size=byte_size,
            media_type=media_type,
            project_id=project_id,
        )
    )


def seed_pending_snapshot(
    repositories: SeedRepositories,
    project_id: UUID,
    *,
    source: Artifact | None = None,
    profile: TeiImportProfile = TeiImportProfile.tei_p5_person_register,
    member_name: str = "source.xml",
) -> DatasetSnapshot:
    """Accept a single-member TEI snapshot the way ``ProjectService.import_snapshot`` does."""
    artifact = source or seed_artifact(repositories, project_id)
    import_config = SnapshotImportConfig(profile=profile, limits=SnapshotImportLimits())
    snapshot = repositories.projects.add_snapshot(
        DatasetSnapshotCreate(
            project_id=project_id,
            source_artifact_id=artifact.id,
            source_sha256=artifact.sha256,
            parser_version=version_for_snapshot_import(import_config),
            import_config=import_config.model_dump(mode="json"),
        )
    )
    repositories.projects.add_snapshot_source_members(
        snapshot.id,
        [
            SnapshotSourceMemberCreate(
                artifact_id=artifact.id,
                ordinal=0,
                logical_name=member_name,
                sha256=artifact.sha256,
                byte_size=artifact.byte_size,
                media_type=artifact.media_type,
            )
        ],
    )
    return snapshot


def seed_ready_snapshot(
    repositories: SeedRepositories,
    project_id: UUID,
    people: Sequence[PersonInput],
    *,
    member_name: str = "source.xml",
    ready_at: datetime = SEED_TIME,
) -> DatasetSnapshot:
    """Accept and import a snapshot the way ``SnapshotImportExecutor`` does."""
    snapshot = seed_pending_snapshot(repositories, project_id, member_name=member_name)
    claimed = repositories.projects.claim_snapshot_import(snapshot.id)
    assert claimed is not None
    repositories.projects.add_imported_person_records(
        snapshot.id,
        [
            ImportedPerson(
                person=person,
                source_member_name=member_name,
                source_record_locator=str(position),
            )
            for position, person in enumerate(people, start=1)
        ],
    )
    return repositories.projects.complete_snapshot_import(snapshot.id, ready_at=ready_at)


def seed_run(
    repositories: SeedRepositories,
    snapshot_id: UUID,
    config: RunConfig | Sequence[MethodRunConfig],
) -> Run:
    """Create a run in the ``created`` state, as ``RunService.create_run`` does."""
    resolved_config = config if isinstance(config, RunConfig) else RunConfig(methods=list(config))
    return repositories.runs.add_run(
        RunCreate(
            dataset_snapshot_id=snapshot_id,
            resolved_config=resolved_config,
            code_git_commit=SEED_CODE_GIT_COMMIT,
            application_version="0.0.0",
            python_version="3.11.0",
            dependency_lock_sha256=SEED_DEPENDENCY_LOCK_SHA256,
        )
    )


def seed_completed_run(
    repositories: SeedRepositories,
    snapshot: DatasetSnapshot,
    method_names: Sequence[str],
    predict: PredictionFactory,
    *,
    at: datetime = SEED_TIME,
) -> CompletedRun:
    """Schedule and execute a run the way ``RunScheduler`` and ``BatchExecutor`` do.

    Every method classifies every person through ``predict``. Batches are planned, claimed,
    and finished with tallies derived from the predictions, and the run reaches its terminal
    state through the same finalization calls the worker makes.
    """
    runs = repositories.runs
    total_count = snapshot.record_count
    assert total_count is not None, "the snapshot must be ready"
    run = seed_run(repositories, snapshot.id, [MethodRunConfig(name=name) for name in method_names])
    runs.mark_run_queued(run.id)
    runs.mark_run_started(run.id, started_at=at)
    people = (
        list(
            repositories.projects.list_person_records_slice(
                snapshot.id, offset=0, limit=total_count
            )
        )
        if total_count
        else []
    )
    execution_ids: list[UUID] = []
    for method_name in method_names:
        execution = runs.add_method_execution(
            MethodExecutionCreate(
                run_id=run.id,
                descriptor=MethodDescriptor(
                    name=method_name,
                    implementation_version=f"{method_name}_v1",
                    normalization_version=f"{method_name}_v1",
                ),
                queue_name="cpu",
                total_count=total_count,
            )
        )
        execution_ids.append(execution.id)
        runs.mark_execution_queued(execution.id)
        runs.mark_execution_started(execution.id, started_at=at)
        plans = plan_task_batches(total_count, batch_size=SEED_BATCH_SIZE)
        for batch in runs.create_task_batches(execution.id, plans):
            claimed = runs.claim_batch(
                batch.id,
                method_execution_id=execution.id,
                worker_task_id=f"seed-{method_name}-{batch.batch_index}",
                started_at=at,
                attempt_count=1,
            )
            assert claimed is not None
            batch_people = people[batch.record_offset : batch.record_offset + batch.record_count]
            writes = [
                PredictionWrite(
                    person_record_id=person.id,
                    task_batch_id=batch.id,
                    input_fingerprint=_input_fingerprint(method_name, person),
                    result=predict(method_name, person),
                )
                for person in batch_people
            ]
            runs.add_predictions(execution.id, writes)
            tallies = Counter(write.result.status for write in writes)
            runs.mark_batch_finished(
                batch.id,
                status=TaskBatchStatus.completed,
                finished_at=at,
                success_count=tallies[PredictionStatus.success],
                abstain_count=tallies[PredictionStatus.abstain],
                error_count=tallies[PredictionStatus.error],
            )
        runs.finalize_execution_if_complete(execution.id, finished_at=at)
    finished = runs.finalize_run_if_complete(run.id, finished_at=at)
    return CompletedRun(
        run=finished,
        execution_ids=tuple(execution_ids),
        people={person.tei_id: person for person in people},
    )


def seed_completed_aggregation(
    repositories: SeedRepositories,
    run_id: UUID,
    execution_ids: Sequence[UUID],
    *,
    results: Sequence[AggregationResultWrite] | None = None,
    at: datetime = SEED_TIME,
) -> AggregationExecution:
    """Create, queue, and complete a ``reference_v1`` aggregation.

    Without ``results`` the person results are assessed from the persisted predictions exactly
    as ``AggregationExecutor`` does. Pass ``results`` to pin specific tiers or outcomes.
    """
    aggregations = repositories.aggregations
    aggregation = aggregations.add_aggregation(
        AggregationExecutionCreate(run_id=run_id, method_execution_ids=tuple(execution_ids))
    )
    aggregations.mark_aggregation_queued(aggregation.id)
    claimed = aggregations.claim_aggregation(aggregation.id, started_at=at)
    assert claimed is not None
    if results is None:
        results = [
            _assessed_result(person.person_record_id, person.predictions)
            for person in aggregations.load_prediction_matrix(aggregation.id)
        ]
    aggregations.add_results(aggregation.id, results)
    return aggregations.mark_aggregation_finished(
        aggregation.id,
        status=AggregationExecutionStatus.completed,
        finished_at=at,
    )


def _assessed_result(
    person_record_id: UUID,
    predictions: Mapping[str, PredictionResult],
) -> AggregationResultWrite:
    # Mirrors AggregationExecutor._assess_people for one person.
    return AggregationResultWrite(
        person_record_id=person_record_id,
        result=assess_reference_predictions(predictions),
        has_prediction_error=any(
            prediction.status is PredictionStatus.error for prediction in predictions.values()
        ),
        metadata={"strategy": "reference_v1"},
    )


def _input_fingerprint(method_name: str, person: PersonRecord) -> str:
    return hashlib.sha256(f"{method_name}:{person.tei_id}".encode()).hexdigest()
