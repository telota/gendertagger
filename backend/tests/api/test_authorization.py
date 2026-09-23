from dataclasses import dataclass, field
from typing import Any, cast
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from gendertagger.api.app import create_app
from gendertagger.api.authentication import require_authenticated_user, require_csrf_protection
from gendertagger.api.authorization import (
    ProjectAccessGuard,
    has_global_role,
    require_admin,
    require_any_grant,
    require_project_creator,
)
from gendertagger.api.dependencies import get_project_access_service
from gendertagger.api.errors import ApiRequestError
from gendertagger.api.settings import AppSettings
from gendertagger.models.user import CurrentUser, GlobalRole, ProjectRole
from gendertagger.services.ports.project_access_repository import ProjectScope
from gendertagger.services.ports.unit_of_work import UnitOfWork
from gendertagger.services.project_access import ProjectAccessService

pytestmark = pytest.mark.unit

DATABASE_URL = "postgresql+psycopg://api:secret@localhost/gendertagger"
RESOURCE_ID = UUID("10000000-0000-0000-0000-000000000001")
OTHER_ID = UUID("20000000-0000-0000-0000-000000000001")


def _user(*roles: GlobalRole) -> CurrentUser:
    return CurrentUser(
        id=UUID("a2f03480-77a7-4f24-82cb-07604d5c2483"),
        display_name="Role fixture",
        roles=set(roles),
    )


@dataclass
class _FixedProjectAccess:
    role: ProjectRole | None = None
    any_grant: bool = False
    calls: list[tuple[ProjectScope, UUID]] = field(default_factory=list)

    def effective_role(
        self, user: CurrentUser, scope: ProjectScope, resource_id: UUID
    ) -> ProjectRole | None:
        self.calls.append((scope, resource_id))
        return self.role

    def has_any_grant(self, user: CurrentUser) -> bool:
        return self.any_grant


def _guard(access: _FixedProjectAccess) -> ProjectAccessGuard:
    return ProjectAccessGuard(user=_user(), service=cast(ProjectAccessService, access))


@pytest.mark.parametrize(
    ("assigned_role", "required_role", "is_authorized"),
    [
        (ProjectRole.viewer, ProjectRole.viewer, True),
        (ProjectRole.viewer, ProjectRole.reviewer, False),
        (ProjectRole.reviewer, ProjectRole.viewer, True),
        (ProjectRole.reviewer, ProjectRole.operator, False),
        (ProjectRole.operator, ProjectRole.viewer, True),
        (ProjectRole.operator, ProjectRole.reviewer, True),
        (ProjectRole.operator, ProjectRole.operator, True),
    ],
)
def test_project_roles_grant_hierarchical_capabilities(
    assigned_role: ProjectRole,
    required_role: ProjectRole,
    is_authorized: bool,
) -> None:
    assert assigned_role.grants(required_role) is is_authorized


@pytest.mark.parametrize(
    ("assigned_roles", "required_role", "is_authorized"),
    [
        ((), GlobalRole.operator, False),
        ((GlobalRole.operator,), GlobalRole.operator, True),
        ((GlobalRole.operator,), GlobalRole.admin, False),
        ((GlobalRole.admin,), GlobalRole.operator, True),
        ((GlobalRole.admin,), GlobalRole.admin, True),
    ],
)
def test_global_roles_grant_hierarchical_capabilities(
    assigned_roles: tuple[GlobalRole, ...],
    required_role: GlobalRole,
    is_authorized: bool,
) -> None:
    assert has_global_role(_user(*assigned_roles), required_role) is is_authorized


def test_guard_hides_resources_outside_the_callers_projects() -> None:
    access = _FixedProjectAccess(role=None)

    with pytest.raises(ApiRequestError) as caught:
        _guard(access).require(ProjectScope.run, RESOURCE_ID, ProjectRole.viewer)

    assert caught.value.status_code == 404
    assert caught.value.code == "resource_not_found"
    assert access.calls == [(ProjectScope.run, RESOURCE_ID)]


