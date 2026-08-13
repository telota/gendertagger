from typing import Annotated

import pytest
from fastapi import Depends
from fastapi.testclient import TestClient
from pydantic import SecretStr, ValidationError

from gendertagger.api.app import create_app
from gendertagger.api.dependencies import get_unit_of_work_factory
from gendertagger.api.settings import AppSettings, load_settings
from gendertagger.services.unit_of_work import UnitOfWork, UnitOfWorkFactory

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

    settings = load_settings()

    assert settings.database_url.get_secret_value() == DATABASE_URL
    assert settings.code_git_commit == CODE_GIT_COMMIT
    assert settings.dependency_lock_sha256 == DEPENDENCY_LOCK_SHA256
    assert settings.database_echo is True
    assert "secret" not in repr(settings)


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
