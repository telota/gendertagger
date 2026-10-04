"""Evaluation execution and report HTTP resources."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status

from gendertagger.api.authorization import ProjectAccessGuard, get_project_access_guard
from gendertagger.api.dependencies import get_evaluation_service
from gendertagger.api.errors import ApiRequestError, invalid_cursor_error
from gendertagger.models.api import CursorPage
from gendertagger.models.evaluation import (
    EvaluationCreateRequest,
    EvaluationExecution,
    EvaluationReport,
)
from gendertagger.models.user import ProjectRole
from gendertagger.services.evaluations import EvaluationService
from gendertagger.services.pagination import InvalidCursorError
from gendertagger.services.ports.persistence_errors import (
    InvalidResourceStateError,
    ResourceNotFoundError,
)
from gendertagger.services.ports.project_access_repository import ProjectScope

router = APIRouter(tags=["evaluations"])


@router.post(
    "/evaluations",
    response_model=EvaluationExecution,
    status_code=status.HTTP_202_ACCEPTED,
)
def create_evaluation(
    command: EvaluationCreateRequest,
    service: Annotated[EvaluationService, Depends(get_evaluation_service)],
    access: Annotated[ProjectAccessGuard, Depends(get_project_access_guard)],
) -> EvaluationExecution:
    """Queue a durable evaluation over exact completed method executions."""
    access.require(ProjectScope.run, command.run_id, ProjectRole.operator)
    try:
        return service.create_evaluation(command)
    except ResourceNotFoundError as error:
        raise _not_found() from error
    except InvalidResourceStateError as error:
        raise ApiRequestError(
            status_code=status.HTTP_409_CONFLICT,
            code="resource_conflict",
            message="The method execution selection is not evaluatable.",
        ) from error


@router.get("/runs/{run_id}/evaluations", response_model=CursorPage[EvaluationExecution])
def list_evaluations(
    run_id: UUID,
    service: Annotated[EvaluationService, Depends(get_evaluation_service)],
    access: Annotated[ProjectAccessGuard, Depends(get_project_access_guard)],
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    cursor: Annotated[str | None, Query(max_length=2048)] = None,
) -> CursorPage[EvaluationExecution]:
    """List a run's evaluations newest first, in every lifecycle state."""
    access.require(ProjectScope.run, run_id, ProjectRole.viewer)
    try:
        return service.list_evaluations(run_id, limit=limit, cursor=cursor)
    except ResourceNotFoundError as error:
        raise _not_found() from error
    except InvalidCursorError as error:
        raise invalid_cursor_error() from error


@router.get("/evaluations/{evaluation_id}", response_model=EvaluationExecution)
def get_evaluation(
    evaluation_id: UUID,
    service: Annotated[EvaluationService, Depends(get_evaluation_service)],
    access: Annotated[ProjectAccessGuard, Depends(get_project_access_guard)],
) -> EvaluationExecution:
    """Read one current evaluation lifecycle resource."""
    access.require(ProjectScope.evaluation, evaluation_id, ProjectRole.viewer)
    try:
        return service.get_evaluation(evaluation_id)
    except ResourceNotFoundError as error:
        raise _not_found() from error


@router.get("/evaluations/{evaluation_id}/report", response_model=EvaluationReport)
def get_evaluation_report(
    evaluation_id: UUID,
    service: Annotated[EvaluationService, Depends(get_evaluation_service)],
    access: Annotated[ProjectAccessGuard, Depends(get_project_access_guard)],
) -> Response:
    """Return a completed evaluation's report bytes by artifact reference."""
    access.require(ProjectScope.evaluation, evaluation_id, ProjectRole.viewer)
    try:
        content, media_type = service.get_report(evaluation_id)
    except ResourceNotFoundError as error:
        raise _not_found() from error
    return Response(content=content, media_type=media_type)


def _not_found() -> ApiRequestError:
    return ApiRequestError(
        status_code=status.HTTP_404_NOT_FOUND,
        code="resource_not_found",
        message="The requested resource does not exist.",
    )
