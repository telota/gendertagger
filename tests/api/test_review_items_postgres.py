from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi import Request
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from gendertagger.api.app import create_app
from gendertagger.api.authentication import AuthenticationBackend
from gendertagger.api.settings import AppSettings
from gendertagger.config.run import MethodRunConfig, RunConfig
from gendertagger.db.session import create_session_factory
from gendertagger.db.unit_of_work import SqlAlchemyUnitOfWork
from gendertagger.domain.aggregation import REFERENCE_REQUIRED_METHODS
from gendertagger.models.aggregation import (
    AggregationExecutionCreate,
    AggregationOutcome,
    AggregationResultWrite,
    OverrideSource,
    ReferenceAggregationResult,
    VoteCounts,
)
from gendertagger.models.artifact import ArtifactCreate
from gendertagger.models.classification import (
    AgreementTier,
    CanonicalLabel,
    CertaintyTier,
    PredictionResult,
    PredictionStatus,
)
from gendertagger.models.lifecycle import (
    AggregationExecutionStatus,
    TaskBatchStatus,
)
from gendertagger.models.method import MethodDescriptor
from gendertagger.models.person import PersonInput
from gendertagger.models.project import DatasetSnapshotCreate, ProjectCreate
from gendertagger.models.review import AnnotationCreate, ReviewAction, ReviewWorkflowState
from gendertagger.models.run import (
    MethodExecutionCreate,
    PredictionWrite,
    RunCreate,
    TaskBatchCreate,
)
from gendertagger.models.user import Role, UserCreate
from gendertagger.services.unit_of_work import UnitOfWork, UnitOfWorkFactory

pytestmark = [pytest.mark.integration, pytest.mark.postgres]

DATABASE_URL = "postgresql+psycopg://unused:unused@localhost/unused"
CODE_GIT_COMMIT = "c" * 40
DEPENDENCY_LOCK_SHA256 = "d" * 64
NOW = datetime(2026, 8, 13, 10, 0, tzinfo=UTC)


class StaticAuthenticationBackend(AuthenticationBackend):
    def __init__(self, user_id: UUID) -> None:
        self._user_id = user_id

    def authenticate(self, request: Request) -> UUID | None:
        return self._user_id

    def validate_csrf(self, request: Request, *, user_id: UUID) -> bool:
        return user_id == self._user_id


def _unit_of_work_factory(
    engine: Engine,
) -> tuple[UnitOfWorkFactory, sessionmaker[Session]]:
    session_factory = create_session_factory(engine)

    def factory() -> UnitOfWork:
        return SqlAlchemyUnitOfWork(session_factory)

    return factory, session_factory


