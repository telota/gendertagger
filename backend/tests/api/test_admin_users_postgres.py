from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi import Request
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import Engine

from gendertagger.api.app import create_app
from gendertagger.api.authentication import AuthenticationBackend
from gendertagger.api.settings import AppSettings
from gendertagger.db.session import create_session_factory
from gendertagger.db.unit_of_work import SqlAlchemyUnitOfWork
from gendertagger.models.user import GlobalRole, UserCreate
from gendertagger.services.ports.unit_of_work import UnitOfWork, UnitOfWorkFactory

pytestmark = [pytest.mark.integration, pytest.mark.postgres]

DATABASE_URL = "postgresql+psycopg://unused:unused@localhost/unused"


class _StaticAuthenticationBackend(AuthenticationBackend):
    def __init__(self, user_id: UUID) -> None:
        self._user_id = user_id

    def authenticate(self, request: Request) -> UUID | None:
        return self._user_id

    def validate_csrf(self, request: Request, *, user_id: UUID) -> bool:
        return user_id == self._user_id


class _Deployment:
    def __init__(self, postgres_engine: Engine, artifact_root: Path) -> None:
        session_factory = create_session_factory(postgres_engine)

        def unit_of_work_factory() -> UnitOfWork:
            return SqlAlchemyUnitOfWork(session_factory)

        self.unit_of_work_factory: UnitOfWorkFactory = unit_of_work_factory
        self.application = create_app(
            settings=AppSettings(
                database_url=SecretStr(DATABASE_URL),
                code_git_commit="a" * 40,
                dependency_lock_sha256="b" * 64,
                artifact_root=artifact_root,
            ),
            unit_of_work_factory=unit_of_work_factory,
            authentication_backend=_StaticAuthenticationBackend(uuid4()),
        )
        self.client = TestClient(self.application)

    def add_local_account(
        self,
        display_name: str,
        username: str,
        *roles: GlobalRole,
    ) -> UUID:
        with self.unit_of_work_factory() as unit_of_work:
            user = unit_of_work.users.add_user(
                UserCreate(display_name=display_name, roles=set(roles))
            )
            unit_of_work.auth.add_credential(
                user_id=user.id,
                username=username,
                password_hash="not-used-by-this-test",
            )
            unit_of_work.commit()
        return user.id

    def add_provider_user_without_local_credential(self, display_name: str) -> UUID:
        with self.unit_of_work_factory() as unit_of_work:
            user = unit_of_work.users.add_user(UserCreate(display_name=display_name))
            unit_of_work.commit()
        return user.id

    def act_as(self, user_id: UUID) -> TestClient:
        self.application.state.authentication_backend = _StaticAuthenticationBackend(user_id)
        return self.client


def test_admin_user_directory_searches_and_paginates_local_accounts(
    postgres_engine: Engine,
    tmp_path: Path,
) -> None:
    deployment = _Deployment(postgres_engine, tmp_path)
    prefix = f"directory-{uuid4().hex[:8]}"
    admin_id = deployment.add_local_account(
        "Directory administrator",
        f"admin-{uuid4().hex[:8]}",
        GlobalRole.admin,
    )
    account_ids = [
        deployment.add_local_account(f"{prefix} Alpha", f"{prefix}-a"),
        deployment.add_local_account(f"{prefix} Beta", f"{prefix}-b", GlobalRole.operator),
        deployment.add_local_account(f"{prefix} Gamma", f"{prefix}-c"),
    ]
    deployment.add_provider_user_without_local_credential(f"{prefix} external")
    client = deployment.act_as(admin_id)

    first_page = client.get(
        "/api/v1/admin/users",
        params={"query": prefix.upper(), "limit": 2},
    )
    second_page = client.get(
        "/api/v1/admin/users",
        params={
            "query": prefix,
            "limit": 2,
            "cursor": first_page.json()["next_cursor"],
        },
    )

    assert first_page.status_code == 200
    assert second_page.status_code == 200
    items = first_page.json()["items"] + second_page.json()["items"]
    assert [item["id"] for item in items] == [str(user_id) for user_id in account_ids]
    assert [item["username"] for item in items] == [
        f"{prefix}-a",
        f"{prefix}-b",
        f"{prefix}-c",
    ]
    assert (first_page.json()["has_more"], second_page.json()["has_more"]) == (True, False)
    assert items[1]["roles"] == ["operator"]
    assert all("password_hash" not in item for item in items)


def test_admin_user_directory_treats_search_wildcards_as_literals(
    postgres_engine: Engine,
    tmp_path: Path,
) -> None:
    deployment = _Deployment(postgres_engine, tmp_path)
    prefix = f"wildcard-{uuid4().hex[:8]}"
    admin_id = deployment.add_local_account("Administrator", f"{prefix}-admin", GlobalRole.admin)
    matching_id = deployment.add_local_account("Literal 100% match", f"{prefix}-match")
    deployment.add_local_account("Literal 1000 match", f"{prefix}-other")

    response = deployment.act_as(admin_id).get(
        "/api/v1/admin/users",
        params={"query": "100%"},
    )

    assert response.status_code == 200
    assert [item["id"] for item in response.json()["items"]] == [str(matching_id)]
