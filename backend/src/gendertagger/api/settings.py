"""Environment-backed FastAPI application settings."""

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field
from pydantic_settings import SettingsConfigDict

from gendertagger.config.settings import ClassificationRuntimeSettings
from gendertagger.models.branding import BrandingInitiative, BrandingLegalEntity
from gendertagger.services.authentication import (
    DEFAULT_KEEP_SIGNED_IN_IDLE,
    DEFAULT_SESSION_IDLE,
    DEFAULT_SESSION_MAX_LIFETIME,
)


class BrandingSettings(BaseModel):
    """Operator-supplied deployment branding (ADR-0036), read from ``GENDERTAGGER_BRANDING__*``.

    Every field is optional and absent by default: an unconfigured deployment serves an empty legal
    notice rather than one institution's hard-coded identity. ``logo_path`` is a file the deployment
    mounts into this container; ``GET /api/v1/branding/logo`` serves it and is otherwise ``404``.
    """

    model_config = ConfigDict(frozen=True)

    institution_name: str | None = None
    institution_url: str | None = None
    logo_path: Path | None = None
    editors: list[str] = Field(default_factory=list)
    published_since_year: int | None = None
    initiatives: list[BrandingInitiative] = Field(default_factory=list)
    contact_email: str | None = None
    privacy_notice_url: str | None = None
    legal_entity: BrandingLegalEntity | None = None


class AppSettings(ClassificationRuntimeSettings):
    """Validated API process settings loaded from ``GENDERTAGGER_*`` variables."""

    model_config = SettingsConfigDict(env_nested_delimiter="__")

    database_echo: bool = Field(
        default=False,
        description="Emit SQLAlchemy SQL logs for local diagnostics.",
    )
    max_snapshot_upload_bytes: int = Field(default=500 * 1024 * 1024, gt=0)
    max_snapshot_source_files: int = Field(default=128, gt=0, le=10_000)
    max_archive_member_bytes: int = Field(default=100 * 1024 * 1024, gt=0)
    max_archive_expanded_bytes: int = Field(default=500 * 1024 * 1024, gt=0)
    max_archive_compression_ratio: float = Field(default=100.0, gt=1.0, le=10_000.0)
    max_import_record_count: int = Field(default=1_000_000, gt=0)
    max_tabular_cell_bytes: int = Field(default=1024 * 1024, gt=0)
    session_idle_seconds: int = Field(
        default=int(DEFAULT_SESSION_IDLE.total_seconds()),
        gt=0,
        description=(
            "Idle limit of a browser-session login; each request slides it forward (ADR-0032). "
            "Limits of 20 hours or less lose WCAG 2.2.1's 20-hour exception."
        ),
    )
    session_keep_signed_in_idle_seconds: int = Field(
        default=int(DEFAULT_KEEP_SIGNED_IN_IDLE.total_seconds()),
        gt=0,
        description="Idle limit of a 'keep me signed in' login; slides like the default (ADR-0032).",
    )
    session_max_lifetime_seconds: int = Field(
        default=int(DEFAULT_SESSION_MAX_LIFETIME.total_seconds()),
        gt=0,
        description="Absolute limit of any session from its login, however active (ADR-0032).",
    )
    branding: BrandingSettings = Field(default_factory=BrandingSettings)


def load_settings() -> AppSettings:
    """Load application settings from process configuration sources."""
    return AppSettings()  # type: ignore[call-arg]  # Values come from configured settings sources.
