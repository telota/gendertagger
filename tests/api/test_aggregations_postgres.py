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
from gendertagger.db.executions import MethodExecutionRow
from gendertagger.db.session import create_session_factory
from gendertagger.db.unit_of_work import SqlAlchemyUnitOfWork
from gendertagger.models.aggregation import (
    AggregationOutcome,
    AggregationResultWrite,
    ReferenceAggregationResult,
    VoteCounts,
)
from gendertagger.models.artifact import ArtifactCreate
from gendertagger.models.classification import AgreementTier, CanonicalLabel, CertaintyTier
from gendertagger.models.lifecycle import AggregationExecutionStatus, MethodExecutionStatus
from gendertagger.models.method import MethodDescriptor
from gendertagger.models.person import PersonInput
from gendertagger.models.project import DatasetSnapshotCreate, ProjectCreate
from gendertagger.models.run import MethodExecutionCreate, RunCreate
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


def _seed_completed_execution(
    unit_of_work_factory: UnitOfWorkFactory,
    session_factory: sessionmaker[Session],
) -> tuple[UUID, UUID, UUID, tuple[UUID, UUID]]:
    with unit_of_work_factory() as unit_of_work:
        user = unit_of_work.users.add_user(
            UserCreate(display_name="Aggregation operator", roles={Role.operator})
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
                slug=f"aggregation-{uuid4().hex}",
                display_name="Aggregation fixture",
            )
        )
        snapshot = unit_of_work.projects.add_snapshot(
            DatasetSnapshotCreate(
                project_id=project.id,
                source_artifact_id=artifact.id,
                source_sha256=artifact.sha256,
                parser_version="tei_parser_v1",
            )
        )
        unit_of_work.projects.begin_snapshot_import(snapshot.id)
        unit_of_work.projects.add_person_records(
            snapshot.id,
            [
                PersonInput(tei_id="p1", surname="Example"),
                PersonInput(tei_id="p2", surname="Second"),
            ],
        )
        unit_of_work.projects.complete_snapshot_import(snapshot.id, ready_at=NOW)
        run = unit_of_work.runs.add_run(
            RunCreate(
                dataset_snapshot_id=snapshot.id,
                resolved_config=RunConfig(methods=[MethodRunConfig(name="demo_method")]),
                code_git_commit=CODE_GIT_COMMIT,
                application_version="0.0.0",
                python_version="3.13.14",
                dependency_lock_sha256=DEPENDENCY_LOCK_SHA256,
            )
        )
        execution = unit_of_work.runs.add_method_execution(
            MethodExecutionCreate(
                run_id=run.id,
                descriptor=MethodDescriptor(
                    name="demo_method",
                    implementation_version="demo_v1",
                    normalization_version="demo_normalization_v1",
                ),
                queue_name="cpu",
                total_count=2,
            )
        )
        first_person = unit_of_work.projects.get_person_record_by_tei_id(snapshot.id, "p1")
        second_person = unit_of_work.projects.get_person_record_by_tei_id(snapshot.id, "p2")
        assert first_person is not None
        assert second_person is not None
        unit_of_work.commit()

    with session_factory() as session:
        execution_row = session.get(MethodExecutionRow, execution.id)
        assert execution_row is not None
        execution_row.status = MethodExecutionStatus.completed
        execution_row.started_at = NOW
        execution_row.finished_at = NOW
        execution_row.completed_count = 2
        session.commit()
    return user.id, run.id, execution.id, (first_person.id, second_person.id)


def test_pending_aggregation_and_immutable_result_round_trip_through_http(
    postgres_engine: Engine,
    tmp_path: Path,
) -> None:
    unit_of_work_factory, session_factory = _unit_of_work_factory(postgres_engine)
    user_id, run_id, execution_id, person_ids = _seed_completed_execution(
        unit_of_work_factory,
        session_factory,
    )
    application = create_app(
        settings=AppSettings(
            database_url=SecretStr(DATABASE_URL),
            code_git_commit=CODE_GIT_COMMIT,
            dependency_lock_sha256=DEPENDENCY_LOCK_SHA256,
            artifact_root=tmp_path,
        ),
        unit_of_work_factory=unit_of_work_factory,
        authentication_backend=StaticAuthenticationBackend(user_id),
    )
    client = TestClient(application)

    create_response = client.post(
        f"/api/v1/runs/{run_id}/aggregations",
        json={"method_execution_ids": [str(execution_id)]},
    )

    assert create_response.status_code == 202
    aggregation_body = create_response.json()
    assert aggregation_body["status"] == AggregationExecutionStatus.pending.value
    assert aggregation_body["run_id"] == str(run_id)
    assert aggregation_body["method_execution_ids"] == [str(execution_id)]
    aggregation_id = UUID(aggregation_body["id"])
    assert client.get(f"/api/v1/aggregations/{aggregation_id}").json() == aggregation_body

    with unit_of_work_factory() as unit_of_work:
        assert (
            unit_of_work.aggregations.add_results(
                aggregation_id,
                [
                    AggregationResultWrite(
                        person_record_id=person_ids[0],
                        result=ReferenceAggregationResult(
                            outcome=AggregationOutcome.decided,
                            label=CanonicalLabel.female,
                            pooled_vote_counts=VoteCounts(female=1),
                            agreement_score=1.0,
                            agreement_tier=AgreementTier.single_rater,
                            certainty_tier=CertaintyTier.uncertain,
                        ),
                    ),
                    AggregationResultWrite(
                        person_record_id=person_ids[1],
                        result=ReferenceAggregationResult(
                            outcome=AggregationOutcome.decided,
                            label=CanonicalLabel.male,
                            pooled_vote_counts=VoteCounts(male=1),
                            agreement_score=1.0,
                            agreement_tier=AgreementTier.single_rater,
                            certainty_tier=CertaintyTier.uncertain,
                        ),
                    ),
                ],
            )
            == 2
        )
        unit_of_work.commit()
    with unit_of_work_factory() as unit_of_work:
        persisted_results = unit_of_work.aggregations.list_results(
            aggregation_id,
            limit=10,
        )
    assert len(persisted_results) == 2
    result_id = persisted_results[0].id

    first_page = client.get(
        f"/api/v1/aggregations/{aggregation_id}/results",
        params={"limit": 1},
    ).json()
    second_page = client.get(
        f"/api/v1/aggregations/{aggregation_id}/results",
        params={"limit": 1, "cursor": first_page["next_cursor"]},
    ).json()
    assert [item["id"] for item in first_page["items"] + second_page["items"]] == [
        str(result.id) for result in persisted_results
    ]
    assert first_page["has_more"] is True
    assert second_page["has_more"] is False
    assert second_page["next_cursor"] is None

    result_response = client.get(f"/api/v1/aggregations/{aggregation_id}/results/{result_id}")

    assert result_response.status_code == 200
    expected_label = persisted_results[0].label
    assert expected_label is not None
    assert result_response.json()["label"] == expected_label.value
    wrong_owner_response = client.get(f"/api/v1/aggregations/{uuid4()}/results/{result_id}")
    assert wrong_owner_response.status_code == 404
