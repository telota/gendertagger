"""End-to-end tests for the local-account authentication endpoints (ADR-0031, ADR-0032)."""

from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from types import TracebackType
from typing import Self, cast
from uuid import UUID

from fastapi.testclient import TestClient
from pydantic import SecretStr

from gendertagger.api.app import create_app
from gendertagger.api.authentication import CSRF_COOKIE_NAME, CSRF_HEADER_NAME, SESSION_COOKIE_NAME
from gendertagger.api.settings import AppSettings
from gendertagger.models.auth import LocalCredential, UserSession
from gendertagger.models.user import GlobalRole, User, UserCreate
from gendertagger.services.auth_repository import AuthRepository
from gendertagger.services.password_hashing import Argon2PasswordHasher
from gendertagger.services.unit_of_work import UnitOfWork
from gendertagger.services.user_repository import UserRepository

DATABASE_URL = "postgresql+psycopg://api:secret@localhost/gendertagger"
CODE_GIT_COMMIT = "a" * 40
DEPENDENCY_LOCK_SHA256 = "b" * 64
NOW = datetime(2026, 9, 3, tzinfo=UTC)
USER_ID = UUID("d0000000-0000-0000-0000-000000000001")
USERNAME = "reviewer.one"
PASSWORD = "a-correct-passphrase-12"  # Test fixture, not a real credential.


class _InMemoryStore:
    """Backs a minimal in-process UnitOfWork so login is exercised end to end."""

    def __init__(self, *, must_change_password: bool = False) -> None:
        self.users: dict[UUID, User] = {
            USER_ID: User(
                id=USER_ID,
                display_name="Reviewer One",
                roles={GlobalRole.operator},
                is_active=True,
                created_at=NOW,
                updated_at=NOW,
            )
        }
        self.credentials: dict[UUID, LocalCredential] = {
            USER_ID: LocalCredential(
                user_id=USER_ID,
                username=USERNAME,
                password_hash=Argon2PasswordHasher().hash(PASSWORD),
                must_change_password=must_change_password,
                updated_at=NOW,
            )
        }
        self.sessions: dict[str, UserSession] = {}


class _InMemoryUserRepository:
    def __init__(self, store: _InMemoryStore) -> None:
        self._store = store

    def add_user(self, command: UserCreate) -> User:
        raise NotImplementedError

    def get_user(self, user_id: UUID) -> User | None:
        return self._store.users.get(user_id)


class _InMemoryAuthRepository:
    def __init__(self, store: _InMemoryStore) -> None:
        self._store = store

    def add_credential(
        self, *, user_id: UUID, username: str, password_hash: str
    ) -> LocalCredential:
        raise NotImplementedError

    def get_credential_by_username(self, username: str) -> LocalCredential | None:
        for credential in self._store.credentials.values():
            if credential.username == username:
                return credential
        return None

    def get_credential(self, user_id: UUID) -> LocalCredential | None:
        return self._store.credentials.get(user_id)

    def set_password(
        self, *, user_id: UUID, password_hash: str, must_change_password: bool
    ) -> None:
        credential = self._store.credentials[user_id]
        self._store.credentials[user_id] = credential.model_copy(
            update={"password_hash": password_hash, "must_change_password": must_change_password}
        )

    def create_session(
        self,
        *,
        session_id: str,
        user_id: UUID,
        csrf_secret: str,
        keep_signed_in: bool,
        expires_at: datetime,
        absolute_expires_at: datetime,
    ) -> None:
        self._store.sessions[session_id] = UserSession(
            user_id=user_id,
            csrf_secret=csrf_secret,
            keep_signed_in=keep_signed_in,
            expires_at=expires_at,
            absolute_expires_at=absolute_expires_at,
            revoked_at=None,
        )

    def get_session(self, session_id: str) -> UserSession | None:
        return self._store.sessions.get(session_id)

    def renew_session(self, session_id: str, *, expires_at: datetime) -> None:
        session = self._store.sessions[session_id]
        if session.revoked_at is None and session.expires_at < expires_at:
            self._store.sessions[session_id] = session.model_copy(update={"expires_at": expires_at})

    def revoke_session(self, session_id: str) -> None:
        session = self._store.sessions.get(session_id)
        if session is not None:
            self._store.sessions[session_id] = session.model_copy(update={"revoked_at": NOW})

    def revoke_all_sessions(self, user_id: UUID) -> None:
        for session_id, session in list(self._store.sessions.items()):
            if session.user_id == user_id and session.revoked_at is None:
                self._store.sessions[session_id] = session.model_copy(update={"revoked_at": NOW})


