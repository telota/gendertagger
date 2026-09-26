from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi import Request
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import Engine, select

from gendertagger.api.app import create_app
from gendertagger.api.authentication import AuthenticationBackend
from gendertagger.api.settings import AppSettings
from gendertagger.db.rows.dispatches import DispatchOutboxRow
from gendertagger.db.rows.executions import MethodExecutionRow, TaskBatchRow
from gendertagger.db.session import create_session_factory
from gendertagger.db.unit_of_work import SqlAlchemyUnitOfWork
from gendertagger.ingestion.tei import TeiPersonParser
from gendertagger.models.classification import (
    CanonicalLabel,
    PredictionResult,
    PredictionStatus,
)
from gendertagger.models.dispatch import DispatchStatus
from gendertagger.models.lifecycle import RunStatus, TaskBatchStatus
from gendertagger.models.method import MethodDescriptor
from gendertagger.models.project import SnapshotImportTaskMessage
from gendertagger.models.run import MethodExecutionCreate, PredictionWrite, TaskBatchPlan
from gendertagger.models.team import TeamCreate
from gendertagger.models.user import GlobalRole, UserCreate
from gendertagger.services.ports.unit_of_work import UnitOfWork, UnitOfWorkFactory
from gendertagger.services.snapshot_import import SnapshotImportExecutor
from gendertagger.storage.local import LocalArtifactStorage

pytestmark = [pytest.mark.integration, pytest.mark.postgres]

DATABASE_URL = "postgresql+psycopg://unused:unused@localhost/unused"
CODE_GIT_COMMIT = "c" * 40
DEPENDENCY_LOCK_SHA256 = "d" * 64
VALID_TEI = b"""<TEI xmlns="http://www.tei-c.org/ns/1.0">
<text><body><listPerson><person xml:id="p1"><persName type="reg"><surname>Example</surname></persName></person></listPerson></body></text>
</TEI>"""
MULTI_PERSON_TEI = b"""<TEI xmlns="http://www.tei-c.org/ns/1.0">
<text><body><listPerson>
<person xml:id="p1"><persName type="reg"><forename>Ada</forename><surname>Unknown</surname></persName></person>
<person xml:id="p2"><persName type="reg"><forename>Bea</forename><surname>Abstained</surname></persName></person>
<person xml:id="p3"><persName type="reg"><forename>Cam</forename><surname>Errored</surname></persName></person>
<person xml:id="p4"><persName type="reg"><forename>Dee</forename><surname>Missing</surname></persName></person>
</listPerson></body></text>
</TEI>"""


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
) -> tuple[TestClient, UnitOfWorkFactory]:
    unit_of_work_factory = _unit_of_work_factory(postgres_engine)
    with unit_of_work_factory() as unit_of_work:
        operator = unit_of_work.users.add_user(
            UserCreate(display_name="Run operator", roles={GlobalRole.operator})
        )
        team = unit_of_work.teams.add_team(
            TeamCreate(slug=f"run-{operator.id.hex}", display_name="Run fixture team")
        )
        unit_of_work.teams.add_member(team.id, operator.id)
        unit_of_work.commit()
    application = create_app(
        settings=AppSettings(
            database_url=SecretStr(DATABASE_URL),
            code_git_commit=CODE_GIT_COMMIT,
            dependency_lock_sha256=DEPENDENCY_LOCK_SHA256,
            artifact_root=artifact_root,
        ),
        unit_of_work_factory=unit_of_work_factory,
        authentication_backend=StaticAuthenticationBackend(operator.id),
    )
    return TestClient(application), unit_of_work_factory


def _ready_snapshot_id(
    client: TestClient,
    unit_of_work_factory: UnitOfWorkFactory,
    artifact_root: Path,
    *,
    source: bytes = VALID_TEI,
) -> UUID:
    project_response = client.post(
        "/api/v1/projects",
        json={
            "slug": f"run-{uuid4().hex}",
            "display_name": "Run endpoint fixture",
            "team_id": client.get("/api/v1/teams").json()["items"][0]["id"],
        },
    )
    project_id = UUID(project_response.json()["id"])
    snapshot_response = client.post(
        f"/api/v1/projects/{project_id}/snapshots",
        files={"source": ("register.xml", source, "application/xml")},
    )
    snapshot_id = UUID(snapshot_response.json()["id"])
    SnapshotImportExecutor(
        unit_of_work_factory=unit_of_work_factory,
        artifact_storage=LocalArtifactStorage(artifact_root),
        parser=TeiPersonParser(),
        import_batch_record_count=1,
        clock=lambda: datetime(2026, 8, 14, 12, tzinfo=UTC),
    ).execute(
        SnapshotImportTaskMessage(dataset_snapshot_id=snapshot_id),
        attempt_count=1,
    )
    return snapshot_id


