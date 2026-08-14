from collections.abc import Callable
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from gendertagger.config.run import MethodRunConfig, RunConfig
from gendertagger.db.aggregation_repository import SqlAlchemyAggregationRepository
from gendertagger.db.aggregations import AggregatedResultRow
from gendertagger.db.artifact_repository import SqlAlchemyArtifactRepository
from gendertagger.db.artifacts import ArtifactRow
from gendertagger.db.executions import MethodExecutionRow, PredictionRow
from gendertagger.db.project_repository import SqlAlchemyProjectRepository
from gendertagger.db.projects import DatasetSnapshotRow, PersonExternalIdRow, PersonRecordRow
from gendertagger.db.review_repository import SqlAlchemyReviewRepository
from gendertagger.db.reviews import AnnotationRow
from gendertagger.db.run_repository import SqlAlchemyRunRepository
from gendertagger.db.user_repository import SqlAlchemyUserRepository
from gendertagger.domain.aggregation import REFERENCE_REQUIRED_METHODS
from gendertagger.models.aggregation import (
    AggregatedResult,
    AggregationExecutionCreate,
    AggregationOutcome,
    AggregationResultWrite,
    ReferenceAggregationResult,
    VoteCounts,
)
from gendertagger.models.artifact import Artifact, ArtifactCreate
from gendertagger.models.classification import (
    AgreementTier,
    CanonicalLabel,
    CertaintyTier,
    PredictionResult,
    PredictionStatus,
)
from gendertagger.models.lifecycle import AggregationExecutionStatus, MethodExecutionStatus
from gendertagger.models.method import MethodDescriptor
from gendertagger.models.person import (
    PersonInput,
    PersonNameForm,
    PersonNameType,
    PersonRecord,
)
from gendertagger.models.project import (
    DatasetSnapshotCreate,
    Project,
    ProjectCreate,
    TeiImportProfile,
)
from gendertagger.models.review import AnnotationCreate, ReviewAction, ReviewWorkflowState
from gendertagger.models.run import (
    MethodExecutionCreate,
    Prediction,
    PredictionWrite,
    RunCreate,
    TaskBatchCreate,
)
from gendertagger.models.user import Role, User, UserCreate
from gendertagger.services.persistence_errors import (
    ImmutableResourceError,
    InvalidResourceStateError,
    ReviewConflictError,
)

pytestmark = [pytest.mark.integration, pytest.mark.postgres]


def _mutate_and_flush(session: Session, mutation: Callable[[], None]) -> None:
    mutation()
    session.flush()


def assert_database_rejects_mutation(
    session: Session,
    mutation: Callable[[], None],
) -> None:
    with pytest.raises(DBAPIError) as error, session.begin_nested():
        _mutate_and_flush(session, mutation)
    assert getattr(error.value.orig, "sqlstate", None) == "55000"
    session.expire_all()


@pytest.mark.parametrize(
    ("profile", "person"),
    [
        (
            TeiImportProfile.tei_p5_person_register_v1,
            PersonInput(
                tei_id="p1",
                surname="Example",
                name_forms=[PersonNameForm(type=PersonNameType.regular, surname="Example")],
            ),
        ),
        (
            TeiImportProfile.tei_p5_person_register_v2,
            PersonInput(tei_id="p1", surname="Example"),
        ),
    ],
)
def test_person_records_require_name_forms_matching_the_snapshot_profile(
    db_session: Session,
    profile: TeiImportProfile,
    person: PersonInput,
) -> None:
    artifacts = SqlAlchemyArtifactRepository(db_session)
    source_artifact = artifacts.add_artifact(
        ArtifactCreate(
            logical_type="source_tei",
            storage_uri=f"file:///synthetic/{profile.value}.xml",
            sha256="e" * 64,
            byte_size=42,
            media_type="application/xml",
        )
    )
    projects = SqlAlchemyProjectRepository(db_session)
    project = projects.add_project(
        ProjectCreate(
            slug=f"profile-{uuid4().hex}",
            display_name="Profile consistency fixture",
        )
    )
    snapshot = projects.add_snapshot(
        DatasetSnapshotCreate(
            project_id=project.id,
            source_artifact_id=source_artifact.id,
            source_sha256=source_artifact.sha256,
            parser_version=f"tei_parser_{profile.value[-2:]}",
            import_config={"profile": profile.value},
        )
    )
    projects.begin_snapshot_import(snapshot.id)

    with pytest.raises(InvalidResourceStateError, match="name_forms"):
        projects.add_person_records(snapshot.id, [person])

    assert (
        db_session.scalar(
            select(func.count())
            .select_from(PersonRecordRow)
            .where(PersonRecordRow.dataset_snapshot_id == snapshot.id)
        )
        == 0
    )