class _InMemoryUnitOfWork:
    def __init__(self, store: _InMemoryStore) -> None:
        self._store = store

    def __enter__(self) -> Self:
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
        return cast(UserRepository, _InMemoryUserRepository(self._store))

    @property
    def auth(self) -> AuthRepository:
        return cast(AuthRepository, _InMemoryAuthRepository(self._store))

    def commit(self) -> None:
        return None

    def rollback(self) -> None:
        return None


def _client(
    *, must_change_password: bool = False, store: _InMemoryStore | None = None
) -> TestClient:
    store = store or _InMemoryStore(must_change_password=must_change_password)

    def unit_of_work_factory() -> UnitOfWork:
        return cast(UnitOfWork, _InMemoryUnitOfWork(store))

    application = create_app(
        settings=AppSettings(
            database_url=SecretStr(DATABASE_URL),
            code_git_commit=CODE_GIT_COMMIT,
            dependency_lock_sha256=DEPENDENCY_LOCK_SHA256,
        ),
        unit_of_work_factory=unit_of_work_factory,
    )
    # The session and CSRF cookies are `Secure`; an https base URL is required for the test
    # client's cookie jar to resend them on follow-up requests, matching real browser behavior.
    return TestClient(application, base_url="https://testserver")


def test_login_with_valid_credentials_issues_session_and_csrf_cookies() -> None:
    client = _client()

    response = client.post("/api/v1/auth/login", json={"username": USERNAME, "password": PASSWORD})

    assert response.status_code == 200
    assert response.json() == {
        "id": str(USER_ID),
        "display_name": "Reviewer One",
        "roles": [GlobalRole.operator.value],
    }
    assert SESSION_COOKIE_NAME in client.cookies
    assert CSRF_COOKIE_NAME in client.cookies


def _set_cookie_headers(headers: list[str]) -> dict[str, str]:
    return {header.split("=", 1)[0]: header.lower() for header in headers}


def test_login_without_keep_signed_in_issues_browser_session_cookies() -> None:
    client = _client()

    response = client.post("/api/v1/auth/login", json={"username": USERNAME, "password": PASSWORD})

    cookies = _set_cookie_headers(response.headers.get_list("set-cookie"))
    assert set(cookies) == {SESSION_COOKIE_NAME, CSRF_COOKIE_NAME}
    for header in cookies.values():
        assert "expires=" not in header
        assert "max-age=" not in header


def test_login_with_keep_signed_in_issues_persistent_cookies_until_the_absolute_limit() -> None:
    store = _InMemoryStore()
    client = _client(store=store)

    response = client.post(
        "/api/v1/auth/login",
        json={"username": USERNAME, "password": PASSWORD, "keep_signed_in": True},
    )

    assert response.status_code == 200
    (session,) = store.sessions.values()
    assert session.keep_signed_in is True
    assert session.absolute_expires_at - session.expires_at == timedelta(days=23)
    cookies = _set_cookie_headers(response.headers.get_list("set-cookie"))
    assert set(cookies) == {SESSION_COOKIE_NAME, CSRF_COOKIE_NAME}
    for header in cookies.values():
        expires = header.split("expires=", 1)[1].split(";", 1)[0]
        assert parsedate_to_datetime(expires) == session.absolute_expires_at.replace(microsecond=0)


