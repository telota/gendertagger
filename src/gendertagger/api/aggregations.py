"""Aggregation execution and immutable result HTTP resources."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from gendertagger.api.authorization import require_operator, require_viewer
from gendertagger.api.dependencies import get_aggregation_service
from gendertagger.api.errors import ApiRequestError
from gendertagger.models.aggregation import (
    AggregatedResult,
    AggregationCreateRequest,
    AggregationExecution,
)
from gendertagger.models.api import CursorPage
from gendertagger.models.user import User
from gendertagger.services.aggregations import AggregationService
from gendertagger.services.pagination import InvalidCursorError
from gendertagger.services.persistence_errors import (
    InvalidResourceStateError,
    ResourceNotFoundError,
)

router = APIRouter(tags=["aggregations"])


@router.post(
    "/runs/{run_id}/aggregations",
    response_model=AggregationExecution,
    status_code=status.HTTP_202_ACCEPTED,
)
def create_aggregation(
    run_id: UUID,
    command: AggregationCreateRequest,
    service: Annotated[AggregationService, Depends(get_aggregation_service)],
    _: Annotated[User, Depends(require_operator)],
) -> AggregationExecution:
    """Persist a pending aggregation over exact completed method executions."""
    try:
        return service.create_aggregation(run_id=run_id, command=command)
    except ResourceNotFoundError as error:
        raise _not_found() from error
    except InvalidResourceStateError as error:
        raise ApiRequestError(
            status_code=status.HTTP_409_CONFLICT,
            code="resource_conflict",
            message="The method execution selection is not aggregatable.",
        ) from error


@router.get("/aggregations/{aggregation_id}", response_model=AggregationExecution)
def get_aggregation(
    aggregation_id: UUID,
    service: Annotated[AggregationService, Depends(get_aggregation_service)],
    _: Annotated[User, Depends(require_viewer)],
) -> AggregationExecution:
    """Read one current aggregation lifecycle resource."""
    try:
        return service.get_aggregation(aggregation_id)
    except ResourceNotFoundError as error:
        raise _not_found() from error


@router.get(
    "/aggregations/{aggregation_id}/results",
    response_model=CursorPage[AggregatedResult],
)
def list_aggregation_results(
    aggregation_id: UUID,
    service: Annotated[AggregationService, Depends(get_aggregation_service)],
    _: Annotated[User, Depends(require_viewer)],
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    cursor: Annotated[str | None, Query(max_length=2048)] = None,
) -> CursorPage[AggregatedResult]:
    """List immutable aggregation results in stable person-ID order."""
    try:
        return service.list_results(aggregation_id, limit=limit, cursor=cursor)
    except ResourceNotFoundError as error:
        raise _not_found() from error
    except InvalidCursorError as error:
        raise ApiRequestError(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            code="validation_error",
            message="The cursor is invalid.",
            details={"reason": "invalid_cursor"},
        ) from error


@router.get(
    "/aggregations/{aggregation_id}/results/{result_id}",
    response_model=AggregatedResult,
)
def get_aggregation_result(
    aggregation_id: UUID,
    result_id: UUID,
    service: Annotated[AggregationService, Depends(get_aggregation_service)],
    _: Annotated[User, Depends(require_viewer)],
) -> AggregatedResult:
    """Read one immutable result under its owning aggregation."""
    try:
        return service.get_result(aggregation_id=aggregation_id, result_id=result_id)
    except ResourceNotFoundError as error:
        raise _not_found() from error


def _not_found() -> ApiRequestError:
    return ApiRequestError(
        status_code=status.HTTP_404_NOT_FOUND,
        code="resource_not_found",
        message="The requested resource does not exist.",
    )