def test_domain_contracts_round_trip_without_orm_leak(db_session: Session) -> None:
    now = datetime.now(UTC)
    artifacts = SqlAlchemyArtifactRepository(db_session)
    source_artifact = artifacts.add_artifact(
        ArtifactCreate(
            logical_type="source_tei",
            storage_uri="file:///synthetic/source.xml",
            sha256="a" * 64,
            byte_size=42,
            media_type="application/xml",
            metadata={"fixture": "synthetic"},
        )
    )

    projects = SqlAlchemyProjectRepository(db_session)
    project = projects.add_project(
        ProjectCreate(
            slug=f"integration-{uuid4().hex}",
            display_name="Synthetic integration project",
        )
    )
    snapshot = projects.add_snapshot(
        DatasetSnapshotCreate(
            project_id=project.id,
            source_artifact_id=source_artifact.id,
            source_sha256=source_artifact.sha256,
            parser_version="tei_parser_v2",
            import_config={"profile": "tei_p5_person_register_v2"},
        )
    )
    projects.begin_snapshot_import(snapshot.id)
    assert (
        projects.add_person_records(
            snapshot.id,
            [
                PersonInput(
                    tei_id="p1",
                    surname="Example",
                    forenames=["Anna"],
                    birth="1900",
                    death="1980",
                    note="Synthetic fixture",
                    alt_names=["Earlier Annette", "A. Example"],
                    name_forms=[
                        PersonNameForm(
                            type=PersonNameType.regular,
                            surname="Example",
                            forenames=["Anna"],
                        ),
                        PersonNameForm(
                            type=PersonNameType.alternative,
                            subtype="birthname",
                            surname="Earlier",
                            forenames=["Annette"],
                        ),
                        PersonNameForm(
                            type=PersonNameType.alternative,
                            name="A. Example",
                        ),
                    ],
                    gnd_id="123456789",
                    external_ids={"wikidata": "Q1"},
                )
            ],
        )
        == 1
    )
    snapshot = projects.complete_snapshot_import(snapshot.id, ready_at=now)
    person = projects.get_person_record_by_tei_id(snapshot.id, "p1")
    assert person is not None

    users = SqlAlchemyUserRepository(db_session)
    reviewer = users.add_user(UserCreate(display_name="Synthetic reviewer", roles={Role.reviewer}))

    runs = SqlAlchemyRunRepository(db_session)
    run_config = RunConfig(
        methods=[MethodRunConfig(name=method_name) for method_name in REFERENCE_REQUIRED_METHODS]
    )
    run = runs.add_run(
        RunCreate(
            dataset_snapshot_id=snapshot.id,
            resolved_config=run_config,
            code_git_commit="abc123",
            application_version="0.0.0",
            python_version="3.13.14",
            dependency_lock_sha256="b" * 64,
        )
    )
    execution = runs.add_method_execution(
        MethodExecutionCreate(
            run_id=run.id,
            descriptor=MethodDescriptor(
                name="gender_guesser",
                implementation_version="1.0.0",
                normalization_version="gender_guesser_v1",
            ),
            resolved_config={"threshold": 0.5},
            queue_name="cpu",
            total_count=1,
        )
    )
    batch = runs.add_task_batch(
        TaskBatchCreate(
            method_execution_id=execution.id,
            batch_index=0,
            queue_name="cpu",
            record_offset=0,
            record_count=1,
        )
    )
    prediction_result = PredictionResult(
        label=CanonicalLabel.unknown,
        status=PredictionStatus.success,
        method_confidence=0.75,
        raw_label="uncertain",
        raw_output={"label": "uncertain", "score": 0.75},
        metadata={
            "normalization_version": "gender_guesser_v1",
            "outcome_reason": "mapped_unknown",
        },
    )
    prediction_write = PredictionWrite(
        person_record_id=person.id,
        task_batch_id=batch.id,
        input_fingerprint="c" * 64,
        result=prediction_result,
    )
    assert runs.add_predictions(execution.id, [prediction_write]) == 1
    assert runs.add_predictions(execution.id, [prediction_write]) == 1
    conflicting_write = prediction_write.model_copy(
        update={"result": prediction_result.model_copy(update={"raw_label": "different"})}
    )
    with pytest.raises(ImmutableResourceError, match="different output or provenance"):
        runs.add_predictions(execution.id, [conflicting_write])
    prediction_count = db_session.scalar(
        select(func.count())
        .select_from(PredictionRow)
        .where(
            PredictionRow.method_execution_id == execution.id,
            PredictionRow.person_record_id == person.id,
        )
    )
    assert prediction_count == 1
    prediction_id = db_session.scalar(
        select(PredictionRow.id).where(
            PredictionRow.method_execution_id == execution.id,
            PredictionRow.person_record_id == person.id,
        )
    )
    assert prediction_id is not None
    prediction = runs.get_prediction(prediction_id)
    assert prediction is not None

    execution_ids = [execution.id]
    for method_name in REFERENCE_REQUIRED_METHODS:
        if method_name == "gender_guesser":
            continue
        additional_execution = runs.add_method_execution(
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
        execution_ids.append(additional_execution.id)
        runs.add_predictions(
            additional_execution.id,
            [
                PredictionWrite(
                    person_record_id=person.id,
                    input_fingerprint="c" * 64,
                    result=PredictionResult(
                        label=None,
                        status=PredictionStatus.abstain,
                    ),
                )
            ],
        )

    execution_rows = tuple(
        db_session.scalars(
            select(MethodExecutionRow).where(MethodExecutionRow.id.in_(execution_ids))
        )
    )
    assert len(execution_rows) == len(REFERENCE_REQUIRED_METHODS)
    for execution_row in execution_rows:
        execution_row.status = MethodExecutionStatus.completed
        execution_row.started_at = now
        execution_row.finished_at = now
        execution_row.completed_count = 1
    db_session.flush()

    aggregations = SqlAlchemyAggregationRepository(db_session)
    aggregation = aggregations.add_aggregation(
        AggregationExecutionCreate(
            run_id=run.id,
            method_execution_ids=tuple(execution_ids),
        )
    )
    claimed_aggregation = aggregations.claim_aggregation(
        aggregation.id,
        started_at=now,
    )
    assert claimed_aggregation is not None
    scientific_result = ReferenceAggregationResult(
        outcome=AggregationOutcome.decided,
        label=CanonicalLabel.unknown,
        pooled_vote_counts=VoteCounts(unknown=1),
        agreement_score=1.0,
        agreement_tier=AgreementTier.single_rater,
        certainty_tier=CertaintyTier.uncertain,
    )
    assert (
        aggregations.add_results(
            aggregation.id,
            [
                AggregationResultWrite(
                    person_record_id=person.id,
                    result=scientific_result,
                    metadata={"strategy": "reference_v1"},
                )
            ],
        )
        == 1
    )
    aggregation = aggregations.mark_aggregation_finished(
        aggregation.id,
        status=AggregationExecutionStatus.completed,
        finished_at=now,
    )
    aggregated_result_id = db_session.scalar(
        select(AggregatedResultRow.id).where(
            AggregatedResultRow.aggregation_execution_id == aggregation.id,
            AggregatedResultRow.person_record_id == person.id,
        )
    )
    assert aggregated_result_id is not None
    aggregated_result = aggregations.get_result(aggregated_result_id)
    assert aggregated_result is not None

    reviews = SqlAlchemyReviewRepository(db_session)
    initial_state = reviews.get_review_state(snapshot.id, person.tei_id)
    assert initial_state is not None
    first_annotation = reviews.add_annotation(
        AnnotationCreate(
            snapshot_id=snapshot.id,
            tei_id=person.tei_id,
            action=ReviewAction.verify,
            label=CanonicalLabel.unknown,
            aggregated_result_id=aggregated_result.id,
            expected_revision=0,
        ),
        reviewer_user_id=reviewer.id,
    )
    with pytest.raises(ReviewConflictError) as conflict:
        reviews.add_annotation(
            AnnotationCreate(
                snapshot_id=snapshot.id,
                tei_id=person.tei_id,
                action=ReviewAction.defer,
                expected_revision=0,
            ),
            reviewer_user_id=reviewer.id,
        )
    second_annotation = reviews.add_annotation(
        AnnotationCreate(
            snapshot_id=snapshot.id,
            tei_id=person.tei_id,
            action=ReviewAction.correct,
            label=CanonicalLabel.female,
            comment="Synthetic correction",
            aggregated_result_id=aggregated_result.id,
            expected_revision=1,
        ),
        reviewer_user_id=reviewer.id,
    )
    review_state = reviews.get_review_state(snapshot.id, person.tei_id)
    assert review_state is not None

    assert isinstance(source_artifact, Artifact)
    assert isinstance(project, Project)
    assert isinstance(person, PersonRecord)
    assert isinstance(reviewer, User)
    assert isinstance(prediction, Prediction)
    assert isinstance(aggregated_result, AggregatedResult)
    assert snapshot.record_count == 1
    assert person.surname == "Example"
    assert person.forenames == ["Anna"]
    assert person.birth == "1900"
    assert person.death == "1980"
    assert person.note == "Synthetic fixture"
    assert person.alt_names == ["Earlier Annette", "A. Example"]
    assert person.name_forms == [
        PersonNameForm(
            type=PersonNameType.regular,
            surname="Example",
            forenames=["Anna"],
        ),
        PersonNameForm(
            type=PersonNameType.alternative,
            subtype="birthname",
            surname="Earlier",
            forenames=["Annette"],
        ),
        PersonNameForm(
            type=PersonNameType.alternative,
            name="A. Example",
        ),
    ]
    assert person.gnd_id == "123456789"
    assert person.external_ids == {"wikidata": "Q1"}
    assert run.config_sha256 == run_config.canonical_sha256()
    assert (
        prediction.model_dump(
            exclude={
                "id",
                "method_execution_id",
                "person_record_id",
                "task_batch_id",
                "input_fingerprint",
                "created_at",
            }
        )
        == prediction_result.model_dump()
    )
    assert aggregation.method_execution_ids == tuple(execution_ids)
    assert aggregated_result.pooled_vote_counts == VoteCounts(unknown=1)
    assert conflict.value.current_revision == 1
    assert second_annotation.supersedes_annotation_id == first_annotation.id
    assert review_state.revision == 2
    assert review_state.workflow_state is ReviewWorkflowState.reviewed
    assert artifacts.get_artifact(source_artifact.id) == source_artifact
    assert users.get_user(reviewer.id) == reviewer

    with pytest.raises(ImmutableResourceError, match="ready and immutable"):
        projects.add_person_records(snapshot.id, [PersonInput(tei_id="p2")])

    artifact_row = db_session.get(ArtifactRow, source_artifact.id)
    snapshot_row = db_session.get(DatasetSnapshotRow, snapshot.id)
    person_row = db_session.get(PersonRecordRow, person.id)
    external_id_row = db_session.scalar(
        select(PersonExternalIdRow).where(
            PersonExternalIdRow.person_record_id == person.id,
            PersonExternalIdRow.scheme == "gnd",
        )
    )
    prediction_row = db_session.get(PredictionRow, prediction.id)
    aggregated_result_row = db_session.get(AggregatedResultRow, aggregated_result.id)
    annotation_row = db_session.get(AnnotationRow, first_annotation.id)
    assert artifact_row is not None
    assert snapshot_row is not None
    assert person_row is not None
    assert external_id_row is not None
    assert prediction_row is not None
    assert aggregated_result_row is not None
    assert annotation_row is not None

    assert_database_rejects_mutation(
        db_session,
        lambda: setattr(artifact_row, "media_type", "text/plain"),
    )
    assert_database_rejects_mutation(
        db_session,
        lambda: setattr(snapshot_row, "parser_version", "changed"),
    )
    assert_database_rejects_mutation(
        db_session,
        lambda: setattr(person_row, "surname", "Changed"),
    )
    assert_database_rejects_mutation(
        db_session,
        lambda: setattr(
            person_row,
            "name_forms",
            [{"type": "reg", "surname": "Changed", "forenames": []}],
        ),
    )
    assert_database_rejects_mutation(
        db_session,
        lambda: setattr(external_id_row, "value", "changed"),
    )
    assert_database_rejects_mutation(
        db_session,
        lambda: setattr(prediction_row, "raw_label", "changed"),
    )
    assert_database_rejects_mutation(
        db_session,
        lambda: setattr(aggregated_result_row, "result_metadata", {"changed": True}),
    )
    assert_database_rejects_mutation(
        db_session,
        lambda: setattr(annotation_row, "comment", "changed"),
    )
