"""Administrative deployment-branding settings reads and mutations (ADR-0040)."""

import logging
from collections.abc import Callable
from uuid import UUID

from sqlalchemy.exc import SQLAlchemyError

from gendertagger.models.admin_settings import (
    AdminSettings,
    AdminSettingsReset,
    AdminSettingsUpdate,
    AggregationSettingsUpdate,
    BrandingEditableValues,
    BrandingOverrides,
    BrandingSettingField,
    DeploymentSettings,
)
from gendertagger.models.branding import BrandingInfo
from gendertagger.services.ports.persistence_errors import SettingsUnavailableError
from gendertagger.services.ports.unit_of_work import UnitOfWorkFactory

logger = logging.getLogger(__name__)


class SettingsRevisionConflictError(RuntimeError):
    """Raised when a mutation's expected settings revision is stale."""

    def __init__(self, *, expected_revision: int, current_revision: int) -> None:
        self.expected_revision = expected_revision
        self.current_revision = current_revision
        super().__init__(
            f"stale settings revision {expected_revision}; current revision is {current_revision}"
        )


class AdminSettingsService:
    """Resolve and mutate deployment branding without exposing persistence or API settings.

    Deployment fallbacks are typed values injected at composition time, so this layer does not depend on
    process configuration or the API package. Every read or mutation opens one primary-database unit of work.
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
        """Read the singleton and return effective branding with administrative metadata."""
        try:
            with self._unit_of_work_factory() as unit_of_work:
                stored = unit_of_work.settings.get_deployment_settings()
        except SQLAlchemyError as error:
            raise SettingsUnavailableError("Settings storage is unavailable.") from error
        return self._admin_settings_from_stored(stored)

    def get_branding(self) -> BrandingInfo:
        """Read the singleton and return only effective public branding."""
        return self.get_settings().branding

    def update_settings(
        self,
        command: AdminSettingsUpdate,
        *,
        actor_user_id: UUID,
        request_id: str,
    ) -> AdminSettings:
        """Atomically apply explicit override fields after an optimistic revision check."""
        return self._mutate(
            expected_revision=command.expected_revision,
            transform=lambda current: _merged_overrides(current, command.branding),
            actor_user_id=actor_user_id,
            request_id=request_id,
            action="settings update",
        )

    def reset_settings(
        self,
        command: AdminSettingsReset,
        *,
        actor_user_id: UUID,
        request_id: str,
    ) -> AdminSettings:
        """Atomically remove selected overrides after an optimistic revision check."""
        return self._mutate(
            expected_revision=command.expected_revision,
            transform=lambda current: _reset_overrides(current, command.fields),
            actor_user_id=actor_user_id,
            request_id=request_id,
            action="settings reset",
        )

    def update_aggregation_settings(
        self,
        command: AggregationSettingsUpdate,
        *,
        actor_user_id: UUID,
        request_id: str,
    ) -> AdminSettings:
        """Atomically set whether `reference_partial_v1` may run (ADR-0051)."""
        try:
            with self._unit_of_work_factory() as unit_of_work:
                stored = unit_of_work.settings.get_deployment_settings_for_update()
                if stored is None:
                    raise SettingsUnavailableError("The deployment settings singleton is missing.")
                if stored.revision != command.expected_revision:
                    raise SettingsRevisionConflictError(
                        expected_revision=command.expected_revision,
                        current_revision=stored.revision,
                    )
                resulting = stored
                if stored.allow_partial_reference_aggregation != (
                    command.allow_partial_reference_aggregation
                ):
                    resulting = DeploymentSettings(
                        revision=stored.revision + 1,
                        branding_overrides=stored.branding_overrides,
                        allow_partial_reference_aggregation=(
                            command.allow_partial_reference_aggregation
                        ),
                    )
                    unit_of_work.settings.save_deployment_settings(resulting)
                unit_of_work.commit()
        except SQLAlchemyError as error:
            raise SettingsUnavailableError("Settings storage is unavailable.") from error
        result = self._admin_settings_from_stored(resulting)
        logger.info(
            "aggregation settings update by user %s (request %s; revision=%d "
            "allow_partial_reference_aggregation=%s)",
            actor_user_id,
            request_id,
            result.revision,
            result.allow_partial_reference_aggregation,
        )
        return result

    def _mutate(
        self,
        *,
        expected_revision: int,
        transform: Callable[[BrandingOverrides], BrandingOverrides],
        actor_user_id: UUID,
        request_id: str,
        action: str,
    ) -> AdminSettings:
        """Lock, compare, apply, persist if changed, and commit one complete settings document."""
        try:
            with self._unit_of_work_factory() as unit_of_work:
                stored = unit_of_work.settings.get_deployment_settings_for_update()
                if stored is None:
                    raise SettingsUnavailableError("The deployment settings singleton is missing.")
                if stored.revision != expected_revision:
                    raise SettingsRevisionConflictError(
                        expected_revision=expected_revision,
                        current_revision=stored.revision,
                    )
                proposed_overrides = transform(stored.branding_overrides)
                changed_fields = _changed_fields(
                    current=stored.branding_overrides,
                    proposed=proposed_overrides,
                )
                resulting = stored
                if changed_fields:
                    resulting = DeploymentSettings(
                        revision=stored.revision + 1,
                        branding_overrides=proposed_overrides,
                        allow_partial_reference_aggregation=stored.allow_partial_reference_aggregation,
                    )
                    unit_of_work.settings.save_deployment_settings(resulting)
                unit_of_work.commit()
        except SQLAlchemyError as error:
            raise SettingsUnavailableError("Settings storage is unavailable.") from error
        result = self._admin_settings_from_stored(resulting)
        logger.info(
            "%s by user %s (request %s; revision=%d fields=%s)",
            action,
            actor_user_id,
            request_id,
            result.revision,
            ",".join(field.value for field in changed_fields) or "none",
        )
        return result

    def _admin_settings_from_stored(self, stored: DeploymentSettings | None) -> AdminSettings:
        """Resolve a persisted singleton, rejecting absent storage as an operational failure."""
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
            allow_partial_reference_aggregation=stored.allow_partial_reference_aggregation,
        )


def _resolve_editable_values(
    *, defaults: BrandingEditableValues, overrides: BrandingOverrides
) -> BrandingEditableValues:
    """Overlay explicit stored keys, including ``null`` and empty-list clearing values."""
    values = defaults.model_dump(mode="python")
    values.update(overrides.model_dump(exclude_unset=True, mode="python"))
    return BrandingEditableValues.model_validate(values)


def _merged_overrides(current: BrandingOverrides, update: BrandingOverrides) -> BrandingOverrides:
    """Apply an explicit sparse update without treating omitted fields as resets."""
    values = current.model_dump(exclude_unset=True, mode="python")
    values.update(update.model_dump(exclude_unset=True, mode="python"))
    return BrandingOverrides.model_validate(values)


def _reset_overrides(
    current: BrandingOverrides, fields: list[BrandingSettingField]
) -> BrandingOverrides:
    """Remove selected explicit keys without substituting deployment fallback values."""
    values = current.model_dump(exclude_unset=True, mode="python")
    for field in fields:
        values.pop(field.value, None)
    return BrandingOverrides.model_validate(values)


def _changed_fields(
    *,
    current: BrandingOverrides,
    proposed: BrandingOverrides,
) -> list[BrandingSettingField]:
    """Return changed persisted keys once in canonical allowlist order."""
    current_values = current.model_dump(exclude_unset=True, mode="python")
    proposed_values = proposed.model_dump(exclude_unset=True, mode="python")
    return [
        field
        for field in BrandingSettingField
        if (field.value in current_values) != (field.value in proposed_values)
        or current_values.get(field.value) != proposed_values.get(field.value)
    ]


def _overridden_fields(overrides: BrandingOverrides) -> list[BrandingSettingField]:
    """Return explicit override names once in the canonical allowlist order."""
    explicit_fields = overrides.model_fields_set
    return [field for field in BrandingSettingField if field.value in explicit_fields]
