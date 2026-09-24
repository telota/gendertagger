"""Unit coverage for revision-checked administrative settings mutations (ADR-0040)."""

import logging
from types import TracebackType
from typing import Self, cast
from uuid import UUID

import pytest

from gendertagger.models.admin_settings import (
    AdminSettingsReset,
    AdminSettingsUpdate,
    BrandingEditableValues,
    BrandingOverrides,
    BrandingSettingField,
    DeploymentSettings,
)
from gendertagger.models.branding import BrandingInfo
from gendertagger.services.admin_settings import (
    AdminSettingsService,
    SettingsRevisionConflictError,
)
from gendertagger.services.ports.persistence_errors import SettingsUnavailableError
from gendertagger.services.ports.settings_repository import SettingsRepository
from gendertagger.services.ports.unit_of_work import UnitOfWork

pytestmark = pytest.mark.unit

ACTOR_ID = UUID("10000000-0000-0000-0000-000000000001")


class StubSettingsRepository:
    """Record singleton mutation interactions without a database."""

    def __init__(self, settings: DeploymentSettings | None) -> None:
        self.settings = settings
        self.saved: list[DeploymentSettings] = []
        self.read_count = 0
        self.locked_read_count = 0
        self.save_error: SettingsUnavailableError | None = None

    def get_deployment_settings(self) -> DeploymentSettings | None:
        self.read_count += 1
        return self.settings

    def get_deployment_settings_for_update(self) -> DeploymentSettings | None:
        self.locked_read_count += 1
        return self.settings

    def save_deployment_settings(self, settings: DeploymentSettings) -> None:
        if self.save_error is not None:
            raise self.save_error
        self.saved.append(settings)


class StubUnitOfWork:
    """Expose a caller-controlled settings repository and commit counter."""

    def __init__(self, repository: StubSettingsRepository) -> None:
        self._repository = repository
        self.commit_count = 0
        self.rolled_back = False

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.rolled_back = exception_type is not None

    @property
    def settings(self) -> SettingsRepository:
        return cast(SettingsRepository, self._repository)

    def commit(self) -> None:
        self.commit_count += 1


def _service(
    settings: DeploymentSettings | None,
) -> tuple[AdminSettingsService, StubSettingsRepository, StubUnitOfWork]:
    repository = StubSettingsRepository(settings)
    unit_of_work = StubUnitOfWork(repository)
    service = AdminSettingsService(
        unit_of_work_factory=lambda: cast(UnitOfWork, unit_of_work),
        branding_defaults=BrandingEditableValues(
            institution_name="Environment Institute",
            institution_url="https://environment.example",
            contact_email="environment@example.org",
            privacy_notice_url="/privacy",
            editors=["Environment Editor"],
            published_since_year=2020,
        ),
        deployment_branding=BrandingInfo(),
    )
    return service, repository, unit_of_work


def test_update_preserves_omitted_overrides_and_logs_only_safe_attribution(
    caplog: pytest.LogCaptureFixture,
) -> None:
    service, repository, unit_of_work = _service(
        DeploymentSettings(
            revision=4,
            branding_overrides=BrandingOverrides(
                institution_name="Existing Institute",
                contact_email="existing@example.org",
            ),
        )
    )

    with caplog.at_level(logging.INFO):
        result = service.update_settings(
            AdminSettingsUpdate(
                expected_revision=4,
                branding=BrandingOverrides(
                    institution_name="Private Institute",
                    editors=[],
                ),
            ),
            actor_user_id=ACTOR_ID,
            request_id="request-123",
        )

    assert repository.locked_read_count == 1
    assert unit_of_work.commit_count == 1
    assert result.revision == 5
    assert repository.saved == [
        DeploymentSettings(
            revision=5,
            branding_overrides=BrandingOverrides(
                institution_name="Private Institute",
                contact_email="existing@example.org",
                editors=[],
            ),
        )
    ]
    assert "Private Institute" not in caplog.text
    assert "settings update" in caplog.text
    assert "institution_name,editors" in caplog.text


def test_setting_a_value_equal_to_fallback_creates_a_pinned_override() -> None:
    service, repository, unit_of_work = _service(
        DeploymentSettings(revision=0, branding_overrides=BrandingOverrides())
    )

    result = service.update_settings(
        AdminSettingsUpdate(
            expected_revision=0,
            branding=BrandingOverrides(institution_name="Environment Institute"),
        ),
        actor_user_id=ACTOR_ID,
        request_id="request-123",
    )

    assert result.revision == 1
    assert result.overridden_fields == [BrandingSettingField.institution_name]
    assert repository.saved[0].branding_overrides.model_dump(exclude_unset=True) == {
        "institution_name": "Environment Institute"
    }
    assert unit_of_work.commit_count == 1


def test_reset_removes_explicit_clear_without_copying_the_fallback() -> None:
    service, repository, _ = _service(
        DeploymentSettings(
            revision=2,
            branding_overrides=BrandingOverrides(contact_email=None, editors=[]),
        )
    )

    result = service.reset_settings(
        AdminSettingsReset(
            expected_revision=2,
            fields=[BrandingSettingField.contact_email],
        ),
        actor_user_id=ACTOR_ID,
        request_id="request-123",
    )

    assert result.revision == 3
    assert result.branding.contact_email == "environment@example.org"
    assert repository.saved[0].branding_overrides.model_dump(exclude_unset=True) == {"editors": []}


def test_matching_revision_noop_does_not_write_or_advance_revision() -> None:
    stored = DeploymentSettings(
        revision=2,
        branding_overrides=BrandingOverrides(contact_email=None),
    )
    service, repository, unit_of_work = _service(stored)

    result = service.update_settings(
        AdminSettingsUpdate(
            expected_revision=2,
            branding=BrandingOverrides(contact_email=None),
        ),
        actor_user_id=ACTOR_ID,
        request_id="request-123",
    )

    assert result.revision == 2
    assert repository.saved == []
    assert unit_of_work.commit_count == 1


def test_stale_mutation_conflicts_before_noop_or_write() -> None:
    service, repository, unit_of_work = _service(
        DeploymentSettings(
            revision=3,
            branding_overrides=BrandingOverrides(contact_email=None),
        )
    )

    with pytest.raises(SettingsRevisionConflictError) as error:
        service.reset_settings(
            AdminSettingsReset(
                expected_revision=2,
                fields=[BrandingSettingField.contact_email],
            ),
            actor_user_id=ACTOR_ID,
            request_id="request-123",
        )

    assert error.value.expected_revision == 2
    assert error.value.current_revision == 3
    assert repository.saved == []
    assert unit_of_work.commit_count == 0


def test_failed_persistence_does_not_commit_or_emit_success_log(
    caplog: pytest.LogCaptureFixture,
) -> None:
    service, repository, unit_of_work = _service(
        DeploymentSettings(revision=0, branding_overrides=BrandingOverrides())
    )
    repository.save_error = SettingsUnavailableError("unavailable")

    with caplog.at_level(logging.INFO), pytest.raises(SettingsUnavailableError):
        service.update_settings(
            AdminSettingsUpdate(
                expected_revision=0,
                branding=BrandingOverrides(institution_name="Private Institute"),
            ),
            actor_user_id=ACTOR_ID,
            request_id="request-123",
        )

    assert repository.saved == []
    assert unit_of_work.commit_count == 0
    assert unit_of_work.rolled_back is True
    assert "settings update" not in caplog.text
