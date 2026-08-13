"""Reproducible run HTTP resources."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from gendertagger.api.authorization import require_operator, require_viewer
from gendertagger.api.dependencies import get_run_service
from gendertagger.models.run import Run, RunCreateRequest
from gendertagger.models.user import User
from gendertagger.services.method_registry import MethodRegistryError
from gendertagger.services.persistence_errors import (
    InvalidResourceStateError,
    ResourceNotFoundError,
)
from gendertagger.services.runs import RunService

router = APIRouter(tags=["runs"])


@router.post("/runs", response_model=Run, status_code=status.HTTP_202_ACCEPTED)
def create_run(
    command: RunCreateRequest,
    service: Annotated[RunService, Depends(get_run_service)],
    _: Annotated[User, Depends(require_operator)],
) -> Run:
    """Persist a validated created run without exposing queue internals."""
    try:
        return service.create_run(command)
    except MethodRegistryError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(error),
        ) from error
    except ResourceNotFoundError as error:
        raise _not_found() from error
    except InvalidResourceStateError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Dataset snapshot is not ready",
        ) from error


@router.get("/runs/{run_id}", response_model=Run)
def get_run(
    run_id: UUID,
    service: Annotated[RunService, Depends(get_run_service)],
    _: Annotated[User, Depends(require_viewer)],
) -> Run:
    """Read current persisted run state."""
    try:
        return service.get_run(run_id)
    except ResourceNotFoundError as error:
        raise _not_found() from error


def _not_found() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Resource not found",
    )
