from concurrent.futures import ThreadPoolExecutor
from functools import partial
from queue import Queue
from threading import Barrier, Event
from time import monotonic, sleep
from unittest.mock import Mock
from uuid import UUID

import pytest
from sqlalchemy import Engine, func, select, text
from sqlalchemy.orm import Session

from gendertagger.db.repositories.user_repository import SqlAlchemyUserRepository
from gendertagger.db.session import SessionFactory, create_session_factory
from gendertagger.db.unit_of_work import SqlAlchemyUnitOfWork
from gendertagger.models.auth import AdminUserUpdate
from gendertagger.models.user import GlobalRole, UserCreate
from gendertagger.services.authentication import AuthenticationService
from gendertagger.services.pagination import CursorCodec
from gendertagger.services.ports.unit_of_work import UnitOfWorkFactory
from gendertagger.services.user_administration import (
    AdminUserStateConflictError,
    UserAdministrationService,
)

pytestmark = [pytest.mark.integration, pytest.mark.postgres]


def _service(factory: UnitOfWorkFactory) -> UserAdministrationService:
    return UserAdministrationService(
        unit_of_work_factory=factory,
        cursor_codec=CursorCodec(),
        authentication_service=Mock(spec=AuthenticationService),
    )


def _add_local_administrator(factory: UnitOfWorkFactory, username: str) -> UUID:
    with factory() as unit_of_work:
        user = unit_of_work.users.add_user(
            UserCreate(display_name=username, roles={GlobalRole.admin})
        )
        unit_of_work.auth.add_credential(
            user_id=user.id,
            username=username,
            password_hash="not-used-by-this-test",
        )
        unit_of_work.commit()
    return user.id


class _CoordinatedUserRepository(SqlAlchemyUserRepository):
    def __init__(
        self,
        session: Session,
        *,
        lock_acquired: Event | None = None,
        release_lock: Event | None = None,
        backend_pids: Queue[int] | None = None,
    ) -> None:
        super().__init__(session)
        self._lock_acquired = lock_acquired
        self._release_lock = release_lock
        self._backend_pids = backend_pids

    def lock_administrator_updates(self) -> None:
        if self._backend_pids is not None:
            backend_pid = self._session.scalar(select(func.pg_backend_pid()))
            assert isinstance(backend_pid, int)
            self._backend_pids.put(backend_pid)
        super().lock_administrator_updates()
        if self._lock_acquired is not None:
            self._lock_acquired.set()
        if self._release_lock is not None:
            assert self._release_lock.wait(timeout=5)


class _CoordinatedUnitOfWork(SqlAlchemyUnitOfWork):
    def __init__(
        self,
        session_factory: SessionFactory,
        *,
        lock_acquired: Event | None = None,
        release_lock: Event | None = None,
        backend_pids: Queue[int] | None = None,
    ) -> None:
        super().__init__(session_factory)
        self._lock_acquired = lock_acquired
        self._release_lock = release_lock
        self._backend_pids = backend_pids

    @property
    def users(self) -> SqlAlchemyUserRepository:
        return _CoordinatedUserRepository(
            self._require_session(),
            lock_acquired=self._lock_acquired,
            release_lock=self._release_lock,
            backend_pids=self._backend_pids,
        )


def _waits_for_advisory_lock(postgres_engine: Engine, backend_pid: int) -> bool:
    deadline = monotonic() + 5
    while monotonic() < deadline:
        with postgres_engine.connect() as observer:
            wait_event = observer.execute(
                text("SELECT wait_event FROM pg_stat_activity WHERE pid = :backend_pid"),
                {"backend_pid": backend_pid},
            ).scalar_one_or_none()
        if wait_event == "advisory":
            return True
        sleep(0.01)
    return False


def test_concurrent_administrator_deactivations_leave_one_active_administrator(
    postgres_engine: Engine,
) -> None:
    """Retain concurrent deactivation coverage under administrator update serialization."""
    factory: UnitOfWorkFactory = partial(
        SqlAlchemyUnitOfWork,
        create_session_factory(postgres_engine),
    )
    first_administrator_id = _add_local_administrator(factory, "first-administrator")
    second_administrator_id = _add_local_administrator(factory, "second-administrator")
    requests_ready = Barrier(2)

    def deactivate_other(actor_user_id: UUID, target_user_id: UUID) -> str:
        requests_ready.wait(timeout=10)
        try:
            _service(factory).update_user(
                target_user_id,
                AdminUserUpdate(is_active=False),
                actor_user_id=actor_user_id,
                request_id="concurrent-admin-update",
            )
        except AdminUserStateConflictError as error:
            return error.code
        return "updated"

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = [
            future.result(timeout=15)
            for future in (
                pool.submit(
                    deactivate_other,
                    first_administrator_id,
                    second_administrator_id,
                ),
                pool.submit(
                    deactivate_other,
                    second_administrator_id,
                    first_administrator_id,
                ),
            )
        ]

    assert sorted(outcomes) == ["acting_user_not_active_administrator", "updated"]
    with factory() as unit_of_work:
        active_administrator_ids = unit_of_work.users.get_active_administrator_ids()
    assert len(active_administrator_ids) == 1
    assert set(active_administrator_ids) <= {
        first_administrator_id,
        second_administrator_id,
    }


def test_waiting_administrator_cannot_demote_the_only_remaining_administrator(
    postgres_engine: Engine,
) -> None:
    session_factory = create_session_factory(postgres_engine)
    factory: UnitOfWorkFactory = partial(SqlAlchemyUnitOfWork, session_factory)
    first_administrator_id = _add_local_administrator(factory, "first-administrator")
    second_administrator_id = _add_local_administrator(factory, "second-administrator")
    first_lock_acquired = Event()
    release_first = Event()
    waiting_backend_pids: Queue[int] = Queue(maxsize=1)
    first_service = _service(
        partial(
            _CoordinatedUnitOfWork,
            session_factory,
            lock_acquired=first_lock_acquired,
            release_lock=release_first,
        )
    )
    second_service = _service(
        partial(
            _CoordinatedUnitOfWork,
            session_factory,
            backend_pids=waiting_backend_pids,
        )
    )

    def demote_administrator(
        service: UserAdministrationService,
        actor_user_id: UUID,
        target_user_id: UUID,
    ) -> str:
        try:
            service.update_user(
                target_user_id,
                AdminUserUpdate(roles=set()),
                actor_user_id=actor_user_id,
                request_id="concurrent-role-demotion",
            )
        except AdminUserStateConflictError as error:
            return error.code
        return "updated"

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(
            demote_administrator,
            first_service,
            first_administrator_id,
            second_administrator_id,
        )
        assert first_lock_acquired.wait(timeout=5)
        second = pool.submit(
            demote_administrator,
            second_service,
            second_administrator_id,
            first_administrator_id,
        )
        waiting_backend_pid = waiting_backend_pids.get(timeout=5)
        try:
            assert _waits_for_advisory_lock(postgres_engine, waiting_backend_pid)
        finally:
            release_first.set()
        assert first.result(timeout=5) == "updated"
        assert second.result(timeout=5) == "acting_user_not_active_administrator"

    with factory() as unit_of_work:
        active_administrator_ids = unit_of_work.users.get_active_administrator_ids()
    assert active_administrator_ids == {first_administrator_id}
