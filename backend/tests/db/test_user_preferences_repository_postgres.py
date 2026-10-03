"""PostgreSQL mapping and integrity coverage for account preferences."""

from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine, func, insert, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from gendertagger.db.repositories.user_preferences_repository import (
    SqlAlchemyUserPreferencesRepository,
)
from gendertagger.db.rows.user_preferences import UserPreferencesRow
from gendertagger.db.rows.users import UserRow
from gendertagger.db.session import create_session_factory
from gendertagger.db.unit_of_work import SqlAlchemyUnitOfWork
from gendertagger.models.user_preferences import UserPreferences

pytestmark = [pytest.mark.integration, pytest.mark.postgres]


def _add_user(session: Session) -> UUID:
    row = UserRow(display_name="Preference owner")
    session.add(row)
    session.flush()
    return row.id


@pytest.mark.postgres_rollback
def test_preferences_read_does_not_materialize_defaults(db_session: Session) -> None:
    user_id = _add_user(db_session)
    repository = SqlAlchemyUserPreferencesRepository(db_session)

    assert repository.get_preferences(user_id) is None
    assert db_session.scalar(select(func.count()).select_from(UserPreferencesRow)) == 0


@pytest.mark.postgres_rollback
def test_preferences_repository_round_trip_keeps_account_values_separate(
    db_session: Session,
) -> None:
    first_user_id = _add_user(db_session)
    second_user_id = _add_user(db_session)
    repository = SqlAlchemyUserPreferencesRepository(db_session)
    first = UserPreferences(locale="de", theme="dark", desktop_sidebar_collapsed=True, revision=1)
    second = UserPreferences(locale="en", theme="light", revision=3)
    repository.save_preferences(first_user_id, first)
    repository.save_preferences(second_user_id, second)
    db_session.expire_all()

    assert repository.get_preferences(first_user_id) == first
    assert repository.get_preferences(second_user_id) == second

    cleared = UserPreferences(theme="dark", desktop_sidebar_collapsed=True, revision=2)
    repository.save_preferences(first_user_id, cleared)
    db_session.expire_all()

    assert repository.get_preferences(first_user_id) == cleared
    assert repository.get_preferences(second_user_id) == second
    assert db_session.scalar(select(func.count()).select_from(UserPreferencesRow)) == 2


@pytest.mark.parametrize(
    "invalid_values",
    [
        {"locale": "fr"},
        {"theme": "auto"},
        {"theme": None},
        {"desktop_sidebar_collapsed": None},
        {"revision": -1},
        {"revision": None},
    ],
)
@pytest.mark.postgres_rollback
def test_preferences_database_rejects_invalid_values(
    db_session: Session, invalid_values: dict[str, Any]
) -> None:
    user_id = _add_user(db_session)
    with pytest.raises(IntegrityError), db_session.begin_nested():
        db_session.execute(insert(UserPreferencesRow).values(user_id=user_id, **invalid_values))


@pytest.mark.postgres_rollback
def test_preferences_database_rejects_missing_owner_and_duplicate_rows(db_session: Session) -> None:
    with pytest.raises(IntegrityError), db_session.begin_nested():
        db_session.execute(insert(UserPreferencesRow).values(user_id=uuid4()))

    user_id = _add_user(db_session)
    db_session.execute(insert(UserPreferencesRow).values(user_id=user_id))
    with pytest.raises(IntegrityError), db_session.begin_nested():
        db_session.execute(insert(UserPreferencesRow).values(user_id=user_id))


def test_preferences_uncommitted_initialization_and_update_are_rolled_back(
    postgres_engine: Engine,
) -> None:
    session_factory = create_session_factory(postgres_engine)
    with session_factory.begin() as session:
        user_id = _add_user(session)
    committed = UserPreferences(locale="de", theme="dark", revision=1)

    with SqlAlchemyUnitOfWork(session_factory) as unit_of_work:
        unit_of_work.users.get_user_for_update(user_id)
        unit_of_work.user_preferences.save_preferences(user_id, committed)
    with SqlAlchemyUnitOfWork(session_factory) as unit_of_work:
        assert unit_of_work.user_preferences.get_preferences(user_id) is None
        unit_of_work.users.get_user_for_update(user_id)
        unit_of_work.user_preferences.save_preferences(user_id, committed)
        unit_of_work.commit()
    with SqlAlchemyUnitOfWork(session_factory) as unit_of_work:
        unit_of_work.users.get_user_for_update(user_id)
        unit_of_work.user_preferences.save_preferences(
            user_id, UserPreferences(locale="en", theme="light", revision=2)
        )
    with SqlAlchemyUnitOfWork(session_factory) as unit_of_work:
        assert unit_of_work.user_preferences.get_preferences(user_id) == committed
