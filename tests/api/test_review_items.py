from unittest.mock import Mock
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from gendertagger.api.app import create_app
from gendertagger.api.authentication import require_authenticated_user, require_csrf_protection
from gendertagger.api.dependencies import get_project_access_service, get_review_item_service
from gendertagger.api.settings import AppSettings
from gendertagger.models.api import CursorPage
from gendertagger.models.classification import AgreementTier, CertaintyTier
from gendertagger.models.review import ReviewSummary, ReviewSummaryGroup, ReviewWorkflowState
from gendertagger.models.user import CurrentUser, ProjectRole
from gendertagger.services.pagination import InvalidCursorError
from gendertagger.services.persistence_errors import (
    InvalidResourceStateError,
    ResourceNotFoundError,
)
from gendertagger.services.project_access_repository import ProjectScope
from gendertagger.services.review_items import ReviewItemService
from gendertagger.services.unit_of_work import UnitOfWork

pytestmark = pytest.mark.unit

DATABASE_URL = "postgresql+psycopg://api:secret@localhost/gendertagger"
AGGREGATION_ID = UUID("30000000-0000-0000-0000-000000000001")


def _unused_unit_of_work_factory() -> UnitOfWork:
    raise AssertionError("the route test must not open persistence")


class _GrantingProjectAccess:
    """Grant the caller viewer in every project without persistence."""

    def effective_role(
        self, user: CurrentUser, scope: ProjectScope, resource_id: UUID
    ) -> ProjectRole:
        return ProjectRole.viewer

    def has_any_grant(self, user: CurrentUser) -> bool:
        return True


def _viewer() -> CurrentUser:
    return CurrentUser(
        id=UUID("60000000-0000-0000-0000-000000000001"),
        display_name="Review viewer",
        roles=set(),
    )


def _client(service: object) -> TestClient:
    application = create_app(
        settings=AppSettings(
            database_url=SecretStr(DATABASE_URL),
            code_git_commit="a" * 40,
            dependency_lock_sha256="b" * 64,
        ),
        unit_of_work_factory=_unused_unit_of_work_factory,
    )
    application.dependency_overrides[require_authenticated_user] = _viewer
    application.dependency_overrides[get_project_access_service] = _GrantingProjectAccess
    application.dependency_overrides[require_csrf_protection] = lambda: None
    application.dependency_overrides[get_review_item_service] = lambda: service
    return TestClient(application)


def test_review_summary_route_serializes_the_grouped_counts() -> None:
    service = Mock(spec=ReviewItemService)
    summary = ReviewSummary(
        aggregation_execution_id=AGGREGATION_ID,
        result_count=3,
        groups=[
            ReviewSummaryGroup(
                certainty_tier=CertaintyTier.low,
                agreement_tier=AgreementTier.weak_majority,
                workflow_state=ReviewWorkflowState.unreviewed,
                result_count=3,
            )
        ],
    )
    service.summarize_review.return_value = summary

    with _client(service) as client:
        response = client.get(f"/api/v1/aggregations/{AGGREGATION_ID}/review-summary")

    assert response.status_code == 200
    assert response.json() == summary.model_dump(mode="json")
    service.summarize_review.assert_called_once_with(AGGREGATION_ID)


def test_review_routes_map_missing_and_unfinished_aggregations() -> None:
    service = Mock(spec=ReviewItemService)
    review_items = f"/api/v1/review-items?aggregation_id={AGGREGATION_ID}"
    review_summary = f"/api/v1/aggregations/{AGGREGATION_ID}/review-summary"

    with _client(service) as client:
        service.list_review_items.side_effect = ResourceNotFoundError("missing")
        service.summarize_review.side_effect = ResourceNotFoundError("missing")
        missing = [client.get(review_items), client.get(review_summary)]
        service.list_review_items.side_effect = InvalidResourceStateError("running")
        service.summarize_review.side_effect = InvalidResourceStateError("running")
        not_ready = [client.get(review_items), client.get(review_summary)]
        service.list_review_items.side_effect = InvalidCursorError("unreadable")
        invalid_cursor = client.get(review_items)

    assert [response.status_code for response in missing] == [404, 404]
    assert {response.json()["error"]["code"] for response in missing} == {"resource_not_found"}
    assert [response.status_code for response in not_ready] == [409, 409]
    assert {response.json()["error"]["message"] for response in not_ready} == {
        "The aggregation is not ready for review."
    }
    assert invalid_cursor.status_code == 422
    assert invalid_cursor.json()["error"]["details"] == {"reason": "invalid_cursor"}


def test_review_items_route_passes_repeated_filters_in_vocabulary_order() -> None:
    service = Mock(spec=ReviewItemService)
    service.list_review_items.return_value = CursorPage(items=[], next_cursor=None, has_more=False)

    with _client(service) as client:
        response = client.get(
            "/api/v1/review-items",
            params={
                "aggregation_id": str(AGGREGATION_ID),
                "certainty_tiers": ["uncertain", "single"],
                "workflow_states": ["deferred", "unreviewed"],
            },
        )

    assert response.status_code == 200
    query = service.list_review_items.call_args.args[0]
    assert query.certainty_tiers == (CertaintyTier.single, CertaintyTier.uncertain)
    assert query.agreement_tiers == ()
    assert query.workflow_states == (ReviewWorkflowState.unreviewed, ReviewWorkflowState.deferred)