def test_created_run_round_trips_with_server_owned_provenance(
    postgres_engine: Engine,
    tmp_path: Path,
) -> None:
    client, unit_of_work_factory = _client(postgres_engine, tmp_path)
    snapshot_id = _ready_snapshot_id(client, unit_of_work_factory, tmp_path)

    create_response = client.post(
        "/api/v1/runs",
        json={"dataset_snapshot_id": str(snapshot_id), "config": {"methods": []}},
    )

    assert create_response.status_code == 202
    body = create_response.json()
    assert body["status"] == RunStatus.created.value
    assert body["dataset_snapshot_id"] == str(snapshot_id)
    assert body["resolved_config"] == {
        "methods": [],
        "aggregation": {"strategy": "reference_v1"},
        "execution": {"fail_run_on_optional_method_error": False},
    }
    assert body["code_git_commit"] == CODE_GIT_COMMIT
    assert body["dependency_lock_sha256"] == DEPENDENCY_LOCK_SHA256
    assert body["application_version"] == "0.0.0"
    assert body["python_version"]
    assert "task_id" not in body

    run_id = UUID(body["id"])
    read_response = client.get(f"/api/v1/runs/{run_id}")
    assert read_response.status_code == 200
    assert read_response.json() == body


def test_run_creation_rejects_unregistered_method_and_client_provenance(
    postgres_engine: Engine,
    tmp_path: Path,
) -> None:
    client, unit_of_work_factory = _client(postgres_engine, tmp_path)
    snapshot_id = _ready_snapshot_id(client, unit_of_work_factory, tmp_path)

    unknown_method_response = client.post(
        "/api/v1/runs",
        json={
            "dataset_snapshot_id": str(snapshot_id),
            "config": {"methods": [{"name": "not_registered"}]},
        },
    )
    client_provenance_response = client.post(
        "/api/v1/runs",
        json={
            "dataset_snapshot_id": str(snapshot_id),
            "config": {"methods": []},
            "code_git_commit": "untrusted",
        },
    )

    assert unknown_method_response.status_code == 422
    assert client_provenance_response.status_code == 422


def test_run_executions_are_scheduled_with_durable_dispatch_intent(
    postgres_engine: Engine,
    tmp_path: Path,
) -> None:
    client, unit_of_work_factory = _client(postgres_engine, tmp_path)
    snapshot_id = _ready_snapshot_id(client, unit_of_work_factory, tmp_path)
    create_response = client.post(
        "/api/v1/runs",
        json={
            "dataset_snapshot_id": str(snapshot_id),
            "config": {"methods": [{"name": "parenthetical_qualifier"}]},
        },
    )
    run_id = create_response.json()["id"]

    start_response = client.post(f"/api/v1/runs/{run_id}/executions")

    assert start_response.status_code == 202
    body = start_response.json()
    assert body["status"] == RunStatus.running.value
    assert "task_id" not in body
    with create_session_factory(postgres_engine)() as session:
        dispatch = session.scalar(
            select(DispatchOutboxRow)
            .join(TaskBatchRow, DispatchOutboxRow.task_batch_id == TaskBatchRow.id)
            .join(
                MethodExecutionRow,
                TaskBatchRow.method_execution_id == MethodExecutionRow.id,
            )
            .where(MethodExecutionRow.run_id == UUID(run_id))
        )
    assert dispatch is not None
    assert dispatch.status is DispatchStatus.pending
    assert dispatch.queue_name == "cpu"
    assert dispatch.payload["task_batch_id"] == str(dispatch.task_batch_id)

    # A run already scheduled cannot be scheduled again.
    conflict = client.post(f"/api/v1/runs/{run_id}/executions")
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "resource_conflict"


