"""Global and project-scoped authorization dependencies for the versioned API (ADR-0033).

Global roles gate the few operations that belong to no project: creating a project and administering
local accounts or memberships. Every project-scoped route instead asks a :class:`ProjectAccessGuard` for
the caller's role in the project that owns the route's root identifier.
"""

from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

from fastapi import Depends, status

from gendertagger.api.authentication import require_authenticated_user
from gendertagger.api.dependencies import get_project_access_service
from gendertagger.api.errors import ApiRequestError
from gendertagger.models.user import CurrentUser, GlobalRole, ProjectRole
from gendertagger.services.ports.project_access_repository import ProjectScope
from gendertagger.services.project_access import ProjectAccessService


def has_global_role(user: CurrentUser, required_role: GlobalRole) -> bool:
    """Return whether any assigned hierarchical global role grants the capability."""
    return any(assigned_role.grants(required_role) for assigned_role in user.roles)


def require_project_creator(
    user: Annotated[CurrentUser, Depends(require_authenticated_user)],
) -> CurrentUser:
    """Return an authenticated user allowed to create projects: a global operator or admin."""
    return _require_global_role(user, GlobalRole.operator)


def require_admin(
    user: Annotated[CurrentUser, Depends(require_authenticated_user)],
) -> CurrentUser:
    """Return an authenticated global administrator."""
    return _require_global_role(user, GlobalRole.admin)


def require_any_grant(
    user: Annotated[CurrentUser, Depends(require_authenticated_user)],
    service: Annotated[ProjectAccessService, Depends(get_project_access_service)],
) -> CurrentUser:
    """Return an authenticated user holding any global role or any project membership."""
    if not service.has_any_grant(user):
        raise _forbidden("The authenticated user holds no role.")
    return user


@dataclass(frozen=True, slots=True)
class ProjectAccessGuard:
    """Authorize one request against the project that owns a resource.

    Attributes:
        user: The authenticated caller.
        service: Resolves the caller's effective role in a resource's owning project.
    """

    user: CurrentUser
    service: ProjectAccessService

    def require(
        self,
        scope: ProjectScope,
        resource_id: UUID,
        least_role: ProjectRole,
    ) -> ProjectRole:
        """Return the caller's project role when it grants ``least_role``.

        Raises:
            ApiRequestError: ``404 resource_not_found`` when the resource does not exist or the
                caller has no role in its project, and ``403 forbidden`` when the caller's role
                is below ``least_role``.
        """
        role = self.service.effective_role(self.user, scope, resource_id)
        if role is None:
            raise ApiRequestError(
                status_code=status.HTTP_404_NOT_FOUND,
                code="resource_not_found",
                message="The requested resource does not exist.",
            )
        if not role.grants(least_role):
            raise _forbidden("The authenticated user lacks the required project role.")
        return role


def get_project_access_guard(
    user: Annotated[CurrentUser, Depends(require_authenticated_user)],
    service: Annotated[ProjectAccessService, Depends(get_project_access_service)],
) -> ProjectAccessGuard:
    """Return the request's project access guard for the authenticated caller."""
    return ProjectAccessGuard(user=user, service=service)



@dataclass(frozen=True, slots=True)
class ProjectMembershipManagementGuard:
    """Authorize only delegated project-membership management, never project data access."""

    user: CurrentUser
    service: ProjectAccessService

    def require(self, project_id: UUID) -> None:
        """Require current global-admin or manager authority, preserving hidden-project 404s."""
        if not self.service.can_manage_members(self.user, project_id):
            raise ApiRequestError(
                status_code=status.HTTP_404_NOT_FOUND,
                code="resource_not_found",
                message="The requested resource does not exist.",
            )


def get_project_membership_management_guard(
    user: Annotated[CurrentUser, Depends(require_authenticated_user)],
    service: Annotated[ProjectAccessService, Depends(get_project_access_service)],
) -> ProjectMembershipManagementGuard:
    """Return the narrow guard for delegated membership administration endpoints."""
    return ProjectMembershipManagementGuard(user=user, service=service)

def _require_global_role(user: CurrentUser, required_role: GlobalRole) -> CurrentUser:
    if not has_global_role(user, required_role):
        raise _forbidden("The authenticated user lacks the required role.")
    return user


def _forbidden(message: str) -> ApiRequestError:
    return ApiRequestError(
        status_code=status.HTTP_403_FORBIDDEN,
        code="forbidden",
        message=message,
    )