def _seed_review_items(
    unit_of_work_factory: UnitOfWorkFactory,
    _session_factory: sessionmaker[Session],
) -> tuple[UUID, UUID]:
    with unit_of_work_factory() as unit_of_work:
        reviewer = unit_of_work.users.add_user(
            UserCreate(display_name="Review query operator", roles={Role.operator})
        )
        artifact = unit_of_work.artifacts.add_artifact(
            ArtifactCreate(
                logical_type="source_tei",
                storage_uri=f"local-sha256:{'a' * 64}",
                sha256="a" * 64,
                byte_size=1,
                media_type="application/tei+xml",
            )
        )
        project = unit_of_work.projects.add_project(
            ProjectCreate(
                slug=f"review-query-{uuid4().hex}",
                display_name="Review query fixture",
            )
        )
        snapshot = unit_of_work.projects.add_snapshot(
            DatasetSnapshotCreate(
                project_id=project.id,
                source_artifact_id=artifact.id,
                source_sha256=artifact.sha256,
                parser_version="tei_parser_v1",
                import_config={"profile": "tei_p5_person_register_v1"},
            )
        )
        unit_of_work.projects.begin_snapshot_import(snapshot.id)
        unit_of_work.projects.add_person_records(
            snapshot.id,
            [
                PersonInput(tei_id="p3", surname="Third", external_ids={"wikidata": "QSearch"}),
                PersonInput(tei_id="p1", surname="First"),
                PersonInput(tei_id="p2", surname="Second"),
            ],
        )
        unit_of_work.projects.complete_snapshot_import(snapshot.id, ready_at=NOW)
        people = {
            tei_id: unit_of_work.projects.get_person_record_by_tei_id(snapshot.id, tei_id)
            for tei_id in ("p1", "p2", "p3")
        }
        assert all(person is not None for person in people.values())
        run = unit_of_work.runs.add_run(
            RunCreate(
                dataset_snapshot_id=snapshot.id,
                resolved_config=RunConfig(
                    methods=[
                        MethodRunConfig(name=method_name)
                        for method_name in REFERENCE_REQUIRED_METHODS
                    ]
                ),
                code_git_commit=CODE_GIT_COMMIT,
                application_version="0.0.0",
                python_version="3.13.14",
                dependency_lock_sha256=DEPENDENCY_LOCK_SHA256,
            )
        )
        unit_of_work.runs.mark_run_queued(run.id)
        unit_of_work.runs.mark_run_started(run.id, started_at=NOW)
        person_one = people["p1"]
        person_two = people["p2"]
        person_three = people["p3"]
        assert person_one is not None
        assert person_two is not None
        assert person_three is not None
        people_in_order = (person_one, person_two, person_three)
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
                    total_count=3,
                )
            )
            execution_ids.append(execution.id)
            batch = unit_of_work.runs.add_task_batch(
                TaskBatchCreate(
                    method_execution_id=execution.id,
                    batch_index=0,
                    queue_name="cpu",
                    record_offset=0,
                    record_count=3,
                )
            )
            unit_of_work.runs.mark_execution_queued(execution.id)
            unit_of_work.runs.mark_execution_started(execution.id, started_at=NOW)
            claimed_batch = unit_of_work.runs.claim_batch(
                batch.id,
                method_execution_id=execution.id,
                worker_task_id=f"fixture-{method_name}",
                started_at=NOW,
                attempt_count=1,
            )
            assert claimed_batch is not None
            results: tuple[PredictionResult, ...]
            if method_name == "gender_guesser":
                results = (
                    PredictionResult(
                        label=None,
                        status=PredictionStatus.error,
                        raw_label="error",
                        raw_output={"diagnostic": "synthetic"},
                    ),
                    PredictionResult(
                        status=PredictionStatus.success,
                        label=CanonicalLabel.male,
                        raw_label="male",
                    ),
                    PredictionResult(
                        status=PredictionStatus.success,
                        label=CanonicalLabel.female,
                        raw_label="female",
                    ),
                )
            else:
                results = tuple(
                    PredictionResult(label=None, status=PredictionStatus.abstain)
                    for _person in people_in_order
                )
            unit_of_work.runs.add_predictions(
                execution.id,
                [
                    PredictionWrite(
                        person_record_id=person.id,
                        task_batch_id=batch.id,
                        input_fingerprint=str(index) * 64,
                        result=result,
                    )
                    for index, (person, result) in enumerate(
                        zip(people_in_order, results, strict=True),
                        start=1,
                    )
                ],
            )
            unit_of_work.runs.mark_batch_finished(
                batch.id,
                status=TaskBatchStatus.completed,
                finished_at=NOW,
                success_count=2 if method_name == "gender_guesser" else 0,
                abstain_count=0 if method_name == "gender_guesser" else 3,
                error_count=1 if method_name == "gender_guesser" else 0,
            )
            unit_of_work.runs.finalize_execution_if_complete(execution.id, finished_at=NOW)
        unit_of_work.runs.finalize_run_if_complete(run.id, finished_at=NOW)
        unit_of_work.commit()

    with unit_of_work_factory() as unit_of_work:
        aggregation = unit_of_work.aggregations.add_aggregation(
            AggregationExecutionCreate(
                run_id=run.id,
                method_execution_ids=tuple(execution_ids),
            )
        )
        claimed = unit_of_work.aggregations.claim_aggregation(
            aggregation.id,
            started_at=NOW,
        )
        assert claimed is not None
        unit_of_work.aggregations.add_results(
            aggregation.id,
            [
                AggregationResultWrite(
                    person_record_id=person_one.id,
                    result=ReferenceAggregationResult(
                        outcome=AggregationOutcome.unresolved_tie,
                        label=None,
                        pooled_vote_counts=VoteCounts(male=1, female=1),
                        tied_labels=(CanonicalLabel.male, CanonicalLabel.female),
                        agreement_score=0.5,
                        agreement_tier=AgreementTier.no_consensus,
                        certainty_tier=CertaintyTier.contested,
                    ),
                ),
                AggregationResultWrite(
                    person_record_id=person_two.id,
                    result=ReferenceAggregationResult(
                        outcome=AggregationOutcome.decided,
                        label=CanonicalLabel.male,
                        pooled_vote_counts=VoteCounts(male=1),
                        agreement_score=1.0,
                        agreement_tier=AgreementTier.single_rater,
                        certainty_tier=CertaintyTier.uncertain,
                    ),
                ),
                AggregationResultWrite(
                    person_record_id=person_three.id,
                    result=ReferenceAggregationResult(
                        outcome=AggregationOutcome.decided,
                        label=CanonicalLabel.female,
                        pooled_vote_counts=VoteCounts(male=1, female=1),
                        override_source=OverrideSource.gnd,
                        override_agreeing_count=1,
                        override_comparison_count=2,
                        agreement_score=0.5,
                        agreement_tier=AgreementTier.weak_majority,
                        certainty_tier=CertaintyTier.high,
                    ),
                ),
            ],
        )
        unit_of_work.aggregations.mark_aggregation_finished(
            aggregation.id,
            status=AggregationExecutionStatus.completed,
            finished_at=NOW,
        )
        persisted_results = unit_of_work.aggregations.list_results(aggregation.id, limit=10)
        results_by_person = {result.person_record_id: result for result in persisted_results}
        unit_of_work.reviews.add_annotation(
            AnnotationCreate(
                snapshot_id=snapshot.id,
                tei_id="p2",
                action=ReviewAction.correct,
                label=CanonicalLabel.female,
                aggregated_result_id=results_by_person[person_two.id].id,
                expected_revision=0,
            ),
            reviewer_user_id=reviewer.id,
        )
        unit_of_work.reviews.add_annotation(
            AnnotationCreate(
                snapshot_id=snapshot.id,
                tei_id="p3",
                action=ReviewAction.defer,
                aggregated_result_id=results_by_person[person_three.id].id,
                expected_revision=0,
            ),
            reviewer_user_id=reviewer.id,
        )
        unit_of_work.commit()
    return reviewer.id, aggregation.id


