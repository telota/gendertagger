"""Aggregation execution and immutable result HTTP resources."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from gendertagger.api.authorization import require_operator, require_viewer
from gendertagger.api.dependencies import get_aggregation_service
from gendertagger.models.aggregation import (
    AggregatedResult,
    AggregationCreateRequest,
    AggregationExecution,
)
from gendertagger.models.user import User
from gendertagger.services.aggregations import AggregationService
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
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Method execution selection is not aggregatable",
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


def _not_found() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Resource not found",
    )
