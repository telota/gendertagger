"""Role authorization dependencies for the versioned API."""

from typing import Annotated

from fastapi import Depends, HTTPException, status

from gendertagger.api.authentication import require_authenticated_user
from gendertagger.models.user import Role, User

_ROLE_RANK = {
    Role.viewer: 0,
    Role.reviewer: 1,
    Role.operator: 2,
    Role.admin: 3,
}


def has_role(user: User, required_role: Role) -> bool:
    """Return whether any assigned hierarchical role grants the capability."""
    required_rank = _ROLE_RANK[required_role]
    return any(_ROLE_RANK[assigned_role] >= required_rank for assigned_role in user.roles)


def require_viewer(
    user: Annotated[User, Depends(require_authenticated_user)],
) -> User:
    """Return an authenticated user with read capability."""
    return _require_role(user, Role.viewer)


def require_reviewer(
    user: Annotated[User, Depends(require_authenticated_user)],
) -> User:
    """Return an authenticated user allowed to append annotations."""
    return _require_role(user, Role.reviewer)


def require_operator(
    user: Annotated[User, Depends(require_authenticated_user)],
) -> User:
    """Return an authenticated user allowed to import and create runs."""
    return _require_role(user, Role.operator)


def _require_role(user: User, required_role: Role) -> User:
    if not has_role(user, required_role):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient role",
        )
    return user
