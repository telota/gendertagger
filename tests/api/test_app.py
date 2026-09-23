from typing import Annotated

import pytest
from fastapi import Depends
from fastapi.testclient import TestClient
from pydantic import SecretStr, ValidationError

from gendertagger.api.app import create_app
from gendertagger.api.dependencies import get_unit_of_work_factory
from gendertagger.api.settings import AppSettings, load_settings
from gendertagger.services.ports.unit_of_work import UnitOfWork, UnitOfWorkFactory

DATABASE_URL = "postgresql+psycopg://api:secret@localhost/gendertagger"
CODE_GIT_COMMIT = "a" * 40
DEPENDENCY_LOCK_SHA256 = "b" * 64


def _unused_unit_of_work_factory() -> UnitOfWork:
    raise AssertionError("the composition test must not open a unit of work")


def test_settings_load_prefixed_environment_without_exposing_database_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GENDERTAGGER_DATABASE_URL", DATABASE_URL)
    monkeypatch.setenv("GENDERTAGGER_DATABASE_ECHO", "true")
    monkeypatch.setenv("GENDERTAGGER_CODE_GIT_COMMIT", CODE_GIT_COMMIT)
    monkeypatch.setenv("GENDERTAGGER_DEPENDENCY_LOCK_SHA256", DEPENDENCY_LOCK_SHA256)
    monkeypatch.setenv("GENDERTAGGER_MAX_SNAPSHOT_SOURCE_FILES", "64")
    monkeypatch.setenv("GENDERTAGGER_MAX_ARCHIVE_EXPANDED_BYTES", "1048576")
    monkeypatch.setenv("GENDERTAGGER_MAX_TABULAR_CELL_BYTES", "4096")

    settings = load_settings()

    assert settings.database_url.get_secret_value() == DATABASE_URL
    assert settings.code_git_commit == CODE_GIT_COMMIT
    assert settings.dependency_lock_sha256 == DEPENDENCY_LOCK_SHA256
    assert settings.database_echo is True
    assert settings.max_snapshot_source_files == 64
    assert settings.max_archive_expanded_bytes == 1_048_576
    assert settings.max_tabular_cell_bytes == 4_096
    assert "secret" not in repr(settings)


def test_settings_load_nested_branding_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GENDERTAGGER_DATABASE_URL", DATABASE_URL)
    monkeypatch.setenv("GENDERTAGGER_CODE_GIT_COMMIT", CODE_GIT_COMMIT)
    monkeypatch.setenv("GENDERTAGGER_DEPENDENCY_LOCK_SHA256", DEPENDENCY_LOCK_SHA256)
    monkeypatch.setenv(
        "GENDERTAGGER_BRANDING__INSTITUTION_NAME", "Berlin-Brandenburgische Akademie"
    )
    monkeypatch.setenv("GENDERTAGGER_BRANDING__CONTACT_EMAIL", "telota@bbaw.de")
    monkeypatch.setenv("GENDERTAGGER_BRANDING__PUBLISHED_SINCE_YEAR", "2026")
    monkeypatch.setenv("GENDERTAGGER_BRANDING__EDITORS", '["Frederike Neuber", "Lou Klappenbach"]')
    monkeypatch.setenv("GENDERTAGGER_BRANDING__LEGAL_ENTITY__NAME", "BBAW")
    monkeypatch.setenv("GENDERTAGGER_BRANDING__LEGAL_ENTITY__VAT_ID", "DE 167 449 058")

    settings = load_settings()

    assert settings.branding.institution_name == "Berlin-Brandenburgische Akademie"
    assert settings.branding.contact_email == "telota@bbaw.de"
    assert settings.branding.published_since_year == 2026
    assert settings.branding.editors == ["Frederike Neuber", "Lou Klappenbach"]
    assert settings.branding.legal_entity is not None
    assert settings.branding.legal_entity.name == "BBAW"
    assert settings.branding.legal_entity.vat_id == "DE 167 449 058"


def test_settings_default_branding_is_fully_unconfigured() -> None:
    settings = AppSettings(
        database_url=SecretStr(DATABASE_URL),
        code_git_commit=CODE_GIT_COMMIT,
        dependency_lock_sha256=DEPENDENCY_LOCK_SHA256,
    )

    assert settings.branding.institution_name is None
    assert settings.branding.legal_entity is None
    assert settings.branding.editors == []


def test_settings_require_supported_postgresql_driver() -> None:
    with pytest.raises(ValidationError, match="postgresql\\+psycopg"):
        AppSettings(
            database_url=SecretStr("sqlite+pysqlite:///:memory:"),
            code_git_commit=CODE_GIT_COMMIT,
            dependency_lock_sha256=DEPENDENCY_LOCK_SHA256,
        )


def test_application_exposes_injected_unit_of_work_factory() -> None:
    settings = AppSettings(
        database_url=SecretStr(DATABASE_URL),
        code_git_commit=CODE_GIT_COMMIT,
        dependency_lock_sha256=DEPENDENCY_LOCK_SHA256,
    )
    unit_of_work_factory: UnitOfWorkFactory = _unused_unit_of_work_factory
    application = create_app(
        settings=settings,
        unit_of_work_factory=unit_of_work_factory,
    )

    @application.get("/dependency-probe")
    def _dependency_probe(
        resolved_factory: Annotated[
            UnitOfWorkFactory,
            Depends(get_unit_of_work_factory),
        ],
    ) -> dict[str, bool]:
        return {"is_injected_factory": resolved_factory is unit_of_work_factory}

    with TestClient(application) as client:
        response = client.get("/dependency-probe")

    assert response.status_code == 200
    assert response.json() == {"is_injected_factory": True}
    assert application.title == "gendertagger API"
    assert application.version == "0.0.0"
