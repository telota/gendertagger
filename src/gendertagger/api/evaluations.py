"""Evaluation execution and report HTTP resources."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Response, status

from gendertagger.api.authorization import ProjectAccessGuard, get_project_access_guard
from gendertagger.api.dependencies import get_evaluation_service
from gendertagger.api.errors import ApiRequestError
from gendertagger.models.evaluation import EvaluationCreateRequest, EvaluationExecution
from gendertagger.models.user import ProjectRole
from gendertagger.services.evaluations import EvaluationService
from gendertagger.services.persistence_errors import (
    InvalidResourceStateError,
    ResourceNotFoundError,
)
from gendertagger.services.project_access_repository import ProjectScope

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


@router.get("/evaluations/{evaluation_id}/report")
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
