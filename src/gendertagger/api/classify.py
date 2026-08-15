"""Synchronous on-demand name classification HTTP resource."""

from typing import Annotated

from fastapi import APIRouter, Depends, status

from gendertagger.api.authorization import require_viewer
from gendertagger.api.dependencies import get_classification_service
from gendertagger.api.errors import ApiRequestError
from gendertagger.models.classify import ClassifyNamesRequest, ClassifyNamesResponse
from gendertagger.models.user import CurrentUser
from gendertagger.services.classification import DirectClassificationService
from gendertagger.services.method_registry import UnknownMethodError

router = APIRouter(tags=["classification"])


@router.post("/classify", response_model=ClassifyNamesResponse)
def classify_names(
    command: ClassifyNamesRequest,
    service: Annotated[DirectClassificationService, Depends(get_classification_service)],
    _: Annotated[CurrentUser, Depends(require_viewer)],
) -> ClassifyNamesResponse:
    """Classify one or more names synchronously across enabled methods."""
    try:
        return service.classify_names(
            names=command.names,
            methods=command.methods,
            method_configs=command.method_configs,
        )
    except UnknownMethodError as error:
        raise ApiRequestError(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            code="validation_error",
            message=str(error),
        ) from error
