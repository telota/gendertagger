from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from httpx2 import Response
from pydantic import SecretStr
from sqlalchemy import Engine
from tests.factories import tei_person_input
from tests.seeding import (
    always_abstain,
    seed_completed_aggregation,
    seed_completed_run,
    seed_member,
    seed_project,
    seed_ready_snapshot,
)

from gendertagger.api.app import create_app
from gendertagger.api.authentication import AuthenticationBackend
from gendertagger.api.settings import AppSettings
from gendertagger.db.session import create_session_factory
from gendertagger.db.unit_of_work import SqlAlchemyUnitOfWork
from gendertagger.domain.aggregation import REFERENCE_REQUIRED_METHODS
from gendertagger.models.aggregation import AggregationExecutionCreate
from gendertagger.models.classification import CanonicalLabel
from gendertagger.models.review import AnnotationCreate, ReviewAction
from gendertagger.models.user import ProjectRole
from gendertagger.services.ports.unit_of_work import UnitOfWork, UnitOfWorkFactory

pytestmark = [pytest.mark.integration, pytest.mark.postgres]

DATABASE_URL = "postgresql+psycopg://unused:unused@localhost/unused"
CODE_GIT_COMMIT = "1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b"
DEPENDENCY_LOCK_SHA256 = "b" * 64


class StaticAuthenticationBackend(AuthenticationBackend):
    def __init__(self, user_id: UUID) -> None:
        self._user_id = user_id

    def authenticate(self, request: Request) -> UUID | None:
        return self._user_id

    def validate_csrf(self, request: Request, *, user_id: UUID) -> bool:
        return user_id == self._user_id


def _unit_of_work_factory(engine: Engine) -> UnitOfWorkFactory:
    session_factory = create_session_factory(engine)

    def factory() -> UnitOfWork:
        return SqlAlchemyUnitOfWork(session_factory)

    return factory


def _client(
    postgres_engine: Engine,
    artifact_root: Path,
) -> tuple[
    TestClient,
    FastAPI,
    UUID,
    UUID,
    UUID,
    UUID,
    UUID,
    tuple[UUID, UUID, UUID, UUID],
]:
    factory = _unit_of_work_factory(postgres_engine)
    with factory() as unit_of_work:
        project = seed_project(unit_of_work, slug_prefix="game-round")
        reviewer = seed_member(
            unit_of_work,
            project.id,
            role=ProjectRole.reviewer,
            display_name="Round reviewer",
        )
        operator = seed_member(
            unit_of_work,
            project.id,
            role=ProjectRole.operator,
            display_name="Project operator",
        )
        snapshot = seed_ready_snapshot(
            unit_of_work,
            project.id,
            [
                tei_person_input(tei_id="p1", surname="First"),
                tei_person_input(tei_id="p2", surname="Second"),
            ],
        )
        completed = seed_completed_run(
            unit_of_work,
            snapshot,
            REFERENCE_REQUIRED_METHODS,
            always_abstain,
        )
        aggregation = seed_completed_aggregation(
            unit_of_work,
            completed.run.id,
            completed.execution_ids,
        )
        pending_aggregation = unit_of_work.aggregations.add_aggregation(
            AggregationExecutionCreate(
                run_id=completed.run.id,
                method_execution_ids=completed.execution_ids,
            )
        )
        results = {
            result.person_record_id: result
            for result in unit_of_work.aggregations.list_results(aggregation.id, limit=10)
        }
        annotations = tuple(
            unit_of_work.reviews.add_annotation(
                AnnotationCreate(
                    snapshot_id=snapshot.id,
                    tei_id=tei_id,
                    action=ReviewAction.correct,
                    label=CanonicalLabel.unknown,
                    aggregated_result_id=results[completed.people[tei_id].id].id,
                    expected_revision=0,
                ),
                reviewer_user_id=reviewer.id,
            )
            for tei_id in ("p1", "p2")
        )
        repeated_person_annotation = unit_of_work.reviews.add_annotation(
            AnnotationCreate(
                snapshot_id=snapshot.id,
                tei_id="p1",
                action=ReviewAction.correct,
                label=CanonicalLabel.male,
                aggregated_result_id=results[completed.people["p1"].id].id,
                expected_revision=1,
            ),
            reviewer_user_id=reviewer.id,
        )
        deferred_annotation = unit_of_work.reviews.add_annotation(
            AnnotationCreate(
                snapshot_id=snapshot.id,
                tei_id="p1",
                action=ReviewAction.defer,
                label=None,
                aggregated_result_id=results[completed.people["p1"].id].id,
                expected_revision=2,
            ),
            reviewer_user_id=reviewer.id,
        )
        unit_of_work.commit()

    application = create_app(
        settings=AppSettings(
            database_url=SecretStr(DATABASE_URL),
            code_git_commit=CODE_GIT_COMMIT,
            dependency_lock_sha256=DEPENDENCY_LOCK_SHA256,
            artifact_root=artifact_root,
        ),
        unit_of_work_factory=factory,
        authentication_backend=StaticAuthenticationBackend(reviewer.id),
    )
    return (
        TestClient(application),
        application,
        reviewer.id,
        operator.id,
        project.id,
        aggregation.id,
        pending_aggregation.id,
        (
            annotations[0].id,
            annotations[1].id,
            repeated_person_annotation.id,
            deferred_annotation.id,
        ),
    )