def test_session_state_reports_the_kind_and_is_reachable_before_a_password_change() -> None:
    client = _client(must_change_password=True)
    client.post(
        "/api/v1/auth/login",
        json={"username": USERNAME, "password": PASSWORD, "keep_signed_in": True},
    )

    response = client.get("/api/v1/auth/session")

    assert response.status_code == 200
    assert response.json() == {"must_change_password": True, "keep_signed_in": True}


def test_session_state_requires_a_session() -> None:
    client = _client()

    response = client.get("/api/v1/auth/session")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "authentication_required"


def test_login_with_wrong_password_is_rejected_without_setting_cookies() -> None:
    client = _client()

    response = client.post(
        "/api/v1/auth/login", json={"username": USERNAME, "password": "not-the-password"}
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_credentials"
    assert SESSION_COOKIE_NAME not in client.cookies


def test_login_with_unknown_username_is_rejected_the_same_way() -> None:
    client = _client()

    response = client.post("/api/v1/auth/login", json={"username": "nobody", "password": PASSWORD})

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_credentials"


def test_me_requires_a_session() -> None:
    client = _client()

    response = client.get("/api/v1/me")

    assert response.status_code == 401


def test_me_returns_the_session_owner_without_a_csrf_header() -> None:
    client = _client()
    client.post("/api/v1/auth/login", json={"username": USERNAME, "password": PASSWORD})

    response = client.get("/api/v1/me")

    assert response.status_code == 200
    assert response.json()["id"] == str(USER_ID)


def test_unsafe_request_without_csrf_header_is_rejected() -> None:
    client = _client()
    client.post("/api/v1/auth/login", json={"username": USERNAME, "password": PASSWORD})

    response = client.post("/api/v1/auth/logout")

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"


def test_logout_with_valid_csrf_revokes_the_session() -> None:
    client = _client()
    client.post("/api/v1/auth/login", json={"username": USERNAME, "password": PASSWORD})
    csrf_token = client.cookies[CSRF_COOKIE_NAME]

    response = client.post("/api/v1/auth/logout", headers={CSRF_HEADER_NAME: csrf_token})
    assert response.status_code == 204

    follow_up = client.get("/api/v1/me")
    assert follow_up.status_code == 401


def test_must_change_password_gate_blocks_general_routes_but_exempts_me_and_password_change() -> (
    None
):
    client = _client(must_change_password=True)
    client.post("/api/v1/auth/login", json={"username": USERNAME, "password": PASSWORD})
    csrf_token = client.cookies[CSRF_COOKIE_NAME]

    gated = client.get("/api/v1/methods")
    assert gated.status_code == 403
    assert gated.json()["error"]["code"] == "password_change_required"

    exempt = client.get("/api/v1/me")
    assert exempt.status_code == 200

    changed = client.post(
        "/api/v1/me/password",
        headers={CSRF_HEADER_NAME: csrf_token},
        json={"current_password": PASSWORD, "new_password": "a-brand-new-passphrase-99"},
    )
    assert changed.status_code == 204

    no_longer_gated = client.get("/api/v1/methods")
    assert no_longer_gated.status_code == 200


def test_change_password_with_wrong_current_password_is_rejected_and_leaves_the_gate_set() -> None:
    client = _client(must_change_password=True)
    client.post("/api/v1/auth/login", json={"username": USERNAME, "password": PASSWORD})
    csrf_token = client.cookies[CSRF_COOKIE_NAME]

    response = client.post(
        "/api/v1/me/password",
        headers={CSRF_HEADER_NAME: csrf_token},
        json={"current_password": "not-the-current-password", "new_password": "irrelevant-pass-99"},
    )

    # 400, not 401: a 401 means the session is gone, and the session here is intact.
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_current_password"
    assert client.get("/api/v1/me").status_code == 200
    assert client.get("/api/v1/methods").status_code == 403
