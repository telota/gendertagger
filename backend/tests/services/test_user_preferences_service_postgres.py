"""Concurrent preference updates use independent PostgreSQL transactions."""

from concurrent.futures import ThreadPoolExecutor
from functools import partial
from threading import Barrier
from uuid import UUID

import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from gendertagger.db.repositories.user_repository import SqlAlchemyUserRepository
from gendertagger.db.rows.auth import UserCredentialRow
from gendertagger.db.rows.user_preferences import UserPreferencesRow
from gendertagger.db.rows.users import UserRow
from gendertagger.db.session import SessionFactory, create_session_factory
from gendertagger.db.unit_of_work import SqlAlchemyUnitOfWork
from gendertagger.models.user import User
from gendertagger.models.user_preferences import UserPreferences, UserPreferencesUpdate
from gendertagger.services.ports.unit_of_work import UnitOfWorkFactory
from gendertagger.services.user_preferences import (
    PreferencesRevisionConflictError,
    UserPreferencesService,
)

pytestmark = [pytest.mark.integration, pytest.mark.postgres]


class SynchronizedUserRepository(SqlAlchemyUserRepository):
    """Start both transaction lock requests only once both writers are ready."""

    def __init__(self, session: Session, barrier: Barrier) -> None:
        super().__init__(session)
        self._barrier = barrier

    def get_user_for_update(self, user_id: UUID) -> User | None:
        self._barrier.wait(timeout=10)
        return super().get_user_for_update(user_id)


class SynchronizedUnitOfWork(SqlAlchemyUnitOfWork):
    def __init__(self, session_factory: SessionFactory, barrier: Barrier) -> None:
        super().__init__(session_factory)
        self._barrier = barrier

    @property
    def users(self) -> SynchronizedUserRepository:
        return SynchronizedUserRepository(self._require_session(), self._barrier)


@pytest.mark.parametrize("has_saved_preferences", [False, True])
def test_concurrent_preferences_writes_keep_one_winner_and_one_stale_conflict(
    postgres_engine: Engine, has_saved_preferences: bool
) -> None:
    session_factory = create_session_factory(postgres_engine)
    initial_revision = 7 if has_saved_preferences else 0
    with session_factory.begin() as session:
        user = UserRow(display_name="Concurrent preference owner")
        session.add(user)
        session.flush()
        user_id = user.id
        session.add(
            UserCredentialRow(
                user_id=user_id,
                username="concurrent_preferences",
                password_hash="unused-by-preferences",
                must_change_password=False,
            )
        )
        if has_saved_preferences:
            session.add(UserPreferencesRow(user_id=user_id, revision=initial_revision))
    barrier = Barrier(2)
    factory: UnitOfWorkFactory = partial(SynchronizedUnitOfWork, session_factory, barrier)
    commands = [
        UserPreferencesUpdate(
            expected_revision=initial_revision,
            locale="de",
            theme="dark",
            desktop_sidebar_collapsed=True,
        ),
        UserPreferencesUpdate(expected_revision=initial_revision, locale="en", theme="light"),
    ]

    def mutate(
        command: UserPreferencesUpdate,
    ) -> UserPreferences | PreferencesRevisionConflictError:
        service = UserPreferencesService(unit_of_work_factory=factory)
        try:
            return service.update_preferences(command, user_id=user_id)
        except PreferencesRevisionConflictError as error:
            return error

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(mutate, command) for command in commands]
        outcomes = [future.result(timeout=15) for future in futures]

    winners = [outcome for outcome in outcomes if isinstance(outcome, UserPreferences)]
    conflicts = [
        outcome for outcome in outcomes if isinstance(outcome, PreferencesRevisionConflictError)
    ]
    assert len(winners) == len(conflicts) == 1
    assert winners[0].revision == initial_revision + 1
    assert conflicts[0].expected_revision == initial_revision
    assert conflicts[0].current_revision == initial_revision + 1
    with SqlAlchemyUnitOfWork(session_factory) as unit_of_work:
        assert unit_of_work.user_preferences.get_preferences(user_id) == winners[0]
    assert winners[0] in (
        UserPreferences(
            locale="de", theme="dark", desktop_sidebar_collapsed=True, revision=initial_revision + 1
        ),
        UserPreferences(locale="en", theme="light", revision=initial_revision + 1),
    )
