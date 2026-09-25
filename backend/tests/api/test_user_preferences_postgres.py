"""Preferences persist by local account through real PostgreSQL-backed browser sessions."""

import hashlib
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi import Request
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import Engine

from gendertagger.api.app import create_app
from gendertagger.api.authentication import CSRF_COOKIE_NAME, CSRF_HEADER_NAME, SESSION_COOKIE_NAME
from gendertagger.api.settings import AppSettings
from gendertagger.db.session import create_session_factory
from gendertagger.db.unit_of_work import SqlAlchemyUnitOfWork
from gendertagger.models.user import UserCreate
from gendertagger.services.password_hashing import Argon2PasswordHasher
from gendertagger.services.ports.unit_of_work import UnitOfWork, UnitOfWorkFactory

pytestmark = [pytest.mark.integration, pytest.mark.postgres]

PREFERENCES_PATH = "/api/v1/me/preferences"
PASSWORD = "test-only-preferences-password-12"
DEFAULT_PREFERENCES: dict[str, object] = {
    "locale": None,
    "theme": "system",
    "desktop_sidebar_collapsed": False,
    "revision": 0,
}


class _ResolvedProviderBackend:
    """Resolve an existing provider identity without creating a local credential."""

    def __init__(self, user_id: UUID) -> None:
        self._user_id = user_id

    def authenticate(self, request: Request) -> UUID | None:
        return self._user_id

    def validate_csrf(self, request: Request, *, user_id: UUID) -> bool:
        return self._user_id == user_id


class _Deployment:
    def __init__(self, postgres_engine: Engine, artifact_root: Path) -> None:
        session_factory = create_session_factory(postgres_engine)

        def unit_of_work_factory() -> UnitOfWork:
            return SqlAlchemyUnitOfWork(session_factory)

        self.unit_of_work_factory: UnitOfWorkFactory = unit_of_work_factory
        self.password_hash = Argon2PasswordHasher().hash(PASSWORD)
        self.application = create_app(
            settings=AppSettings(
                database_url=SecretStr("postgresql+psycopg://unused:unused@localhost/unused"),
                code_git_commit="a" * 40,
                dependency_lock_sha256="b" * 64,
                artifact_root=artifact_root,
            ),
            unit_of_work_factory=unit_of_work_factory,
        )

    def add_account(self, *, must_change_password: bool = False) -> tuple[UUID, str]:
        username = f"preferences-{uuid4().hex[:12]}"
        with self.unit_of_work_factory() as unit_of_work:
            user = unit_of_work.users.add_user(UserCreate(display_name="Account without grants"))
            unit_of_work.auth.add_credential(
                user_id=user.id,
                username=username,
                password_hash=self.password_hash,
            )
            unit_of_work.auth.set_password(
                user_id=user.id,
                password_hash=self.password_hash,
                must_change_password=must_change_password,
            )
            unit_of_work.commit()
        return user.id, username

    def login(self, username: str, *, password: str = PASSWORD) -> TestClient:
        client = TestClient(self.application, base_url="https://testserver")
        response = client.post(
            "/api/v1/auth/login",
            json={"username": username, "password": password},
        )
        assert response.status_code == 200
        assert SESSION_COOKIE_NAME in client.cookies
        assert CSRF_COOKIE_NAME in client.cookies
        return client


def _csrf(client: TestClient) -> dict[str, str]:
    return {CSRF_HEADER_NAME: client.cookies[CSRF_COOKIE_NAME]}


def test_preferences_defaults_stay_unresolved_and_reads_do_not_initialize_storage(
    postgres_engine: Engine,
    tmp_path: Path,
) -> None:
    deployment = _Deployment(postgres_engine, tmp_path)
    user_id, username = deployment.add_account()
    client = deployment.login(username)

    english = client.get(PREFERENCES_PATH, headers={"accept-language": "en-US,en;q=0.9"})
    german = client.get(PREFERENCES_PATH, headers={"accept-language": "de-DE,de;q=0.9"})

    assert english.status_code == german.status_code == 200
    assert english.json() == german.json() == DEFAULT_PREFERENCES
    assert english.headers["cache-control"] == german.headers["cache-control"] == "no-store"
    with deployment.unit_of_work_factory() as unit_of_work:
        assert unit_of_work.user_preferences.get_preferences(user_id) is None


