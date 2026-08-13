"""Reproducible run HTTP resources."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status

from gendertagger.api.authorization import require_operator, require_viewer
from gendertagger.api.dependencies import (
    get_batch_dispatcher,
    get_run_scheduler,
    get_run_service,
)
from gendertagger.api.errors import ApiRequestError
from gendertagger.models.run import Run, RunCreateRequest
from gendertagger.models.user import CurrentUser
from gendertagger.services.execution import BatchDispatcher, RunScheduler
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
    _: Annotated[CurrentUser, Depends(require_operator)],
) -> Run:
    """Persist a validated created run without exposing queue internals."""
    try:
        return service.create_run(command)
    except MethodRegistryError as error:
        raise ApiRequestError(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            code="validation_error",
            message="The run configuration is invalid.",
            details={"reason": str(error)},
        ) from error
    except ResourceNotFoundError as error:
        raise _not_found() from error
    except InvalidResourceStateError as error:
        raise ApiRequestError(
            status_code=status.HTTP_409_CONFLICT,
            code="resource_conflict",
            message="The dataset snapshot is not ready.",
        ) from error


@router.get("/runs/{run_id}", response_model=Run)
def get_run(
    run_id: UUID,
    service: Annotated[RunService, Depends(get_run_service)],
    _: Annotated[CurrentUser, Depends(require_viewer)],
) -> Run:
    """Read current persisted run state."""
    try:
        return service.get_run(run_id)
    except ResourceNotFoundError as error:
        raise _not_found() from error


@router.post(
    "/runs/{run_id}/executions",
    response_model=Run,
    status_code=status.HTTP_202_ACCEPTED,
)
def start_run_executions(
    run_id: UUID,
    scheduler: Annotated[RunScheduler, Depends(get_run_scheduler)],
    dispatcher: Annotated[BatchDispatcher, Depends(get_batch_dispatcher)],
    service: Annotated[RunService, Depends(get_run_service)],
    _: Annotated[CurrentUser, Depends(require_operator)],
) -> Run:
    """Schedule a created run's method executions and enqueue their batches."""
    try:
        scheduled = scheduler.schedule_run(run_id)
    except ResourceNotFoundError as error:
        raise _not_found() from error
    except InvalidResourceStateError as error:
        raise ApiRequestError(
            status_code=status.HTTP_409_CONFLICT,
            code="resource_conflict",
            message="The run cannot be scheduled from its current state.",
        ) from error
    dispatcher.dispatch(scheduled)
    return service.get_run(run_id)


def _not_found() -> ApiRequestError:
    return ApiRequestError(
        status_code=status.HTTP_404_NOT_FOUND,
        code="resource_not_found",
        message="The requested resource does not exist.",
    )