def test_guard_forbids_a_member_below_the_least_role() -> None:
    with pytest.raises(ApiRequestError) as caught:
        _guard(_FixedProjectAccess(role=ProjectRole.reviewer)).require(
            ProjectScope.snapshot, RESOURCE_ID, ProjectRole.operator
        )

    assert caught.value.status_code == 403
    assert caught.value.code == "forbidden"


def test_guard_returns_the_callers_effective_role() -> None:
    role = _guard(_FixedProjectAccess(role=ProjectRole.operator)).require(
        ProjectScope.project, RESOURCE_ID, ProjectRole.reviewer
    )

    assert role is ProjectRole.operator


def test_global_dependencies_require_their_role() -> None:
    assert require_project_creator(_user(GlobalRole.operator)).roles == {GlobalRole.operator}
    assert require_admin(_user(GlobalRole.admin)).roles == {GlobalRole.admin}
    with pytest.raises(ApiRequestError) as creator_error:
        require_project_creator(_user())
    with pytest.raises(ApiRequestError) as admin_error:
        require_admin(_user(GlobalRole.operator))

    assert creator_error.value.status_code == 403
    assert admin_error.value.status_code == 403


def test_any_grant_rejects_a_user_without_roles_or_memberships() -> None:
    no_grant = cast(ProjectAccessService, _FixedProjectAccess(any_grant=False))
    member = cast(ProjectAccessService, _FixedProjectAccess(any_grant=True))

    with pytest.raises(ApiRequestError) as caught:
        require_any_grant(_user(), no_grant)

    assert caught.value.status_code == 403
    assert require_any_grant(_user(), member) == _user()


@dataclass(frozen=True)
class _ScopedRoute:
    method: str
    path: str
    scope: ProjectScope
    least_role: ProjectRole
    request: dict[str, Any] = field(default_factory=dict)

    @property
    def url(self) -> str:
        return f"/api/v1{self.path}".format(**PATH_VALUES)