def test_preferences_survive_logout_and_new_session_in_a_new_application(
    postgres_engine: Engine,
    tmp_path: Path,
) -> None:
    deployment = _Deployment(postgres_engine, tmp_path)
    _, username = deployment.add_account()
    first_client = deployment.login(username)
    first_token = first_client.cookies[SESSION_COOKIE_NAME]

    saved = first_client.patch(
        PREFERENCES_PATH,
        headers=_csrf(first_client),
        json={
            "expected_revision": 0,
            "locale": "en",
            "theme": "dark",
            "desktop_sidebar_collapsed": True,
        },
    )
    logged_out = first_client.post("/api/v1/auth/logout", headers=_csrf(first_client))
    restored_application = _Deployment(postgres_engine, tmp_path)
    second_client = restored_application.login(username)
    restored = second_client.get(PREFERENCES_PATH)

    assert saved.status_code == 200
    assert saved.json() == {
        "locale": "en",
        "theme": "dark",
        "desktop_sidebar_collapsed": True,
        "revision": 1,
    }
    assert logged_out.status_code == 204
    assert first_client.get(PREFERENCES_PATH).status_code == 401
    assert second_client.cookies[SESSION_COOKIE_NAME] != first_token
    assert restored.status_code == 200
    assert restored.json() == saved.json()


def test_preferences_partial_updates_preserve_omissions_and_explicit_locale_null_clears(
    postgres_engine: Engine,
    tmp_path: Path,
) -> None:
    deployment = _Deployment(postgres_engine, tmp_path)
    _, username = deployment.add_account()
    client = deployment.login(username)
    initial = client.patch(
        PREFERENCES_PATH,
        headers=_csrf(client),
        json={
            "expected_revision": 0,
            "locale": "de",
            "theme": "dark",
            "desktop_sidebar_collapsed": True,
        },
    )

    changed_theme = client.patch(
        PREFERENCES_PATH,
        headers=_csrf(client),
        json={"expected_revision": 1, "theme": "light"},
    )
    cleared_locale = client.patch(
        PREFERENCES_PATH,
        headers=_csrf(client),
        json={"expected_revision": 2, "locale": None},
    )

    assert initial.status_code == changed_theme.status_code == cleared_locale.status_code == 200
    assert changed_theme.json() == {
        "locale": "de",
        "theme": "light",
        "desktop_sidebar_collapsed": True,
        "revision": 2,
    }
    assert cleared_locale.json() == {
        "locale": None,
        "theme": "light",
        "desktop_sidebar_collapsed": True,
        "revision": 3,
    }
    assert client.get(PREFERENCES_PATH).json() == cleared_locale.json()