def test_start_executions_rejects_unknown_run(
    postgres_engine: Engine,
    tmp_path: Path,
) -> None:
    client, _ = _client(postgres_engine, tmp_path)

    response = client.post(f"/api/v1/runs/{uuid4()}/executions")

    assert response.status_code == 404


def test_run_and_executions_expose_progress(
    postgres_engine: Engine,
    tmp_path: Path,
) -> None:
    client, unit_of_work_factory = _client(postgres_engine, tmp_path)
    snapshot_id = _ready_snapshot_id(client, unit_of_work_factory, tmp_path)
    run_id = client.post(
        "/api/v1/runs",
        json={
            "dataset_snapshot_id": str(snapshot_id),
            "config": {"methods": [{"name": "parenthetical_qualifier"}]},
        },
    ).json()["id"]

    created_run = client.get(f"/api/v1/runs/{run_id}").json()
    assert created_run["progress"] == {
        "total": None,
        "completed": 0,
        "failed": 0,
        "percentage": None,
    }
    assert client.get(f"/api/v1/runs/{run_id}/executions").json() == []

    client.post(f"/api/v1/runs/{run_id}/executions")

    executions = client.get(f"/api/v1/runs/{run_id}/executions")
    assert executions.status_code == 200
    (execution,) = executions.json()
    assert execution["method_name"] == "parenthetical_qualifier"
    assert execution["progress"]["total"] == 1
    assert execution["progress"]["completed"] == 0  # dispatched but not executed
    # Queue routing and worker provenance stay behind the public client boundary.
    assert "queue_name" not in execution
    assert "worker_metadata" not in execution

    run_progress = client.get(f"/api/v1/runs/{run_id}").json()["progress"]
    assert run_progress["total"] == 1
    assert run_progress["completed"] == 0


def test_list_executions_rejects_unknown_run(
    postgres_engine: Engine,
    tmp_path: Path,
) -> None:
    client, _ = _client(postgres_engine, tmp_path)

    response = client.get(f"/api/v1/runs/{uuid4()}/executions")

    assert response.status_code == 404


def test_run_events_stream_projects_terminal_state(
    postgres_engine: Engine,
    tmp_path: Path,
) -> None:
    client, unit_of_work_factory = _client(postgres_engine, tmp_path)
    snapshot_id = _ready_snapshot_id(client, unit_of_work_factory, tmp_path)
    run_id = client.post(
        "/api/v1/runs",
        json={"dataset_snapshot_id": str(snapshot_id), "config": {"methods": []}},
    ).json()["id"]
    # A run with no methods completes as soon as it is scheduled.
    client.post(f"/api/v1/runs/{run_id}/executions")

    with client.stream("GET", f"/api/v1/runs/{run_id}/events") as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        body = response.read().decode()

    assert "event: run.state_changed" in body
    assert "event: run.progress" in body
    assert "event: run.completed" in body
    # Reconnect-safe: the authoritative state is available via a plain GET.
    assert client.get(f"/api/v1/runs/{run_id}").json()["status"] == RunStatus.completed.value


def test_run_events_reject_unknown_run(
    postgres_engine: Engine,
    tmp_path: Path,
) -> None:
    client, _ = _client(postgres_engine, tmp_path)

    response = client.get(f"/api/v1/runs/{uuid4()}/events")

    assert response.status_code == 404


