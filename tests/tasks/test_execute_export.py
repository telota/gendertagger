from typing import Protocol, cast
from unittest.mock import Mock
from uuid import UUID

import pytest
from celery.exceptions import Retry

import gendertagger.tasks.export as export_task
from gendertagger.models.export import ExportTaskMessage
from gendertagger.services.export_execution import (
    DEFAULT_MAX_EXPORT_ATTEMPTS,
    TransientExportError,
)

pytestmark = pytest.mark.unit

EXPORT_ID = UUID("10000000-0000-0000-0000-000000000001")


class _ExportTask(Protocol):
    def run(self, *, export_execution_id: str) -> None: ...


def _task_proxy() -> _ExportTask:
    """Expose Celery's untyped runtime proxy through the interface under test."""
    return cast(_ExportTask, export_task.execute_export)


def test_task_rebuilds_identifier_envelope_and_calls_executor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executor = Mock()
    monkeypatch.setattr(export_task, "_export_executor", lambda: executor)

    _task_proxy().run(
        export_execution_id=str(EXPORT_ID),
    )

    executor.execute.assert_called_once_with(
        ExportTaskMessage(export_execution_id=EXPORT_ID),
        attempt_count=1,
        max_attempts=DEFAULT_MAX_EXPORT_ATTEMPTS,
    )


def test_task_retries_only_transient_export_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executor = Mock()
    executor.execute.side_effect = TransientExportError("retry export")
    retry = Mock(side_effect=Retry())
    monkeypatch.setattr(export_task, "_export_executor", lambda: executor)
    monkeypatch.setattr(export_task.execute_export, "retry", retry)
    monkeypatch.setattr(export_task, "_retry_countdown", lambda _retries: 2.0)

    with pytest.raises(Retry):
        _task_proxy().run(
            export_execution_id=str(EXPORT_ID),
        )

    retry_kwargs = retry.call_args.kwargs
    assert isinstance(retry_kwargs["exc"], TransientExportError)
    assert retry_kwargs["countdown"] == 2.0
