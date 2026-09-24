"""PostgreSQL coverage for public ADR-0040 branding resolution."""

from functools import partial
from typing import cast
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import Engine, insert

from gendertagger.api.app import create_app
from gendertagger.api.settings import AppSettings, BrandingSettings
from gendertagger.db.rows.settings import DeploymentSettingsRow
from gendertagger.db.session import create_session_factory
from gendertagger.db.unit_of_work import SqlAlchemyUnitOfWork
from gendertagger.models.admin_settings import AdminSettingsUpdate, BrandingOverrides
from gendertagger.services.admin_settings import AdminSettingsService
from gendertagger.services.ports.unit_of_work import UnitOfWorkFactory

pytestmark = [pytest.mark.integration, pytest.mark.postgres]

DATABASE_URL = "postgresql+psycopg://api:secret@localhost/gendertagger"
ACTOR_ID = UUID("10000000-0000-0000-0000-000000000001")


def _settings() -> AppSettings:
    return AppSettings(
        database_url=SecretStr(DATABASE_URL),
        code_git_commit="a" * 40,
        dependency_lock_sha256="b" * 64,
        branding=BrandingSettings(
            institution_name="Environment Institute",
            contact_email="environment@example.org",
        ),
    )


def test_independent_applications_read_committed_branding_overrides(
    postgres_engine: Engine,
) -> None:
    with postgres_engine.begin() as connection:
        connection.execute(
            insert(DeploymentSettingsRow).values(
                id=1,
                revision=0,
                branding_overrides={},
            )
        )
    factory: UnitOfWorkFactory = partial(
        SqlAlchemyUnitOfWork,
        create_session_factory(postgres_engine),
    )
    first_application = create_app(settings=_settings(), unit_of_work_factory=factory)
    second_application = create_app(settings=_settings(), unit_of_work_factory=factory)
    first_service = cast(AdminSettingsService, first_application.state.admin_settings_service)

    first_service.update_settings(
        AdminSettingsUpdate(
            expected_revision=0,
            branding=BrandingOverrides(
                institution_name="Committed Institute",
                contact_email=None,
            ),
        ),
        actor_user_id=ACTOR_ID,
        request_id="cross-instance-update",
    )

    with (
        TestClient(first_application) as first_client,
        TestClient(second_application) as second_client,
    ):
        first_response = first_client.get("/api/v1/branding")
        second_response = second_client.get("/api/v1/branding")

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    assert first_response.headers["cache-control"] == "no-store"
    assert first_response.json() == second_response.json()
    assert first_response.json()["institution_name"] == "Committed Institute"
    assert first_response.json()["contact_email"] is None
    assert "revision" not in first_response.json()
    assert "branding_defaults" not in first_response.json()
