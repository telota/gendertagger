from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi import Request
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker
from tests.factories import tei_person_input
from tests.seeding import seed_completed_run, seed_member, seed_project, seed_ready_snapshot

from gendertagger.api.app import create_app
from gendertagger.api.authentication import AuthenticationBackend
from gendertagger.api.settings import AppSettings
from gendertagger.db.session import create_session_factory
from gendertagger.db.unit_of_work import SqlAlchemyUnitOfWork
from gendertagger.domain.aggregation import REFERENCE_REQUIRED_METHODS
from gendertagger.models.aggregation import (
    AggregationCreateRequest,
    AggregationTaskMessage,
)
from gendertagger.models.classification import (
    CanonicalLabel,
    PredictionResult,
    PredictionStatus,
)
from gendertagger.models.lifecycle import AggregationExecutionStatus
from gendertagger.models.person import PersonRecord
from gendertagger.models.user import ProjectRole, UserCreate
from gendertagger.services.aggregation_execution import AggregationExecutor
from gendertagger.services.aggregations import AggregationService
from gendertagger.services.pagination import CursorCodec
from gendertagger.services.ports.unit_of_work import UnitOfWork, UnitOfWorkFactory

pytestmark = [pytest.mark.integration, pytest.mark.postgres]

DATABASE_URL = "postgresql+psycopg://unused:unused@localhost/unused"
CODE_GIT_COMMIT = "1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b"
DEPENDENCY_LOCK_SHA256 = "b" * 64
NOW = datetime(2026, 8, 14, 18, 0, tzinfo=UTC)


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


def _seed_completed_reference_executions(
    unit_of_work_factory: UnitOfWorkFactory,
    _session_factory: sessionmaker[Session],
) -> tuple[UUID, UUID, tuple[UUID, ...], tuple[UUID, UUID]]:
    with unit_of_work_factory() as unit_of_work:
        project = seed_project(unit_of_work, slug_prefix="aggregation")
        user = seed_member(unit_of_work, project.id, display_name="Aggregation operator")
        snapshot = seed_ready_snapshot(
            unit_of_work,
            project.id,
            [
                tei_person_input(tei_id="p1", surname="Example"),
                tei_person_input(tei_id="p2", surname="Second"),
            ],
        )
        completed = seed_completed_run(
            unit_of_work, snapshot, REFERENCE_REQUIRED_METHODS, _llm_decides
        )
        unit_of_work.commit()
    people = completed.people
    return user.id, completed.run.id, completed.execution_ids, (people["p1"].id, people["p2"].id)


def _llm_decides(method_name: str, person: PersonRecord) -> PredictionResult:
    """Only the LLM answers: female for p1, male for p2; every other method abstains."""
    if method_name != "local_llm":
        return PredictionResult(label=None, status=PredictionStatus.abstain)
    label = CanonicalLabel.female if person.tei_id == "p1" else CanonicalLabel.male
    return PredictionResult(
        label=label,
        status=PredictionStatus.success,
        raw_label=label.value,
        metadata={"self_reported_certainty": "high"},
    )


def _outsider_id(unit_of_work_factory: UnitOfWorkFactory) -> UUID:
    with unit_of_work_factory() as unit_of_work:
        outsider = unit_of_work.users.add_user(UserCreate(display_name="Other project member"))
        unit_of_work.commit()
    return outsider.id


