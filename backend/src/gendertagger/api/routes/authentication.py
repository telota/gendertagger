"""Session, login, logout, and own-password HTTP resources for local accounts.

See [ADR-0031](../../../../../docs/decisions/ADR-0031-local-database-authentication.md) for the cookie
contract and [ADR-0032](../../../../../docs/decisions/ADR-0032-sliding-session-lifetime.md) for session
lifetimes and persistent sign-in. Request authentication itself lives in
``gendertagger.api.authentication``.
"""

from datetime import datetime
from typing import Annotated, cast

from fastapi import APIRouter, Depends, Request, Response, status

from gendertagger.api.authentication import (
    CSRF_COOKIE_NAME,
    SESSION_COOKIE_NAME,
    require_authenticated_user,
)
from gendertagger.api.dependencies import get_authentication_service
from gendertagger.api.errors import ApiRequestError
from gendertagger.models.auth import ChangePasswordRequest, CurrentSession, LoginRequest
from gendertagger.models.user import CurrentUser
from gendertagger.services.authentication import (
    AuthenticationService,
    InvalidCredentialsError,
    InvalidCurrentPasswordError,
)

router = APIRouter(tags=["authentication"])
unauthenticated_router = APIRouter(tags=["authentication"])


@router.get("/me", response_model=CurrentUser)
def read_current_user(
    current_user: Annotated[CurrentUser, Depends(require_authenticated_user)],
) -> CurrentUser:
    """Return the authenticated principal without persistence-only fields."""
    return current_user


@router.get("/auth/session", response_model=CurrentSession)
def read_current_session(
    request: Request,
    _current_user: Annotated[CurrentUser, Depends(require_authenticated_user)],
) -> CurrentSession:
    """Return whether the session owes a password change and whether it was kept signed in."""
    return CurrentSession(
        must_change_password=cast(bool, getattr(request.state, "must_change_password", False)),
        keep_signed_in=cast(bool, getattr(request.state, "keep_signed_in", False)),
    )


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
    except InvalidCurrentPasswordError as error:
        # Not 401: that status means the session is gone, and the client would sign the user out.
        raise ApiRequestError(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="invalid_current_password",
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
            keep_signed_in=body.keep_signed_in,
        )
    except InvalidCredentialsError as error:
        raise ApiRequestError(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="invalid_credentials",
            message="The username or password is incorrect.",
        ) from error
    _set_session_cookies(
        response,
        token=issued.token,
        csrf_secret=issued.csrf_secret,
        # A kept-signed-in session survives browser restarts until its absolute limit; any other
        # session gets browser-session cookies that the browser discards when it closes.
        expires=issued.absolute_expires_at if issued.keep_signed_in else None,
    )
    return issued.user


def _set_session_cookies(
    response: Response, *, token: str, csrf_secret: str, expires: datetime | None
) -> None:
    response.set_cookie(
        SESSION_COOKIE_NAME,
        token,
        expires=expires,
        httponly=True,
        secure=True,
        samesite="lax",
        path="/",
    )
    response.set_cookie(
        CSRF_COOKIE_NAME,
        csrf_secret,
        expires=expires,
        httponly=False,
        secure=True,
        samesite="lax",
        path="/",
    )


def _clear_session_cookies(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE_NAME, path="/")
    response.delete_cookie(CSRF_COOKIE_NAME, path="/")
