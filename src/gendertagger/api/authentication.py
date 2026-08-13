"""Provider-neutral request authentication and CSRF enforcement."""

from typing import Annotated, Protocol, cast
from uuid import UUID

from fastapi import Depends, HTTPException, Request, status

from gendertagger.api.dependencies import get_unit_of_work_factory
from gendertagger.models.user import User
from gendertagger.services.unit_of_work import UnitOfWorkFactory

_SAFE_REQUEST_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})


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
) -> User:
    """Resolve one active persisted user or return an indistinguishable 401."""
    user_id = authentication_backend.authenticate(request)
    if user_id is None:
        raise _authentication_required()

    with unit_of_work_factory() as unit_of_work:
        user = unit_of_work.users.get_user(user_id)
    if user is None or not user.is_active:
        raise _authentication_required()
    return user


def require_csrf_protection(
    request: Request,
    authenticated_user: Annotated[User, Depends(require_authenticated_user)],
    authentication_backend: Annotated[
        AuthenticationBackend,
        Depends(get_authentication_backend),
    ],
) -> None:
    """Require backend-owned CSRF validation for unsafe browser requests."""
    if request.method in _SAFE_REQUEST_METHODS:
        return
    if not authentication_backend.validate_csrf(request, user_id=authenticated_user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="CSRF validation failed",
        )


def _authentication_required() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required",
        headers={"WWW-Authenticate": "Session"},
    )
