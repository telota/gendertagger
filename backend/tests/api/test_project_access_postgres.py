from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import Engine

from gendertagger.api.app import create_app
from gendertagger.api.authentication import AuthenticationBackend
from gendertagger.api.settings import AppSettings
from gendertagger.db.session import create_session_factory
from gendertagger.db.unit_of_work import SqlAlchemyUnitOfWork
from gendertagger.models.team import TeamCreate
from gendertagger.models.user import GlobalRole, UserCreate
from gendertagger.services.ports.unit_of_work import UnitOfWork, UnitOfWorkFactory

pytestmark = [pytest.mark.integration, pytest.mark.postgres]

DATABASE_URL = "postgresql+psycopg://unused:unused@localhost/unused"


class StaticAuthenticationBackend(AuthenticationBackend):
    def __init__(self, user_id: UUID) -> None:
        self._user_id = user_id

    def authenticate(self, request: Request) -> UUID | None:
        return self._user_id

    def validate_csrf(self, request: Request, *, user_id: UUID) -> bool:
        return user_id == self._user_id


class _Deployment:
    """One application whose caller can be switched between persisted users."""

    def __init__(self, postgres_engine: Engine, artifact_root: Path) -> None:
        session_factory = create_session_factory(postgres_engine)

        def unit_of_work_factory() -> UnitOfWork:
            return SqlAlchemyUnitOfWork(session_factory)

        self.unit_of_work_factory: UnitOfWorkFactory = unit_of_work_factory
        self.application: FastAPI = create_app(
            settings=AppSettings(
                database_url=SecretStr(DATABASE_URL),
                code_git_commit="a" * 40,
                dependency_lock_sha256="b" * 64,
                artifact_root=artifact_root,
            ),
            unit_of_work_factory=unit_of_work_factory,
            authentication_backend=StaticAuthenticationBackend(uuid4()),
        )
        self.user_team_ids: dict[UUID, UUID] = {}
        self.client = TestClient(self.application)

    def add_user(self, display_name: str, *roles: GlobalRole) -> UUID:
        with self.unit_of_work_factory() as unit_of_work:
            user = unit_of_work.users.add_user(
                UserCreate(display_name=display_name, roles=set(roles))
            )
            team = unit_of_work.teams.add_team(
                TeamCreate(slug=f"user-{user.id.hex}", display_name=f"{display_name} team")
            )
            unit_of_work.teams.add_member(team.id, user.id)
            unit_of_work.commit()
        self.user_team_ids[user.id] = team.id
        return user.id

    def act_as(self, user_id: UUID) -> TestClient:
        self.application.state.authentication_backend = StaticAuthenticationBackend(user_id)
        return self.client

    def create_project(self, creator_id: UUID, slug: str) -> UUID:
        response = self.act_as(creator_id).post(
            "/api/v1/projects",
            json={
                "slug": slug,
                "display_name": slug.title(),
                "team_id": str(self.user_team_ids[creator_id]),
            },
        )
        assert response.status_code == 201
        assert response.json()["current_user_role"] == "operator"
        return UUID(response.json()["id"])

    def grant(self, admin_id: UUID, project_id: UUID, user_id: UUID, role: str) -> None:
        with self.unit_of_work_factory() as unit_of_work:
            project = unit_of_work.projects.get_project(project_id)
            assert project is not None
            unit_of_work.teams.add_member(project.team.id, user_id)
            unit_of_work.commit()
        response = self.act_as(admin_id).put(
            f"/api/v1/projects/{project_id}/members/{user_id}", json={"role": role}
        )
        assert response.status_code == 200


@pytest.fixture
def deployment(postgres_engine: Engine, tmp_path: Path) -> _Deployment:
    return _Deployment(postgres_engine, tmp_path)


def _slug(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex[:12]}"


def test_project_list_shows_only_member_projects_with_the_callers_role(
    deployment: _Deployment,
) -> None:
    creator = deployment.add_user("Creator", GlobalRole.operator)
    other_operator = deployment.add_user("Other operator", GlobalRole.operator)
    admin = deployment.add_user("Administrator", GlobalRole.admin)
    reviewer = deployment.add_user("Reviewer")
    outsider = deployment.add_user("Outsider")
    first = deployment.create_project(creator, _slug("a-first"))
    second = deployment.create_project(creator, _slug("b-second"))
    foreign = deployment.create_project(other_operator, _slug("c-foreign"))
    deployment.grant(admin, second, reviewer, "reviewer")

    creator_projects = deployment.act_as(creator).get("/api/v1/projects").json()["items"]
    reviewer_projects = deployment.act_as(reviewer).get("/api/v1/projects").json()["items"]
    outsider_page = deployment.act_as(outsider).get("/api/v1/projects").json()
    admin_ids = {
        item["id"]: item["current_user_role"]
        for item in deployment.act_as(admin).get("/api/v1/projects").json()["items"]
    }

    assert [(item["id"], item["current_user_role"]) for item in creator_projects] == [
        (str(first), "operator"),
        (str(second), "operator"),
    ]
    assert [(item["id"], item["current_user_role"]) for item in reviewer_projects] == [
        (str(second), "reviewer")
    ]
    assert outsider_page == {"items": [], "next_cursor": None, "has_more": False}
    assert {admin_ids[str(project)] for project in (first, second, foreign)} == {"operator"}