def test_completed_game_round_is_server_scored_idempotent_and_ranked(
    postgres_engine: Engine,
    tmp_path: Path,
) -> None:
    (
        client,
        application,
        reviewer_id,
        operator_id,
        project_id,
        aggregation_id,
        pending_aggregation_id,
        annotation_ids,
    ) = _client(postgres_engine, tmp_path)
    round_id = uuid4()
    command = {
        "id": str(round_id),
        "aggregation_execution_id": str(aggregation_id),
        "round_size": 10,
        "annotation_ids": [str(annotation_ids[0]), str(annotation_ids[1])],
    }

    disabled = client.post(f"/api/v1/projects/{project_id}/game-rounds", json=command)
    denied = client.put(
        f"/api/v1/projects/{project_id}/game-mode",
        json={"enabled": True},
    )
    application.state.authentication_backend = StaticAuthenticationBackend(operator_id)
    enabled = client.put(
        f"/api/v1/projects/{project_id}/game-mode",
        json={"enabled": True},
    )
    application.state.authentication_backend = StaticAuthenticationBackend(reviewer_id)
    pending_aggregation_response = client.post(
        f"/api/v1/projects/{project_id}/game-rounds",
        json={
            "id": str(uuid4()),
            "aggregation_execution_id": str(pending_aggregation_id),
            "round_size": 10,
            "annotation_ids": [],
        },
    )
    repeated_person_response = client.post(
        f"/api/v1/projects/{project_id}/game-rounds",
        json={
            "id": str(uuid4()),
            "aggregation_execution_id": str(aggregation_id),
            "round_size": 10,
            "annotation_ids": [str(annotation_ids[0]), str(annotation_ids[2])],
        },
    )
    deferred_answer_response = client.post(
        f"/api/v1/projects/{project_id}/game-rounds",
        json={
            "id": str(uuid4()),
            "aggregation_execution_id": str(aggregation_id),
            "round_size": 10,
            "annotation_ids": [str(annotation_ids[3])],
        },
    )

    created = client.post(f"/api/v1/projects/{project_id}/game-rounds", json=command)
    repeated = client.post(f"/api/v1/projects/{project_id}/game-rounds", json=command)
    leaderboard = client.get(
        f"/api/v1/projects/{project_id}/game-leaderboard",
        params={"round_size": 10},
    )
    application.state.authentication_backend = StaticAuthenticationBackend(operator_id)
    turned_off = client.put(
        f"/api/v1/projects/{project_id}/game-mode",
        json={"enabled": False},
    )
    leaderboard_while_disabled = client.get(
        f"/api/v1/projects/{project_id}/game-leaderboard",
        params={"round_size": 10},
    )

    assert disabled.status_code == 409
    assert disabled.json()["error"]["code"] == "game_mode_disabled"
    assert denied.status_code == 403
    assert enabled.status_code == 200
    assert enabled.json()["game_mode_enabled"] is True
    assert turned_off.status_code == 200
    assert turned_off.json()["game_mode_enabled"] is False
    assert leaderboard_while_disabled.status_code == 409
    assert leaderboard_while_disabled.json()["error"]["code"] == "game_mode_disabled"
    assert pending_aggregation_response.status_code == 409
    assert pending_aggregation_response.json()["error"]["code"] == "resource_conflict"
    assert repeated_person_response.status_code == 409
    assert repeated_person_response.json()["error"]["code"] == "resource_conflict"
    assert deferred_answer_response.status_code == 409
    assert deferred_answer_response.json()["error"]["code"] == "resource_conflict"

    assert created.status_code == repeated.status_code == 201
    created_body = created.json()
    assert created_body == repeated.json()
    assert {
        key: created_body[key]
        for key in (
            "id",
            "project_id",
            "aggregation_execution_id",
            "round_size",
            "score",
            "answered_count",
        )
    } == {
        "id": str(round_id),
        "project_id": str(project_id),
        "aggregation_execution_id": str(aggregation_id),
        "round_size": 10,
        "score": 20,
        "answered_count": 2,
    }
    assert leaderboard.status_code == 200
    body = leaderboard.json()
    assert body["total_players"] == 1
    assert body["round_size"] == 10
    assert [
        (entry["rank"], entry["reviewer_display_name"], entry["score"]) for entry in body["entries"]
    ] == [(1, "Round reviewer", 20)]


