"""Project and dataset-snapshot HTTP resources."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status

from gendertagger.api.authorization import require_operator, require_viewer
from gendertagger.api.dependencies import get_project_service
from gendertagger.models.project import (
    DatasetSnapshot,
    Project,
    ProjectCreate,
    SnapshotImportRequest,
    TeiImportProfile,
)
from gendertagger.models.user import User
from gendertagger.services.persistence_errors import ResourceNotFoundError
from gendertagger.services.projects import ProjectService
from gendertagger.storage.local import ArtifactTooLargeError

router = APIRouter(tags=["projects"])


@router.post("/projects", response_model=Project, status_code=status.HTTP_201_CREATED)
def create_project(
    command: ProjectCreate,
    service: Annotated[ProjectService, Depends(get_project_service)],
    _: Annotated[User, Depends(require_operator)],
) -> Project:
    """Create one editorial project as an operator."""
    return service.create_project(command)


@router.get("/projects/{project_id}", response_model=Project)
def get_project(
    project_id: UUID,
    service: Annotated[ProjectService, Depends(get_project_service)],
    _: Annotated[User, Depends(require_viewer)],
) -> Project:
    """Read one project without exposing persistence models."""
    try:
        return service.get_project(project_id)
    except ResourceNotFoundError as error:
        raise _not_found() from error


@router.post(
    "/projects/{project_id}/snapshots",
    response_model=DatasetSnapshot,
    status_code=status.HTTP_202_ACCEPTED,
)
def import_snapshot(
    project_id: UUID,
    source: Annotated[
        UploadFile,
        File(description="Exact TEI XML source retained as an immutable artifact."),
    ],
    service: Annotated[ProjectService, Depends(get_project_service)],
    _: Annotated[User, Depends(require_operator)],
    profile: Annotated[TeiImportProfile, Form()] = (TeiImportProfile.tei_p5_person_register_v1),
) -> DatasetSnapshot:
    """Preserve and synchronously import a bounded TEI upload."""
    try:
        return service.import_snapshot(
            project_id=project_id,
            source=source.file,
            command=SnapshotImportRequest(profile=profile),
        )
    except ResourceNotFoundError as error:
        raise _not_found() from error
    except ArtifactTooLargeError as error:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=str(error),
        ) from error


@router.get("/snapshots/{snapshot_id}", response_model=DatasetSnapshot)
def get_snapshot(
    snapshot_id: UUID,
    service: Annotated[ProjectService, Depends(get_project_service)],
    _: Annotated[User, Depends(require_viewer)],
) -> DatasetSnapshot:
    """Read one immutable dataset snapshot lifecycle resource."""
    try:
        return service.get_snapshot(snapshot_id)
    except ResourceNotFoundError as error:
        raise _not_found() from error


def _not_found() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Resource not found",
    )
