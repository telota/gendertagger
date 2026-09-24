"""Administrative deployment-branding settings contracts (ADR-0040)."""

import re
from datetime import UTC, datetime
from enum import StrEnum
from urllib.parse import urlsplit

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictInt,
    ValidationInfo,
    field_validator,
    model_validator,
)

from gendertagger.models.branding import BrandingInfo

_CONTROL_CHARACTER_PATTERN = re.compile(r"[\x00-\x1f\x7f-\x9f]")
_EMAIL_PATTERN = re.compile(
    r"(?=.{1,254}\Z)(?=.{1,64}@)[A-Za-z0-9!#$%&'*+/=?^_`{|}~-]+"
    r"(?:\.[A-Za-z0-9!#$%&'*+/=?^_`{|}~-]+)*@"
    r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
    r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)*\Z"
)
MAX_BRANDING_TEXT_LENGTH = 200
MAX_BRANDING_URL_LENGTH = 2048
MAX_EDITOR_COUNT = 50


def _reject_control_characters(value: str, *, field_name: str) -> None:
    """Reject control characters from a human-facing administrative value."""
    if _CONTROL_CHARACTER_PATTERN.search(value):
        msg = f"{field_name} must not contain control characters"
        raise ValueError(msg)


def _normalized_text(value: str, *, field_name: str) -> str:
    """Trim and validate a short publication text value."""
    normalized = value.strip()
    _reject_control_characters(normalized, field_name=field_name)
    if not normalized or len(normalized) > MAX_BRANDING_TEXT_LENGTH:
        msg = f"{field_name} must contain 1 to 200 characters"
        raise ValueError(msg)
    return normalized


def _validated_url(value: str, *, field_name: str) -> str:
    """Accept an absolute HTTP(S) URL or a same-origin path with no unsafe syntax."""
    _reject_control_characters(value, field_name=field_name)
    if len(value) > MAX_BRANDING_URL_LENGTH or any(character.isspace() for character in value):
        msg = f"{field_name} must be a URL no longer than 2048 characters"
        raise ValueError(msg)
    if "\\" in value:
        msg = f"{field_name} must not contain backslashes"
        raise ValueError(msg)
    if value.startswith("/"):
        if value.startswith("//"):
            msg = f"{field_name} must begin with exactly one slash"
            raise ValueError(msg)
        return value
    parsed = urlsplit(value)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.netloc
        or parsed.username is not None
        or parsed.password is not None
    ):
        msg = f"{field_name} must be an absolute HTTP(S) URL or same-origin path"
        raise ValueError(msg)
    return value


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
    confined to ``BrandingOverrides``, so read construction cannot tighten accepted environment settings.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    institution_name: str | None
    institution_url: str | None
    contact_email: str | None
    privacy_notice_url: str | None
    editors: list[str]
    published_since_year: int | None


class BrandingOverrides(BaseModel):
    """Sparse, write-validated overrides retaining omission separately from explicit clearing."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    institution_name: str | None = None
    institution_url: str | None = None
    contact_email: str | None = None
    privacy_notice_url: str | None = None
    editors: list[str] = Field(default_factory=list)
    published_since_year: StrictInt | None = None

    @field_validator("institution_name")
    @classmethod
    def _validate_institution_name(cls, value: str | None) -> str | None:
        return None if value is None else _normalized_text(value, field_name="institution_name")

    @field_validator("institution_url", "privacy_notice_url")
    @classmethod
    def _validate_url(cls, value: str | None, info: ValidationInfo) -> str | None:
        field_name = info.field_name or "url"
        return None if value is None else _validated_url(value, field_name=field_name)

    @field_validator("contact_email")
    @classmethod
    def _validate_contact_email(cls, value: str | None) -> str | None:
        if value is None:
            return None
        _reject_control_characters(value, field_name="contact_email")
        if not _EMAIL_PATTERN.fullmatch(value):
            msg = "contact_email must contain one syntactically valid mailbox address"
            raise ValueError(msg)
        return value

    @field_validator("editors")
    @classmethod
    def _validate_editors(cls, values: list[str]) -> list[str]:
        if len(values) > MAX_EDITOR_COUNT:
            msg = "editors must contain at most 50 entries"
            raise ValueError(msg)
        normalized = [_normalized_text(value, field_name="editors") for value in values]
        if len(set(normalized)) != len(normalized):
            msg = "editors must not contain duplicate trimmed entries"
            raise ValueError(msg)
        return normalized

    @field_validator("published_since_year")
    @classmethod
    def _validate_published_since_year(cls, value: int | None) -> int | None:
        if value is None:
            return None
        current_year = datetime.now(UTC).year
        if not 1 <= value <= current_year:
            msg = f"published_since_year must be between 1 and {current_year}"
            raise ValueError(msg)
        return value


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


class AdminSettingsUpdate(BaseModel):
    """Revision-checked request to set one or more explicit branding overrides."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    expected_revision: int = Field(ge=0)
    branding: BrandingOverrides

    @model_validator(mode="after")
    def _require_nonempty_branding(self) -> "AdminSettingsUpdate":
        if not self.branding.model_fields_set:
            msg = "branding must contain at least one override field"
            raise ValueError(msg)
        return self


class AdminSettingsReset(BaseModel):
    """Revision-checked request to remove selected branding overrides."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    expected_revision: int = Field(ge=0)
    fields: list[BrandingSettingField] = Field(min_length=1)

    @field_validator("fields")
    @classmethod
    def _validate_distinct_fields(
        cls, values: list[BrandingSettingField]
    ) -> list[BrandingSettingField]:
        if len(set(values)) != len(values):
            msg = "fields must not contain duplicates"
            raise ValueError(msg)
        return values
