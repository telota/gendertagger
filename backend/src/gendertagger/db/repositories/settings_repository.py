"""SQLAlchemy repository for the deployment-settings singleton."""

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from gendertagger.db.rows.settings import DeploymentSettingsRow
from gendertagger.models.admin_settings import BrandingOverrides, DeploymentSettings
from gendertagger.services.ports.persistence_errors import SettingsUnavailableError


class SqlAlchemySettingsRepository:
    """Map the validated settings singleton to its row within an owned session."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get_deployment_settings(self) -> DeploymentSettings | None:
        """Return the singleton or map inaccessible/corrupt settings storage to one safe failure."""
        try:
            row = self._session.scalar(
                select(DeploymentSettingsRow).where(DeploymentSettingsRow.id == 1)
            )
        except SQLAlchemyError as error:
            raise SettingsUnavailableError("Settings storage is unavailable.") from error
        if row is None:
            return None
        try:
            return DeploymentSettings(
                revision=row.revision,
                branding_overrides=BrandingOverrides.model_validate(row.branding_overrides),
            )
        except ValidationError as error:
            raise SettingsUnavailableError("Stored settings are invalid.") from error