def test_project_snapshots_and_snapshot_runs_list_newest_first(
    postgres_engine: Engine,
    tmp_path: Path,
) -> None:
    client, unit_of_work_factory = _client(postgres_engine, tmp_path)
    ready_snapshot_id = _ready_snapshot_id(client, unit_of_work_factory, tmp_path)
    project_id = client.get(f"/api/v1/snapshots/{ready_snapshot_id}").json()["project_id"]
    pending_snapshot = client.post(
        f"/api/v1/projects/{project_id}/snapshots",
        files={"source": ("register.xml", VALID_TEI, "application/xml")},
    ).json()

    snapshots = client.get(f"/api/v1/projects/{project_id}/snapshots")

    assert snapshots.status_code == 200
    assert [(snapshot["id"], snapshot["status"]) for snapshot in snapshots.json()["items"]] == [
        (pending_snapshot["id"], "pending"),
        (str(ready_snapshot_id), "ready"),
    ]
    assert snapshots.json()["has_more"] is False

    idle_run = client.post(
        "/api/v1/runs",
        json={"dataset_snapshot_id": str(ready_snapshot_id), "config": {"methods": []}},
    ).json()
    scheduled_run_id = client.post(
        "/api/v1/runs",
        json={
            "dataset_snapshot_id": str(ready_snapshot_id),
            "config": {"methods": [{"name": "parenthetical_qualifier"}]},
        },
    ).json()["id"]
    client.post(f"/api/v1/runs/{scheduled_run_id}/executions")

    first_page = client.get(
        f"/api/v1/snapshots/{ready_snapshot_id}/runs", params={"limit": 1}
    ).json()
    second_page = client.get(
        f"/api/v1/snapshots/{ready_snapshot_id}/runs",
        params={"limit": 1, "cursor": first_page["next_cursor"]},
    ).json()

    # A listed run carries the same progress its detail read computes one run at a time.
    assert first_page["items"] == [client.get(f"/api/v1/runs/{scheduled_run_id}").json()]
    assert first_page["items"][0]["progress"]["total"] == 1
    assert second_page["items"] == [idle_run]
    assert (first_page["has_more"], second_page["has_more"]) == (True, False)
    assert client.get(f"/api/v1/snapshots/{pending_snapshot['id']}/runs").json() == {
        "items": [],
        "next_cursor": None,
        "has_more": False,
    }
    assert client.get(f"/api/v1/snapshots/{uuid4()}/runs").status_code == 404
    assert client.get(f"/api/v1/projects/{uuid4()}/snapshots").status_code == 404
    invalid_cursor = client.get(
        f"/api/v1/snapshots/{ready_snapshot_id}/runs",
        params={"cursor": second_page["items"][0]["id"]},
    )
    assert invalid_cursor.status_code == 422


