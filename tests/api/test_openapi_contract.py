import json
from pathlib import Path

from pydantic import SecretStr

from gendertagger.api.app import create_app
from gendertagger.api.settings import AppSettings
from gendertagger.services.unit_of_work import UnitOfWork

DATABASE_URL = "postgresql+psycopg://api:secret@localhost/gendertagger"
CODE_GIT_COMMIT = "a" * 40
DEPENDENCY_LOCK_SHA256 = "b" * 64
OPENAPI_SNAPSHOT = Path(__file__).parents[1] / "fixtures" / "openapi-v1.json"


def _unused_unit_of_work_factory() -> UnitOfWork:
    raise AssertionError("OpenAPI generation must not open persistence")


def test_openapi_matches_committed_public_contract() -> None:
    application = create_app(
        settings=AppSettings(
            database_url=SecretStr(DATABASE_URL),
            code_git_commit=CODE_GIT_COMMIT,
            dependency_lock_sha256=DEPENDENCY_LOCK_SHA256,
        ),
        unit_of_work_factory=_unused_unit_of_work_factory,
    )

    rendered_schema = (
        json.dumps(
            application.openapi(),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )

    assert rendered_schema == OPENAPI_SNAPSHOT.read_text(encoding="utf-8")
    assert "storage_uri" not in rendered_schema
    assert "task_id" not in rendered_schema
