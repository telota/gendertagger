"""Filtered review-candidate HTTP collection."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from gendertagger.api.authorization import ProjectAccessGuard, get_project_access_guard
from gendertagger.api.dependencies import get_review_item_service
from gendertagger.api.errors import ApiRequestError, invalid_cursor_error
from gendertagger.models.api import CursorPage
from gendertagger.models.review import ReviewItem, ReviewItemQuery
from gendertagger.models.user import ProjectRole
from gendertagger.services.pagination import InvalidCursorError
from gendertagger.services.persistence_errors import (
    InvalidResourceStateError,
    ResourceNotFoundError,
)
from gendertagger.services.project_access_repository import ProjectScope
from gendertagger.services.review_items import ReviewItemService

router = APIRouter(tags=["review"])


@router.get("/review-items", response_model=CursorPage[ReviewItem])
def list_review_items(
    query: Annotated[ReviewItemQuery, Query()],
    service: Annotated[ReviewItemService, Depends(get_review_item_service)],
    access: Annotated[ProjectAccessGuard, Depends(get_project_access_guard)],
) -> CursorPage[ReviewItem]:
    """List one aggregation's candidates using explicit server-side filters."""
    access.require(ProjectScope.aggregation, query.aggregation_id, ProjectRole.viewer)
    try:
        return service.list_review_items(query)
    except ResourceNotFoundError as error:
        raise ApiRequestError(
            status_code=status.HTTP_404_NOT_FOUND,
            code="resource_not_found",
            message="The requested aggregation does not exist.",
        ) from error
    except InvalidResourceStateError as error:
        raise ApiRequestError(
            status_code=status.HTTP_409_CONFLICT,
            code="resource_conflict",
            message="The aggregation is not ready for review.",
        ) from error
    except InvalidCursorError as error:
        raise invalid_cursor_error() from error