def _persist_method_execution_results(
    unit_of_work_factory: UnitOfWorkFactory,
    *,
    snapshot_id: UUID,
    run_id: UUID,
) -> UUID:
    """Persist a partial execution through repositories for the public read fixture."""
    now = datetime(2026, 9, 26, 12, tzinfo=UTC)
    with unit_of_work_factory() as unit_of_work:
        run = unit_of_work.runs.get_run(run_id)
        assert run is not None
        unit_of_work.runs.mark_run_queued(run.id)
        unit_of_work.runs.mark_run_started(run.id, started_at=now)
        execution = unit_of_work.runs.add_method_execution(
            MethodExecutionCreate(
                run_id=run.id,
                descriptor=MethodDescriptor(
                    name="gender_guesser",
                    implementation_version="gender_guesser_v1",
                    normalization_version="gender_guesser_v1",
                ),
                resolved_config=dict(run.resolved_config.methods[0].config),
                queue_name="cpu",
                total_count=4,
            )
        )
        unit_of_work.runs.mark_execution_queued(execution.id)
        unit_of_work.runs.mark_execution_started(execution.id, started_at=now)
        records = unit_of_work.projects.list_person_records_slice(
            snapshot_id,
            offset=0,
            limit=4,
        )
        assert len(records) == 4
        batches = unit_of_work.runs.create_task_batches(
            execution.id,
            [
                TaskBatchPlan(batch_index=index, record_offset=index, record_count=1)
                for index in range(4)
            ],
        )
        expected = {
            "p1": PredictionResult(
                label=CanonicalLabel.unknown,
                status=PredictionStatus.success,
                method_confidence=0.8,
                raw_label="uncertain",
                raw_output={"internal": "not part of list response"},
                metadata={"normalization": "test-only"},
            ),
            "p2": PredictionResult(
                label=None,
                status=PredictionStatus.abstain,
                raw_label="no_name",
            ),
            "p3": PredictionResult(
                label=None,
                status=PredictionStatus.error,
                raw_label="timeout",
            ),
        }
        for batch, record in zip(batches, records, strict=True):
            claimed = unit_of_work.runs.claim_batch(
                batch.id,
                method_execution_id=execution.id,
                worker_task_id=f"method-result-{batch.batch_index}",
                started_at=now,
                attempt_count=1,
            )
            assert claimed is not None
            result = expected.get(record.tei_id)
            if result is None:
                unit_of_work.runs.mark_batch_finished(
                    batch.id,
                    status=TaskBatchStatus.failed,
                    finished_at=now,
                    error_count=1,
                    failure_class="FixtureFailure",
                    failure_diagnostic="result not persisted",
                )
                continue
            unit_of_work.runs.add_predictions(
                execution.id,
                [
                    PredictionWrite(
                        person_record_id=record.id,
                        task_batch_id=batch.id,
                        input_fingerprint="f" * 64,
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
                error_count=int(result.status is PredictionStatus.error),
            )
        unit_of_work.runs.finalize_execution_if_complete(execution.id, finished_at=now)
        unit_of_work.runs.finalize_run_if_complete(run.id, finished_at=now)
        unit_of_work.commit()
    return execution.id


def test_method_execution_results_list_is_paginated_filtered_and_execution_scoped(
    postgres_engine: Engine,
    tmp_path: Path,
) -> None:
    client, unit_of_work_factory = _client(postgres_engine, tmp_path)
    snapshot_id = _ready_snapshot_id(
        client,
        unit_of_work_factory,
        tmp_path,
        source=MULTI_PERSON_TEI,
    )
    run = client.post(
        "/api/v1/runs",
        json={
            "dataset_snapshot_id": str(snapshot_id),
            "config": {"methods": [{"name": "gender_guesser"}]},
        },
    ).json()
    run_id = UUID(run["id"])
    execution_id = _persist_method_execution_results(
        unit_of_work_factory,
        snapshot_id=snapshot_id,
        run_id=run_id,
    )
    results_url = f"/api/v1/runs/{run_id}/executions/{execution_id}/results"

    first = client.get(results_url, params={"limit": 2})
    assert first.status_code == 200
    first_body = first.json()
    assert [item["tei_id"] for item in first_body["items"]] == ["p1", "p2"]
    assert first_body["has_more"] is True
    assert first_body["next_cursor"] is not None
    first_item, abstained_item = first_body["items"]
    assert first_item["method_execution_id"] == str(execution_id)
    assert first_item["dataset_snapshot_id"] == str(snapshot_id)
    assert first_item["person_record_id"]
    assert first_item["tei_id"] == "p1"
    assert first_item["surname"] == "Unknown"
    assert first_item["forenames"] == ["Ada"]
    assert first_item["result_state"] == "success"
    assert first_item["prediction_id"]
    assert first_item["prediction"] == {
        "label": "unknown",
        "status": "success",
        "method_confidence": 0.8,
        "raw_label": "uncertain",
    }
    assert set(first_item["prediction"]) == {
        "label",
        "status",
        "method_confidence",
        "raw_label",
    }
    assert abstained_item["result_state"] == "abstain"
    assert abstained_item["prediction"] == {
        "label": None,
        "status": "abstain",
        "method_confidence": None,
        "raw_label": "no_name",
    }

    second = client.get(
        results_url,
        params={"limit": 2, "cursor": first_body["next_cursor"]},
    )
    assert second.status_code == 200
    second_body = second.json()
    assert [item["tei_id"] for item in second_body["items"]] == ["p3", "p4"]
    errored_item, missing_item = second_body["items"]
    assert errored_item["result_state"] == "error"
    assert errored_item["prediction"] == {
        "label": None,
        "status": "error",
        "method_confidence": None,
        "raw_label": "timeout",
    }
    assert missing_item["result_state"] == "missing"
    assert missing_item["prediction_id"] is None
    assert missing_item["prediction"] is None
    assert second_body["has_more"] is False
    assert second_body["next_cursor"] is None

    assert [
        item["tei_id"]
        for item in client.get(
            results_url,
            params={"result_state": "missing"},
        ).json()["items"]
    ] == ["p4"]
    assert [
        item["tei_id"]
        for item in client.get(
            results_url,
            params={"result_state": "success", "label": "unknown"},
        ).json()["items"]
    ] == ["p1"]
    assert [
        item["tei_id"]
        for item in client.get(
            results_url,
            params={"q": "Errored"},
        ).json()["items"]
    ] == ["p3"]
    assert (
        client.get(
            results_url,
            params={"result_state": "missing", "cursor": first_body["next_cursor"]},
        ).status_code
        == 422
    )

    unrelated_run = client.post(
        "/api/v1/runs",
        json={"dataset_snapshot_id": str(snapshot_id), "config": {"methods": []}},
    ).json()
    assert (
        client.get(
            f"/api/v1/runs/{unrelated_run['id']}/executions/{execution_id}/results"
        ).status_code
        == 404
    )
