from datetime import UTC, datetime
from types import TracebackType
from typing import Self, cast
from unittest.mock import ANY, Mock
from uuid import UUID

import pytest

from gendertagger.models.auth import (
    AdminUser,
    AdminUserCreate,
    AdminUserUpdate,
    LocalCredential,
)
from gendertagger.models.user import GlobalRole, User
from gendertagger.services.authentication import AuthenticationService
from gendertagger.services.pagination import CursorCodec, InvalidCursorError
from gendertagger.services.ports.auth_repository import AdminUserCursor, AuthRepository
from gendertagger.services.ports.persistence_errors import ResourceNotFoundError
from gendertagger.services.ports.unit_of_work import UnitOfWork
from gendertagger.services.ports.user_repository import UserRepository
from gendertagger.services.user_administration import (
    AdminUserStateConflictError,
    UserAdministrationService,
)

pytestmark = pytest.mark.unit

NOW = datetime(2026, 9, 24, 10, 0, tzinfo=UTC)
USER_IDS = (
    UUID("10000000-0000-0000-0000-000000000001"),
    UUID("10000000-0000-0000-0000-000000000002"),
    UUID("10000000-0000-0000-0000-000000000003"),
)


class _UnitOfWork:
    def __init__(self, auth: AuthRepository, users: UserRepository | None = None) -> None:
        self.auth = auth
        self.users = users or Mock(spec=UserRepository)
        self.commit = Mock()

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        return None


def _user(index: int) -> AdminUser:
    return AdminUser(
        id=USER_IDS[index],
        display_name=f"User {index}",
        username=f"user{index}",
        roles={GlobalRole.admin} if index == 0 else set(),
        is_active=True,
        must_change_password=index == 2,
        created_at=NOW,
    )


def _service(
    repository: AuthRepository,
    authentication_service: AuthenticationService | None = None,
    users: UserRepository | None = None,
) -> UserAdministrationService:
    unit_of_work = _UnitOfWork(repository, users)

    def factory() -> UnitOfWork:
        return cast(UnitOfWork, unit_of_work)

    return UserAdministrationService(
        unit_of_work_factory=factory,
        cursor_codec=CursorCodec(),
        authentication_service=authentication_service or Mock(spec=AuthenticationService),
    )


def test_user_directory_normalizes_search_and_paginates() -> None:
    repository = Mock(spec=AuthRepository)
    users = [_user(index) for index in range(3)]
    repository.list_admin_users.side_effect = [users, [users[2]]]
    service = _service(repository)

    first_page = service.list_users(query="  USER  ", limit=2, cursor=None)
    second_page = service.list_users(query="user", limit=2, cursor=first_page.next_cursor)

    assert first_page.items == users[:2]
    assert first_page.has_more is True
    assert second_page.items == users[2:]
    assert second_page.has_more is False
    assert repository.list_admin_users.call_args_list[0].kwargs == {
        "search": "user",
        "limit": 3,
        "after": None,
    }
    assert repository.list_admin_users.call_args_list[1].kwargs == {
        "search": "user",
        "limit": 3,
        "after": AdminUserCursor(username="user1", user_id=USER_IDS[1]),
    }


def test_user_directory_scopes_cursor_to_normalized_search() -> None:
    repository = Mock(spec=AuthRepository)
    repository.list_admin_users.return_value = [_user(0), _user(1)]
    service = _service(repository)
    first_page = service.list_users(query="user", limit=1, cursor=None)

    with pytest.raises(InvalidCursorError, match="different resource"):
        service.list_users(query="other", limit=1, cursor=first_page.next_cursor)
    with pytest.raises(ValueError, match="limit must be positive"):
        service.list_users(query=None, limit=0, cursor=None)


