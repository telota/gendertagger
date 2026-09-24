"""Local-account authentication transport and domain contracts.

See [ADR-0031](../../../../docs/decisions/ADR-0031-local-database-authentication.md). `CurrentUser` in
`gendertagger.models.user` stays provider-neutral; everything here is specific to the local,
database-backed account provider.
"""

import re
from typing import Annotated, Self
from uuid import UUID

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    field_validator,
    model_validator,
)
from pydantic.json_schema import SkipJsonSchema

from gendertagger.models.common import UtcDatetime
from gendertagger.models.user import GlobalRole

MIN_LOCAL_PASSWORD_LENGTH = 12
_USERNAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]{0,62}[a-z0-9]$")


def validate_local_password_length(password: str) -> str:
    """Enforce the minimum length shared by every path that sets a local password."""
    if len(password) < MIN_LOCAL_PASSWORD_LENGTH:
        msg = f"password must be at least {MIN_LOCAL_PASSWORD_LENGTH} characters"
        raise ValueError(msg)
    return password


def normalize_username(value: str) -> str:
    """Fold a login identifier to its canonical, case-insensitive stored form."""
    normalized = value.strip().lower()
    if not _USERNAME_PATTERN.fullmatch(normalized):
        msg = "username must be 2-64 lowercase letters, digits, '.', '_', or '-'"
        raise ValueError(msg)
    return normalized


Username = Annotated[str, AfterValidator(normalize_username)]


class AdminUser(BaseModel):
    """Administrator-facing read model for one local account (ADR-0039)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID
    display_name: str = Field(min_length=1, max_length=200)
    username: Username
    roles: set[GlobalRole]
    is_active: bool
    must_change_password: bool
    created_at: UtcDatetime


class AdminUserCreate(BaseModel):
    """Global-administrator command for provisioning one local account."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    display_name: str = Field(min_length=1, max_length=200)
    username: Username
    roles: set[GlobalRole] = Field(default_factory=set)

    @field_validator("display_name")
    @classmethod
    def _validate_display_name(cls, value: str) -> str:
        if not value.strip():
            msg = "display_name must not be blank"
            raise ValueError(msg)
        return value


class AdminUserCreateResult(BaseModel):
    """Created account plus its once-returned temporary password."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    account: AdminUser
    temporary_password: str = Field(min_length=MIN_LOCAL_PASSWORD_LENGTH, repr=False)


class AdminUserPasswordResetResult(BaseModel):
    """Once-disclosed temporary password from a global-administrator reset."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    temporary_password: str = Field(min_length=MIN_LOCAL_PASSWORD_LENGTH, repr=False)


class AdminUserUpdate(BaseModel):
    """Global-administrator patch for mutable local-account fields."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    display_name: Annotated[str, Field(max_length=200)] | SkipJsonSchema[None] = None
    roles: set[GlobalRole] | SkipJsonSchema[None] = None
    is_active: bool | SkipJsonSchema[None] = None

    @field_validator("display_name")
    @classmethod
    def _validate_display_name(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            msg = "display_name must not be blank"
            raise ValueError(msg)
        return value

    @model_validator(mode="after")
    def _reject_explicit_nulls(self) -> Self:
        for field_name in self.model_fields_set:
            if getattr(self, field_name) is None:
                msg = f"{field_name} must not be null"
                raise ValueError(msg)
        return self


class LoginRequest(BaseModel):
    """Public credentials submitted to establish a session."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    username: Username
    password: SecretStr = Field(min_length=1)
    keep_signed_in: bool = Field(
        default=False,
        description=(
            "Issue persistent cookies and a 7-day idle limit instead of browser-session "
            "cookies and a 24-hour idle limit (ADR-0032)."
        ),
    )


class ChangePasswordRequest(BaseModel):
    """Self-service password change, requiring proof of the current password."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    current_password: SecretStr = Field(min_length=1)
    new_password: SecretStr

    @field_validator("new_password")
    @classmethod
    def _validate_new_password(cls, value: SecretStr) -> SecretStr:
        validate_local_password_length(value.get_secret_value())
        return value


class LocalCredential(BaseModel):
    """Persistence-adjacent read model for one local account's credential state."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    user_id: UUID
    username: str
    password_hash: str
    must_change_password: bool
    updated_at: UtcDatetime


class UserSession(BaseModel):
    """Persistence-adjacent read model for one issued, not-yet-reaped session.

    ``expires_at`` is the sliding idle expiry and never passes ``absolute_expires_at``, the limit
    fixed at login (ADR-0032).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    user_id: UUID
    csrf_secret: str
    keep_signed_in: bool
    expires_at: UtcDatetime
    absolute_expires_at: UtcDatetime
    revoked_at: UtcDatetime | None = None


class CurrentSession(BaseModel):
    """Public state of the presented local-account session, readable before a password change."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    must_change_password: bool
    keep_signed_in: bool
