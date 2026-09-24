"""PostgreSQL coverage for the ADR-0040 deployment settings singleton."""

import pytest
from sqlalchemy import update
from sqlalchemy.orm import Session

from gendertagger.db.repositories.settings_repository import SqlAlchemySettingsRepository
from gendertagger.db.rows.settings import DeploymentSettingsRow

pytestmark = [pytest.mark.integration, pytest.mark.postgres]


def test_settings_repository_retains_sparse_null_and_empty_list_overrides(
    db_session: Session,
) -> None:
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
