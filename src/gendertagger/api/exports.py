"""Export execution and output HTTP resources."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Response, status

from gendertagger.api.authorization import require_operator, require_viewer
from gendertagger.api.dependencies import get_export_service
from gendertagger.api.errors import ApiRequestError
from gendertagger.models.export import ExportCreateRequest, ExportExecution
from gendertagger.models.user import CurrentUser
from gendertagger.services.exports import ExportService
from gendertagger.services.persistence_errors import (
    InvalidResourceStateError,
    ResourceNotFoundError,
)

router = APIRouter(tags=["exports"])


@router.post(
    "/exports",
    response_model=ExportExecution,
    status_code=status.HTTP_202_ACCEPTED,
)
def create_export(
    command: ExportCreateRequest,
    service: Annotated[ExportService, Depends(get_export_service)],
    _: Annotated[CurrentUser, Depends(require_operator)],
) -> ExportExecution:
    """Queue a durable export over one completed aggregation."""
    try:
        return service.create_export(command)
    except ResourceNotFoundError as error:
        raise _not_found() from error
    except InvalidResourceStateError as error:
        raise ApiRequestError(
            status_code=status.HTTP_409_CONFLICT,
            code="resource_conflict",
            message="The selected aggregation is not exportable.",
        ) from error


@router.get("/exports/{export_id}", response_model=ExportExecution)
def get_export(
    export_id: UUID,
    service: Annotated[ExportService, Depends(get_export_service)],
    _: Annotated[CurrentUser, Depends(require_viewer)],
) -> ExportExecution:
    """Read one current export lifecycle resource."""
    try:
        return service.get_export(export_id)
    except ResourceNotFoundError as error:
        raise _not_found() from error


@router.get("/exports/{export_id}/download")
def download_export(
    export_id: UUID,
    service: Annotated[ExportService, Depends(get_export_service)],
    _: Annotated[CurrentUser, Depends(require_viewer)],
) -> Response:
    """Return a completed export's primary output bytes by artifact reference."""
    try:
        content, media_type = service.download_export(export_id)
    except ResourceNotFoundError as error:
        raise _not_found() from error
    return Response(content=content, media_type=media_type)


def _not_found() -> ApiRequestError:
    return ApiRequestError(
        status_code=status.HTTP_404_NOT_FOUND,
        code="resource_not_found",
        message="The requested resource does not exist.",
    )
