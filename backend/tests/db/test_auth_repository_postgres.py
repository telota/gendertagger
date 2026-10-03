from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from gendertagger.db.repositories.auth_repository import SqlAlchemyAuthRepository
from gendertagger.db.repositories.user_repository import SqlAlchemyUserRepository
from gendertagger.models.user import UserCreate
from gendertagger.services.ports.persistence_errors import DuplicateUsernameError

pytestmark = [pytest.mark.integration, pytest.mark.postgres]

SESSION_ID = "a" * 64
LOGIN_AT = datetime(2026, 9, 21, 9, tzinfo=UTC)


def _auth_repository_with_session(db_session: Session) -> SqlAlchemyAuthRepository:
    user = SqlAlchemyUserRepository(db_session).add_user(
        UserCreate(display_name="Synthetic reviewer")
    )
    auth = SqlAlchemyAuthRepository(db_session)
    auth.create_session(
        session_id=SESSION_ID,
        user_id=user.id,
        csrf_secret="csrf-secret",
        keep_signed_in=True,
        expires_at=LOGIN_AT + timedelta(days=7),
        absolute_expires_at=LOGIN_AT + timedelta(days=30),
    )
    return auth


@pytest.mark.postgres_rollback
def test_created_session_round_trips_its_kind_and_limits(db_session: Session) -> None:
    auth = _auth_repository_with_session(db_session)

    session = auth.get_session(SESSION_ID)

    assert session is not None
    assert session.keep_signed_in is True
    assert session.expires_at == LOGIN_AT + timedelta(days=7)
    assert session.absolute_expires_at == LOGIN_AT + timedelta(days=30)


@pytest.mark.postgres_rollback
def test_renew_session_moves_the_expiry_forward_but_never_backwards(db_session: Session) -> None:
    auth = _auth_repository_with_session(db_session)

    auth.renew_session(SESSION_ID, expires_at=LOGIN_AT + timedelta(days=8))
    auth.renew_session(SESSION_ID, expires_at=LOGIN_AT + timedelta(days=7, hours=12))
    db_session.expire_all()

    session = auth.get_session(SESSION_ID)
    assert session is not None
    assert session.expires_at == LOGIN_AT + timedelta(days=8)


@pytest.mark.postgres_rollback
def test_renew_session_leaves_a_revoked_session_untouched(db_session: Session) -> None:
    auth = _auth_repository_with_session(db_session)
    auth.revoke_session(SESSION_ID)

    auth.renew_session(SESSION_ID, expires_at=LOGIN_AT + timedelta(days=8))
    db_session.expire_all()

    session = auth.get_session(SESSION_ID)
    assert session is not None
    assert session.revoked_at is not None
    assert session.expires_at == LOGIN_AT + timedelta(days=7)


@pytest.mark.postgres_rollback
def test_session_expiry_cannot_pass_its_absolute_limit(db_session: Session) -> None:
    auth = _auth_repository_with_session(db_session)

    with pytest.raises(IntegrityError, match="ck_user_sessions_expiry_within_lifetime"):
        auth.renew_session(SESSION_ID, expires_at=LOGIN_AT + timedelta(days=31))


@pytest.mark.postgres_rollback
def test_duplicate_username_is_translated_to_application_error(db_session: Session) -> None:
    users = SqlAlchemyUserRepository(db_session)
    first_user = users.add_user(UserCreate(display_name="First local user"))
    second_user = users.add_user(UserCreate(display_name="Second local user"))
    auth = SqlAlchemyAuthRepository(db_session)
    auth.add_credential(
        user_id=first_user.id,
        username="duplicate-user",
        password_hash="first-hash",
    )

    with pytest.raises(DuplicateUsernameError, match="duplicate-user"):
        auth.add_credential(
            user_id=second_user.id,
            username="duplicate-user",
            password_hash="second-hash",
        )
