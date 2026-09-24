"""Unit coverage for administrative settings resolution (ADR-0040)."""

from types import TracebackType
from typing import Self, cast

import pytest

from gendertagger.models.admin_settings import (
    BrandingEditableValues,
    BrandingOverrides,
    DeploymentSettings,
)
from gendertagger.models.branding import BrandingInfo, BrandingInitiative
from gendertagger.services.admin_settings import AdminSettingsService
from gendertagger.services.ports.persistence_errors import SettingsUnavailableError
from gendertagger.services.ports.settings_repository import SettingsRepository
from gendertagger.services.ports.unit_of_work import UnitOfWork

pytestmark = pytest.mark.unit


class StubUnitOfWork:
    """Minimal read-only settings unit of work for deterministic service tests."""

    def __init__(self, settings: DeploymentSettings | None) -> None:
        self._settings = settings
        self.settings_reads = 0

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
    def settings(self) -> SettingsRepository:
        return cast(SettingsRepository, self)

    def get_deployment_settings(self) -> DeploymentSettings | None:
        self.settings_reads += 1
        return self._settings


def _service(overrides: BrandingOverrides) -> tuple[AdminSettingsService, StubUnitOfWork]:
    unit_of_work = StubUnitOfWork(DeploymentSettings(revision=3, branding_overrides=overrides))
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
        deployment_branding=BrandingInfo(
            institution_name="Environment Institute",
            institution_url="https://environment.example",
            logo_url="/api/v1/branding/logo",
            editors=["Environment Editor"],
            published_since_year=2020,
            initiatives=[BrandingInitiative(name="Initiative", url="https://initiative.example")],
            contact_email="environment@example.org",
            privacy_notice_url="/privacy",
        ),
    )
    return service, unit_of_work


def test_settings_resolution_prioritizes_explicit_overrides_and_preserves_clears() -> None:
    service, unit_of_work = _service(
        BrandingOverrides(
            institution_name="Stored Institute",
            contact_email=None,
            editors=[],
        )
    )

    settings = service.get_settings()

    assert unit_of_work.settings_reads == 1
    assert settings.revision == 3
    assert settings.branding.institution_name == "Stored Institute"
    assert settings.branding.institution_url == "https://environment.example"
    assert settings.branding.contact_email is None
    assert settings.branding.editors == []
    assert settings.branding.initiatives == [
        BrandingInitiative(name="Initiative", url="https://initiative.example")
    ]
    assert settings.branding.logo_url == "/api/v1/branding/logo"
    assert settings.branding_defaults.contact_email == "environment@example.org"
    assert settings.overridden_fields == ["institution_name", "contact_email", "editors"]


def test_settings_resolution_uses_defaults_for_empty_override_document() -> None:
    service, _ = _service(BrandingOverrides())

    settings = service.get_settings()

    assert settings.branding.institution_name == "Environment Institute"
    assert settings.branding.editors == ["Environment Editor"]
    assert settings.overridden_fields == []


def test_missing_settings_singleton_is_an_operational_failure() -> None:
    unit_of_work = StubUnitOfWork(None)
    service = AdminSettingsService(
        unit_of_work_factory=lambda: cast(UnitOfWork, unit_of_work),
        branding_defaults=BrandingEditableValues(
            institution_name=None,
            institution_url=None,
            contact_email=None,
            privacy_notice_url=None,
            editors=[],
            published_since_year=None,
        ),
        deployment_branding=BrandingInfo(),
    )

    with pytest.raises(SettingsUnavailableError, match="singleton is missing"):
        service.get_settings()

    assert unit_of_work.settings_reads == 1
