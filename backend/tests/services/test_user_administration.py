from datetime import UTC, datetime
from types import TracebackType
from typing import Self, cast
from unittest.mock import Mock
from uuid import UUID

import pytest

from gendertagger.models.auth import AdminUser, AdminUserCreate
from gendertagger.models.user import GlobalRole, User
from gendertagger.services.authentication import AuthenticationService
from gendertagger.services.pagination import CursorCodec, InvalidCursorError
from gendertagger.services.ports.auth_repository import AdminUserCursor, AuthRepository
from gendertagger.services.ports.unit_of_work import UnitOfWork
from gendertagger.services.user_administration import UserAdministrationService

pytestmark = pytest.mark.unit

NOW = datetime(2026, 9, 24, 10, 0, tzinfo=UTC)
USER_IDS = (
    UUID("10000000-0000-0000-0000-000000000001"),
    UUID("10000000-0000-0000-0000-000000000002"),
    UUID("10000000-0000-0000-0000-000000000003"),
)


class _UnitOfWork:
    def __init__(self, auth: AuthRepository) -> None:
        self.auth = auth

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
) -> UserAdministrationService:
    unit_of_work = _UnitOfWork(repository)

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
