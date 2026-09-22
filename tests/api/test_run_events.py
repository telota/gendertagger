import asyncio
from dataclasses import dataclass
from typing import cast
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from gendertagger.api.app import create_app
from gendertagger.api.authentication import require_authenticated_user
from gendertagger.api.dependencies import get_project_access_service, get_run_service
from gendertagger.api.run_events import (
    METHOD_EXECUTION_PROGRESS,
    METHOD_EXECUTION_STATE_CHANGED,
    RUN_COMPLETED,
    RUN_FAILED,
    RUN_PROGRESS,
    RUN_STATE_CHANGED,
    stream_run_events,
)
from gendertagger.api.settings import AppSettings
from gendertagger.models.lifecycle import MethodExecutionStatus, RunStatus
from gendertagger.models.run import Progress
from gendertagger.models.user import CurrentUser, ProjectRole
from gendertagger.services.persistence_errors import ResourceNotFoundError
from gendertagger.services.project_access_repository import ProjectScope
from gendertagger.services.runs import RunService
from gendertagger.services.unit_of_work import UnitOfWork

pytestmark = pytest.mark.unit

RUN_ID = UUID("10000000-0000-0000-0000-000000000001")
EXECUTION_ID = UUID("20000000-0000-0000-0000-000000000001")
DATABASE_URL = "postgresql+psycopg://api:secret@localhost/gendertagger"
CODE_GIT_COMMIT = "a" * 40
DEPENDENCY_LOCK_SHA256 = "b" * 64


@dataclass(frozen=True)
class _RunView:
    id: UUID
    status: RunStatus
    progress: Progress


@dataclass(frozen=True)
class _ExecutionView:
    id: UUID
    method_name: str
    status: MethodExecutionStatus
    progress: Progress


class _SequencedRunService:
    def __init__(
        self,
        states: list[tuple[_RunView, list[_ExecutionView]]],
        *,
        disappear_during_execution_lookup: bool = False,
    ) -> None:
        self._states = states
        self._index = 0
        self._disappear_during_execution_lookup = disappear_during_execution_lookup

    def get_run(self, run_id: UUID) -> _RunView:
        assert run_id == RUN_ID
        if not self._states:
            raise ResourceNotFoundError("run disappeared")
        return self._states[self._index][0]

    def list_executions(self, run_id: UUID) -> list[_ExecutionView]:
        assert run_id == RUN_ID
        if self._disappear_during_execution_lookup:
            raise ResourceNotFoundError("run disappeared")
        executions = self._states[self._index][1]
        self._index = min(self._index + 1, len(self._states) - 1)
        return executions


def _unused_unit_of_work_factory() -> UnitOfWork:
    raise AssertionError("the event route test must not open persistence")


class _GrantingProjectAccess:
    """Grant the caller operator in every project without persistence."""

    def effective_role(
        self, user: CurrentUser, scope: ProjectScope, resource_id: UUID
    ) -> ProjectRole:
        return ProjectRole.operator

    def has_any_grant(self, user: CurrentUser) -> bool:
        return True


def _viewer() -> CurrentUser:
    return CurrentUser(
        id=UUID("30000000-0000-0000-0000-000000000001"),
        display_name="Run event viewer",
        roles=set(),
    )


def _event_client(service: object) -> TestClient:
    application = create_app(
        settings=AppSettings(
            database_url=SecretStr(DATABASE_URL),
            code_git_commit=CODE_GIT_COMMIT,
            dependency_lock_sha256=DEPENDENCY_LOCK_SHA256,
        ),
        unit_of_work_factory=_unused_unit_of_work_factory,
    )
    application.dependency_overrides[require_authenticated_user] = _viewer
    application.dependency_overrides[get_project_access_service] = _GrantingProjectAccess
    application.dependency_overrides[get_run_service] = lambda: service
    return TestClient(application)


async def _collect_events(
    service: _SequencedRunService,
    *,
    poll_interval_seconds: float = 0.0,
    max_stream_seconds: float = 1.0,
) -> list[str]:
    return [
        event
        async for event in stream_run_events(
            cast(RunService, service),
            RUN_ID,
            poll_interval_seconds=poll_interval_seconds,
            max_stream_seconds=max_stream_seconds,
        )
    ]


