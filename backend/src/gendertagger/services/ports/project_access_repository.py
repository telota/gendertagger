"""Application repository contract for project ownership and memberships (ADR-0033)."""

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol
from uuid import UUID

from gendertagger.models.project import (
    AccessibleProject,
    ProjectEligibleUser,
    ProjectMember,
    ProjectMembershipState,
)
from gendertagger.models.user import ProjectRole


@dataclass(frozen=True, slots=True)
class EligibleUserCursor:
    """Keyset position for project-team eligibility candidates."""

    normalized_display_name: str
    user_id: UUID


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

    def list_members(self, project_id: UUID) -> ProjectMembershipState:
        """Return a project's manager assignment and explicit member roster."""
        ...

    def is_manager(self, project_id: UUID, user_id: UUID) -> bool:
        """Return whether a user is currently assigned as one project's manager."""
        ...

    def list_eligible_users(
        self,
        team_id: UUID,
        *,
        search: str | None,
        limit: int,
        after: EligibleUserCursor | None,
    ) -> Sequence[ProjectEligibleUser]:
        """Return one active direct-team-member candidate slice."""
        ...

    def set_manager(self, project_id: UUID, user_id: UUID) -> None:
        """Replace one project's manager assignment and flush without committing."""
        ...

    def list_managed_project_ids(self, team_id: UUID, user_id: UUID) -> Sequence[UUID]:
        """Return the sorted projects in a team currently managed by one user."""
        ...

    def remove_team_member_project_memberships(self, team_id: UUID, user_id: UUID) -> None:
        """Remove every explicit project role the user holds in a team's projects."""
        ...

    def set_member_role(self, project_id: UUID, user_id: UUID, role: ProjectRole) -> ProjectMember:
        """Grant or change one eligible user's role in a project.

        Raises:
            ResourceNotFoundError: If the project or the user does not exist.
        """
        ...

    def remove_member(self, project_id: UUID, user_id: UUID) -> bool:
        """Revoke one membership and return whether it existed."""
        ...
