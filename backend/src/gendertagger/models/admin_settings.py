"""Administrative deployment-branding settings contracts (ADR-0040)."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from gendertagger.models.branding import BrandingInfo


class BrandingSettingField(StrEnum):
    """One branding property administrators may override."""

    institution_name = "institution_name"
    institution_url = "institution_url"
    contact_email = "contact_email"
    privacy_notice_url = "privacy_notice_url"
    editors = "editors"
    published_since_year = "published_since_year"


class BrandingEditableValues(BaseModel):
    """The six editable branding values after deployment fallback resolution.

    This contract deliberately mirrors existing environment value types. Administrative write validation is
    introduced with the mutation slice, so read construction cannot tighten accepted environment settings.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    institution_name: str | None
    institution_url: str | None
    contact_email: str | None
    privacy_notice_url: str | None
    editors: list[str]
    published_since_year: int | None


class BrandingOverrides(BaseModel):
    """Sparse stored branding overrides retaining omission separately from explicit clearing.

    Use ``model_dump(exclude_unset=True)`` when persisting or resolving this model. A nullable field set
    to ``None`` remains present in that document, while an omitted field is absent. ``editors`` cannot be
    ``None``; an explicit empty list is its clearing override.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    institution_name: str | None = None
    institution_url: str | None = None
    contact_email: str | None = None
    privacy_notice_url: str | None = None
    editors: list[str] = Field(default_factory=list)
    published_since_year: int | None = None


class DeploymentSettings(BaseModel):
    """Canonical singleton settings record returned by persistence without an ORM row."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    revision: int = Field(ge=0)
    branding_overrides: BrandingOverrides


class AdminSettings(BaseModel):
    """Administrator-visible effective branding, fallback values, and override metadata."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    revision: int = Field(ge=0)
    branding: BrandingInfo
    branding_defaults: BrandingEditableValues
    overridden_fields: list[BrandingSettingField]
