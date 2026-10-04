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

from gendertagger.config.public_classification import PublicClassificationPolicy
from gendertagger.models.project import SHA256_PATTERN


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
    public_classification: PublicClassificationPolicy = Field(
        default_factory=PublicClassificationPolicy
    )


class ClassificationRuntimeSettings(RuntimeSettings):
    """Require one shared build identity for API and classification-worker provenance."""

    code_git_commit: str = Field(min_length=1, max_length=100)
    dependency_lock_sha256: str = Field(pattern=SHA256_PATTERN)
    container_image_digest: str | None = None

    @field_validator("code_git_commit")
    @classmethod
    def _validate_code_git_commit(cls, value: str) -> str:
        if not value.strip():
            msg = "code_git_commit must not be blank"
            raise ValueError(msg)
        return value