def test_queued_aggregation_executes_and_results_round_trip_through_http(
    postgres_engine: Engine,
    tmp_path: Path,
) -> None:
    unit_of_work_factory, session_factory = _unit_of_work_factory(postgres_engine)
    user_id, run_id, execution_ids, person_ids = _seed_completed_reference_executions(
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
        json={"method_execution_ids": [str(execution_id) for execution_id in execution_ids]},
    )

    assert create_response.status_code == 202
    aggregation_body = create_response.json()
    assert aggregation_body["status"] == AggregationExecutionStatus.queued.value
    assert aggregation_body["run_id"] == str(run_id)
    assert aggregation_body["method_execution_ids"] == [
        str(execution_id) for execution_id in execution_ids
    ]
    aggregation_id = UUID(aggregation_body["id"])
    assert client.get(f"/api/v1/aggregations/{aggregation_id}").json() == aggregation_body

    completed = AggregationExecutor(
        unit_of_work_factory=unit_of_work_factory,
        clock=lambda: NOW,
    ).execute(
        AggregationTaskMessage(aggregation_execution_id=aggregation_id),
        attempt_count=1,
    )
    assert completed.status is AggregationExecutionStatus.completed

    with unit_of_work_factory() as unit_of_work:
        dispatch = unit_of_work.dispatches.get_dispatch_for_aggregation(aggregation_id)
        persisted_results = unit_of_work.aggregations.list_results(
            aggregation_id,
            limit=10,
        )
    assert dispatch is not None
    assert len(persisted_results) == 2
    results_by_person = {result.person_record_id: result for result in persisted_results}
    assert results_by_person[person_ids[0]].label is CanonicalLabel.female
    assert results_by_person[person_ids[1]].label is CanonicalLabel.male
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

    predictions_response = client.get(
        f"/api/v1/aggregations/{aggregation_id}/results/{result_id}/predictions"
    )
    assert predictions_response.status_code == 200
    method_predictions = predictions_response.json()
    assert [entry["method_execution_id"] for entry in method_predictions] == [
        str(execution_id) for execution_id in execution_ids
    ]
    predictions_by_method = {
        entry["method_name"]: entry["prediction"] for entry in method_predictions
    }
    assert predictions_by_method["local_llm"]["status"] == "success"
    assert predictions_by_method["local_llm"]["label"] == expected_label.value
    assert predictions_by_method["local_llm"]["metadata"] == {"self_reported_certainty": "high"}
    assert {
        prediction["status"]
        for method_name, prediction in predictions_by_method.items()
        if method_name != "local_llm"
    } == {"abstain"}
    with unit_of_work_factory() as unit_of_work:
        unpredicted = unit_of_work.aggregations.list_result_predictions(aggregation_id, uuid4())
    assert [(entry.prediction_id, entry.prediction) for entry in unpredicted] == [
        (None, None)
    ] * len(execution_ids)

    application.state.authentication_backend = StaticAuthenticationBackend(
        _outsider_id(unit_of_work_factory)
    )
    hidden_responses = [
        client.get(f"/api/v1/aggregations/{aggregation_id}"),
        client.get(f"/api/v1/aggregations/{aggregation_id}/results"),
        client.get(f"/api/v1/aggregations/{aggregation_id}/results/{result_id}"),
        client.get(f"/api/v1/aggregations/{aggregation_id}/results/{result_id}/predictions"),
        client.get(f"/api/v1/runs/{run_id}"),
        client.post(
            f"/api/v1/runs/{run_id}/aggregations",
            json={"method_execution_ids": [str(execution_id) for execution_id in execution_ids]},
        ),
    ]
    assert [response.status_code for response in hidden_responses] == [404] * 6


def test_repeated_aggregation_requests_reuse_live_or_completed_matches_only(
    postgres_engine: Engine,
    tmp_path: Path,
) -> None:
    unit_of_work_factory, session_factory = _unit_of_work_factory(postgres_engine)
    user_id, run_id, execution_ids, _person_ids = _seed_completed_reference_executions(
        unit_of_work_factory,
        session_factory,
    )
    client = TestClient(
        create_app(
            settings=AppSettings(
                database_url=SecretStr(DATABASE_URL),
                code_git_commit=CODE_GIT_COMMIT,
                dependency_lock_sha256=DEPENDENCY_LOCK_SHA256,
                artifact_root=tmp_path,
            ),
            unit_of_work_factory=unit_of_work_factory,
            authentication_backend=StaticAuthenticationBackend(user_id),
        )
    )
    selection = [str(execution_id) for execution_id in execution_ids]

    def create(method_execution_ids: list[str]) -> tuple[int, dict[str, object]]:
        response = client.post(
            f"/api/v1/runs/{run_id}/aggregations",
            json={"method_execution_ids": method_execution_ids},
        )
        return response.status_code, response.json()

    first_status, first = create(selection)
    queued_status, queued_repeat = create(selection)
    reordered_status, reordered = create(list(reversed(selection)))
    first_id = UUID(str(first["id"]))
    reordered_id = UUID(str(reordered["id"]))

    assert (first_status, queued_status, reordered_status) == (202, 200, 202)
    assert queued_repeat == first
    assert reordered_id != first_id

    AggregationExecutor(unit_of_work_factory=unit_of_work_factory, clock=lambda: NOW).execute(
        AggregationTaskMessage(aggregation_execution_id=first_id),
        attempt_count=1,
    )
    with unit_of_work_factory() as unit_of_work:
        unit_of_work.aggregations.claim_aggregation(reordered_id, started_at=NOW)
        unit_of_work.aggregations.mark_aggregation_finished(
            reordered_id,
            status=AggregationExecutionStatus.failed,
            finished_at=NOW,
            failure_class="FixtureFailure",
            failure_diagnostic="The fixture failed this aggregation.",
        )
        unit_of_work.commit()
    completed_status, completed_repeat = create(selection)
    retry_status, retry = create(list(reversed(selection)))
    retry_id = UUID(str(retry["id"]))

    assert completed_status == 200
    assert completed_repeat["id"] == str(first_id)
    assert completed_repeat["status"] == AggregationExecutionStatus.completed.value
    assert retry_status == 202
    assert retry_id not in {first_id, reordered_id}
    with unit_of_work_factory() as unit_of_work:
        assert unit_of_work.dispatches.get_dispatch_for_aggregation(first_id) is not None
        assert unit_of_work.dispatches.get_dispatch_for_aggregation(retry_id) is not None

    first_page = client.get(f"/api/v1/runs/{run_id}/aggregations", params={"limit": 2}).json()
    second_page = client.get(
        f"/api/v1/runs/{run_id}/aggregations",
        params={"limit": 2, "cursor": first_page["next_cursor"]},
    ).json()

    assert [item["id"] for item in first_page["items"] + second_page["items"]] == [
        str(retry_id),
        str(reordered_id),
        str(first_id),
    ]
    assert [item["status"] for item in first_page["items"] + second_page["items"]] == [
        AggregationExecutionStatus.queued.value,
        AggregationExecutionStatus.failed.value,
        AggregationExecutionStatus.completed.value,
    ]
    assert first_page["has_more"] is True
    assert second_page["has_more"] is False
    assert second_page["items"][0]["method_execution_ids"] == selection
    assert client.get(f"/api/v1/runs/{uuid4()}/aggregations").status_code == 404