_ID = str(RESOURCE_ID)
_OTHER = str(OTHER_ID)
PATH_VALUES = {
    "project_id": _ID,
    "snapshot_id": _ID,
    "run_id": _ID,
    "aggregation_id": _ID,
    "result_id": _OTHER,
    "evaluation_id": _ID,
    "export_execution_id": _ID,
}
PROJECT_SCOPED_ROUTES = (
    _ScopedRoute("GET", "/projects/{project_id}", ProjectScope.project, ProjectRole.viewer),
    _ScopedRoute(
        "PUT",
        "/projects/{project_id}/working-aggregation",
        ProjectScope.project,
        ProjectRole.operator,
        {"json": {"aggregation_execution_id": _OTHER}},
    ),
    _ScopedRoute(
        "POST",
        "/projects/{project_id}/snapshots",
        ProjectScope.project,
        ProjectRole.operator,
        {"files": {"source": ("register.xml", b"<TEI/>", "application/tei+xml")}},
    ),
    _ScopedRoute(
        "GET", "/projects/{project_id}/snapshots", ProjectScope.project, ProjectRole.viewer
    ),
    _ScopedRoute("GET", "/snapshots/{snapshot_id}", ProjectScope.snapshot, ProjectRole.viewer),
    _ScopedRoute(
        "GET",
        "/snapshots/{snapshot_id}/source-members",
        ProjectScope.snapshot,
        ProjectRole.viewer,
    ),
    _ScopedRoute("GET", "/snapshots/{snapshot_id}/runs", ProjectScope.snapshot, ProjectRole.viewer),
    _ScopedRoute(
        "GET", "/snapshots/{snapshot_id}/people", ProjectScope.snapshot, ProjectRole.viewer
    ),
    _ScopedRoute(
        "POST",
        "/runs",
        ProjectScope.snapshot,
        ProjectRole.operator,
        {"json": {"dataset_snapshot_id": _ID, "config": {"methods": []}}},
    ),
    _ScopedRoute("GET", "/runs/{run_id}", ProjectScope.run, ProjectRole.viewer),
    _ScopedRoute("GET", "/runs/{run_id}/executions", ProjectScope.run, ProjectRole.viewer),
    _ScopedRoute("POST", "/runs/{run_id}/executions", ProjectScope.run, ProjectRole.operator),
    _ScopedRoute("GET", "/runs/{run_id}/events", ProjectScope.run, ProjectRole.viewer),
    _ScopedRoute(
        "POST",
        "/runs/{run_id}/aggregations",
        ProjectScope.run,
        ProjectRole.operator,
        {"json": {"method_execution_ids": [_OTHER]}},
    ),
    _ScopedRoute("GET", "/runs/{run_id}/aggregations", ProjectScope.run, ProjectRole.viewer),
    _ScopedRoute("GET", "/runs/{run_id}/evaluations", ProjectScope.run, ProjectRole.viewer),
    _ScopedRoute("GET", "/runs/{run_id}/exports", ProjectScope.run, ProjectRole.viewer),
    _ScopedRoute(
        "GET", "/aggregations/{aggregation_id}", ProjectScope.aggregation, ProjectRole.viewer
    ),
    _ScopedRoute(
        "GET",
        "/aggregations/{aggregation_id}/results",
        ProjectScope.aggregation,
        ProjectRole.viewer,
    ),
    _ScopedRoute(
        "GET",
        "/aggregations/{aggregation_id}/results/{result_id}",
        ProjectScope.aggregation,
        ProjectRole.viewer,
    ),
    _ScopedRoute(
        "GET",
        "/aggregations/{aggregation_id}/results/{result_id}/predictions",
        ProjectScope.aggregation,
        ProjectRole.viewer,
    ),
    _ScopedRoute(
        "GET",
        "/aggregations/{aggregation_id}/review-summary",
        ProjectScope.aggregation,
        ProjectRole.viewer,
    ),
    _ScopedRoute(
        "GET",
        "/annotations",
        ProjectScope.snapshot,
        ProjectRole.viewer,
        {"params": {"snapshot_id": _ID, "tei_id": "p1"}},
    ),
    _ScopedRoute(
        "GET",
        "/review-items",
        ProjectScope.aggregation,
        ProjectRole.viewer,
        {"params": {"aggregation_id": _ID}},
    ),
    _ScopedRoute(
        "POST",
        "/annotations",
        ProjectScope.snapshot,
        ProjectRole.reviewer,
        {
            "json": {
                "snapshot_id": _ID,
                "tei_id": "p1",
                "action": "defer",
                "expected_revision": 0,
            }
        },
    ),
    _ScopedRoute(
        "POST",
        "/evaluations",
        ProjectScope.run,
        ProjectRole.operator,
        {"json": {"run_id": _ID, "method_execution_ids": [_OTHER]}},
    ),
    _ScopedRoute(
        "GET", "/evaluations/{evaluation_id}", ProjectScope.evaluation, ProjectRole.viewer
    ),
    _ScopedRoute(
        "GET", "/evaluations/{evaluation_id}/report", ProjectScope.evaluation, ProjectRole.viewer
    ),
    _ScopedRoute(
        "POST",
        "/exports",
        ProjectScope.run,
        ProjectRole.operator,
        {"json": {"run_id": _ID, "aggregation_execution_id": _OTHER, "format": "json"}},
    ),
    _ScopedRoute("GET", "/exports/{export_execution_id}", ProjectScope.export, ProjectRole.viewer),
    _ScopedRoute(
        "GET", "/exports/{export_execution_id}/download", ProjectScope.export, ProjectRole.viewer
    ),
)
GLOBAL_ROUTES = {
    ("POST", "/projects"),
    ("GET", "/projects"),
    ("GET", "/projects/{project_id}/members"),
    ("PUT", "/projects/{project_id}/members/{user_id}"),
    ("DELETE", "/projects/{project_id}/members/{user_id}"),
    ("GET", "/methods"),
    ("GET", "/snapshot-upload-limits"),
    ("POST", "/classify"),
    ("GET", "/me"),
    ("POST", "/me/password"),
    ("GET", "/auth/session"),
    ("POST", "/auth/login"),
    ("POST", "/auth/logout"),
    ("GET", "/branding"),
    ("GET", "/branding/logo"),
}


