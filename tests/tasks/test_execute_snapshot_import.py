from pathlib import Path
from typing import Protocol, cast
from unittest.mock import Mock
from uuid import UUID

import pytest
from celery.exceptions import Retry
from pydantic import SecretStr, ValidationError

import gendertagger.tasks.snapshot_import as snapshot_import_task
from gendertagger.models.project import SnapshotImportTaskMessage
from gendertagger.services.snapshot_import import (
    DEFAULT_MAX_SNAPSHOT_IMPORT_ATTEMPTS,
    TransientSnapshotImportError,
)

pytestmark = pytest.mark.unit

SNAPSHOT_ID = UUID("20000000-0000-0000-0000-000000000001")
DATABASE_URL = "postgresql+psycopg://worker:secret@db/gendertagger"


class _SnapshotImportTask(Protocol):
    def run(self, *, dataset_snapshot_id: str) -> None: ...


def _task_proxy() -> _SnapshotImportTask:
    """Expose Celery's untyped runtime proxy through the interface under test."""
    return cast(_SnapshotImportTask, snapshot_import_task.execute_snapshot_import)


def test_task_rebuilds_identifier_envelope_and_calls_executor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executor = Mock()
    monkeypatch.setattr(snapshot_import_task, "_snapshot_import_executor", lambda: executor)

    _task_proxy().run(dataset_snapshot_id=str(SNAPSHOT_ID))

    executor.execute.assert_called_once_with(
        SnapshotImportTaskMessage(dataset_snapshot_id=SNAPSHOT_ID),
        attempt_count=1,
        max_attempts=DEFAULT_MAX_SNAPSHOT_IMPORT_ATTEMPTS,
    )


def test_task_retries_only_transient_import_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executor = Mock()
    executor.execute.side_effect = TransientSnapshotImportError("retry import")
    retry = Mock(side_effect=Retry())
    monkeypatch.setattr(snapshot_import_task, "_snapshot_import_executor", lambda: executor)
    monkeypatch.setattr(snapshot_import_task.execute_snapshot_import, "retry", retry)
    monkeypatch.setattr(snapshot_import_task, "_retry_countdown", lambda _retries: 2.0)

    with pytest.raises(Retry):
        _task_proxy().run(dataset_snapshot_id=str(SNAPSHOT_ID))

    retry_kwargs = retry.call_args.kwargs
    assert isinstance(retry_kwargs["exc"], TransientSnapshotImportError)
    assert retry_kwargs["countdown"] == 2.0


def test_worker_settings_share_the_api_artifact_and_batch_configuration(tmp_path: Path) -> None:
    settings = snapshot_import_task.SnapshotImportWorkerSettings(
        database_url=SecretStr(DATABASE_URL),
        artifact_root=tmp_path,
        tei_import_batch_record_count=123,
    )

    assert settings.artifact_root == tmp_path
    assert settings.tei_import_batch_record_count == 123

    with pytest.raises(ValidationError, match="greater than 0"):
        snapshot_import_task.SnapshotImportWorkerSettings(
            database_url=SecretStr(DATABASE_URL),
            tei_import_batch_record_count=0,
        )
