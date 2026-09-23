"""Project and dataset-snapshot HTTP resources."""

from collections.abc import Sequence
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile, status
from pydantic import ValidationError

from gendertagger.api.authentication import require_authenticated_user
from gendertagger.api.authorization import (
    ProjectAccessGuard,
    get_project_access_guard,
    require_any_grant,
    require_project_creator,
)
from gendertagger.api.dependencies import get_project_access_service, get_project_service
from gendertagger.api.errors import ApiRequestError, invalid_cursor_error
from gendertagger.models.api import CursorPage
from gendertagger.models.person import PersonRecord
from gendertagger.models.project import (
    DEFAULT_SOURCE_FORMAT,
    DEFAULT_SOURCE_PACKAGING,
    AccessibleProject,
    DatasetSnapshot,
    ProjectCreate,
    ProjectWorkingAggregationUpdate,
    SnapshotImportRequest,
    SnapshotSourceMember,
    SnapshotUploadLimits,
    SourceFormat,
    SourcePackaging,
)
from gendertagger.models.user import CurrentUser, ProjectRole
from gendertagger.services.pagination import InvalidCursorError
from gendertagger.services.ports.persistence_errors import (
    InvalidResourceStateError,
    ResourceNotFoundError,
)
from gendertagger.services.ports.project_access_repository import ProjectScope
from gendertagger.services.project_access import ProjectAccessService
from gendertagger.services.projects import (
    InvalidSnapshotSourceError,
    ProjectService,
    SnapshotUpload,
    SnapshotUploadTooLargeError,
)
from gendertagger.storage.local import ArtifactTooLargeError

router = APIRouter(tags=["projects"])


@router.post("/projects", response_model=AccessibleProject, status_code=status.HTTP_201_CREATED)
def create_project(
    command: ProjectCreate,
    service: Annotated[ProjectService, Depends(get_project_service)],
    creator: Annotated[CurrentUser, Depends(require_project_creator)],
) -> AccessibleProject:
    """Create one editorial project and make its creator the project operator."""
    return service.create_project(command, creator_user_id=creator.id)


@router.get("/projects", response_model=CursorPage[AccessibleProject])
def list_projects(
    service: Annotated[ProjectAccessService, Depends(get_project_access_service)],
    user: Annotated[CurrentUser, Depends(require_authenticated_user)],
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    cursor: Annotated[str | None, Query(max_length=2048)] = None,
) -> CursorPage[AccessibleProject]:
    """List the projects the caller has a role in, in slug order, with that role."""
    try:
        return service.list_projects(user, limit=limit, cursor=cursor)
    except InvalidCursorError as error:
        raise invalid_cursor_error() from error


@router.get("/projects/{project_id}", response_model=AccessibleProject)
def get_project(
    project_id: UUID,
    service: Annotated[ProjectService, Depends(get_project_service)],
    access: Annotated[ProjectAccessGuard, Depends(get_project_access_guard)],
) -> AccessibleProject:
    """Read one project with the caller's role in it."""
    role = access.require(ProjectScope.project, project_id, ProjectRole.viewer)
    try:
        project = service.get_project(project_id)
    except ResourceNotFoundError as error:
        raise _not_found() from error
    return AccessibleProject(**project.model_dump(), current_user_role=role)


@router.put(
    "/projects/{project_id}/working-aggregation",
    response_model=AccessibleProject,
)
def set_working_aggregation(
    project_id: UUID,
    command: ProjectWorkingAggregationUpdate,
    service: Annotated[ProjectService, Depends(get_project_service)],
    access: Annotated[ProjectAccessGuard, Depends(get_project_access_guard)],
) -> AccessibleProject:
    """Point the project at one of its own completed aggregations, or clear the pointer."""
    role = access.require(ProjectScope.project, project_id, ProjectRole.operator)
    try:
        project = service.set_working_aggregation(
            project_id,
            aggregation_execution_id=command.aggregation_execution_id,
        )
    except ResourceNotFoundError as error:
        raise _not_found() from error
    except InvalidResourceStateError as error:
        raise ApiRequestError(
            status_code=status.HTTP_409_CONFLICT,
            code="resource_conflict",
            message="The aggregation execution is not completed.",
        ) from error
    return AccessibleProject(**project.model_dump(), current_user_role=role)


@router.get("/snapshot-upload-limits", response_model=SnapshotUploadLimits)
def get_snapshot_upload_limits(
    service: Annotated[ProjectService, Depends(get_project_service)],
    _: Annotated[CurrentUser, Depends(require_any_grant)],
) -> SnapshotUploadLimits:
    """Return the deployment's snapshot upload and import bounds, so a client can check first."""
    return service.upload_limits()