def test_create_user_returns_once_disclosed_temporary_password_and_logs_context(
    caplog: pytest.LogCaptureFixture,
) -> None:
    repository = Mock(spec=AuthRepository)
    authentication_service = Mock(spec=AuthenticationService)
    authentication_service.create_local_account.return_value = User(
        id=USER_IDS[1],
        display_name="New user",
        roles={GlobalRole.operator},
        is_active=True,
        created_at=NOW,
        updated_at=NOW,
    )
    service = _service(repository, authentication_service)
    command = AdminUserCreate(
        display_name="New user",
        username="  NEW.USER  ",
        roles={GlobalRole.operator},
    )

    with caplog.at_level("INFO"):
        result = service.create_user(
            command,
            actor_user_id=USER_IDS[0],
            request_id="request-123",
        )

    assert result.account == AdminUser(
        id=USER_IDS[1],
        display_name="New user",
        username="new.user",
        roles={GlobalRole.operator},
        is_active=True,
        must_change_password=True,
        created_at=NOW,
    )
    assert len(result.temporary_password) >= 12
    authentication_service.create_local_account.assert_called_once_with(
        display_name="New user",
        roles={GlobalRole.operator},
        username="new.user",
        password=result.temporary_password,
    )
    assert str(USER_IDS[0]) in caplog.text
    assert str(USER_IDS[1]) in caplog.text
    assert "request-123" in caplog.text
    assert result.temporary_password not in caplog.text


def _local_credential(index: int) -> LocalCredential:
    return LocalCredential(
        user_id=USER_IDS[index],
        username=f"user{index}",
        password_hash="not-exposed",
        must_change_password=False,
        updated_at=NOW,
    )


def test_update_user_applies_only_supplied_fields_revokes_sessions_and_logs(
    caplog: pytest.LogCaptureFixture,
) -> None:
    auth = Mock(spec=AuthRepository)
    users = Mock(spec=UserRepository)
    target = User(
        id=USER_IDS[1],
        display_name="Existing user",
        roles=set(),
        is_active=True,
        created_at=NOW,
        updated_at=NOW,
    )
    updated = target.model_copy(
        update={
            "display_name": "Renamed user",
            "roles": {GlobalRole.operator},
            "is_active": False,
        }
    )
    users.get_active_administrator_ids.return_value = {USER_IDS[0]}
    users.get_user_for_update.return_value = target
    users.update_user.return_value = updated
    auth.get_credential.return_value = _local_credential(1)
    service = _service(auth, users=users)

    with caplog.at_level("INFO"):
        account = service.update_user(
            USER_IDS[1],
            AdminUserUpdate(
                display_name="Renamed user",
                roles={GlobalRole.operator},
                is_active=False,
            ),
            actor_user_id=USER_IDS[0],
            request_id="request-456",
        )

    assert account.display_name == "Renamed user"
    assert account.roles == {GlobalRole.operator}
    assert account.is_active is False
    users.update_user.assert_called_once_with(
        user_id=USER_IDS[1],
        display_name="Renamed user",
        roles={GlobalRole.operator},
        is_active=False,
    )
    auth.revoke_all_sessions.assert_called_once_with(USER_IDS[1])
    users.lock_administrator_updates.assert_called_once_with()
    assert "request-456" in caplog.text
    assert "display_name,roles,is_active" in caplog.text


def test_update_user_is_idempotent_when_requested_state_already_holds() -> None:
    auth = Mock(spec=AuthRepository)
    users = Mock(spec=UserRepository)
    target = User(
        id=USER_IDS[1],
        display_name="Existing user",
        roles={GlobalRole.operator},
        is_active=True,
        created_at=NOW,
        updated_at=NOW,
    )
    users.get_active_administrator_ids.return_value = {USER_IDS[0]}
    users.get_user_for_update.return_value = target
    auth.get_credential.return_value = _local_credential(1)
    service = _service(auth, users=users)

    account = service.update_user(
        USER_IDS[1],
        AdminUserUpdate(is_active=True),
        actor_user_id=USER_IDS[0],
        request_id="request-789",
    )

    assert account.display_name == "Existing user"
    users.update_user.assert_not_called()
    auth.revoke_all_sessions.assert_not_called()


