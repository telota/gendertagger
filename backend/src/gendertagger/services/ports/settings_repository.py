"""Application repository contract for the deployment settings singleton."""

from typing import Protocol

from gendertagger.models.admin_settings import DeploymentSettings


class SettingsRepository(Protocol):
    """Read the one deployment-wide settings record without owning the transaction."""

    def get_deployment_settings(self) -> DeploymentSettings | None:
        """Return the singleton record, or ``None`` when required storage state is absent."""
        ...
