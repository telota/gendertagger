"""Append-only human annotation HTTP resource."""

from typing import Annotated

from fastapi import APIRouter, Depends, status

from gendertagger.api.authorization import ProjectAccessGuard, get_project_access_guard
from gendertagger.api.dependencies import get_annotation_service
from gendertagger.api.errors import ApiRequestError
from gendertagger.models.review import Annotation, AnnotationCreate
from gendertagger.models.user import ProjectRole
from gendertagger.services.annotations import AnnotationService
from gendertagger.services.persistence_errors import (
    InvalidResourceStateError,
    ResourceNotFoundError,
    ReviewConflictError,
)
from gendertagger.services.project_access_repository import ProjectScope

router = APIRouter(tags=["annotations"])


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
