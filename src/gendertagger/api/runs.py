"""Reproducible run HTTP resources."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from fastapi.responses import StreamingResponse

from gendertagger.api.authorization import require_operator, require_viewer
from gendertagger.api.dependencies import get_run_scheduler, get_run_service
from gendertagger.api.errors import ApiRequestError
from gendertagger.api.run_events import stream_run_events
from gendertagger.models.run import MethodExecution, Run, RunCreateRequest
from gendertagger.models.user import CurrentUser
from gendertagger.services.execution import RunScheduler
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


@router.get("/runs/{run_id}/executions", response_model=list[MethodExecution])
def list_run_executions(
    run_id: UUID,
    service: Annotated[RunService, Depends(get_run_service)],
    _: Annotated[CurrentUser, Depends(require_viewer)],
) -> list[MethodExecution]:
    """List a run's method executions with their persisted progress."""
    try:
        return service.list_executions(run_id)
    except ResourceNotFoundError as error:
        raise _not_found() from error


@router.get("/runs/{run_id}/events")
def stream_run_progress(
    run_id: UUID,
    service: Annotated[RunService, Depends(get_run_service)],
    _: Annotated[CurrentUser, Depends(require_viewer)],
) -> StreamingResponse:
    """Stream persisted run progress as Server-Sent Events until the run ends."""
    try:
        service.get_run(run_id)
    except ResourceNotFoundError as error:
        raise _not_found() from error
    return StreamingResponse(
        stream_run_events(service, run_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post(
    "/runs/{run_id}/executions",
    response_model=Run,
    status_code=status.HTTP_202_ACCEPTED,
)
def start_run_executions(
    run_id: UUID,
    scheduler: Annotated[RunScheduler, Depends(get_run_scheduler)],
    service: Annotated[RunService, Depends(get_run_service)],
    _: Annotated[CurrentUser, Depends(require_operator)],
) -> Run:
    """Atomically persist a run's executions, batches, and dispatch intents."""
    try:
        scheduler.schedule_run(run_id)
    except ResourceNotFoundError as error:
        raise _not_found() from error
    except InvalidResourceStateError as error:
        raise ApiRequestError(
            status_code=status.HTTP_409_CONFLICT,
            code="resource_conflict",
            message="The run cannot be scheduled from its current state.",
        ) from error
    return service.get_run(run_id)


def _not_found() -> ApiRequestError:
    return ApiRequestError(
        status_code=status.HTTP_404_NOT_FOUND,
        code="resource_not_found",
        message="The requested resource does not exist.",
    )