def test_game_round_concurrency_is_idempotent_and_conflict_safe(
    postgres_engine: Engine,
    tmp_path: Path,
) -> None:
    (
        client,
        application,
        reviewer_id,
        operator_id,
        project_id,
        aggregation_id,
        _pending_aggregation_id,
        annotation_ids,
    ) = _client(postgres_engine, tmp_path)
    application.state.authentication_backend = StaticAuthenticationBackend(operator_id)
    enabled = client.put(
        f"/api/v1/projects/{project_id}/game-mode",
        json={"enabled": True},
    )
    application.state.authentication_backend = StaticAuthenticationBackend(reviewer_id)
    assert enabled.status_code == 200

    round_id = uuid4()
    identical_command = {
        "id": str(round_id),
        "aggregation_execution_id": str(aggregation_id),
        "round_size": 10,
        "annotation_ids": [str(annotation_ids[0])],
    }
    identical_barrier = Barrier(2)

    def post_identical() -> Response:
        identical_barrier.wait()
        return client.post(
            f"/api/v1/projects/{project_id}/game-rounds",
            json=identical_command,
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        identical_responses = tuple(executor.map(lambda _: post_identical(), range(2)))

    assert [response.status_code for response in identical_responses] == [201, 201]
    assert identical_responses[0].json() == identical_responses[1].json()

    shared_annotation_barrier = Barrier(2)
    conflicting_commands = (
        {
            "id": str(uuid4()),
            "aggregation_execution_id": str(aggregation_id),
            "round_size": 10,
            "annotation_ids": [str(annotation_ids[1])],
        },
        {
            "id": str(uuid4()),
            "aggregation_execution_id": str(aggregation_id),
            "round_size": 20,
            "annotation_ids": [str(annotation_ids[1])],
        },
    )

    def post_conflicting(command: dict[str, object]) -> Response:
        shared_annotation_barrier.wait()
        return client.post(
            f"/api/v1/projects/{project_id}/game-rounds",
            json=command,
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        conflict_responses = tuple(executor.map(post_conflicting, conflicting_commands))

    assert sorted(response.status_code for response in conflict_responses) == [201, 409]
    conflict = next(response for response in conflict_responses if response.status_code == 409)
    assert conflict.json()["error"]["code"] == "resource_conflict"
