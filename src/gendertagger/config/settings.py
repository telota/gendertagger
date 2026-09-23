"""Shared environment-backed process settings.

Every process reads ``GENDERTAGGER_*`` variables through one of these classes or a subclass, so a
setting shared by the API, the Celery workers, and the CLI is declared and validated exactly once.
Process-specific settings extend them where they are consumed: ``AppSettings`` in the API,
``AssetCliSettings`` in the CLI, and ``CelerySettings`` for the broker.
"""

from pathlib import Path

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError


class GendertaggerSettings(BaseSettings):
    """Common loading rules: the ``GENDERTAGGER_`` prefix, frozen values, no echoed input."""

    model_config = SettingsConfigDict(
        env_prefix="GENDERTAGGER_",
        extra="ignore",
        frozen=True,
        hide_input_in_errors=True,
    )


class DatabaseSettings(GendertaggerSettings):
    """Settings for a process that talks to the application database."""

    database_url: SecretStr

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


class ArtifactStorageSettings(DatabaseSettings):
    """Settings for a process that also reads or writes content-addressed artifacts."""

    artifact_root: Path = Path("data/artifacts")


class RuntimeSettings(ArtifactStorageSettings):
    """Settings shared by the API process and every Celery worker."""

    model_cache_root: Path = Path("data/model-cache")
    tei_import_batch_record_count: int = Field(default=500, gt=0, le=10_000)