def _unused_unit_of_work_factory() -> UnitOfWork:
    raise AssertionError("an unauthorized request must not reach persistence")


def _client(access: _FixedProjectAccess, user: CurrentUser | None = None) -> TestClient:
    application = create_app(
        settings=AppSettings(
            database_url=SecretStr(DATABASE_URL),
            code_git_commit="a" * 40,
            dependency_lock_sha256="b" * 64,
        ),
        unit_of_work_factory=_unused_unit_of_work_factory,
    )
    application.dependency_overrides[require_authenticated_user] = lambda: user or _user()
    application.dependency_overrides[require_csrf_protection] = lambda: None
    application.dependency_overrides[get_project_access_service] = lambda: access
    return TestClient(application)


def _request(client: TestClient, route: _ScopedRoute) -> Any:
    return client.request(route.method, route.url, **route.request)


def test_every_versioned_route_has_a_declared_access_rule() -> None:
    schema = _client(_FixedProjectAccess()).app.openapi()  # type: ignore[attr-defined]  # FastAPI.
    declared = GLOBAL_ROUTES | {(route.method, route.path) for route in PROJECT_SCOPED_ROUTES}
    published = {
        (method.upper(), path.removeprefix("/api/v1"))
        for path, operations in schema["paths"].items()
        if path.startswith("/api/v1/")
        for method in operations
    }

    assert published == declared


@pytest.mark.parametrize("route", PROJECT_SCOPED_ROUTES, ids=lambda route: route.path)
def test_project_scoped_route_hides_resources_outside_the_callers_projects(
    route: _ScopedRoute,
) -> None:
    access = _FixedProjectAccess(role=None)

    response = _request(_client(access), route)

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "resource_not_found"
    assert access.calls == [(route.scope, RESOURCE_ID)]


@pytest.mark.parametrize(
    "route",
    [route for route in PROJECT_SCOPED_ROUTES if route.least_role is not ProjectRole.viewer],
    ids=lambda route: f"{route.method} {route.path}",
)
def test_project_scoped_route_forbids_the_role_below_its_least_role(
    route: _ScopedRoute,
) -> None:
    ranking = tuple(ProjectRole)
    below = ranking[ranking.index(route.least_role) - 1]

    response = _request(_client(_FixedProjectAccess(role=below)), route)

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"


def test_member_administration_requires_a_global_admin() -> None:
    client = _client(_FixedProjectAccess(role=ProjectRole.operator), _user(GlobalRole.operator))

    responses = [
        client.get(f"/api/v1/projects/{_ID}/members"),
        client.put(f"/api/v1/projects/{_ID}/members/{_OTHER}", json={"role": "viewer"}),
        client.delete(f"/api/v1/projects/{_ID}/members/{_OTHER}"),
    ]

    assert [response.status_code for response in responses] == [403, 403, 403]


def test_project_creation_requires_a_global_operator() -> None:
    client = _client(_FixedProjectAccess(role=ProjectRole.operator))

    response = client.post("/api/v1/projects", json={"slug": "denied", "display_name": "Denied"})

    assert response.status_code == 403


def test_method_catalog_requires_some_grant() -> None:
    client = _client(_FixedProjectAccess(any_grant=False))

    response = client.get("/api/v1/methods")

    assert response.status_code == 403


def test_snapshot_upload_limits_require_some_grant() -> None:
    client = _client(_FixedProjectAccess(any_grant=False))

    response = client.get("/api/v1/snapshot-upload-limits")

    assert response.status_code == 403
