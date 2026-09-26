"""Public list routes validate picker filters and pass canonical models to services."""

from collections.abc import Callable
from unittest.mock import Mock
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel, SecretStr

from gendertagger.api.app import create_app
from gendertagger.api.authentication import require_authenticated_user
from gendertagger.api.authorization import get_project_access_guard
from gendertagger.api.dependencies import (
    get_aggregation_service,
    get_project_service,
    get_run_service,
)
from gendertagger.api.settings import AppSettings
from gendertagger.models.aggregation import AggregationExecutionListFilter
from gendertagger.models.api import CursorPage
from gendertagger.models.lifecycle import AggregationExecutionStatus, DatasetSnapshotStatus
from gendertagger.models.project import DatasetSnapshotListFilter
from gendertagger.models.run import RunListFilter
from gendertagger.models.user import CurrentUser
from gendertagger.services.ports.unit_of_work import UnitOfWork

pytestmark = pytest.mark.unit

PARENT_ID = UUID("10000000-0000-0000-0000-000000000001")


def _unused_unit_of_work_factory() -> UnitOfWork:
    raise AssertionError("route contract tests must not access persistence")


@pytest.mark.parametrize(
    ("collection", "dependency", "method", "params", "expected"),
    [
        (
            "projects/{parent}/snapshots",
            get_project_service,
            "list_snapshots",
            {"status": "ready", "has_completed_aggregations": "true"},
            DatasetSnapshotListFilter(
                status=DatasetSnapshotStatus.ready, has_completed_aggregations=True
            ),
        ),
        (
            "snapshots/{parent}/runs",
            get_run_service,
            "list_runs",
            {"has_completed_aggregations": "false"},
            RunListFilter(has_completed_aggregations=False),
        ),
        (
            "runs/{parent}/aggregations",
            get_aggregation_service,
            "list_aggregations",
            {"status": "completed"},
            AggregationExecutionListFilter(status=AggregationExecutionStatus.completed),
        ),
    ],
)
def test_collection_routes_validate_filters(
    collection: str,
    dependency: Callable[..., object],
    method: str,
    params: dict[str, str],
    expected: BaseModel,
) -> None:
    service = Mock()
    list_method = getattr(service, method)
    list_method.return_value = CursorPage(items=[], has_more=False)
    access = Mock()
    application = create_app(
        settings=AppSettings(
            database_url=SecretStr("postgresql+psycopg://unused:unused@localhost/unused"),
            code_git_commit="a" * 40,
            dependency_lock_sha256="b" * 64,
        ),
        unit_of_work_factory=_unused_unit_of_work_factory,
    )
    application.dependency_overrides[dependency] = lambda: service
    application.dependency_overrides[get_project_access_guard] = lambda: access
    application.dependency_overrides[require_authenticated_user] = lambda: CurrentUser(
        id=PARENT_ID, display_name="Reader", roles=set()
    )
    path = f"/api/v1/{collection.format(parent=PARENT_ID)}"
    with TestClient(application) as client:
        response = client.get(path, params=params)
        assert response.status_code == 200
        list_method.assert_called_once_with(PARENT_ID, limit=100, cursor=None, filters=expected)
        invalid = client.get(path, params=dict.fromkeys(params, "not-a-valid-filter"))
        assert invalid.status_code == 422
        assert list_method.call_count == 1
        assert access.require.call_count == 1


def test_project_review_results_route_calls_project_service() -> None:
    service = Mock()
    service.list_review_results.return_value = CursorPage(items=[], has_more=False)
    access = Mock()
    application = create_app(
        settings=AppSettings(
            database_url=SecretStr("postgresql+psycopg://unused:unused@localhost/unused"),
            code_git_commit="a" * 40,
            dependency_lock_sha256="b" * 64,
        ),
        unit_of_work_factory=_unused_unit_of_work_factory,
    )
    application.dependency_overrides[get_project_service] = lambda: service
    application.dependency_overrides[get_project_access_guard] = lambda: access
    application.dependency_overrides[require_authenticated_user] = lambda: CurrentUser(
        id=PARENT_ID, display_name="Reader", roles=set()
    )

    with TestClient(application) as client:
        response = client.get(
            f"/api/v1/projects/{PARENT_ID}/review-results",
            params={"limit": "25", "cursor": "next"},
        )

    assert response.status_code == 200
    service.list_review_results.assert_called_once_with(PARENT_ID, limit=25, cursor="next")
    access.require.assert_called_once()
