from datetime import UTC, datetime
from types import TracebackType
from typing import Annotated, Self, cast
from uuid import UUID

import pytest
from fastapi import Depends
from fastapi.testclient import TestClient
from pydantic import SecretStr

from gendertagger.api.app import create_app
from gendertagger.api.authentication import (
    AuthenticationBackend,
    require_authenticated_user,
)
from gendertagger.api.router import create_api_router
from gendertagger.api.settings import AppSettings
from gendertagger.models.user import CurrentUser, GlobalRole, User
from gendertagger.services.unit_of_work import UnitOfWork
from gendertagger.services.user_repository import UserRepository

DATABASE_URL = "postgresql+psycopg://api:secret@localhost/gendertagger"
CODE_GIT_COMMIT = "a" * 40
DEPENDENCY_LOCK_SHA256 = "b" * 64
USER_ID = UUID("a2f03480-77a7-4f24-82cb-07604d5c2483")
NOW = datetime(2026, 8, 13, tzinfo=UTC)


class StubAuthenticationBackend:
    def __init__(self, *, user_id: UUID | None, is_csrf_valid: bool = False) -> None:
        self.user_id = user_id
        self.is_csrf_valid = is_csrf_valid
        self.csrf_check_count = 0

    def authenticate(self, request: object) -> UUID | None:
        return self.user_id

    def validate_csrf(self, request: object, *, user_id: UUID) -> bool:
        self.csrf_check_count += 1
        return self.is_csrf_valid


class StubUserRepository:
    def __init__(self, user: User | None) -> None:
        self.user = user

    def get_user(self, user_id: UUID) -> User | None:
        if self.user is None or self.user.id != user_id:
            return None
        return self.user


class StubUnitOfWork:
    def __init__(self, user: User | None) -> None:
        self._users = StubUserRepository(user)
        self.enter_count = 0

    def __enter__(self) -> Self:
        self.enter_count += 1
        return self

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        return None

    @property
    def users(self) -> UserRepository:
        return cast(UserRepository, self._users)


def _user(*, is_active: bool = True) -> User:
    return User(
        id=USER_ID,
        display_name="API Reviewer",
        roles={GlobalRole.operator},
        is_active=is_active,
        created_at=NOW,
        updated_at=NOW,
    )


def _protected_client(
    *,
    user: User | None,
    authentication_backend: AuthenticationBackend | None,
) -> tuple[TestClient, StubUnitOfWork]:
    unit_of_work = StubUnitOfWork(user)

    def unit_of_work_factory() -> UnitOfWork:
        return cast(UnitOfWork, unit_of_work)

    settings = AppSettings(
        database_url=SecretStr(DATABASE_URL),
        code_git_commit=CODE_GIT_COMMIT,
        dependency_lock_sha256=DEPENDENCY_LOCK_SHA256,
    )
    application = create_app(
        settings=settings,
        unit_of_work_factory=unit_of_work_factory,
        authentication_backend=authentication_backend,
    )
    protected_router = create_api_router()

    @protected_router.get("/protected")
    def _read_protected(
        authenticated_user: Annotated[CurrentUser, Depends(require_authenticated_user)],
    ) -> dict[str, str]:
        return {"user_id": str(authenticated_user.id)}

    @protected_router.post("/protected")
    def _write_protected() -> dict[str, bool]:
        return {"created": True}

    application.include_router(protected_router)
    return TestClient(application), unit_of_work


def test_versioned_api_fails_closed_without_authentication_backend() -> None:
    client, unit_of_work = _protected_client(user=_user(), authentication_backend=None)

    response = client.get("/api/v1/protected")

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Session"
    assert unit_of_work.enter_count == 0


@pytest.mark.parametrize("user", [None, _user(is_active=False)])
def test_authentication_rejects_unknown_or_inactive_persisted_user(user: User | None) -> None:
    backend = StubAuthenticationBackend(user_id=USER_ID)
    client, unit_of_work = _protected_client(user=user, authentication_backend=backend)

    response = client.get("/api/v1/protected")

    assert response.status_code == 401
    assert unit_of_work.enter_count == 1


def test_authenticated_safe_request_returns_persisted_user_without_csrf_check() -> None:
    backend = StubAuthenticationBackend(user_id=USER_ID)
    client, _ = _protected_client(user=_user(), authentication_backend=backend)

    response = client.get("/api/v1/protected")

    assert response.status_code == 200
    assert response.json() == {"user_id": str(USER_ID)}
    assert backend.csrf_check_count == 0


def test_me_exposes_typed_principal_without_persistence_fields() -> None:
    backend = StubAuthenticationBackend(user_id=USER_ID)
    client, _ = _protected_client(user=_user(), authentication_backend=backend)

    response = client.get("/api/v1/me")

    assert response.status_code == 200
    assert response.json() == {
        "id": str(USER_ID),
        "display_name": "API Reviewer",
        "roles": [GlobalRole.operator.value],
    }


def test_unsafe_request_requires_backend_csrf_validation() -> None:
    rejected_backend = StubAuthenticationBackend(user_id=USER_ID)
    rejected_client, _ = _protected_client(
        user=_user(),
        authentication_backend=rejected_backend,
    )
    accepted_backend = StubAuthenticationBackend(user_id=USER_ID, is_csrf_valid=True)
    accepted_client, _ = _protected_client(
        user=_user(),
        authentication_backend=accepted_backend,
    )

    rejected_response = rejected_client.post("/api/v1/protected")
    accepted_response = accepted_client.post("/api/v1/protected")

    assert rejected_response.status_code == 403
    assert accepted_response.status_code == 200
    assert rejected_backend.csrf_check_count == 1
    assert accepted_backend.csrf_check_count == 1
