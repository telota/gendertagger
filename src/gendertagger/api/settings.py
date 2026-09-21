"""Environment-backed FastAPI application settings."""

from pathlib import Path

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

from gendertagger.models.project import SHA256_PATTERN
from gendertagger.services.authentication import (
    DEFAULT_KEEP_SIGNED_IN_IDLE,
    DEFAULT_SESSION_IDLE,
    DEFAULT_SESSION_MAX_LIFETIME,
)


class AppSettings(BaseSettings):
    """Validated process settings loaded from ``GENDERTAGGER_*`` variables."""

    model_config = SettingsConfigDict(
        env_prefix="GENDERTAGGER_",
        extra="ignore",
        frozen=True,
        hide_input_in_errors=True,
    )

    database_url: SecretStr
    code_git_commit: str = Field(min_length=1, max_length=100)
    dependency_lock_sha256: str = Field(pattern=SHA256_PATTERN)
    container_image_digest: str | None = None
    database_echo: bool = Field(
        default=False,
        description="Emit SQLAlchemy SQL logs for local diagnostics.",
    )
    artifact_root: Path = Path("data/artifacts")
    model_cache_root: Path = Path("data/model-cache")
    max_snapshot_upload_bytes: int = Field(default=500 * 1024 * 1024, gt=0)
    max_snapshot_source_files: int = Field(default=128, gt=0, le=10_000)
    max_archive_member_bytes: int = Field(default=100 * 1024 * 1024, gt=0)
    max_archive_expanded_bytes: int = Field(default=500 * 1024 * 1024, gt=0)
    max_archive_compression_ratio: float = Field(default=100.0, gt=1.0, le=10_000.0)
    max_import_record_count: int = Field(default=1_000_000, gt=0)
    max_tabular_cell_bytes: int = Field(default=1024 * 1024, gt=0)
    tei_import_batch_record_count: int = Field(default=500, gt=0, le=10_000)
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

    @field_validator("database_url")
    @classmethod
    def _validate_database_url(cls, value: SecretStr) -> SecretStr:
        try:
            database_url = make_url(value.get_secret_value())
        except ArgumentError as error:
            msg = "database_url must be a valid SQLAlchemy URL"
            raise ValueError(msg) from error
        if database_url.drivername != "postgresql+psycopg":
            msg = "database_url must use the postgresql+psycopg driver"
            raise ValueError(msg)
        return value

    @field_validator("code_git_commit")
    @classmethod
    def _validate_code_git_commit(cls, value: str) -> str:
        if not value.strip():
            msg = "code_git_commit must not be blank"
            raise ValueError(msg)
        return value


def load_settings() -> AppSettings:
    """Load application settings from process configuration sources."""
    return AppSettings()  # type: ignore[call-arg]  # Values come from configured settings sources.
