"""Export execution and output HTTP resources."""

from pathlib import PurePosixPath
from typing import Annotated
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status

from gendertagger.api.authorization import ProjectAccessGuard, get_project_access_guard
from gendertagger.api.dependencies import get_export_service
from gendertagger.api.errors import ApiRequestError, invalid_cursor_error
from gendertagger.models.api import CursorPage
from gendertagger.models.export import ExportCreateRequest, ExportExecution, ExportManifest
from gendertagger.models.project import SHA256_PATTERN
from gendertagger.models.user import ProjectRole
from gendertagger.services.exports import ExportService
from gendertagger.services.pagination import InvalidCursorError
from gendertagger.services.ports.persistence_errors import (
    InvalidResourceStateError,
    ResourceNotFoundError,
)
from gendertagger.services.ports.project_access_repository import ProjectScope

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


@router.get("/runs/{run_id}/exports", response_model=CursorPage[ExportExecution])
def list_exports(
    run_id: UUID,
    service: Annotated[ExportService, Depends(get_export_service)],
    access: Annotated[ProjectAccessGuard, Depends(get_project_access_guard)],
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    cursor: Annotated[str | None, Query(max_length=2048)] = None,
) -> CursorPage[ExportExecution]:
    """List a run's exports newest first, in every lifecycle state."""
    access.require(ProjectScope.run, run_id, ProjectRole.viewer)
    try:
        return service.list_exports(run_id, limit=limit, cursor=cursor)
    except ResourceNotFoundError as error:
        raise _not_found() from error
    except InvalidCursorError as error:
        raise invalid_cursor_error() from error


@router.get("/exports/{export_execution_id}", response_model=ExportExecution)
def get_export(
    export_execution_id: UUID,
    service: Annotated[ExportService, Depends(get_export_service)],
    access: Annotated[ProjectAccessGuard, Depends(get_project_access_guard)],
) -> ExportExecution:
    """Read one current export lifecycle resource."""
    access.require(ProjectScope.export, export_execution_id, ProjectRole.viewer)
    try:
        return service.get_export(export_execution_id)
    except ResourceNotFoundError as error:
        raise _not_found() from error


@router.get("/exports/{export_execution_id}/manifest", response_model=ExportManifest)
def get_export_manifest(
    export_execution_id: UUID,
    service: Annotated[ExportService, Depends(get_export_service)],
    access: Annotated[ProjectAccessGuard, Depends(get_project_access_guard)],
) -> ExportManifest:
    """Read a completed export's persisted provenance and output checksums."""
    access.require(ProjectScope.export, export_execution_id, ProjectRole.viewer)
    try:
        return service.get_manifest(export_execution_id)
    except ResourceNotFoundError as error:
        raise _not_found() from error


@router.get(
    "/exports/{export_execution_id}/download",
    response_class=Response,
    responses={
        200: {
            "description": "Primary output bytes, or the manifest for a multi-output export.",
            "content": {
                media_type: {"schema": {"type": "string", "format": "binary"}}
                for media_type in ("application/json", "text/csv", "application/tei+xml")
            },
            "headers": {
                "Content-Disposition": {
                    "description": "Attachment filename from the logical output basename (UTF-8).",
                    "schema": {"type": "string"},
                },
                "X-Checksum-SHA256": {
                    "description": "Persisted lowercase hexadecimal SHA-256 of the downloaded artifact.",
                    "schema": {"type": "string", "pattern": SHA256_PATTERN},
                },
            },
        },
    },
)
def download_export(
    export_execution_id: UUID,
    service: Annotated[ExportService, Depends(get_export_service)],
    access: Annotated[ProjectAccessGuard, Depends(get_project_access_guard)],
) -> Response:
    """Return a completed export's primary output bytes by artifact reference."""
    access.require(ProjectScope.export, export_execution_id, ProjectRole.viewer)
    try:
        download = service.download_export(export_execution_id)
    except ResourceNotFoundError as error:
        raise _not_found() from error
    filename = PurePosixPath(download.logical_name).name
    encoded_filename = quote(filename, safe="")
    disposition = (
        f"attachment; filename*=UTF-8''{encoded_filename}"
        if encoded_filename != filename
        else f'attachment; filename="{filename}"'
    )
    return Response(
        content=download.content,
        media_type=download.media_type,
        headers={
            "Content-Disposition": disposition,
            "X-Checksum-SHA256": download.sha256,
        },
    )


def _not_found() -> ApiRequestError:
    return ApiRequestError(
        status_code=status.HTTP_404_NOT_FOUND,
        code="resource_not_found",
        message="The requested resource does not exist.",
    )
