"""Provider-neutral request authentication and CSRF enforcement, plus the local-account provider.

See [ADR-0031](../../../../docs/decisions/ADR-0031-local-database-authentication.md) for the cookie
contract, session model, and the ``must_change_password`` gate that ``require_password_current``
enforces, and [ADR-0032](../../../../docs/decisions/ADR-0032-sliding-session-lifetime.md) for session
lifetimes and persistent sign-in. The session, login, and password endpoints live in
``gendertagger.api.routes.authentication``.
"""

import hmac
from typing import Annotated, Protocol, cast
from uuid import UUID

from fastapi import Depends, Request, status

from gendertagger.api.dependencies import get_unit_of_work_factory
from gendertagger.api.errors import ApiRequestError
from gendertagger.models.user import CurrentUser
from gendertagger.services.authentication import AuthenticationService
from gendertagger.services.ports.unit_of_work import UnitOfWorkFactory

SESSION_COOKIE_NAME = "session"
CSRF_COOKIE_NAME = "csrf_token"
CSRF_HEADER_NAME = "x-csrf-token"

_SAFE_REQUEST_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})


class AuthenticationBackend(Protocol):
    """Resolve browser requests without fixing the identity provider."""

    def authenticate(self, request: Request) -> UUID | None:
        """Return the persisted user ID represented by the request, if valid."""
        ...

    def validate_csrf(self, request: Request, *, user_id: UUID) -> bool:
        """Validate the state-changing request against its browser session."""
        ...


class DatabaseAuthenticationBackend:
    """Local-account ``AuthenticationBackend`` backed by ``AuthenticationService`` (ADR-0031).

    Resolves the ``session`` cookie into a user ID, and stashes the session's CSRF secret, its
    forced-password-change flag, and its kind on ``request.state`` so ``validate_csrf``,
    ``require_password_current``, and ``GET /auth/session`` need no second session lookup.
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
        request.state.keep_signed_in = resolved.keep_signed_in
        return resolved.user_id

    # The CSRF secret on request.state was bound to this user's session by authenticate().
    def validate_csrf(self, request: Request, *, user_id: UUID) -> bool:  # noqa: ARG002
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


def _authentication_required() -> ApiRequestError:
    return ApiRequestError(
        status_code=status.HTTP_401_UNAUTHORIZED,
        code="authentication_required",
        message="Authentication is required.",
        headers={"WWW-Authenticate": "Session"},
    )
