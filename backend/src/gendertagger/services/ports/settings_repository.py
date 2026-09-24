"""Application repository contract for the deployment settings singleton."""

from typing import Protocol

from gendertagger.models.admin_settings import DeploymentSettings


class SettingsRepository(Protocol):
    """Read the one deployment-wide settings record without owning the transaction."""

    def get_deployment_settings(self) -> DeploymentSettings | None:
        """Return the singleton record, or ``None`` when required storage state is absent."""
        ...

    def get_deployment_settings_for_update(self) -> DeploymentSettings | None:
        """Return the singleton under a transaction-scoped row lock, or ``None`` when absent."""
        ...

    def save_deployment_settings(self, settings: DeploymentSettings) -> None:
        """Persist a complete changed override document and revision without committing."""
        ...
