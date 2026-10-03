from __future__ import annotations

import json
import subprocess
import sys
from textwrap import dedent

import pytest
from pydantic import SecretStr

from gendertagger.models.queues import CLASSIFICATION_QUEUES, CPU_QUEUE
from gendertagger.tasks.celery_app import CelerySettings, create_celery_app


@pytest.mark.unit
def test_celery_app_uses_json_only_durable_friendly_defaults() -> None:
    app = create_celery_app(CelerySettings(celery_broker_url=SecretStr("redis://broker:6379/1")))

    assert app.conf.broker_url == "redis://broker:6379/1"
    assert app.conf.task_serializer == "json"
    assert app.conf.accept_content == ["json"]
    # Scientific results are authoritative in PostgreSQL, not the Celery backend.
    assert app.conf.result_backend is None
    assert app.conf.task_ignore_result is True
    # At-least-once delivery paired with idempotent bounded batches.
    assert app.conf.task_acks_late is True
    assert app.conf.task_reject_on_worker_lost is True
    assert app.conf.worker_prefetch_multiplier == 1
    assert app.conf.task_default_queue == "default"
    assert set(app.conf.include) == {
        "gendertagger.tasks.aggregation",
        "gendertagger.tasks.evaluation",
        "gendertagger.tasks.execution",
        "gendertagger.tasks.export",
        "gendertagger.tasks.snapshot_import",
        "gendertagger.tasks.public_classification",
    }


@pytest.mark.unit
def test_celery_app_declares_routing_class_queues() -> None:
    app = create_celery_app(CelerySettings(celery_broker_url=SecretStr("redis://broker:6379/0")))

    declared = {queue.name for queue in app.conf.task_queues}
    assert declared == set(CLASSIFICATION_QUEUES)
    assert CPU_QUEUE in declared


@pytest.mark.unit
def test_fresh_worker_loads_every_dispatch_task() -> None:
    # Test collection imports shared tasks; a fresh interpreter prevents those
    # imports from masking a missing worker include.
    startup = dedent(
        """
        import json

        from gendertagger.tasks.celery_app import app

        app.loader.init_worker()
        app.finalize()
        print(json.dumps(sorted(name for name in app.tasks if name.startswith("gendertagger."))))
        """
    )
    result = subprocess.run(  # noqa: S603 -- the interpreter and startup code are repository-controlled.
        [sys.executable, "-c", startup],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert set(json.loads(result.stdout)) == {
        "gendertagger.tasks.execute_aggregation",
        "gendertagger.tasks.execute_batch",
        "gendertagger.tasks.execute_evaluation",
        "gendertagger.tasks.execute_export",
        "gendertagger.tasks.execute_snapshot_import",
        "gendertagger.tasks.execute_public_classification",
    }


@pytest.mark.unit
def test_celery_app_enables_result_backend_only_when_configured() -> None:
    app = create_celery_app(
        CelerySettings(
            celery_broker_url=SecretStr("redis://broker:6379/0"),
            celery_result_backend=SecretStr("redis://broker:6379/2"),
        )
    )

    assert app.conf.result_backend == "redis://broker:6379/2"
    assert app.conf.task_ignore_result is False


@pytest.mark.unit
def test_celery_settings_reject_non_redis_urls() -> None:
    with pytest.raises(ValueError, match="redis://"):
        CelerySettings(celery_broker_url=SecretStr("amqp://guest@localhost//"))


@pytest.mark.integration
@pytest.mark.redis
def test_configured_broker_is_reachable() -> None:
    app = create_celery_app()
    with app.connection() as connection:
        connection.ensure_connection(max_retries=3, timeout=5)