@pytest.mark.parametrize(
    ("command", "code"),
    [
        (AdminUserUpdate(is_active=False), "self_deactivation_forbidden"),
        (AdminUserUpdate(roles={GlobalRole.operator}), "self_admin_role_removal_forbidden"),
    ],
)
def test_update_user_rejects_self_administrator_state_changes(
    command: AdminUserUpdate,
    code: str,
) -> None:
    auth = Mock(spec=AuthRepository)
    users = Mock(spec=UserRepository)
    target = User(
        id=USER_IDS[0],
        display_name="Administrator",
        roles={GlobalRole.admin},
        is_active=True,
        created_at=NOW,
        updated_at=NOW,
    )
    users.get_active_administrator_ids.return_value = {USER_IDS[0]}
    users.get_user_for_update.return_value = target
    auth.get_credential.return_value = _local_credential(0)
    service = _service(auth, users=users)

    with pytest.raises(AdminUserStateConflictError) as error:
        service.update_user(
            USER_IDS[0],
            command,
            actor_user_id=USER_IDS[0],
            request_id="request-012",
        )

    assert error.value.code == code
    users.update_user.assert_not_called()


def test_update_user_hides_missing_and_nonlocal_accounts() -> None:
    auth = Mock(spec=AuthRepository)
    users = Mock(spec=UserRepository)
    users.get_active_administrator_ids.return_value = {USER_IDS[0]}
    users.get_user_for_update.return_value = None
    auth.get_credential.return_value = None
    service = _service(auth, users=users)

    with pytest.raises(ResourceNotFoundError):
        service.update_user(
            USER_IDS[2],
            AdminUserUpdate(display_name="No account"),
            actor_user_id=USER_IDS[0],
            request_id="request-345",
        )


def test_reset_user_password_preserves_activation_and_logs_no_secret(
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    auth = Mock(spec=AuthRepository)
    users = Mock(spec=UserRepository)
    target = User(
        id=USER_IDS[1],
        display_name="Inactive user",
        roles=set(),
        is_active=False,
        created_at=NOW,
        updated_at=NOW,
    )
    users.get_user_for_update.return_value = target
    auth.get_credential.return_value = _local_credential(1)
    authentication_service = Mock(spec=AuthenticationService)
    service = _service(auth, authentication_service, users)
    temporary_password = "fresh-temporary-password"
    monkeypatch.setattr(
        "gendertagger.services.user_administration.secrets.token_urlsafe",
        lambda _: temporary_password,
    )

    with caplog.at_level("INFO"):
        result = service.reset_user_password(
            USER_IDS[1],
            actor_user_id=USER_IDS[0],
            request_id="request-987",
        )

    assert result.temporary_password == temporary_password
    authentication_service.reset_password_in_transaction.assert_called_once_with(
        unit_of_work=ANY,
        user_id=USER_IDS[1],
        new_password=temporary_password,
    )
    users.update_user.assert_not_called()
    assert str(USER_IDS[0]) in caplog.text
    assert str(USER_IDS[1]) in caplog.text
    assert "request-987" in caplog.text
    assert temporary_password not in caplog.text


def test_revoke_user_sessions_validates_local_target_and_logs_attribution(
    caplog: pytest.LogCaptureFixture,
) -> None:
    auth = Mock(spec=AuthRepository)
    users = Mock(spec=UserRepository)
    users.get_user_for_update.return_value = User(
        id=USER_IDS[1],
        display_name="Target user",
        roles=set(),
        is_active=True,
        created_at=NOW,
        updated_at=NOW,
    )
    auth.get_credential.return_value = _local_credential(1)
    service = _service(auth, users=users)

    with caplog.at_level("INFO"):
        service.revoke_user_sessions(
            USER_IDS[1],
            actor_user_id=USER_IDS[0],
            request_id="request-654",
        )

    auth.revoke_all_sessions.assert_called_once_with(USER_IDS[1])
    users.update_user.assert_not_called()
    assert str(USER_IDS[0]) in caplog.text
    assert str(USER_IDS[1]) in caplog.text
    assert "request-654" in caplog.text
