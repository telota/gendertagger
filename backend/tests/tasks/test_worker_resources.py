from __future__ import annotations

import multiprocessing
import os
import sqlite3
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from multiprocessing.connection import Connection
from pathlib import Path
from socket import gethostname
from threading import Barrier
from typing import cast

import pytest
from celery.signals import worker_process_init, worker_process_shutdown, worker_shutdown
from pydantic import ValidationError
from sqlalchemy import Engine, event
from sqlalchemy.engine.interfaces import DBAPIConnection
from sqlalchemy.orm import Session
from sqlalchemy.pool import QueuePool

from gendertagger.db.session import (
    SessionFactory,
    create_database_engine,
    create_session_factory,
)
from gendertagger.db.unit_of_work import SqlAlchemyUnitOfWork
from gendertagger.tasks import worker_resources
from gendertagger.tasks.worker_resources import (
    WorkerClassificationResources,
    WorkerResources,
    get_worker_resources,
    reset_worker_resources,
)

pytestmark = pytest.mark.unit

_THREAD_COUNT = 8
_BUILD_COMMIT = "worker-ownership-build"
_LOCK_SHA256 = "a" * 64


@dataclass
class _InfrastructureObservations:
    engines: list[Engine] = field(default_factory=list)
    sessions: list[Session] = field(default_factory=list)
    disposed_engines: list[Engine] = field(default_factory=list)


@pytest.fixture
def infrastructure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> Iterator[_InfrastructureObservations]:
    reset_worker_resources()
    monkeypatch.setenv(
        "GENDERTAGGER_DATABASE_URL",
        "postgresql+psycopg://worker:secret@localhost/worker_ownership",
    )
    monkeypatch.setenv("GENDERTAGGER_ARTIFACT_ROOT", str(tmp_path))
    monkeypatch.setenv("GENDERTAGGER_MODEL_CACHE_ROOT", str(tmp_path / "model-cache"))
    monkeypatch.delenv("GENDERTAGGER_CODE_GIT_COMMIT", raising=False)
    monkeypatch.delenv("GENDERTAGGER_DEPENDENCY_LOCK_SHA256", raising=False)
    monkeypatch.delenv("GENDERTAGGER_CONTAINER_IMAGE_DIGEST", raising=False)
    observations = _InfrastructureObservations()

    def pool_probe() -> DBAPIConnection:
        # Exercise actual pool close/detach behavior without PostgreSQL or SQL
        # through the engine. Sessions below are created but never issue queries.
        return cast(DBAPIConnection, sqlite3.connect(":memory:"))

    def observed_engine(database_url: str) -> Engine:
        engine = create_database_engine(database_url)
        engine.pool = QueuePool(pool_probe, reset_on_return=None)
        observations.engines.append(engine)
        event.listen(engine, "engine_disposed", observations.disposed_engines.append)
        return engine

    def observed_session_factory(engine: Engine) -> SessionFactory:
        factory = create_session_factory(engine)

        def new_session() -> Session:
            session = factory()
            observations.sessions.append(session)
            return session

        return new_session

    monkeypatch.setattr(worker_resources, "create_database_engine", observed_engine)
    monkeypatch.setattr(worker_resources, "create_session_factory", observed_session_factory)
    try:
        yield observations
    finally:
        reset_worker_resources()


def _idle_pool_connection(engine: Engine) -> sqlite3.Connection:
    pooled = engine.pool.connect()
    connection = cast(sqlite3.Connection, pooled.dbapi_connection)
    pooled.close()
    return connection


def test_concurrent_worker_operations_share_one_pool_but_not_sessions(
    infrastructure: _InfrastructureObservations,
) -> None:
    ready = Barrier(_THREAD_COUNT)
    active = Barrier(_THREAD_COUNT)

    def operation(_index: int) -> tuple[WorkerResources, SqlAlchemyUnitOfWork]:
        ready.wait(timeout=10)
        owner = get_worker_resources()
        unit_of_work = owner.create_unit_of_work()
        with unit_of_work:
            active.wait(timeout=10)
        return owner, unit_of_work

    with ThreadPoolExecutor(max_workers=_THREAD_COUNT) as pool:
        operations = tuple(pool.map(operation, range(_THREAD_COUNT)))

    assert len({id(owner) for owner, _unit_of_work in operations}) == 1
    assert len({id(unit_of_work) for _owner, unit_of_work in operations}) == _THREAD_COUNT
    assert len(infrastructure.engines) == 1
    assert len({id(session) for session in infrastructure.sessions}) == _THREAD_COUNT
    assert all(
        session.get_bind() is infrastructure.engines[0] for session in infrastructure.sessions
    )
    assert infrastructure.disposed_engines == []


