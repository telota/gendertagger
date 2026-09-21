"""Uniform API exception mapping and validation-error normalization."""

from collections.abc import Mapping
from http import HTTPStatus
from typing import cast

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import JsonValue
from starlette.exceptions import HTTPException as StarletteHTTPException

from gendertagger.models.api import ApiErrorDetail, ApiErrorEnvelope

_STATUS_ERROR_CODES = {
    400: "invalid_request",
    401: "authentication_required",
    403: "forbidden",
    404: "resource_not_found",
    405: "method_not_allowed",
    409: "resource_conflict",
    413: "payload_too_large",
    422: "validation_error",
    500: "internal_error",
}


class ApiRequestError(Exception):
    """Intentional public failure with a stable code and safe details."""

    def __init__(
        self,
        *,
        status_code: int,
        code: str,
        message: str,
        details: Mapping[str, JsonValue] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> None:
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = dict(details) if details is not None else {}
        self.headers = dict(headers) if headers is not None else {}
        super().__init__(message)


def install_error_handlers(application: FastAPI) -> None:
    """Install transport-wide handlers without exposing internal diagnostics."""

    @application.exception_handler(ApiRequestError)
    async def _handle_api_exception(
        request: Request,
        exception: Exception,
    ) -> JSONResponse:
        api_exception = cast(ApiRequestError, exception)
        return _error_response(
            request,
            status_code=api_exception.status_code,
            code=api_exception.code,
            message=api_exception.message,
            details=api_exception.details,
            headers=api_exception.headers,
        )

    @application.exception_handler(RequestValidationError)
    async def _handle_validation_error(
        request: Request,
        exception: Exception,
    ) -> JSONResponse:
        validation_error = cast(RequestValidationError, exception)
        issues: list[JsonValue] = [
            {
                "location": list(error["loc"]),
                "message": error["msg"],
                "type": error["type"],
            }
            for error in validation_error.errors()
        ]
        return _error_response(
            request,
            status_code=422,
            code="validation_error",
            message="The request is invalid.",
            details={"issues": issues},
        )

    @application.exception_handler(StarletteHTTPException)
    async def _handle_http_exception(
        request: Request,
        exception: Exception,
    ) -> JSONResponse:
        http_exception = cast(StarletteHTTPException, exception)
        status_code = http_exception.status_code
        return _error_response(
            request,
            status_code=status_code,
            code=_STATUS_ERROR_CODES.get(status_code, "http_error"),
            message=_status_message(status_code),
            headers=http_exception.headers,
        )

    @application.exception_handler(Exception)
    async def _handle_unexpected_exception(
        request: Request,
        _exception: Exception,
    ) -> JSONResponse:
        return _error_response(
            request,
            status_code=500,
            code="internal_error",
            message="The server could not complete the request.",
        )


def _error_response(
    request: Request,
    *,
    status_code: int,
    code: str,
    message: str,
    details: Mapping[str, JsonValue] | None = None,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    request_id = cast(str | None, getattr(request.state, "request_id", None))
    response_headers = dict(headers) if headers is not None else {}
    if request_id is not None:
        response_headers["x-request-id"] = request_id
    envelope = ApiErrorEnvelope(
        error=ApiErrorDetail(
            code=code,
            message=message,
            details=dict(details) if details is not None else {},
            request_id=request_id,
        )
    )
    return JSONResponse(
        status_code=status_code,
        content=envelope.model_dump(mode="json"),
        headers=response_headers,
    )


def _status_message(status_code: int) -> str:
    try:
        phrase = HTTPStatus(status_code).phrase
    except ValueError:
        phrase = "HTTP error"
    return f"{phrase}."
