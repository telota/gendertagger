"""SQLAlchemy repository for the deployment-settings singleton."""

from pydantic import ValidationError
from sqlalchemy import func, select, update
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
        return self._get_deployment_settings(lock=False)

    def get_deployment_settings_for_update(self) -> DeploymentSettings | None:
        """Return the singleton under a row lock, or map inaccessible storage to one safe failure."""
        return self._get_deployment_settings(lock=True)

    def save_deployment_settings(self, settings: DeploymentSettings) -> None:
        """Persist a complete changed settings document without committing the caller's transaction."""
        try:
            self._session.execute(
                update(DeploymentSettingsRow)
                .where(DeploymentSettingsRow.id == 1)
                .values(
                    revision=settings.revision,
                    branding_overrides=settings.branding_overrides.model_dump(
                        exclude_unset=True,
                        mode="json",
                    ),
                    updated_at=func.now(),
                )
            )
            self._session.flush()
        except SQLAlchemyError as error:
            raise SettingsUnavailableError("Settings storage is unavailable.") from error

    def _get_deployment_settings(self, *, lock: bool) -> DeploymentSettings | None:
        statement = select(DeploymentSettingsRow).where(DeploymentSettingsRow.id == 1)
        if lock:
            statement = statement.with_for_update()
        try:
            row = self._session.scalar(statement)
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