def _client(postgres_engine: Engine, artifact_root: Path) -> tuple[TestClient, UUID]:
    unit_of_work_factory, session_factory = _unit_of_work_factory(postgres_engine)
    reviewer_id, aggregation_id = _seed_review_items(
        unit_of_work_factory,
        session_factory,
    )
    application = create_app(
        settings=AppSettings(
            database_url=SecretStr(DATABASE_URL),
            code_git_commit=CODE_GIT_COMMIT,
            dependency_lock_sha256=DEPENDENCY_LOCK_SHA256,
            artifact_root=artifact_root,
        ),
        unit_of_work_factory=unit_of_work_factory,
        authentication_backend=StaticAuthenticationBackend(reviewer_id),
    )
    return TestClient(application), aggregation_id


def _tei_ids(response: object) -> list[str]:
    assert isinstance(response, dict)
    items = response["items"]
    assert isinstance(items, list)
    return [str(item["tei_id"]) for item in items]


def test_review_items_project_final_state_and_paginate_stably(
    postgres_engine: Engine,
    tmp_path: Path,
) -> None:
    client, aggregation_id = _client(postgres_engine, tmp_path)
    first_page = client.get(
        "/api/v1/review-items",
        params={"aggregation_id": str(aggregation_id), "limit": 2},
    ).json()
    second_page = client.get(
        "/api/v1/review-items",
        params={
            "aggregation_id": str(aggregation_id),
            "limit": 2,
            "cursor": first_page["next_cursor"],
        },
    ).json()

    assert _tei_ids(first_page) == ["p1", "p2"]
    assert _tei_ids(second_page) == ["p3"]
    first_item, second_item = first_page["items"]
    third_item = second_page["items"][0]
    assert first_item["final_label"] is None
    assert first_item["workflow_state"] == ReviewWorkflowState.unreviewed.value
    assert first_item["has_prediction_error"] is True
    assert second_item["machine_label"] == CanonicalLabel.male.value
    assert second_item["final_label"] == CanonicalLabel.female.value
    assert second_item["workflow_state"] == ReviewWorkflowState.reviewed.value
    assert third_item["has_authority_conflict"] is True
    assert third_item["workflow_state"] == ReviewWorkflowState.deferred.value
    assert third_item["final_label"] == CanonicalLabel.female.value