def test_classification_is_lazy_and_concurrently_captures_one_worker_build(
    infrastructure: _InfrastructureObservations,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner = get_worker_resources()
    with owner.create_unit_of_work():
        pass
    with pytest.raises(ValidationError, match="code_git_commit"):
        _ = owner.classification

    monkeypatch.setenv("GENDERTAGGER_CODE_GIT_COMMIT", _BUILD_COMMIT)
    monkeypatch.setenv("GENDERTAGGER_DEPENDENCY_LOCK_SHA256", _LOCK_SHA256)
    ready = Barrier(_THREAD_COUNT)

    def classification(_index: int) -> WorkerClassificationResources:
        ready.wait(timeout=10)
        return owner.classification

    with ThreadPoolExecutor(max_workers=_THREAD_COUNT) as pool:
        resources = tuple(pool.map(classification, range(_THREAD_COUNT)))

    assert len({id(resource) for resource in resources}) == 1
    provenance = resources[0].worker_provenance
    assert provenance.process_id == os.getpid()
    assert provenance.hostname == gethostname()
    assert provenance.code_git_commit == _BUILD_COMMIT
    assert provenance.dependency_lock_sha256 == _LOCK_SHA256
    assert provenance.dependency_versions
    assert len(infrastructure.engines) == 1


@pytest.mark.parametrize(
    "boundary",
    ["reset", "process_init", "process_shutdown", "worker_shutdown"],
)
def test_worker_lifecycle_closes_owned_pool_and_rejects_stale_scopes_before_reinitializing(
    boundary: str,
    infrastructure: _InfrastructureObservations,
) -> None:
    owner = get_worker_resources()
    stale_scope = owner.create_unit_of_work()
    engine = infrastructure.engines[0]
    connection = _idle_pool_connection(engine)

    for _repeat in range(2):
        if boundary == "reset":
            reset_worker_resources()
        elif boundary == "process_init":
            worker_process_init.send(sender=None)
        elif boundary == "process_shutdown":
            worker_process_shutdown.send(sender=None)
        else:
            worker_shutdown.send(sender=None)

    with pytest.raises(sqlite3.ProgrammingError, match="closed database"):
        connection.execute("SELECT 1")
    assert infrastructure.disposed_engines == [engine]
    with pytest.raises(RuntimeError, match="shut down"):
        owner.create_unit_of_work()
    with pytest.raises(RuntimeError, match="shut down"):
        stale_scope.__enter__()

    fresh_owner = get_worker_resources()
    assert fresh_owner is not owner
    with fresh_owner.create_unit_of_work():
        pass
    assert len(infrastructure.engines) == 2
    assert infrastructure.sessions[-1].get_bind() is infrastructure.engines[1]


def _observe_child_resources(
    response: Connection,
    inherited_owner: WorkerResources,
    inherited_scope: SqlAlchemyUnitOfWork,
    inherited_connection: sqlite3.Connection,
) -> None:
    try:
        # The fork callback detaches the inherited pool rather than closing its
        # physical connections. Celery's process-init is deliberately lazy.
        inherited_connection.execute("SELECT 1")
        worker_process_init.send(sender=None)
        with pytest.raises(RuntimeError, match="inherited process"):
            inherited_owner.create_unit_of_work()
        with pytest.raises(RuntimeError, match="inherited process"):
            inherited_scope.__enter__()
        owner = get_worker_resources()
        with owner.create_unit_of_work():
            pass
        provenance = owner.classification.worker_provenance
        response.send(
            {
                "process_id": os.getpid(),
                "worker_provenance": provenance.model_dump(mode="json"),
                "hostname": gethostname(),
            }
        )
    finally:
        reset_worker_resources()
        response.close()


def test_fork_detaches_parent_pool_and_recaptures_child_worker_evidence(
    infrastructure: _InfrastructureObservations,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GENDERTAGGER_CODE_GIT_COMMIT", _BUILD_COMMIT)
    monkeypatch.setenv("GENDERTAGGER_DEPENDENCY_LOCK_SHA256", _LOCK_SHA256)
    owner = get_worker_resources()
    parent_classification = owner.classification
    inherited_scope = owner.create_unit_of_work()
    parent_engine = infrastructure.engines[0]
    parent_connection = _idle_pool_connection(parent_engine)
    context = multiprocessing.get_context("fork")
    receive, send = context.Pipe(duplex=False)
    child = context.Process(
        target=_observe_child_resources,
        args=(send, owner, inherited_scope, parent_connection),
    )
    child.start()
    send.close()
    try:
        assert receive.poll(30), "forked worker did not return resource evidence"
        observed = cast(dict[str, object], receive.recv())
        child.join(timeout=30)
        assert child.exitcode == 0
        provenance = cast(dict[str, object], observed["worker_provenance"])
        assert observed["process_id"] == child.pid
        assert provenance["process_id"] == child.pid
        assert provenance["process_id"] != parent_classification.worker_provenance.process_id
        assert provenance["hostname"] == observed["hostname"]
        assert provenance["code_git_commit"] == _BUILD_COMMIT
        assert provenance["dependency_lock_sha256"] == _LOCK_SHA256
        assert provenance["dependency_versions"] == (
            parent_classification.worker_provenance.dependency_versions
        )
        assert get_worker_resources() is owner
        assert owner.classification is parent_classification
        assert _idle_pool_connection(parent_engine) is parent_connection
        assert parent_connection.execute("SELECT 1").fetchone() == (1,)
        assert infrastructure.disposed_engines == []
    finally:
        if child.is_alive():
            child.terminate()
            child.join(timeout=10)
        child.close()
        receive.close()


def test_pid_guard_detaches_inherited_pool_when_process_hooks_were_not_called(
    infrastructure: _InfrastructureObservations,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner = get_worker_resources()
    inherited_scope = owner.create_unit_of_work()
    engine = infrastructure.engines[0]
    inherited_pool = engine.pool
    connection = _idle_pool_connection(engine)
    child_process_id = os.getpid() + 1
    monkeypatch.setattr(os, "getpid", lambda: child_process_id)
    try:
        fresh_owner = get_worker_resources()
        assert fresh_owner is not owner
        assert connection.execute("SELECT 1").fetchone() == (1,)
        with pytest.raises(RuntimeError, match="inherited process"):
            owner.create_unit_of_work()
        with pytest.raises(RuntimeError, match="inherited process"):
            inherited_scope.__enter__()
        with fresh_owner.create_unit_of_work():
            pass
        assert infrastructure.disposed_engines == [engine]
        assert len(infrastructure.engines) == 2
    finally:
        inherited_pool.dispose()
