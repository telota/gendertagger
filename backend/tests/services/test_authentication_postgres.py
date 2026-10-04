"""Credential mutations serialize across independent PostgreSQL transactions (RG-01)."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from functools import partial
from queue import Queue
from threading import Event
from time import monotonic, sleep
from typing import Literal
from uuid import UUID

import pytest
from sqlalchemy import Engine, func, select, text
from sqlalchemy.orm import Session
from tests.passwords import hash_fixture_password

from gendertagger.db.repositories.auth_repository import SqlAlchemyAuthRepository
from gendertagger.db.repositories.user_repository import SqlAlchemyUserRepository
from gendertagger.db.rows.auth import UserCredentialRow
from gendertagger.db.rows.users import UserRow
from gendertagger.db.session import SessionFactory, create_session_factory
from gendertagger.db.unit_of_work import SqlAlchemyUnitOfWork
from gendertagger.models.user import User, UserCreate
from gendertagger.services.authentication import (
    AuthenticationService,
    InvalidCurrentPasswordError,
    SessionLifetimePolicy,
)
from gendertagger.services.pagination import CursorCodec
from gendertagger.services.password_hashing import Argon2PasswordHasher, PasswordHasherProtocol
from gendertagger.services.ports.unit_of_work import UnitOfWorkFactory
from gendertagger.services.user_administration import UserAdministrationService

pytestmark = [pytest.mark.integration, pytest.mark.postgres]

_INITIAL_PASSWORD = "initial-synthetic-passphrase"
_CHANGED_PASSWORD = "changed-synthetic-passphrase"
_RESET_PASSWORD = "reset-synthetic-passphrase"
_NOW = datetime(2026, 10, 4, 12, tzinfo=UTC)
_SESSION_IDS = ("a" * 64, "b" * 64)
_ResetPath = Literal["administration", "direct"]


def _authentication_service(
    factory: UnitOfWorkFactory,
    hasher: PasswordHasherProtocol | None = None,
) -> AuthenticationService:
    return AuthenticationService(
        unit_of_work_factory=factory,
        password_hasher=hasher or Argon2PasswordHasher(),
        clock=lambda: _NOW,
        session_lifetime=SessionLifetimePolicy(),
    )


def _seed_account(
    factory: UnitOfWorkFactory,
    *,
    is_active: bool = True,
    must_change_password: bool = True,
) -> UUID:
    with factory() as unit_of_work:
        user = unit_of_work.users.add_user(
            UserCreate(display_name="Synthetic credential owner", is_active=is_active)
        )
        unit_of_work.auth.add_credential(
            user_id=user.id,
            username="synthetic-credential-owner",
            password_hash=hash_fixture_password(_INITIAL_PASSWORD),
        )
        if not must_change_password:
            unit_of_work.auth.set_password(
                user_id=user.id,
                password_hash=hash_fixture_password(_INITIAL_PASSWORD),
                must_change_password=False,
            )
        for session_id in _SESSION_IDS:
            unit_of_work.auth.create_session(
                session_id=session_id,
                user_id=user.id,
                csrf_secret="synthetic-csrf-secret",
                keep_signed_in=False,
                expires_at=_NOW + timedelta(days=1),
                absolute_expires_at=_NOW + timedelta(days=30),
            )
        unit_of_work.commit()
    return user.id


def _reset_password(factory: UnitOfWorkFactory, user_id: UUID, path: _ResetPath) -> str:
    authentication = _authentication_service(factory)
    if path == "direct":
        authentication.reset_password(user_id=user_id, new_password=_RESET_PASSWORD)
        return _RESET_PASSWORD
    administration = UserAdministrationService(
        unit_of_work_factory=factory,
        cursor_codec=CursorCodec(),
        authentication_service=authentication,
    )
    return administration.reset_user_password(
        user_id,
        actor_user_id=user_id,
        request_id="synthetic-credential-race",
    ).temporary_password


def _change_password(service: AuthenticationService, user_id: UUID, new_password: str) -> str:
    try:
        service.change_password(
            user_id=user_id,
            current_password=_INITIAL_PASSWORD,
            new_password=new_password,
        )
    except InvalidCurrentPasswordError:
        return "invalid_current_password"
    return "changed"


class _PausingPasswordHasher(Argon2PasswordHasher):
    """Pause a verified user change while its transaction still owns credential protection."""

    def __init__(self, verified: Event, release: Event) -> None:
        super().__init__()
        self._verified = verified
        self._release = release

    def verify(self, password_hash: str, password: str) -> bool:
        result = super().verify(password_hash, password)
        self._verified.set()
        assert self._release.wait(timeout=10)
        return result


class _CoordinatedUserRepository(SqlAlchemyUserRepository):
    """Expose lock contention and optionally hold the first mutation after its user lock."""

    def __init__(
        self,
        session: Session,
        *,
        acquired: Event | None,
        release: Event | None,
        backend_pids: Queue[int] | None,
    ) -> None:
        super().__init__(session)
        self._acquired = acquired
        self._release = release
        self._backend_pids = backend_pids

    def get_user_for_update(self, user_id: UUID) -> User | None:
        if self._backend_pids is not None:
            backend_pid = self._session.scalar(select(func.pg_backend_pid()))
            assert isinstance(backend_pid, int)
            self._backend_pids.put(backend_pid)
        user = super().get_user_for_update(user_id)
        if self._acquired is not None:
            self._acquired.set()
        if self._release is not None:
            assert self._release.wait(timeout=10)
        return user


class _CoordinatedUnitOfWork(SqlAlchemyUnitOfWork):
    """Give each racing service its own database session and coordinated user repository."""

    def __init__(
        self,
        session_factory: SessionFactory,
        *,
        acquired: Event | None = None,
        release: Event | None = None,
        backend_pids: Queue[int] | None = None,
    ) -> None:
        super().__init__(session_factory)
        self._acquired = acquired
        self._release = release
        self._backend_pids = backend_pids

    @property
    def users(self) -> SqlAlchemyUserRepository:
        return _CoordinatedUserRepository(
            self._require_session(),
            acquired=self._acquired,
            release=self._release,
            backend_pids=self._backend_pids,
        )


def _waits_for_row_lock(postgres_engine: Engine, backend_pid: int) -> bool:
    deadline = monotonic() + 5
    while monotonic() < deadline:
        with postgres_engine.connect() as observer:
            waiting = observer.execute(
                text("SELECT wait_event_type FROM pg_stat_activity WHERE pid = :backend_pid"),
                {"backend_pid": backend_pid},
            ).scalar_one_or_none()
        if waiting == "Lock":
            return True
        sleep(0.01)
    return False


def _assert_reset_state(factory: UnitOfWorkFactory, user_id: UUID, reset_password: str) -> None:
    with factory() as unit_of_work:
        credential = unit_of_work.auth.get_credential(user_id)
        assert credential is not None
        assert Argon2PasswordHasher().verify(credential.password_hash, reset_password)
        assert not Argon2PasswordHasher().verify(credential.password_hash, _CHANGED_PASSWORD)
        assert credential.must_change_password is True
        for session_id in _SESSION_IDS:
            session = unit_of_work.auth.get_session(session_id)
            assert session is not None
            assert session.revoked_at is not None


@pytest.mark.parametrize("reset_path", ["administration", "direct"])
def test_password_reset_waits_for_verified_user_change_and_preserves_its_reset(
    postgres_engine: Engine, reset_path: _ResetPath
) -> None:
    session_factory = create_session_factory(postgres_engine)
    factory: UnitOfWorkFactory = partial(SqlAlchemyUnitOfWork, session_factory)
    user_id = _seed_account(factory)
    verified, release_change = Event(), Event()
    change_service = _authentication_service(
        factory, _PausingPasswordHasher(verified, release_change)
    )
    backend_pids: Queue[int] = Queue()
    reset_factory = partial(_CoordinatedUnitOfWork, session_factory, backend_pids=backend_pids)

    with ThreadPoolExecutor(max_workers=2) as pool:
        changing = pool.submit(_change_password, change_service, user_id, _CHANGED_PASSWORD)
        try:
            assert verified.wait(timeout=5)
            resetting = pool.submit(_reset_password, reset_factory, user_id, reset_path)
            assert _waits_for_row_lock(postgres_engine, backend_pids.get(timeout=5))
        finally:
            release_change.set()
        assert changing.result(timeout=10) == "changed"
        reset_password = resetting.result(timeout=10)

    _assert_reset_state(factory, user_id, reset_password)


@pytest.mark.parametrize("reset_path", ["administration", "direct"])
def test_user_change_waits_for_reset_and_rejects_the_superseded_password(
    postgres_engine: Engine, reset_path: _ResetPath
) -> None:
    session_factory = create_session_factory(postgres_engine)
    factory: UnitOfWorkFactory = partial(SqlAlchemyUnitOfWork, session_factory)
    user_id = _seed_account(factory)
    acquired, release_reset = Event(), Event()
    reset_factory = partial(
        _CoordinatedUnitOfWork, session_factory, acquired=acquired, release=release_reset
    )
    backend_pids: Queue[int] = Queue()
    change_factory = partial(_CoordinatedUnitOfWork, session_factory, backend_pids=backend_pids)

    with ThreadPoolExecutor(max_workers=2) as pool:
        resetting = pool.submit(_reset_password, reset_factory, user_id, reset_path)
        try:
            assert acquired.wait(timeout=5)
            changing = pool.submit(
                _change_password,
                _authentication_service(change_factory),
                user_id,
                _CHANGED_PASSWORD,
            )
            assert _waits_for_row_lock(postgres_engine, backend_pids.get(timeout=5))
        finally:
            release_reset.set()
        reset_password = resetting.result(timeout=10)
        assert changing.result(timeout=10) == "invalid_current_password"

    _assert_reset_state(factory, user_id, reset_password)


def test_concurrent_user_changes_keep_only_the_first_verified_replacement(
    postgres_engine: Engine,
) -> None:
    session_factory = create_session_factory(postgres_engine)
    factory: UnitOfWorkFactory = partial(SqlAlchemyUnitOfWork, session_factory)
    user_id = _seed_account(factory)
    verified, release_first = Event(), Event()
    first_service = _authentication_service(
        factory, _PausingPasswordHasher(verified, release_first)
    )
    backend_pids: Queue[int] = Queue()
    second_factory = partial(_CoordinatedUnitOfWork, session_factory, backend_pids=backend_pids)

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(_change_password, first_service, user_id, _CHANGED_PASSWORD)
        try:
            assert verified.wait(timeout=5)
            second = pool.submit(
                _change_password, _authentication_service(second_factory), user_id, _RESET_PASSWORD
            )
            assert _waits_for_row_lock(postgres_engine, backend_pids.get(timeout=5))
        finally:
            release_first.set()
        assert first.result(timeout=10) == "changed"
        assert second.result(timeout=10) == "invalid_current_password"

    with factory() as unit_of_work:
        credential = unit_of_work.auth.get_credential(user_id)
        assert credential is not None
        assert Argon2PasswordHasher().verify(credential.password_hash, _CHANGED_PASSWORD)
        assert credential.must_change_password is False
        for session_id in _SESSION_IDS:
            session = unit_of_work.auth.get_session(session_id)
            assert session is not None
            assert session.revoked_at is None


class _FailingCommitUnitOfWork(SqlAlchemyUnitOfWork):
    """Abort after credential and revocation writes to verify complete transaction rollback."""

    def commit(self) -> None:
        raise RuntimeError("synthetic commit failure")


@pytest.mark.parametrize("reset_path", ["administration", "direct"])
def test_failed_password_reset_rolls_back_credential_and_sessions_and_releases_locks(
    postgres_engine: Engine, reset_path: _ResetPath
) -> None:
    session_factory = create_session_factory(postgres_engine)
    factory: UnitOfWorkFactory = partial(SqlAlchemyUnitOfWork, session_factory)
    user_id = _seed_account(factory, must_change_password=False)
    failing_factory = partial(_FailingCommitUnitOfWork, session_factory)

    with pytest.raises(RuntimeError, match="synthetic commit failure"):
        _reset_password(failing_factory, user_id, reset_path)

    with factory() as unit_of_work:
        credential = unit_of_work.auth.get_credential(user_id)
        assert credential is not None
        assert credential.password_hash == hash_fixture_password(_INITIAL_PASSWORD)
        assert credential.must_change_password is False
        for session_id in _SESSION_IDS:
            session = unit_of_work.auth.get_session(session_id)
            assert session is not None
            assert session.revoked_at is None
    assert (
        _change_password(_authentication_service(factory), user_id, _CHANGED_PASSWORD) == "changed"
    )


def test_inactive_account_cannot_complete_a_user_password_change(postgres_engine: Engine) -> None:
    factory: UnitOfWorkFactory = partial(
        SqlAlchemyUnitOfWork, create_session_factory(postgres_engine)
    )
    user_id = _seed_account(factory, is_active=False)

    assert (
        _change_password(_authentication_service(factory), user_id, _CHANGED_PASSWORD)
        == "invalid_current_password"
    )
    with factory() as unit_of_work:
        credential = unit_of_work.auth.get_credential(user_id)
        assert credential is not None
        assert credential.password_hash == hash_fixture_password(_INITIAL_PASSWORD)
        assert credential.must_change_password is True


def test_waiting_password_change_rechecks_account_after_completed_deactivation(
    postgres_engine: Engine,
) -> None:
    session_factory = create_session_factory(postgres_engine)
    factory: UnitOfWorkFactory = partial(SqlAlchemyUnitOfWork, session_factory)
    user_id = _seed_account(factory)
    backend_pids: Queue[int] = Queue()
    change_factory = partial(_CoordinatedUnitOfWork, session_factory, backend_pids=backend_pids)

    with ThreadPoolExecutor(max_workers=1) as pool:
        with session_factory.begin() as deactivation_session:
            user = deactivation_session.get(UserRow, user_id, with_for_update=True)
            assert user is not None
            user.is_active = False
            deactivation_session.flush()
            SqlAlchemyAuthRepository(deactivation_session).revoke_all_sessions(user_id)
            changing = pool.submit(
                _change_password,
                _authentication_service(change_factory),
                user_id,
                _CHANGED_PASSWORD,
            )
            assert _waits_for_row_lock(postgres_engine, backend_pids.get(timeout=5))
        assert changing.result(timeout=10) == "invalid_current_password"

    with factory() as unit_of_work:
        credential = unit_of_work.auth.get_credential(user_id)
        assert credential is not None
        assert credential.password_hash == hash_fixture_password(_INITIAL_PASSWORD)
        assert credential.must_change_password is True
        for session_id in _SESSION_IDS:
            session = unit_of_work.auth.get_session(session_id)
            assert session is not None
            assert session.revoked_at is not None


def test_credential_locks_refresh_previously_loaded_account_and_credential_state(
    postgres_engine: Engine,
) -> None:
    session_factory = create_session_factory(postgres_engine)
    factory: UnitOfWorkFactory = partial(SqlAlchemyUnitOfWork, session_factory)
    user_id = _seed_account(factory, must_change_password=False)

    with session_factory() as stale_session:
        cached_user = stale_session.get(UserRow, user_id)
        cached_credential = stale_session.get(UserCredentialRow, user_id)
        assert cached_user is not None
        assert cached_credential is not None
        assert cached_user.is_active is True
        assert cached_credential.password_hash == hash_fixture_password(_INITIAL_PASSWORD)
        assert cached_credential.must_change_password is False
        with session_factory.begin() as fresh_session:
            user_row = fresh_session.get(UserRow, user_id)
            assert user_row is not None
            user_row.is_active = False
            SqlAlchemyAuthRepository(fresh_session).set_password(
                user_id=user_id,
                password_hash=hash_fixture_password(_RESET_PASSWORD),
                must_change_password=True,
            )

        user = SqlAlchemyUserRepository(stale_session).get_user_for_update(user_id)
        credential = SqlAlchemyAuthRepository(stale_session).get_credential_for_update(user_id)
        assert user is not None
        assert user.is_active is False
        assert credential is not None
        assert credential.password_hash == hash_fixture_password(_RESET_PASSWORD)
        assert credential.must_change_password is True