def test_review_item_filters_are_server_side_and_composable(
    postgres_engine: Engine,
    tmp_path: Path,
) -> None:
    client, aggregation_id = _client(postgres_engine, tmp_path)
    base = {"aggregation_id": str(aggregation_id)}
    cases = [
        ({"certainty_tier": CertaintyTier.contested.value}, ["p1"]),
        ({"agreement_tier": AgreementTier.weak_majority.value}, ["p3"]),
        ({"final_label": CanonicalLabel.female.value}, ["p2", "p3"]),
        ({"workflow_state": ReviewWorkflowState.reviewed.value}, ["p2"]),
        ({"has_authority_conflict": "true"}, ["p3"]),
        ({"has_prediction_error": "true"}, ["p1"]),
        ({"method_name": "gender_guesser", "prediction_status": "error"}, ["p1"]),
        ({"method_name": "gender_guesser", "method_label": "male"}, ["p2"]),
        ({"q": "Second"}, ["p2"]),
        ({"q": "QSearch"}, ["p3"]),
    ]

    for filters, expected_tei_ids in cases:
        response = client.get(
            "/api/v1/review-items",
            params={**base, **filters},
        )
        assert response.status_code == 200
        assert _tei_ids(response.json()) == expected_tei_ids

    method_response = client.get(
        "/api/v1/review-items",
        params={**base, "method_name": "gender_guesser", "method_label": "male"},
    ).json()
    assert method_response["items"][0]["selected_method_result"] == {
        "method_name": "gender_guesser",
        "status": PredictionStatus.success.value,
        "label": CanonicalLabel.male.value,
    }


def test_review_cursor_is_filter_scoped_and_method_filters_require_name(
    postgres_engine: Engine,
    tmp_path: Path,
) -> None:
    client, aggregation_id = _client(postgres_engine, tmp_path)
    first_page = client.get(
        "/api/v1/review-items",
        params={
            "aggregation_id": str(aggregation_id),
            "final_label": CanonicalLabel.female.value,
            "limit": 1,
        },
    ).json()

    cross_filter_response = client.get(
        "/api/v1/review-items",
        params={
            "aggregation_id": str(aggregation_id),
            "limit": 1,
            "cursor": first_page["next_cursor"],
        },
    )
    missing_method_response = client.get(
        "/api/v1/review-items",
        params={
            "aggregation_id": str(aggregation_id),
            "method_label": CanonicalLabel.male.value,
        },
    )

    assert cross_filter_response.status_code == 422
    assert cross_filter_response.json()["error"]["details"] == {"reason": "invalid_cursor"}
    assert missing_method_response.status_code == 422
    assert missing_method_response.json()["error"]["code"] == "validation_error"
