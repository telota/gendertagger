"""Provider-neutral request authentication and CSRF enforcement, plus the local-account provider.

See [ADR-0031](../../../docs/decisions/ADR-0031-local-database-authentication.md) for the cookie
contract, session model, and the ``must_change_password`` gate that ``require_password_current``
enforces.
"""

import hmac
from typing import Annotated, Protocol, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response, status

from gendertagger.api.dependencies import get_authentication_service, get_unit_of_work_factory
from gendertagger.api.errors import ApiRequestError
from gendertagger.models.auth import ChangePasswordRequest, LoginRequest
from gendertagger.models.user import CurrentUser
from gendertagger.services.authentication import AuthenticationService, InvalidCredentialsError
from gendertagger.services.unit_of_work import UnitOfWorkFactory

SESSION_COOKIE_NAME = "session"
CSRF_COOKIE_NAME = "csrf_token"
CSRF_HEADER_NAME = "x-csrf-token"

_SAFE_REQUEST_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})
router = APIRouter(tags=["authentication"])
unauthenticated_router = APIRouter(tags=["authentication"])


class AuthenticationBackend(Protocol):
    """Resolve browser requests without fixing the identity provider."""

    def authenticate(self, request: Request) -> UUID | None:
        """Return the persisted user ID represented by the request, if valid."""
        ...

    def validate_csrf(self, request: Request, *, user_id: UUID) -> bool:
        """Validate the state-changing request against its browser session."""
        ...


class RejectAllAuthenticationBackend:
    """Fail closed until deployment supplies an authentication provider."""

    def authenticate(self, request: Request) -> UUID | None:
        """Reject every request without inspecting untrusted credentials."""
        return None

    def validate_csrf(self, request: Request, *, user_id: UUID) -> bool:
        """Reject every state-changing request without a configured session."""
        return False


class DatabaseAuthenticationBackend:
    """Local-account ``AuthenticationBackend`` backed by ``AuthenticationService`` (ADR-0031).

    Resolves the ``session`` cookie into a user ID, and stashes the session's CSRF secret and
    forced-password-change flag on ``request.state`` so ``validate_csrf`` and
    ``require_password_current`` need no second session lookup.
    """

    def __init__(self, authentication_service: AuthenticationService) -> None:
        self._authentication_service = authentication_service

    def authenticate(self, request: Request) -> UUID | None:
        """Resolve the ``session`` cookie into a persisted user ID, or ``None`` if invalid."""
        token = request.cookies.get(SESSION_COOKIE_NAME)
        if not token:
            return None
        resolved = self._authentication_service.resolve_session(session_token=token)
        if resolved is None:
            return None
        request.state.csrf_secret = resolved.csrf_secret
        request.state.must_change_password = resolved.must_change_password
        return resolved.user_id

    def validate_csrf(self, request: Request, *, user_id: UUID) -> bool:
        """Compare the ``X-CSRF-Token`` header against the session's stored secret."""
        csrf_secret = cast(str | None, getattr(request.state, "csrf_secret", None))
        header_value = request.headers.get(CSRF_HEADER_NAME)
        if not csrf_secret or not header_value:
            return False
        return hmac.compare_digest(csrf_secret, header_value)


def get_authentication_backend(request: Request) -> AuthenticationBackend:
    """Return the process-scoped authentication provider."""
    return cast(AuthenticationBackend, request.app.state.authentication_backend)


def require_authenticated_user(
    request: Request,
    authentication_backend: Annotated[
        AuthenticationBackend,
        Depends(get_authentication_backend),
    ],
    unit_of_work_factory: Annotated[
        UnitOfWorkFactory,
        Depends(get_unit_of_work_factory),
    ],
) -> CurrentUser:
    """Resolve one active user as a provider-neutral public principal."""
    user_id = authentication_backend.authenticate(request)
    if user_id is None:
        raise _authentication_required()

    with unit_of_work_factory() as unit_of_work:
        user = unit_of_work.users.get_user(user_id)
    if user is None or not user.is_active:
        raise _authentication_required()
    return CurrentUser(id=user.id, display_name=user.display_name, roles=user.roles)