def test_manager_without_project_role_can_manage_roster_but_cannot_read_project_data(
    deployment: _Deployment,
) -> None:
    creator = deployment.add_user("Creator", GlobalRole.operator)
    administrator = deployment.add_user("Administrator", GlobalRole.admin)
    manager = deployment.add_user("Manager")
    project_id = deployment.create_project(creator, _slug("manager"))

    with deployment.unit_of_work_factory() as unit_of_work:
        project = unit_of_work.projects.get_project(project_id)
        assert project is not None
        unit_of_work.teams.add_member(project.team.id, manager)
        unit_of_work.commit()
    transfer = deployment.act_as(administrator).put(
        f"/api/v1/projects/{project_id}/manager",
        json={
            "manager_user_id": str(manager),
            "expected_manager_user_id": str(creator),
        },
    )

    assert transfer.status_code == 200
    assert transfer.json()["manager"]["user_id"] == str(manager)
    assert deployment.act_as(manager).get(f"/api/v1/projects/{project_id}").status_code == 404
    roster = deployment.act_as(manager).get(f"/api/v1/projects/{project_id}/members")
    assert roster.status_code == 200
    assert roster.json()["manager"]["project_role"] is None


def test_managed_projects_discovers_only_management_identities_without_project_access(
    deployment: _Deployment,
) -> None:
    creator = deployment.add_user("Creator", GlobalRole.operator)
    administrator = deployment.add_user("Administrator", GlobalRole.admin)
    manager = deployment.add_user("Manager")
    outsider = deployment.add_user("Outsider", GlobalRole.operator)
    project_id = deployment.create_project(creator, _slug("managed"))

    with deployment.unit_of_work_factory() as unit_of_work:
        project = unit_of_work.projects.get_project(project_id)
        assert project is not None
        unit_of_work.teams.add_member(project.team.id, manager)
        unit_of_work.commit()
    transfer = deployment.act_as(administrator).put(
        f"/api/v1/projects/{project_id}/manager",
        json={
            "manager_user_id": str(manager),
            "expected_manager_user_id": str(creator),
        },
    )
    assert transfer.status_code == 200

    managed = deployment.act_as(manager).get("/api/v1/projects/managed")
    outsider_page = deployment.act_as(outsider).get("/api/v1/projects/managed")

    assert managed.status_code == 200
    assert managed.json() == {
        "items": [
            {
                "id": str(project_id),
                "slug": project.slug,
                "display_name": project.display_name,
                "team": project.team.model_dump(mode="json"),
            }
        ],
        "next_cursor": None,
        "has_more": False,
    }
    assert outsider_page.json() == {"items": [], "next_cursor": None, "has_more": False}


def test_project_list_paginates_in_slug_order(deployment: _Deployment) -> None:
    creator = deployment.add_user("Creator", GlobalRole.operator)
    prefix = _slug("page")
    project_ids = [deployment.create_project(creator, f"{prefix}-{index}") for index in range(3)]
    client = deployment.act_as(creator)

    first_page = client.get("/api/v1/projects", params={"limit": 2}).json()
    second_page = client.get(
        "/api/v1/projects", params={"limit": 2, "cursor": first_page["next_cursor"]}
    ).json()
    invalid_cursor = client.get("/api/v1/projects", params={"cursor": "not-a-cursor"})

    assert [item["id"] for item in first_page["items"] + second_page["items"]] == [
        str(project_id) for project_id in project_ids
    ]
    assert (first_page["has_more"], second_page["has_more"]) == (True, False)
    assert invalid_cursor.status_code == 422


