"""Append-only human annotation HTTP resource."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from gendertagger.api.authorization import require_reviewer
from gendertagger.api.dependencies import get_annotation_service
from gendertagger.models.review import Annotation, AnnotationCreate
from gendertagger.models.user import User
from gendertagger.services.annotations import AnnotationService
from gendertagger.services.persistence_errors import (
    InvalidResourceStateError,
    ResourceNotFoundError,
    ReviewConflictError,
)

router = APIRouter(tags=["annotations"])


@router.post(
    "/annotations",
    response_model=Annotation,
    status_code=status.HTTP_201_CREATED,
)
def create_annotation(
    command: AnnotationCreate,
    service: Annotated[AnnotationService, Depends(get_annotation_service)],
    reviewer: Annotated[User, Depends(require_reviewer)],
) -> Annotation:
    """Append an attributable decision when the observed revision is current."""
    try:
        return service.create_annotation(command, reviewer_user_id=reviewer.id)
    except ReviewConflictError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "annotation_conflict",
                "current_revision": error.current_revision,
            },
        ) from error
    except ResourceNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Resource not found",
        ) from error
    except InvalidResourceStateError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Annotation references an incompatible resource",
        ) from error
