"""Preference services fail closed on storage and freshly changed account state."""

from datetime import UTC, datetime
from types import TracebackType
from typing import Self, cast
from unittest.mock import Mock
from uuid import UUID

import pytest

from gendertagger.models.auth import LocalCredential
from gendertagger.models.user import User
from gendertagger.models.user_preferences import UserPreferences, UserPreferencesUpdate
from gendertagger.services.ports.auth_repository import AuthRepository
from gendertagger.services.ports.unit_of_work import UnitOfWork
from gendertagger.services.ports.user_repository import UserRepository
from gendertagger.services.user_preferences import (
    PreferencesAccountUnavailableError,
    PreferencesPasswordChangeRequiredError,
    UserPreferencesService,
)

pytestmark = pytest.mark.unit

USER_ID = UUID("10000000-0000-0000-0000-000000000001")
NOW = datetime(2026, 9, 25, tzinfo=UTC)


class StubPreferencesRepository:
    """Stage writes separately so a failed commit cannot become persisted state."""

    def __init__(self, stored: UserPreferences | None) -> None:
        self.stored = stored
        self.pending: UserPreferences | None = None
        self.read_error: RuntimeError | None = None
        self.read_count = 0
        self.save_count = 0

    def get_preferences(self, user_id: UUID) -> UserPreferences | None:
        assert user_id == USER_ID
        self.read_count += 1
        if self.read_error is not None:
            raise self.read_error
        return self.stored

    def save_preferences(self, user_id: UUID, preferences: UserPreferences) -> None:
        assert user_id == USER_ID
        self.save_count += 1
        self.pending = preferences


class StubUnitOfWork:
    """Model the transaction contract with injectable read and commit failures."""

    def __init__(self, stored: UserPreferences | None) -> None:
        self.users = Mock(spec=UserRepository)
        self.auth = Mock(spec=AuthRepository)
        self.user_preferences = StubPreferencesRepository(stored)
        user = User(id=USER_ID, display_name="Local account", created_at=NOW, updated_at=NOW)
        credential = LocalCredential(
            user_id=USER_ID,
            username="local_account",
            password_hash="unused-preferences-test-hash",
            must_change_password=False,
            updated_at=NOW,
        )
        self.users.get_user.return_value = user
        self.users.get_user_for_update.return_value = user
        self.auth.get_credential.return_value = credential
        self.commit_error: RuntimeError | None = None
        self.commit_count = 0
        self.rollback_count = 0

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.user_preferences.pending = None
        self.rollback_count += 1

    def commit(self) -> None:
        self.commit_count += 1
        if self.commit_error is not None:
            raise self.commit_error
        if self.user_preferences.pending is not None:
            self.user_preferences.stored = self.user_preferences.pending
            self.user_preferences.pending = None


def _service(unit_of_work: StubUnitOfWork) -> UserPreferencesService:
    return UserPreferencesService(unit_of_work_factory=lambda: cast(UnitOfWork, unit_of_work))


def _invoke(service: UserPreferencesService, operation: str) -> UserPreferences:
    if operation == "read":
        return service.get_preferences(user_id=USER_ID)
    return service.update_preferences(
        UserPreferencesUpdate(expected_revision=0, theme="dark"), user_id=USER_ID
    )


@pytest.mark.parametrize("operation", ["read", "write"])
def test_preferences_read_failure_never_becomes_defaults_or_a_successful_write(
    operation: str,
) -> None:
    unit_of_work = StubUnitOfWork(None)
    error = RuntimeError("injected storage read failure")
    unit_of_work.user_preferences.read_error = error

    with pytest.raises(RuntimeError) as raised:
        _invoke(_service(unit_of_work), operation)

    assert raised.value is error
    assert unit_of_work.user_preferences.stored is None
    assert unit_of_work.user_preferences.save_count == 0
    assert unit_of_work.commit_count == 0
    assert unit_of_work.rollback_count == 1


@pytest.mark.parametrize("stored", [None, UserPreferences(locale="de", revision=2)])
def test_preferences_commit_failure_rolls_back_initialization_or_update_without_success(
    stored: UserPreferences | None,
) -> None:
    unit_of_work = StubUnitOfWork(stored)
    error = RuntimeError("injected commit failure")
    unit_of_work.commit_error = error
    expected_revision = 0 if stored is None else stored.revision

    with pytest.raises(RuntimeError) as raised:
        _service(unit_of_work).update_preferences(
            UserPreferencesUpdate(expected_revision=expected_revision, theme="dark"),
            user_id=USER_ID,
        )

    assert raised.value is error
    assert unit_of_work.user_preferences.save_count == 1
    assert unit_of_work.user_preferences.pending is None
    assert unit_of_work.user_preferences.stored == stored
    assert unit_of_work.commit_count == 1
    assert unit_of_work.rollback_count == 1


@pytest.mark.parametrize("operation", ["read", "write"])
@pytest.mark.parametrize("account_state", ["missing", "inactive", "nonlocal", "forced_password"])
def test_preferences_fresh_account_ineligibility_stops_before_reading_or_saving(
    operation: str, account_state: str
) -> None:
    unit_of_work = StubUnitOfWork(None)
    expected_error: type[RuntimeError] = PreferencesAccountUnavailableError
    if account_state == "missing":
        unit_of_work.users.get_user.return_value = None
        unit_of_work.users.get_user_for_update.return_value = None
    elif account_state == "inactive":
        inactive = User(
            id=USER_ID,
            display_name="Inactive account",
            is_active=False,
            created_at=NOW,
            updated_at=NOW,
        )
        unit_of_work.users.get_user.return_value = inactive
        unit_of_work.users.get_user_for_update.return_value = inactive
    elif account_state == "nonlocal":
        unit_of_work.auth.get_credential.return_value = None
    else:
        unit_of_work.auth.get_credential.return_value = LocalCredential(
            user_id=USER_ID,
            username="local_account",
            password_hash="unused-preferences-test-hash",
            must_change_password=True,
            updated_at=NOW,
        )
        expected_error = PreferencesPasswordChangeRequiredError

    with pytest.raises(expected_error):
        _invoke(_service(unit_of_work), operation)

    assert unit_of_work.user_preferences.read_count == 0
    assert unit_of_work.user_preferences.save_count == 0
    assert unit_of_work.commit_count == 0
    assert unit_of_work.rollback_count == 1
