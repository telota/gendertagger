from typing import Protocol, cast
from unittest.mock import Mock
from uuid import UUID, uuid4

import pytest
from celery.exceptions import Retry
from pydantic import SecretStr, ValidationError
from sqlalchemy.exc import OperationalError

import gendertagger.tasks.public_classification as public_task
from gendertagger.models.public_classification import PublicClassificationTaskMessage
from gendertagger.tasks.dispatch import CeleryMessagePublisher

pytestmark = pytest.mark.unit

JOB_ID = UUID("10000000-0000-0000-0000-000000000001")


class _PublicClassificationTask(Protocol):
    def run(self, *, classification_job_id: str) -> None: ...


def test_public_classification_task_validates_identifier_and_calls_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = Mock()
    monkeypatch.setattr(public_task, "_public_classification_service", lambda: service)
    task = cast(_PublicClassificationTask, public_task.execute_public_classification)

    task.run(classification_job_id=str(JOB_ID))

    service.execute_job.assert_called_once_with(JOB_ID)


def test_public_classification_task_rejects_invalid_identifier_before_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = Mock()
    monkeypatch.setattr(public_task, "_public_classification_service", lambda: service)
    task = cast(_PublicClassificationTask, public_task.execute_public_classification)

    with pytest.raises(ValueError, match="badly formed hexadecimal UUID"):
        task.run(classification_job_id="unvalidated-work")

    service.execute_job.assert_not_called()


def test_public_classification_publisher_sends_only_stable_identifier() -> None:
    celery_app = Mock()
    publisher = CeleryMessagePublisher(celery_app)

    publisher.publish(
        PublicClassificationTaskMessage(classification_job_id=JOB_ID),
        queue_name="cpu",
        task_id=JOB_ID,
    )

    celery_app.send_task.assert_called_once_with(
        public_task.EXECUTE_PUBLIC_CLASSIFICATION_TASK_NAME,
        kwargs={"classification_job_id": str(JOB_ID)},
        queue="cpu",
        task_id=str(JOB_ID),
        retry=False,
    )


def test_public_classification_task_retries_transient_database_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = Mock()
    error = OperationalError("synthetic database statement", {}, RuntimeError("connection lost"))
    service.execute_job.side_effect = error
    retry = Mock(side_effect=Retry())
    monkeypatch.setattr(public_task, "_public_classification_service", lambda: service)
    monkeypatch.setattr(public_task.execute_public_classification, "retry", retry)
    monkeypatch.setattr(
        "gendertagger.tasks.public_classification.random.uniform",
        lambda _minimum, _maximum: 1.0,
    )

    with pytest.raises(Retry):
        cast(_PublicClassificationTask, public_task.execute_public_classification).run(
            classification_job_id=str(JOB_ID)
        )

    retry.assert_called_once_with(exc=error, countdown=1.0)


def test_public_classification_publisher_rejects_mismatched_task_identifier() -> None:
    celery_app = Mock()
    publisher = CeleryMessagePublisher(celery_app)

    with pytest.raises(ValueError, match="task_id must match"):
        publisher.publish(
            PublicClassificationTaskMessage(classification_job_id=JOB_ID),
            queue_name="cpu",
            task_id=uuid4(),
        )

    celery_app.send_task.assert_not_called()


def test_public_classification_worker_requires_explicit_nonblank_build_provenance() -> None:
    with pytest.raises(ValidationError, match="code_git_commit"):
        public_task.PublicClassificationWorkerSettings(
            database_url=SecretStr("postgresql+psycopg://user:password@localhost/test"),
            code_git_commit=" ",
            dependency_lock_sha256="a" * 64,
        )
