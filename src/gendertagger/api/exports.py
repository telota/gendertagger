"""Export execution and output HTTP resources."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Response, status

from gendertagger.api.authorization import ProjectAccessGuard, get_project_access_guard
from gendertagger.api.dependencies import get_export_service
from gendertagger.api.errors import ApiRequestError
from gendertagger.models.export import ExportCreateRequest, ExportExecution
from gendertagger.models.user import ProjectRole
from gendertagger.services.exports import ExportService
from gendertagger.services.persistence_errors import (
    InvalidResourceStateError,
    ResourceNotFoundError,
)
from gendertagger.services.project_access_repository import ProjectScope

router = APIRouter(tags=["exports"])


@router.post(
    "/exports",
    response_model=ExportExecution,
    status_code=status.HTTP_202_ACCEPTED,
)
def create_export(
    command: ExportCreateRequest,
    service: Annotated[ExportService, Depends(get_export_service)],
    access: Annotated[ProjectAccessGuard, Depends(get_project_access_guard)],
) -> ExportExecution:
    """Queue a durable export over one completed aggregation."""
    access.require(ProjectScope.run, command.run_id, ProjectRole.operator)
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
    access: Annotated[ProjectAccessGuard, Depends(get_project_access_guard)],
) -> ExportExecution:
    """Read one current export lifecycle resource."""
    access.require(ProjectScope.export, export_id, ProjectRole.viewer)
    try:
        return service.get_export(export_id)
    except ResourceNotFoundError as error:
        raise _not_found() from error


@router.get("/exports/{export_id}/download")
def download_export(
    export_id: UUID,
    service: Annotated[ExportService, Depends(get_export_service)],
    access: Annotated[ProjectAccessGuard, Depends(get_project_access_guard)],
) -> Response:
    """Return a completed export's primary output bytes by artifact reference."""
    access.require(ProjectScope.export, export_id, ProjectRole.viewer)
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