def test_project_roles_bound_what_members_may_do(deployment: _Deployment) -> None:
    creator = deployment.add_user("Creator", GlobalRole.operator)
    admin = deployment.add_user("Administrator", GlobalRole.admin)
    viewer = deployment.add_user("Viewer")
    other_operator = deployment.add_user("Other operator", GlobalRole.operator)
    project_id = deployment.create_project(creator, _slug("roles"))
    snapshot_response = deployment.act_as(creator).post(
        f"/api/v1/projects/{project_id}/snapshots",
        files={"source": ("register.xml", b"<TEI/>", "application/tei+xml")},
    )
    assert snapshot_response.status_code == 202
    snapshot_id = snapshot_response.json()["id"]
    deployment.grant(admin, project_id, viewer, "viewer")

    viewer_client = deployment.act_as(viewer)
    project = viewer_client.get(f"/api/v1/projects/{project_id}")
    snapshot = viewer_client.get(f"/api/v1/snapshots/{snapshot_id}")
    viewer_import = viewer_client.post(
        f"/api/v1/projects/{project_id}/snapshots",
        files={"source": ("register.xml", b"<TEI/>", "application/tei+xml")},
    )
    viewer_run = viewer_client.post(
        "/api/v1/runs", json={"dataset_snapshot_id": snapshot_id, "config": {"methods": []}}
    )
    viewer_annotation = viewer_client.post(
        "/api/v1/annotations",
        json={
            "snapshot_id": snapshot_id,
            "tei_id": "p1",
            "action": "defer",
            "expected_revision": 0,
        },
    )
    operator_client = deployment.act_as(other_operator)
    foreign_project = operator_client.get(f"/api/v1/projects/{project_id}")
    foreign_snapshot = operator_client.get(f"/api/v1/snapshots/{snapshot_id}")
    foreign_history = operator_client.get(
        "/api/v1/annotations", params={"snapshot_id": snapshot_id, "tei_id": "p1"}
    )

    assert project.status_code == 200
    assert project.json()["current_user_role"] == "viewer"
    assert snapshot.status_code == 200
    assert [viewer_import.status_code, viewer_run.status_code, viewer_annotation.status_code] == [
        403,
        403,
        403,
    ]
    assert [
        foreign_project.status_code,
        foreign_snapshot.status_code,
        foreign_history.status_code,
    ] == [404, 404, 404]


def test_revoking_the_creators_membership_revokes_access(deployment: _Deployment) -> None:
    creator = deployment.add_user("Creator", GlobalRole.operator)
    admin = deployment.add_user("Administrator", GlobalRole.admin)
    project_id = deployment.create_project(creator, _slug("revoke"))

    revoked = deployment.act_as(admin).delete(f"/api/v1/projects/{project_id}/members/{creator}")
    after = deployment.act_as(creator).get(f"/api/v1/projects/{project_id}")

    assert revoked.status_code == 204
    assert after.status_code == 404


def test_administrators_grant_change_list_and_revoke_memberships(
    deployment: _Deployment,
) -> None:
    creator = deployment.add_user("Creator", GlobalRole.operator)
    admin = deployment.add_user("Administrator", GlobalRole.admin)
    member = deployment.add_user("Member")
    project_id = deployment.create_project(creator, _slug("members"))
    with deployment.unit_of_work_factory() as unit_of_work:
        project = unit_of_work.projects.get_project(project_id)
        assert project is not None
        unit_of_work.teams.add_member(project.team.id, member)
        unit_of_work.commit()
    client = deployment.act_as(admin)
    members_url = f"/api/v1/projects/{project_id}/members"

    granted = client.put(f"{members_url}/{member}", json={"role": "viewer"})
    changed = client.put(f"{members_url}/{member}", json={"role": "operator"})
    listed = client.get(members_url)
    removed = client.delete(f"{members_url}/{member}")
    removed_again = client.delete(f"{members_url}/{member}")
    unknown_user = client.put(f"{members_url}/{uuid4()}", json={"role": "viewer"})
    unknown_project = client.get(f"/api/v1/projects/{uuid4()}/members")
    invalid_role = client.put(f"{members_url}/{member}", json={"role": "admin"})

    assert granted.status_code == 200
    assert granted.json()["role"] == "viewer"
    assert changed.json()["role"] == "operator"
    assert changed.json()["created_at"] == granted.json()["created_at"]
    assert [(item["display_name"], item["role"]) for item in listed.json()["members"]] == [
        ("Creator", "operator"),
        ("Member", "operator"),
    ]
    assert removed.status_code == 204
    assert [removed_again.status_code, unknown_user.status_code] == [404, 404]
    assert unknown_project.status_code == 404
    assert invalid_role.status_code == 422


def test_method_catalog_requires_a_role_or_a_membership(deployment: _Deployment) -> None:
    creator = deployment.add_user("Creator", GlobalRole.operator)
    admin = deployment.add_user("Administrator", GlobalRole.admin)
    member = deployment.add_user("Member")
    unassigned = deployment.add_user("Unassigned")
    project_id = deployment.create_project(creator, _slug("catalog"))
    deployment.grant(admin, project_id, member, "viewer")

    member_response = deployment.act_as(member).get("/api/v1/methods")
    unassigned_response = deployment.act_as(unassigned).get("/api/v1/methods")

    assert member_response.status_code == 200
    assert unassigned_response.status_code == 403
