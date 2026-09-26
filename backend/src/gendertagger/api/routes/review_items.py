"""Filtered review-candidate HTTP collection and its counts."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from gendertagger.api.authorization import ProjectAccessGuard, get_project_access_guard
from gendertagger.api.dependencies import get_review_item_service
from gendertagger.api.errors import ApiRequestError, invalid_cursor_error
from gendertagger.models.api import CursorPage
from gendertagger.models.review import ReviewItem, ReviewItemQuery, ReviewSummary
from gendertagger.models.user import ProjectRole
from gendertagger.services.pagination import InvalidCursorError
from gendertagger.services.ports.persistence_errors import (
    InvalidResourceStateError,
    ResourceNotFoundError,
)
from gendertagger.services.ports.project_access_repository import ProjectScope
from gendertagger.services.review_items import ReviewItemService

router = APIRouter(tags=["review"])


@router.get("/review-items", response_model=CursorPage[ReviewItem])
def list_review_items(
    query: Annotated[ReviewItemQuery, Query()],
    service: Annotated[ReviewItemService, Depends(get_review_item_service)],
    access: Annotated[ProjectAccessGuard, Depends(get_project_access_guard)],
) -> CursorPage[ReviewItem]:
    """List aggregation candidates with server-side filters, including exact TEI identity."""
    access.require(ProjectScope.aggregation, query.aggregation_id, ProjectRole.viewer)
    try:
        return service.list_review_items(query)
    except ResourceNotFoundError as error:
        raise _aggregation_not_found() from error
    except InvalidResourceStateError as error:
        raise _aggregation_not_ready() from error
    except InvalidCursorError as error:
        raise invalid_cursor_error() from error


@router.get("/aggregations/{aggregation_id}/review-summary", response_model=ReviewSummary)
def get_review_summary(
    aggregation_id: UUID,
    service: Annotated[ReviewItemService, Depends(get_review_item_service)],
    access: Annotated[ProjectAccessGuard, Depends(get_project_access_guard)],
) -> ReviewSummary:
    """Count a completed aggregation's results by certainty, agreement, and review state."""
    access.require(ProjectScope.aggregation, aggregation_id, ProjectRole.viewer)
    try:
        return service.summarize_review(aggregation_id)
    except ResourceNotFoundError as error:
        raise _aggregation_not_found() from error
    except InvalidResourceStateError as error:
        raise _aggregation_not_ready() from error


def _aggregation_not_found() -> ApiRequestError:
    return ApiRequestError(
        status_code=status.HTTP_404_NOT_FOUND,
        code="resource_not_found",
        message="The requested aggregation does not exist.",
    )


def _aggregation_not_ready() -> ApiRequestError:
    return ApiRequestError(
        status_code=status.HTTP_409_CONFLICT,
        code="resource_conflict",
        message="The aggregation is not ready for review.",
    )
