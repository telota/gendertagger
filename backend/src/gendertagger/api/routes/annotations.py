"""Append-only human annotation HTTP resources."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from gendertagger.api.authorization import ProjectAccessGuard, get_project_access_guard
from gendertagger.api.dependencies import get_annotation_service, get_review_item_service
from gendertagger.api.errors import ApiRequestError, invalid_cursor_error
from gendertagger.models.api import CursorPage
from gendertagger.models.review import (
    Annotation,
    AnnotationCreate,
    AnnotationHistory,
    SnapshotAnnotationItem,
    SnapshotAnnotationItemQuery,
)
from gendertagger.models.user import ProjectRole
from gendertagger.services.annotations import AnnotationService
from gendertagger.services.pagination import InvalidCursorError
from gendertagger.services.ports.persistence_errors import (
    InvalidResourceStateError,
    ResourceNotFoundError,
    ReviewConflictError,
)
from gendertagger.services.ports.project_access_repository import ProjectScope
from gendertagger.services.review_items import ReviewItemService

router = APIRouter(tags=["annotations"])


@router.get(
    "/snapshots/{snapshot_id}/annotation-items",
    response_model=CursorPage[SnapshotAnnotationItem],
)
def list_snapshot_annotation_items(
    snapshot_id: UUID,
    query: Annotated[SnapshotAnnotationItemQuery, Query()],
    service: Annotated[ReviewItemService, Depends(get_review_item_service)],
    access: Annotated[ProjectAccessGuard, Depends(get_project_access_guard)],
) -> CursorPage[SnapshotAnnotationItem]:
    """List imported people and human decisions without requiring machine classification."""
    access.require(ProjectScope.snapshot, snapshot_id, ProjectRole.viewer)
    try:
        return service.list_annotation_items(snapshot_id, query)
    except ResourceNotFoundError as error:
        raise _annotation_item_not_found() from error
    except InvalidResourceStateError as error:
        raise _snapshot_not_ready() from error
    except InvalidCursorError as error:
        raise invalid_cursor_error() from error


@router.get(
    "/snapshots/{snapshot_id}/annotation-items/{tei_id}",
    response_model=SnapshotAnnotationItem,
)
def get_snapshot_annotation_item(
    snapshot_id: UUID,
    tei_id: str,
    service: Annotated[ReviewItemService, Depends(get_review_item_service)],
    access: Annotated[ProjectAccessGuard, Depends(get_project_access_guard)],
) -> SnapshotAnnotationItem:
    """Read one imported person's current human decision in a ready snapshot."""
    access.require(ProjectScope.snapshot, snapshot_id, ProjectRole.viewer)
    try:
        return service.get_annotation_item(snapshot_id, tei_id)
    except ResourceNotFoundError as error:
        raise _annotation_item_not_found() from error
    except InvalidResourceStateError as error:
        raise _snapshot_not_ready() from error


def _annotation_item_not_found() -> ApiRequestError:
    return ApiRequestError(
        status_code=status.HTTP_404_NOT_FOUND,
        code="resource_not_found",
        message="The requested snapshot or person does not exist.",
    )


def _snapshot_not_ready() -> ApiRequestError:
    return ApiRequestError(
        status_code=status.HTTP_409_CONFLICT,
        code="resource_conflict",
        message="The snapshot is not ready for annotation.",
    )


@router.post(
    "/annotations",
    response_model=Annotation,
    status_code=status.HTTP_201_CREATED,
)
def create_annotation(
    command: AnnotationCreate,
    service: Annotated[AnnotationService, Depends(get_annotation_service)],
    access: Annotated[ProjectAccessGuard, Depends(get_project_access_guard)],
) -> Annotation:
    """Append an attributable decision when the observed revision is current."""
    access.require(ProjectScope.snapshot, command.snapshot_id, ProjectRole.reviewer)
    try:
        return service.create_annotation(command, reviewer_user_id=access.user.id)
    except ReviewConflictError as error:
        raise ApiRequestError(
            status_code=status.HTTP_409_CONFLICT,
            code="annotation_conflict",
            message="The review state has changed.",
            details={"current_revision": error.current_revision},
        ) from error
    except ResourceNotFoundError as error:
        raise ApiRequestError(
            status_code=status.HTTP_404_NOT_FOUND,
            code="resource_not_found",
            message="The requested resource does not exist.",
        ) from error
    except InvalidResourceStateError as error:
        raise ApiRequestError(
            status_code=status.HTTP_409_CONFLICT,
            code="resource_conflict",
            message="The annotation references an incompatible resource.",
        ) from error


@router.get("/annotations", response_model=AnnotationHistory)
def get_annotation_history(
    snapshot_id: Annotated[UUID, Query()],
    tei_id: Annotated[str, Query(min_length=1)],
    service: Annotated[AnnotationService, Depends(get_annotation_service)],
    access: Annotated[ProjectAccessGuard, Depends(get_project_access_guard)],
) -> AnnotationHistory:
    """Read one person's review state and complete attributed annotation chain.

    The chain is newest first, so its first entry is the current decision, and ``revision``
    is the ``expected_revision`` for the next append.
    """
    access.require(ProjectScope.snapshot, snapshot_id, ProjectRole.viewer)
    try:
        return service.get_history(snapshot_id=snapshot_id, tei_id=tei_id)
    except ResourceNotFoundError as error:
        raise ApiRequestError(
            status_code=status.HTTP_404_NOT_FOUND,
            code="resource_not_found",
            message="The requested resource does not exist.",
        ) from error