def _run(status: RunStatus, *, completed: int = 0, failed: int = 0) -> _RunView:
    return _RunView(
        id=RUN_ID,
        status=status,
        progress=Progress.of(total=1, completed=completed, failed=failed),
    )


def _execution(
    status: MethodExecutionStatus,
    *,
    completed: int = 0,
    failed: int = 0,
) -> _ExecutionView:
    return _ExecutionView(
        id=EXECUTION_ID,
        method_name="parenthetical_qualifier",
        status=status,
        progress=Progress.of(total=1, completed=completed, failed=failed),
    )


def test_stream_emits_only_changed_progress_and_terminal_success() -> None:
    running = (_run(RunStatus.running), [_execution(MethodExecutionStatus.running)])
    service = _SequencedRunService(
        [
            running,
            running,
            (
                _run(RunStatus.running, completed=1),
                [_execution(MethodExecutionStatus.running, completed=1)],
            ),
            (
                _run(RunStatus.completed, completed=1),
                [_execution(MethodExecutionStatus.completed, completed=1)],
            ),
        ]
    )

    events = asyncio.run(_collect_events(service))

    event_names = [event.splitlines()[0].removeprefix("event: ") for event in events]
    assert event_names == [
        RUN_STATE_CHANGED,
        RUN_PROGRESS,
        METHOD_EXECUTION_STATE_CHANGED,
        METHOD_EXECUTION_PROGRESS,
        RUN_PROGRESS,
        METHOD_EXECUTION_PROGRESS,
        RUN_STATE_CHANGED,
        METHOD_EXECUTION_STATE_CHANGED,
        RUN_COMPLETED,
    ]
    assert f'"run_id":"{RUN_ID}"' in events[-1]
    assert '"status":"completed"' in events[-1]


def test_stream_emits_failed_terminal_event() -> None:
    service = _SequencedRunService(
        [
            (
                _run(RunStatus.failed, failed=1),
                [_execution(MethodExecutionStatus.failed, failed=1)],
            )
        ]
    )

    events = asyncio.run(_collect_events(service))

    assert events[-1].startswith(f"event: {RUN_FAILED}\n")


@pytest.mark.parametrize("disappear_during_execution_lookup", [False, True])
def test_stream_stops_when_run_is_missing(disappear_during_execution_lookup: bool) -> None:
    states: list[tuple[_RunView, list[_ExecutionView]]] = (
        [(_run(RunStatus.running), [])] if disappear_during_execution_lookup else []
    )
    service = _SequencedRunService(
        states,
        disappear_during_execution_lookup=disappear_during_execution_lookup,
    )

    assert asyncio.run(_collect_events(service)) == []


def test_stream_stops_at_time_limit_for_nonterminal_run() -> None:
    service = _SequencedRunService([(_run(RunStatus.running), [])])

    events = asyncio.run(
        _collect_events(
            service,
            poll_interval_seconds=0.25,
            max_stream_seconds=0.25,
        )
    )

    assert [event.splitlines()[0] for event in events] == [
        f"event: {RUN_STATE_CHANGED}",
        f"event: {RUN_PROGRESS}",
    ]


def test_event_endpoint_reconnects_from_current_terminal_state() -> None:
    terminal = (
        _run(RunStatus.completed, completed=1),
        [_execution(MethodExecutionStatus.completed, completed=1)],
    )
    service = _SequencedRunService([terminal])

    with _event_client(service) as client:
        first = client.get(
            f"/api/v1/runs/{RUN_ID}/events",
            headers={"Last-Event-ID": "not-a-persisted-event"},
        )
        second = client.get(f"/api/v1/runs/{RUN_ID}/events")

    assert first.status_code == 200
    assert first.headers["cache-control"] == "no-cache"
    assert first.headers["x-accel-buffering"] == "no"
    assert first.headers["content-type"].startswith("text/event-stream")
    assert first.text == second.text
    assert "event: run.completed" in first.text
    assert "\nid: " not in first.text


def test_event_endpoint_rejects_missing_run_before_opening_stream() -> None:
    service = _SequencedRunService([])

    with _event_client(service) as client:
        response = client.get(f"/api/v1/runs/{RUN_ID}/events")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "resource_not_found"