@router.post(
    "/projects/{project_id}/snapshots",
    response_model=DatasetSnapshot,
    status_code=status.HTTP_202_ACCEPTED,
)
def import_snapshot(
    project_id: UUID,
    source: Annotated[
        list[UploadFile],
        File(
            description=(
                "One or more exact source files. Repeat the source part for loose TEI files."
            )
        ),
    ],
    service: Annotated[ProjectService, Depends(get_project_service)],
    access: Annotated[ProjectAccessGuard, Depends(get_project_access_guard)],
    source_format: Annotated[SourceFormat, Form()] = DEFAULT_SOURCE_FORMAT,
    packaging: Annotated[SourcePackaging, Form()] = DEFAULT_SOURCE_PACKAGING,
) -> DatasetSnapshot:
    """Durably stage bounded sources and queue their snapshot import."""
    access.require(ProjectScope.project, project_id, ProjectRole.operator)
    try:
        return service.import_snapshot(
            project_id=project_id,
            sources=[
                SnapshotUpload(
                    source=upload.file,
                    filename=upload.filename or "",
                    media_type=upload.content_type,
                )
                for upload in source
            ],
            command=SnapshotImportRequest(
                source_format=source_format,
                packaging=packaging,
            ),
        )
    except ResourceNotFoundError as error:
        raise _not_found() from error
    except (ArtifactTooLargeError, SnapshotUploadTooLargeError) as error:
        raise ApiRequestError(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            code="payload_too_large",
            message=str(error),
        ) from error
    except InvalidSnapshotSourceError as error:
        raise ApiRequestError(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            code="validation_error",
            message=str(error),
        ) from error
    except ValidationError as error:
        raise ApiRequestError(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            code="validation_error",
            message="The source format, packaging, and import profile are incompatible.",
            details={"reason": "incompatible_import_options"},
        ) from error


@router.get(
    "/projects/{project_id}/snapshots",
    response_model=CursorPage[DatasetSnapshot],
)
def list_snapshots(
    project_id: UUID,
    service: Annotated[ProjectService, Depends(get_project_service)],
    access: Annotated[ProjectAccessGuard, Depends(get_project_access_guard)],
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    cursor: Annotated[str | None, Query(max_length=2048)] = None,
) -> CursorPage[DatasetSnapshot]:
    """List a project's snapshots newest first, in every lifecycle state."""
    access.require(ProjectScope.project, project_id, ProjectRole.viewer)
    try:
        return service.list_snapshots(project_id, limit=limit, cursor=cursor)
    except ResourceNotFoundError as error:
        raise _not_found() from error
    except InvalidCursorError as error:
        raise invalid_cursor_error() from error


@router.get("/snapshots/{snapshot_id}", response_model=DatasetSnapshot)
def get_snapshot(
    snapshot_id: UUID,
    service: Annotated[ProjectService, Depends(get_project_service)],
    access: Annotated[ProjectAccessGuard, Depends(get_project_access_guard)],
) -> DatasetSnapshot:
    """Read one immutable dataset snapshot lifecycle resource."""
    access.require(ProjectScope.snapshot, snapshot_id, ProjectRole.viewer)
    try:
        return service.get_snapshot(snapshot_id)
    except ResourceNotFoundError as error:
        raise _not_found() from error


@router.get(
    "/snapshots/{snapshot_id}/source-members",
    response_model=list[SnapshotSourceMember],
)
def list_snapshot_source_members(
    snapshot_id: UUID,
    service: Annotated[ProjectService, Depends(get_project_service)],
    access: Annotated[ProjectAccessGuard, Depends(get_project_access_guard)],
) -> Sequence[SnapshotSourceMember]:
    """List the snapshot's source provenance in canonical ordinal order."""
    access.require(ProjectScope.snapshot, snapshot_id, ProjectRole.viewer)
    try:
        return service.list_snapshot_source_members(snapshot_id)
    except ResourceNotFoundError as error:
        raise _not_found() from error


@router.get(
    "/snapshots/{snapshot_id}/people",
    response_model=CursorPage[PersonRecord],
)
def list_people(
    snapshot_id: UUID,
    service: Annotated[ProjectService, Depends(get_project_service)],
    access: Annotated[ProjectAccessGuard, Depends(get_project_access_guard)],
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    cursor: Annotated[str | None, Query(max_length=2048)] = None,
) -> CursorPage[PersonRecord]:
    """List snapshot people in stable TEI-ID order."""
    access.require(ProjectScope.snapshot, snapshot_id, ProjectRole.viewer)
    try:
        return service.list_people(snapshot_id, limit=limit, cursor=cursor)
    except ResourceNotFoundError as error:
        raise _not_found() from error
    except InvalidResourceStateError as error:
        raise ApiRequestError(
            status_code=status.HTTP_409_CONFLICT,
            code="resource_conflict",
            message="The dataset snapshot is not ready.",
        ) from error
    except InvalidCursorError as error:
        raise invalid_cursor_error() from error


def _not_found() -> ApiRequestError:
    return ApiRequestError(
        status_code=status.HTTP_404_NOT_FOUND,
        code="resource_not_found",
        message="The requested resource does not exist.",
    )
