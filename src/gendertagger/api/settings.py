"""Environment-backed FastAPI application settings."""

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError


class AppSettings(BaseSettings):
    """Validated process settings loaded from ``GENDERTAGGER_*`` variables."""

    model_config = SettingsConfigDict(
        env_prefix="GENDERTAGGER_",
        extra="ignore",
        frozen=True,
        hide_input_in_errors=True,
    )

    database_url: SecretStr
    database_echo: bool = Field(
        default=False,
        description="Emit SQLAlchemy SQL logs for local diagnostics.",
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


def load_settings() -> AppSettings:
    """Load application settings from process configuration sources."""
    return AppSettings()  # type: ignore[call-arg]  # Values come from configured settings sources.
