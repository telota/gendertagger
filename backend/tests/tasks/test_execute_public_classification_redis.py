from contextlib import AbstractContextManager
from datetime import UTC, datetime
from functools import partial
from importlib.metadata import version
from pathlib import Path
from platform import python_version
from time import monotonic, sleep
from typing import cast

import pytest
from sqlalchemy import Engine

from gendertagger.config.public_classification import PublicClassificationPolicy
from gendertagger.db.session import create_session_factory
from gendertagger.db.unit_of_work import SqlAlchemyUnitOfWork
from gendertagger.models.classification import CanonicalLabel
from gendertagger.models.public_classification import (
    PublicClassificationJob,
    PublicClassificationJobAccepted,
    PublicClassificationStatus,
    PublicClassifyNamesRequest,
)
from gendertagger.services.classification import DirectClassificationService
from gendertagger.services.dispatch import OutboxRelay
from gendertagger.services.method_registry import default_method_registry
from gendertagger.services.ports.unit_of_work import UnitOfWorkFactory
from gendertagger.services.public_classification import PublicClassificationService
from gendertagger.services.runs import RunProvenance
from gendertagger.tasks.celery_app import create_celery_app
from gendertagger.tasks.dispatch import CeleryMessagePublisher
from gendertagger.tasks.worker_resources import reset_worker_resources

pytestmark = [pytest.mark.integration, pytest.mark.redis, pytest.mark.e2e]


def test_public_names_job_runs_through_outbox_and_real_worker_with_persisted_evidence(
    repository_database_url: str,
    postgres_engine: Engine,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from celery.contrib.testing.worker import start_worker

    monkeypatch.setenv("GENDERTAGGER_DATABASE_URL", repository_database_url)
    monkeypatch.setenv("GENDERTAGGER_ARTIFACT_ROOT", str(tmp_path))
    monkeypatch.setenv("GENDERTAGGER_CODE_GIT_COMMIT", "redis-synthetic")
    monkeypatch.setenv("GENDERTAGGER_DEPENDENCY_LOCK_SHA256", "a" * 64)
    monkeypatch.delenv("GENDERTAGGER_CONTAINER_IMAGE_DIGEST", raising=False)
    reset_worker_resources()
    factory: UnitOfWorkFactory = partial(
        SqlAlchemyUnitOfWork,
        create_session_factory(postgres_engine),
    )
    registry = default_method_registry()
    service = PublicClassificationService(
        unit_of_work_factory=factory,
        method_registry=registry,
        direct_service=DirectClassificationService(method_registry=registry),
        policy=PublicClassificationPolicy(methods=["parenthetical_qualifier"]),
        provenance=RunProvenance(
            code_git_commit="redis-synthetic",
            application_version=version("gendertagger"),
            python_version=python_version(),
            dependency_lock_sha256="a" * 64,
        ),
        clock=partial(datetime.now, UTC),
    )
    accepted = service.classify(
        PublicClassifyNamesRequest(
            names=["Ada (Tochter)"] * 21,
            methods=["parenthetical_qualifier"],
        )
    )
    assert isinstance(accepted, PublicClassificationJobAccepted)
    assert accepted.status is PublicClassificationStatus.queued

    app = create_celery_app()
    relay = OutboxRelay(
        unit_of_work_factory=factory,
        publisher=CeleryMessagePublisher(app),
        relay_id="public-classification-redis-relay",
        clock=partial(datetime.now, UTC),
    )
    try:
        worker_context = cast(
            AbstractContextManager[object],
            start_worker(app, queues=["cpu"], perform_ping_check=False, shutdown_timeout=30),
        )
        with worker_context:
            assert relay.run_once().published == 1
            deadline = monotonic() + 30
            current: PublicClassificationJob = accepted
            while monotonic() < deadline:
                current = service.get_job(accepted.id, accepted.retrieval_token)
                if current.status in {
                    PublicClassificationStatus.completed,
                    PublicClassificationStatus.failed,
                }:
                    break
                sleep(0.25)

        assert current.status is PublicClassificationStatus.completed
        assert current.response is not None
        assert len(current.response.results) == 21
        assert all(
            result.classifications["parenthetical_qualifier"].label is CanonicalLabel.female
            for result in current.response.results
        )
        with factory() as unit_of_work:
            persisted = unit_of_work.public_classifications.get_job(accepted.id)
            dispatch = unit_of_work.dispatches.get_dispatch_for_classification(accepted.id)
        assert persisted is not None
        assert persisted.raw_predictions is not None
        assert len(persisted.raw_predictions) == 21
        assert persisted.raw_predictions[0]["parenthetical_qualifier"].metadata
        assert dispatch is not None
        assert dispatch.payload.model_dump(mode="json") == {
            "classification_job_id": str(accepted.id)
        }
        service.execute_job(accepted.id)
        with factory() as unit_of_work:
            assert unit_of_work.public_classifications.get_job(accepted.id) == persisted
    finally:
        app.close()
        reset_worker_resources()