def require_csrf_protection(
    request: Request,
    authenticated_user: Annotated[CurrentUser, Depends(require_authenticated_user)],
    authentication_backend: Annotated[
        AuthenticationBackend,
        Depends(get_authentication_backend),
    ],
) -> None:
    """Require backend-owned CSRF validation for unsafe browser requests."""
    if request.method in _SAFE_REQUEST_METHODS:
        return
    if not authentication_backend.validate_csrf(request, user_id=authenticated_user.id):
        raise ApiRequestError(
            status_code=status.HTTP_403_FORBIDDEN,
            code="forbidden",
            message="CSRF validation failed.",
        )


def require_password_current(
    request: Request,
    user: Annotated[CurrentUser, Depends(require_authenticated_user)],
) -> CurrentUser:
    """Block access while a flagged local account still owes a password change (ADR-0031).

    Reads the flag `DatabaseAuthenticationBackend.authenticate` already attached to
    ``request.state``, so this never issues a persistence lookup of its own. A backend that never
    sets the attribute (``RejectAllAuthenticationBackend``, or a dependency-overridden test) leaves
    every request ungated.
    """
    if cast(bool, getattr(request.state, "must_change_password", False)):
        raise ApiRequestError(
            status_code=status.HTTP_403_FORBIDDEN,
            code="password_change_required",
            message="The password must be changed before continuing.",
        )
    return user


@router.get("/me", response_model=CurrentUser)
def read_current_user(
    current_user: Annotated[CurrentUser, Depends(require_authenticated_user)],
) -> CurrentUser:
    """Return the authenticated principal without persistence-only fields."""
    return current_user


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    request: Request,
    response: Response,
    _current_user: Annotated[CurrentUser, Depends(require_authenticated_user)],
    authentication_service: Annotated[AuthenticationService, Depends(get_authentication_service)],
) -> None:
    """Revoke the presented session and clear its cookies."""
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if token:
        authentication_service.logout(session_token=token)
    _clear_session_cookies(response)


@router.post("/me/password", status_code=status.HTTP_204_NO_CONTENT)
def change_own_password(
    body: ChangePasswordRequest,
    current_user: Annotated[CurrentUser, Depends(require_authenticated_user)],
    authentication_service: Annotated[AuthenticationService, Depends(get_authentication_service)],
) -> None:
    """Change the authenticated user's own password, clearing the forced-change flag."""
    try:
        authentication_service.change_password(
            user_id=current_user.id,
            current_password=body.current_password.get_secret_value(),
            new_password=body.new_password.get_secret_value(),
        )
    except InvalidCredentialsError as error:
        raise ApiRequestError(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="invalid_credentials",
            message="The current password is incorrect.",
        ) from error


@unauthenticated_router.post("/auth/login", response_model=CurrentUser)
def login(
    body: LoginRequest,
    response: Response,
    authentication_service: Annotated[AuthenticationService, Depends(get_authentication_service)],
) -> CurrentUser:
    """Verify local-account credentials and issue a new session."""
    try:
        issued = authentication_service.login(
            username=body.username,
            password=body.password.get_secret_value(),
        )
    except InvalidCredentialsError as error:
        raise ApiRequestError(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="invalid_credentials",
            message="The username or password is incorrect.",
        ) from error
    _set_session_cookies(response, token=issued.token, csrf_secret=issued.csrf_secret)
    return issued.user


def _set_session_cookies(response: Response, *, token: str, csrf_secret: str) -> None:
    response.set_cookie(
        SESSION_COOKIE_NAME,
        token,
        httponly=True,
        secure=True,
        samesite="lax",
        path="/",
    )
    response.set_cookie(
        CSRF_COOKIE_NAME,
        csrf_secret,
        httponly=False,
        secure=True,
        samesite="lax",
        path="/",
    )


def _clear_session_cookies(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE_NAME, path="/")
    response.delete_cookie(CSRF_COOKIE_NAME, path="/")


def _authentication_required() -> ApiRequestError:
    return ApiRequestError(
        status_code=status.HTTP_401_UNAUTHORIZED,
        code="authentication_required",
        message="Authentication is required.",
        headers={"WWW-Authenticate": "Session"},
    )