def test_preferences_noop_preserves_virtual_defaults_and_saved_revision(
    postgres_engine: Engine,
    tmp_path: Path,
) -> None:
    deployment = _Deployment(postgres_engine, tmp_path)
    user_id, username = deployment.add_account()
    client = deployment.login(username)

    unchanged_defaults = client.patch(
        PREFERENCES_PATH,
        headers=_csrf(client),
        json={"expected_revision": 0, "locale": None, "theme": "system"},
    )
    assert unchanged_defaults.status_code == 200
    assert unchanged_defaults.json() == DEFAULT_PREFERENCES
    with deployment.unit_of_work_factory() as unit_of_work:
        assert unit_of_work.user_preferences.get_preferences(user_id) is None

    saved = client.patch(
        PREFERENCES_PATH,
        headers=_csrf(client),
        json={"expected_revision": 0, "theme": "dark"},
    )
    unchanged_saved = client.patch(
        PREFERENCES_PATH,
        headers=_csrf(client),
        json={"expected_revision": 1, "theme": "dark"},
    )
    stale_noop = client.patch(
        PREFERENCES_PATH,
        headers=_csrf(client),
        json={"expected_revision": 0, "theme": "dark"},
    )
    reset_values = client.patch(
        PREFERENCES_PATH,
        headers=_csrf(client),
        json={"expected_revision": 1, "theme": "system"},
    )

    assert saved.status_code == unchanged_saved.status_code == reset_values.status_code == 200
    assert unchanged_saved.json() == saved.json()
    assert stale_noop.status_code == 409
    assert stale_noop.json()["error"]["details"] == {
        "expected_revision": 0,
        "current_revision": 1,
    }
    assert reset_values.json() == {**DEFAULT_PREFERENCES, "revision": 2}
    with deployment.unit_of_work_factory() as unit_of_work:
        persisted = unit_of_work.user_preferences.get_preferences(user_id)
    assert persisted is not None
    assert persisted.revision == 2


def test_preferences_isolate_accounts_and_cannot_select_another_owner(
    postgres_engine: Engine,
    tmp_path: Path,
) -> None:
    deployment = _Deployment(postgres_engine, tmp_path)
    first_id, first_username = deployment.add_account()
    _, second_username = deployment.add_account()
    first_client = deployment.login(first_username)
    second_client = deployment.login(second_username)
    saved = first_client.patch(
        PREFERENCES_PATH,
        headers=_csrf(first_client),
        json={"expected_revision": 0, "locale": "en", "desktop_sidebar_collapsed": True},
    )

    second_read = second_client.get(PREFERENCES_PATH, params={"user_id": str(first_id)})
    forged_owner = second_client.patch(
        PREFERENCES_PATH,
        headers=_csrf(second_client),
        json={"expected_revision": 1, "user_id": str(first_id), "locale": "de"},
    )
    second_saved = second_client.patch(
        PREFERENCES_PATH,
        headers=_csrf(second_client),
        json={"expected_revision": 0, "theme": "light"},
    )

    assert saved.status_code == second_read.status_code == second_saved.status_code == 200
    assert second_read.json() == DEFAULT_PREFERENCES
    assert forged_owner.status_code == 422
    assert second_saved.json() == {**DEFAULT_PREFERENCES, "theme": "light", "revision": 1}
    assert first_client.get(PREFERENCES_PATH).json() == saved.json()


def test_preferences_sessions_detect_stale_writes_without_losing_saved_fields(
    postgres_engine: Engine,
    tmp_path: Path,
) -> None:
    deployment = _Deployment(postgres_engine, tmp_path)
    _, username = deployment.add_account()
    first_client = deployment.login(username)
    second_client = deployment.login(username)
    first_saved = first_client.patch(
        PREFERENCES_PATH,
        headers=_csrf(first_client),
        json={"expected_revision": 0, "locale": "en"},
    )

    stale = second_client.patch(
        PREFERENCES_PATH,
        headers=_csrf(second_client),
        json={"expected_revision": 0, "theme": "dark"},
    )
    refreshed = second_client.get(PREFERENCES_PATH)
    reconciled = second_client.patch(
        PREFERENCES_PATH,
        headers=_csrf(second_client),
        json={"expected_revision": refreshed.json()["revision"], "theme": "dark"},
    )

    assert first_saved.status_code == refreshed.status_code == reconciled.status_code == 200
    assert stale.status_code == 409
    assert stale.headers["cache-control"] == "no-store"
    assert stale.json()["error"]["code"] == "preferences_revision_conflict"
    assert stale.json()["error"]["details"] == {"expected_revision": 0, "current_revision": 1}
    assert refreshed.json() == first_saved.json()
    assert reconciled.json() == {**first_saved.json(), "theme": "dark", "revision": 2}


