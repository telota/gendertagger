"""Administrative deployment-branding settings reads (ADR-0040)."""

from gendertagger.models.admin_settings import (
    AdminSettings,
    BrandingEditableValues,
    BrandingOverrides,
    BrandingSettingField,
)
from gendertagger.models.branding import BrandingInfo
from gendertagger.services.ports.persistence_errors import SettingsUnavailableError
from gendertagger.services.ports.unit_of_work import UnitOfWorkFactory


class AdminSettingsService:
    """Resolve stored branding overrides without exposing persistence or API settings.

    The service reads the singleton once per invocation. Deployment fallbacks are typed values injected at
    composition time, so this layer does not depend on process configuration or the API package.
    """

    def __init__(
        self,
        *,
        unit_of_work_factory: UnitOfWorkFactory,
        branding_defaults: BrandingEditableValues,
        deployment_branding: BrandingInfo,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._branding_defaults = branding_defaults
        self._deployment_branding = deployment_branding

    def get_settings(self) -> AdminSettings:
        """Read the singleton and resolve override, deployment fallback, then application default."""
        with self._unit_of_work_factory() as unit_of_work:
            stored = unit_of_work.settings.get_deployment_settings()
        if stored is None:
            raise SettingsUnavailableError("The deployment settings singleton is missing.")
        effective_values = _resolve_editable_values(
            defaults=self._branding_defaults,
            overrides=stored.branding_overrides,
        )
        return AdminSettings(
            revision=stored.revision,
            branding=self._deployment_branding.model_copy(
                update=effective_values.model_dump(mode="python")
            ),
            branding_defaults=self._branding_defaults,
            overridden_fields=_overridden_fields(stored.branding_overrides),
        )


def _resolve_editable_values(
    *, defaults: BrandingEditableValues, overrides: BrandingOverrides
) -> BrandingEditableValues:
    """Overlay explicit stored keys, including ``null`` and empty-list clearing values."""
    values = defaults.model_dump(mode="python")
    values.update(overrides.model_dump(exclude_unset=True, mode="python"))
    return BrandingEditableValues.model_validate(values)


def _overridden_fields(overrides: BrandingOverrides) -> list[BrandingSettingField]:
    """Return explicit override names once in the canonical allowlist order."""
    explicit_fields = overrides.model_fields_set
    return [field for field in BrandingSettingField if field.value in explicit_fields]
