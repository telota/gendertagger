"""Closed account-owned presentation preference contracts (ADR-0043)."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, StrictBool, StrictInt, model_validator

InterfaceLocale = Literal["de", "en"]
InterfaceTheme = Literal["system", "light", "dark"]
InterfaceMode = Literal["guided", "advanced"]


def _omit_patch_default(schema: dict[str, JsonValue]) -> None:
    """Keep omission-preserving PATCH fields free of advertised replacement values."""
    schema.pop("default", None)


class UserPreferences(BaseModel):
    """Saved personal presentation choices, or virtual defaults at revision zero."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    locale: InterfaceLocale | None = Field(
        default=None,
        description="Explicit interface language; null leaves resolution to the browser.",
    )
    theme: InterfaceTheme = Field(
        default="system", description="System follows the browser's preferred color scheme."
    )
    desktop_sidebar_collapsed: StrictBool = Field(
        default=False, description="Explicit desktop choice, independent of responsive layout."
    )
    interface_mode: InterfaceMode = Field(
        default="guided",
        description=(
            "Guided shows one reduced path per project (import, generate suggestions, review); "
            "advanced shows the full navigation. A presentation choice, not a role or permission."
        ),
    )
    revision: StrictInt = Field(default=0, ge=0)


class UserPreferencesUpdate(BaseModel):
    """Nonempty partial update preserving omitted fields and checking the saved revision."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    expected_revision: StrictInt = Field(ge=0)
    locale: InterfaceLocale | None = Field(
        default=None,
        description="Omit to preserve; null clears the explicit language choice.",
        json_schema_extra=_omit_patch_default,
    )
    theme: InterfaceTheme = Field(default="system", json_schema_extra=_omit_patch_default)
    desktop_sidebar_collapsed: StrictBool = Field(
        default=False, json_schema_extra=_omit_patch_default
    )
    interface_mode: InterfaceMode = Field(default="guided", json_schema_extra=_omit_patch_default)

    @model_validator(mode="after")
    def _require_preference_field(self) -> "UserPreferencesUpdate":
        if not self.model_fields_set - {"expected_revision"}:
            msg = "at least one preference field is required"
            raise ValueError(msg)
        return self
