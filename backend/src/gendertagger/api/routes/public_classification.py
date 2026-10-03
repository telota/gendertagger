"""Anonymous bounded name classification and capability-authorized job reads."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Response, status
from fastapi.responses import JSONResponse

from gendertagger.api.dependencies import get_public_classification_service
from gendertagger.api.errors import ApiRequestError
from gendertagger.models.public_classification import (
    PublicClassificationJob,
    PublicClassificationJobAccepted,
    PublicClassificationMethods,
    PublicClassificationResponse,
    PublicClassifyNamesRequest,
)
from gendertagger.services.ports.persistence_errors import ResourceNotFoundError
from gendertagger.services.public_classification import (
    PublicClassificationService,
    PublicClassificationUnavailableError,
    PublicMethodUnavailableError,
)

router = APIRouter(prefix="/public", tags=["public classification"])


@router.get("/methods", response_model=PublicClassificationMethods)
def list_public_methods(
    response: Response,
    service: Annotated[PublicClassificationService, Depends(get_public_classification_service)],
) -> PublicClassificationMethods:
    """Discover deployment-allowlisted anonymous methods without exposing their configuration."""
    response.headers["Cache-Control"] = "no-store"
    try:
        return service.list_methods()
    except PublicClassificationUnavailableError as error:
        raise _classification_unavailable() from error


@router.post(
    "/classify",
    response_model=PublicClassificationResponse,
    responses={
        200: {
            "model": PublicClassificationResponse,
            "description": "Immediate classification result",
        },
        202: {
            "model": PublicClassificationJobAccepted,
            "description": "Classification job accepted",
        },
    },
)
def classify_public_names(
    command: PublicClassifyNamesRequest,
    response: Response,
    service: Annotated[PublicClassificationService, Depends(get_public_classification_service)],
) -> PublicClassificationResponse | JSONResponse:
    """Classify a bounded name request immediately or return its persisted asynchronous job."""
    response.headers["Cache-Control"] = "no-store"
    try:
        result = service.classify(command)
    except PublicMethodUnavailableError as error:
        raise ApiRequestError(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            code="validation_error",
            message=str(error),
        ) from error
    except PublicClassificationUnavailableError as error:
        raise _classification_unavailable() from error
    if isinstance(result, PublicClassificationJobAccepted):
        return JSONResponse(
            status_code=status.HTTP_202_ACCEPTED,
            content=result.model_dump(mode="json"),
            headers={
                "Cache-Control": "no-store",
                "Location": f"/api/v1/public/classification-jobs/{result.id}",
            },
        )
    return result


@router.get("/classification-jobs/{classification_job_id}", response_model=PublicClassificationJob)
def get_public_classification_job(
    classification_job_id: UUID,
    response: Response,
    service: Annotated[PublicClassificationService, Depends(get_public_classification_service)],
    retrieval_token: Annotated[
        str | None, Header(alias="X-Classification-Token", max_length=100)
    ] = None,
) -> PublicClassificationJob:
    """Read one anonymous classification job using its private retrieval capability."""
    response.headers["Cache-Control"] = "no-store"
    try:
        return service.get_job(classification_job_id, retrieval_token)
    except ResourceNotFoundError as error:
        raise ApiRequestError(
            status_code=status.HTTP_404_NOT_FOUND,
            code="resource_not_found",
            message="Classification job does not exist.",
            headers={"Cache-Control": "no-store"},
        ) from error


def _classification_unavailable() -> ApiRequestError:
    """Return a secret-free deployment configuration/asset failure."""
    return ApiRequestError(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        code="classification_unavailable",
        message="Public classification is temporarily unavailable.",
        headers={"Cache-Control": "no-store"},
    )
