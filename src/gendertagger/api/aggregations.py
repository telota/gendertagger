"""Aggregation execution and immutable result HTTP resources."""

from collections.abc import Sequence
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status

from gendertagger.api.authorization import ProjectAccessGuard, get_project_access_guard
from gendertagger.api.dependencies import get_aggregation_service
from gendertagger.api.errors import ApiRequestError, invalid_cursor_error
from gendertagger.models.aggregation import (
    AggregatedResult,
    AggregationCreateRequest,
    AggregationExecution,
    ResultMethodPrediction,
)
from gendertagger.models.api import CursorPage
from gendertagger.models.user import ProjectRole
from gendertagger.services.aggregations import AggregationService
from gendertagger.services.pagination import InvalidCursorError
from gendertagger.services.persistence_errors import (
    InvalidResourceStateError,
    ResourceNotFoundError,
)
from gendertagger.services.project_access_repository import ProjectScope

router = APIRouter(tags=["aggregations"])


@router.post(
    "/runs/{run_id}/aggregations",
    response_model=AggregationExecution,
    status_code=status.HTTP_202_ACCEPTED,
    responses={
        status.HTTP_200_OK: {
            "model": AggregationExecution,
            "description": (
                "An aggregation with the same strategy, configuration, and ordered selection "
                "is queued, running, or completed, and is returned unchanged."
            ),
        },
    },
)
def create_aggregation(
    run_id: UUID,
    command: AggregationCreateRequest,
    response: Response,
    service: Annotated[AggregationService, Depends(get_aggregation_service)],
    access: Annotated[ProjectAccessGuard, Depends(get_project_access_guard)],
) -> AggregationExecution:
    """Queue a durable aggregation, or return the live or completed one it repeats (ADR-0034)."""
    access.require(ProjectScope.run, run_id, ProjectRole.operator)
    try:
        creation = service.create_aggregation(run_id=run_id, command=command)
    except ResourceNotFoundError as error:
        raise _not_found() from error
    except InvalidResourceStateError as error:
        raise ApiRequestError(
            status_code=status.HTTP_409_CONFLICT,
            code="resource_conflict",
            message="The method execution selection is not aggregatable.",
        ) from error
    if not creation.created:
        response.status_code = status.HTTP_200_OK
    return creation.aggregation


@router.get("/runs/{run_id}/aggregations", response_model=CursorPage[AggregationExecution])
def list_aggregations(
    run_id: UUID,
    service: Annotated[AggregationService, Depends(get_aggregation_service)],
    access: Annotated[ProjectAccessGuard, Depends(get_project_access_guard)],
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    cursor: Annotated[str | None, Query(max_length=2048)] = None,
) -> CursorPage[AggregationExecution]:
    """List a run's aggregations newest first, in every lifecycle state."""
    access.require(ProjectScope.run, run_id, ProjectRole.viewer)
    try:
        return service.list_aggregations(run_id, limit=limit, cursor=cursor)
    except ResourceNotFoundError as error:
        raise _not_found() from error
    except InvalidCursorError as error:
        raise invalid_cursor_error() from error


@router.get("/aggregations/{aggregation_id}", response_model=AggregationExecution)
def get_aggregation(
    aggregation_id: UUID,
    service: Annotated[AggregationService, Depends(get_aggregation_service)],
    access: Annotated[ProjectAccessGuard, Depends(get_project_access_guard)],
) -> AggregationExecution:
    """Read one current aggregation lifecycle resource."""
    access.require(ProjectScope.aggregation, aggregation_id, ProjectRole.viewer)
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
    access: Annotated[ProjectAccessGuard, Depends(get_project_access_guard)],
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    cursor: Annotated[str | None, Query(max_length=2048)] = None,
) -> CursorPage[AggregatedResult]:
    """List immutable aggregation results in stable person-ID order."""
    access.require(ProjectScope.aggregation, aggregation_id, ProjectRole.viewer)
    try:
        return service.list_results(aggregation_id, limit=limit, cursor=cursor)
    except ResourceNotFoundError as error:
        raise _not_found() from error
    except InvalidCursorError as error:
        raise invalid_cursor_error() from error


@router.get(
    "/aggregations/{aggregation_id}/results/{result_id}",
    response_model=AggregatedResult,
)
def get_aggregation_result(
    aggregation_id: UUID,
    result_id: UUID,
    service: Annotated[AggregationService, Depends(get_aggregation_service)],
    access: Annotated[ProjectAccessGuard, Depends(get_project_access_guard)],
) -> AggregatedResult:
    """Read one immutable result under its owning aggregation."""
    access.require(ProjectScope.aggregation, aggregation_id, ProjectRole.viewer)
    try:
        return service.get_result(aggregation_id=aggregation_id, result_id=result_id)
    except ResourceNotFoundError as error:
        raise _not_found() from error


@router.get(
    "/aggregations/{aggregation_id}/results/{result_id}/predictions",
    response_model=list[ResultMethodPrediction],
)
def list_aggregation_result_predictions(
    aggregation_id: UUID,
    result_id: UUID,
    service: Annotated[AggregationService, Depends(get_aggregation_service)],
    access: Annotated[ProjectAccessGuard, Depends(get_project_access_guard)],
) -> Sequence[ResultMethodPrediction]:
    """List every selected method's prediction for the person behind one result.

    Entries follow the aggregation's method selection order. A method with no persisted
    prediction for the person appears with a null ``prediction``.
    """
    access.require(ProjectScope.aggregation, aggregation_id, ProjectRole.viewer)
    try:
        return service.list_result_predictions(aggregation_id=aggregation_id, result_id=result_id)
    except ResourceNotFoundError as error:
        raise _not_found() from error


def _not_found() -> ApiRequestError:
    return ApiRequestError(
        status_code=status.HTTP_404_NOT_FOUND,
        code="resource_not_found",
        message="The requested resource does not exist.",
    )
