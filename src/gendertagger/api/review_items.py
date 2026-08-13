"""Filtered review-candidate HTTP collection."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from gendertagger.api.authorization import require_viewer
from gendertagger.api.dependencies import get_review_item_service
from gendertagger.api.errors import ApiRequestError
from gendertagger.models.api import CursorPage
from gendertagger.models.review import ReviewItem, ReviewItemQuery
from gendertagger.models.user import User
from gendertagger.services.pagination import InvalidCursorError
from gendertagger.services.persistence_errors import (
    InvalidResourceStateError,
    ResourceNotFoundError,
)
from gendertagger.services.review_items import ReviewItemService

router = APIRouter(tags=["review"])


@router.get("/review-items", response_model=CursorPage[ReviewItem])
def list_review_items(
    query: Annotated[ReviewItemQuery, Query()],
    service: Annotated[ReviewItemService, Depends(get_review_item_service)],
    _: Annotated[User, Depends(require_viewer)],
) -> CursorPage[ReviewItem]:
    """List one aggregation's candidates using explicit server-side filters."""
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
        raise ApiRequestError(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            code="validation_error",
            message="The cursor is invalid.",
            details={"reason": "invalid_cursor"},
        ) from error
