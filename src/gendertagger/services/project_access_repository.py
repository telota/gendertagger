"""Application repository contract for project ownership and memberships (ADR-0033)."""

from collections.abc import Sequence
from enum import StrEnum
from typing import Protocol
from uuid import UUID

from gendertagger.models.project import AccessibleProject, ProjectMember
from gendertagger.models.user import ProjectRole


class ProjectScope(StrEnum):
    """Resource type whose owning project an access check resolves."""

    project = "project"
    snapshot = "snapshot"
    run = "run"
    aggregation = "aggregation"
    evaluation = "evaluation"
    export = "export"


class ProjectAccessRepository(Protocol):
    """Resolve resource ownership and persist project memberships without owning the transaction."""

    def get_owning_project_id(self, scope: ProjectScope, resource_id: UUID) -> UUID | None:
        """Return the project that owns one resource, or ``None`` when the resource is absent."""
        ...

    def get_member_role(self, project_id: UUID, user_id: UUID) -> ProjectRole | None:
        """Return a user's membership role in one project, or ``None`` when not a member."""
        ...

    def has_any_membership(self, user_id: UUID) -> bool:
        """Return whether a user is a member of at least one project."""
        ...

    def list_member_projects(
        self,
        user_id: UUID,
        *,
        limit: int,
        after_slug: str | None = None,
    ) -> Sequence[AccessibleProject]:
        """Return one slug-ordered keyset slice of a member's projects with the member's role."""
        ...

    def list_members(self, project_id: UUID) -> Sequence[ProjectMember]:
        """Return a project's members ordered by display name, then user ID."""
        ...

    def set_member_role(self, project_id: UUID, user_id: UUID, role: ProjectRole) -> ProjectMember:
        """Grant or change one user's role in a project.

        Raises:
            ResourceNotFoundError: If the project or the user does not exist.
        """
        ...

    def remove_member(self, project_id: UUID, user_id: UUID) -> bool:
        """Revoke one membership and return whether it existed."""
        ...