def _owning_project_id(unit_of_work_factory: UnitOfWorkFactory, run_id: UUID) -> UUID:
    with unit_of_work_factory() as unit_of_work:
        run = unit_of_work.runs.get_run(run_id)
        assert run is not None
        snapshot = unit_of_work.projects.get_snapshot(run.dataset_snapshot_id)
        assert snapshot is not None
        return snapshot.project_id


def test_project_working_aggregation_points_at_ones_own_completed_aggregation(
    postgres_engine: Engine,
    tmp_path: Path,
) -> None:
    unit_of_work_factory, session_factory = _unit_of_work_factory(postgres_engine)
    user_id, run_id, execution_ids, _person_ids = _seed_completed_reference_executions(
        unit_of_work_factory,
        session_factory,
    )
    _other_user_id, other_run_id, other_execution_ids, _other_person_ids = (
        _seed_completed_reference_executions(unit_of_work_factory, session_factory)
    )
    project_id = _owning_project_id(unit_of_work_factory, run_id)

    # The other project's own completed aggregation, built directly through the service so it
    # does not need a client authenticated as that project's own operator.
    aggregation_service = AggregationService(
        unit_of_work_factory=unit_of_work_factory,
        cursor_codec=CursorCodec(),
        clock=lambda: NOW,
    )
    other_aggregation_id = aggregation_service.create_aggregation(
        run_id=other_run_id,
        command=AggregationCreateRequest(method_execution_ids=other_execution_ids),
    ).aggregation.id
    AggregationExecutor(unit_of_work_factory=unit_of_work_factory, clock=lambda: NOW).execute(
        AggregationTaskMessage(aggregation_execution_id=other_aggregation_id),
        attempt_count=1,
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
    aggregation_id = UUID(
        client.post(
            f"/api/v1/runs/{run_id}/aggregations",
            json={"method_execution_ids": [str(execution_id) for execution_id in execution_ids]},
        ).json()["id"]
    )

    not_completed_response = client.put(
        f"/api/v1/projects/{project_id}/working-aggregation",
        json={"aggregation_execution_id": str(aggregation_id)},
    )
    wrong_project_response = client.put(
        f"/api/v1/projects/{project_id}/working-aggregation",
        json={"aggregation_execution_id": str(other_aggregation_id)},
    )
    missing_aggregation_response = client.put(
        f"/api/v1/projects/{project_id}/working-aggregation",
        json={"aggregation_execution_id": str(uuid4())},
    )
    missing_project_response = client.put(
        f"/api/v1/projects/{uuid4()}/working-aggregation",
        json={"aggregation_execution_id": str(aggregation_id)},
    )

    assert not_completed_response.status_code == 409
    assert not_completed_response.json()["error"]["code"] == "resource_conflict"
    assert wrong_project_response.status_code == 404
    assert missing_aggregation_response.status_code == 404
    assert missing_project_response.status_code == 404

    AggregationExecutor(unit_of_work_factory=unit_of_work_factory, clock=lambda: NOW).execute(
        AggregationTaskMessage(aggregation_execution_id=aggregation_id),
        attempt_count=1,
    )
    pointed_response = client.put(
        f"/api/v1/projects/{project_id}/working-aggregation",
        json={"aggregation_execution_id": str(aggregation_id)},
    )
    read_after_pointing = client.get(f"/api/v1/projects/{project_id}").json()
    listed_after_pointing = client.get("/api/v1/projects").json()
    cleared_response = client.put(
        f"/api/v1/projects/{project_id}/working-aggregation",
        json={"aggregation_execution_id": None},
    )
    read_after_clearing = client.get(f"/api/v1/projects/{project_id}").json()

    assert pointed_response.status_code == 200
    assert pointed_response.json()["working_aggregation_execution_id"] == str(aggregation_id)
    assert pointed_response.json()["current_user_role"] == ProjectRole.operator.value
    assert read_after_pointing["working_aggregation_execution_id"] == str(aggregation_id)
    assert {
        item["id"]: item["working_aggregation_execution_id"]
        for item in listed_after_pointing["items"]
    }[str(project_id)] == str(aggregation_id)
    assert cleared_response.status_code == 200
    assert cleared_response.json()["working_aggregation_execution_id"] is None
    assert read_after_clearing["working_aggregation_execution_id"] is None

    application.state.authentication_backend = StaticAuthenticationBackend(
        _outsider_id(unit_of_work_factory)
    )
    hidden_response = client.put(
        f"/api/v1/projects/{project_id}/working-aggregation",
        json={"aggregation_execution_id": str(aggregation_id)},
    )
    assert hidden_response.status_code == 404