def test_preferences_reject_missing_wrong_and_other_session_csrf_tokens(
    postgres_engine: Engine,
    tmp_path: Path,
) -> None:
    deployment = _Deployment(postgres_engine, tmp_path)
    user_id, username = deployment.add_account()
    client = deployment.login(username)
    other_session = deployment.login(username)

    for headers in ({}, {CSRF_HEADER_NAME: "wrong-token"}, _csrf(other_session)):
        response = client.patch(
            PREFERENCES_PATH,
            headers=headers,
            json={"expected_revision": 0, "theme": "dark"},
        )
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "forbidden"

    with deployment.unit_of_work_factory() as unit_of_work:
        assert unit_of_work.user_preferences.get_preferences(user_id) is None


def test_preferences_require_password_change_before_read_or_write(
    postgres_engine: Engine,
    tmp_path: Path,
) -> None:
    deployment = _Deployment(postgres_engine, tmp_path)
    user_id, username = deployment.add_account(must_change_password=True)
    client = deployment.login(username)

    read = client.get(PREFERENCES_PATH)
    write = client.patch(
        PREFERENCES_PATH,
        headers=_csrf(client),
        json={"expected_revision": 0, "theme": "dark"},
    )

    assert read.status_code == write.status_code == 403
    assert (
        read.json()["error"]["code"] == write.json()["error"]["code"] == "password_change_required"
    )
    with deployment.unit_of_work_factory() as unit_of_work:
        assert unit_of_work.user_preferences.get_preferences(user_id) is None

    changed = client.post(
        "/api/v1/me/password",
        headers=_csrf(client),
        json={"current_password": PASSWORD, "new_password": "new-test-preferences-password-34"},
    )
    assert changed.status_code == 204
    assert client.get(PREFERENCES_PATH).json() == DEFAULT_PREFERENCES


@pytest.mark.parametrize(
    "account_state",
    ["inactive", "revoked", "invalid_token", "nonlocal", "expired", "unknown_user"],
)
def test_preferences_reject_unusable_authentication(
    postgres_engine: Engine,
    tmp_path: Path,
    account_state: str,
) -> None:
    deployment = _Deployment(postgres_engine, tmp_path)
    user_id, username = deployment.add_account()
    client = deployment.login(username)
    with deployment.unit_of_work_factory() as unit_of_work:
        if account_state == "inactive":
            unit_of_work.users.update_user(
                user_id=user_id,
                display_name="Inactive account",
                roles=set(),
                is_active=False,
            )
        elif account_state == "revoked":
            unit_of_work.auth.revoke_all_sessions(user_id)
        elif account_state == "expired":
            token = "expired-preferences-session-token"
            expired_at = datetime.now(UTC) - timedelta(minutes=1)
            unit_of_work.auth.create_session(
                session_id=hashlib.sha256(token.encode("ascii")).hexdigest(),
                user_id=user_id,
                csrf_secret="expired-csrf-secret",
                keep_signed_in=False,
                expires_at=expired_at,
                absolute_expires_at=expired_at,
            )
            client.cookies.clear()
            client.cookies.set(SESSION_COOKIE_NAME, token)
        elif account_state == "unknown_user":
            deployment.application.state.authentication_backend = _ResolvedProviderBackend(uuid4())
        elif account_state == "nonlocal":
            nonlocal_user = unit_of_work.users.add_user(UserCreate(display_name="Provider account"))
            deployment.application.state.authentication_backend = _ResolvedProviderBackend(
                nonlocal_user.id
            )
        else:
            client.cookies.clear()
            client.cookies.set(SESSION_COOKIE_NAME, "invalid-session-token")
        unit_of_work.commit()

    read = client.get(PREFERENCES_PATH)
    write = client.patch(
        PREFERENCES_PATH,
        headers={CSRF_HEADER_NAME: "not-an-authentication-credential"},
        json={"expected_revision": 0, "theme": "dark"},
    )

    assert read.status_code == write.status_code == 401
    assert (
        read.json()["error"]["code"] == write.json()["error"]["code"] == "authentication_required"
    )
