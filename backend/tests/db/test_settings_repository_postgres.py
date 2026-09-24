"""PostgreSQL coverage for the ADR-0040 deployment settings singleton."""

import pytest
from sqlalchemy import insert, update
from sqlalchemy.orm import Session

from gendertagger.db.repositories.settings_repository import SqlAlchemySettingsRepository
from gendertagger.db.rows.settings import DeploymentSettingsRow
from gendertagger.models.admin_settings import BrandingOverrides, DeploymentSettings

pytestmark = [pytest.mark.integration, pytest.mark.postgres]


def test_settings_repository_retains_sparse_null_and_empty_list_overrides(
    db_session: Session,
) -> None:
    db_session.execute(
        insert(DeploymentSettingsRow).values(
            id=1,
            revision=0,
            branding_overrides={},
        )
    )
    db_session.execute(
        update(DeploymentSettingsRow)
        .where(DeploymentSettingsRow.id == 1)
        .values(
            revision=4,
            branding_overrides={"contact_email": None, "editors": []},
        )
    )
    db_session.flush()

    settings = SqlAlchemySettingsRepository(db_session).get_deployment_settings()

    assert settings is not None
    assert settings.revision == 4
    assert settings.branding_overrides.model_dump(exclude_unset=True) == {
        "contact_email": None,
        "editors": [],
    }
    assert settings.branding_overrides.model_fields_set == {"contact_email", "editors"}


def test_settings_repository_locks_and_persists_a_complete_changed_document(
    db_session: Session,
) -> None:
    db_session.execute(
        insert(DeploymentSettingsRow).values(
            id=1,
            revision=0,
            branding_overrides={},
        )
    )
    repository = SqlAlchemySettingsRepository(db_session)

    locked = repository.get_deployment_settings_for_update()
    repository.save_deployment_settings(
        DeploymentSettings(
            revision=1,
            branding_overrides=BrandingOverrides(
                institution_name="Committed Institute",
                contact_email=None,
            ),
        )
    )
    db_session.flush()
    db_session.expire_all()

    persisted = repository.get_deployment_settings()

    assert locked is not None
    assert locked.revision == 0
    assert persisted is not None
    assert persisted.revision == 1
    assert persisted.branding_overrides.model_dump(exclude_unset=True) == {
        "institution_name": "Committed Institute",
        "contact_email": None,
    }
