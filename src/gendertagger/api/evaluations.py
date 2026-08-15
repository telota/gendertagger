"""Evaluation execution and report HTTP resources."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Response, status

from gendertagger.api.authorization import require_operator, require_viewer
from gendertagger.api.dependencies import get_evaluation_service
from gendertagger.api.errors import ApiRequestError
from gendertagger.models.evaluation import EvaluationCreateRequest, EvaluationExecution
from gendertagger.models.user import CurrentUser
from gendertagger.services.evaluations import EvaluationService
from gendertagger.services.persistence_errors import (
    InvalidResourceStateError,
    ResourceNotFoundError,
)

router = APIRouter(tags=["evaluations"])


@router.post(
    "/evaluations",
    response_model=EvaluationExecution,
    status_code=status.HTTP_202_ACCEPTED,
)
def create_evaluation(
    command: EvaluationCreateRequest,
    service: Annotated[EvaluationService, Depends(get_evaluation_service)],
    _: Annotated[CurrentUser, Depends(require_operator)],
) -> EvaluationExecution:
    """Queue a durable evaluation over exact completed method executions."""
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
    _: Annotated[CurrentUser, Depends(require_viewer)],
) -> EvaluationExecution:
    """Read one current evaluation lifecycle resource."""
    try:
        return service.get_evaluation(evaluation_id)
    except ResourceNotFoundError as error:
        raise _not_found() from error


@router.get("/evaluations/{evaluation_id}/report")
def get_evaluation_report(
    evaluation_id: UUID,
    service: Annotated[EvaluationService, Depends(get_evaluation_service)],
    _: Annotated[CurrentUser, Depends(require_viewer)],
) -> Response:
    """Return a completed evaluation's report bytes by artifact reference."""
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
