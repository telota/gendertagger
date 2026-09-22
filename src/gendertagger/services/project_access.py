"""Application use cases for project-scoped authorization and memberships (ADR-0033)."""

import logging
from collections.abc import Sequence
from uuid import UUID

from gendertagger.models.api import CursorPage
from gendertagger.models.project import AccessibleProject, ProjectMember
from gendertagger.models.user import CurrentUser, GlobalRole, ProjectRole
from gendertagger.services.pagination import CursorCodec
from gendertagger.services.persistence_errors import ResourceNotFoundError
from gendertagger.services.project_access_repository import ProjectScope
from gendertagger.services.unit_of_work import UnitOfWorkFactory

logger = logging.getLogger(__name__)

_PROJECT_LIST_RESOURCE = "projects"


class ProjectAccessService:
    """Resolve a caller's effective project role and administer project memberships.

    A global ``admin`` holds ``operator`` in every project. Any other caller holds exactly its
    membership role, or none; a global ``operator`` grants no project access by itself.
    """

    def __init__(
        self,
        *,
        unit_of_work_factory: UnitOfWorkFactory,
        cursor_codec: CursorCodec,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._cursor_codec = cursor_codec

    def effective_role(
        self,
        user: CurrentUser,
        scope: ProjectScope,
        resource_id: UUID,
    ) -> ProjectRole | None:
        """Return the caller's role in the project that owns one resource.

        Args:
            user: The authenticated caller.
            scope: The resource type ``resource_id`` identifies.
            resource_id: The resource whose owning project is resolved.

        Returns:
            The caller's effective role, or ``None`` when the resource does not exist or the caller
            has no role in its project. The two cases are deliberately indistinguishable.
        """
        with self._unit_of_work_factory() as unit_of_work:
            project_id = unit_of_work.access.get_owning_project_id(scope, resource_id)
            if project_id is None:
                return None
            if GlobalRole.admin in user.roles:
                return ProjectRole.operator
            return unit_of_work.access.get_member_role(project_id, user.id)

    def has_any_grant(self, user: CurrentUser) -> bool:
        """Return whether the caller holds any global role or any project membership."""
        if user.roles:
            return True
        with self._unit_of_work_factory() as unit_of_work:
            return unit_of_work.access.has_any_membership(user.id)

    def list_projects(
        self,
        user: CurrentUser,
        *,
        limit: int,
        cursor: str | None,
    ) -> CursorPage[AccessibleProject]:
        """Return one slug-ordered opaque-cursor page of the projects the caller can access."""
        if limit <= 0:
            msg = "limit must be positive"
            raise ValueError(msg)
        position = (
            self._cursor_codec.decode(cursor, expected_resource=_PROJECT_LIST_RESOURCE)
            if cursor is not None
            else None
        )
        after_slug = position.sort_values[0] if position is not None else None
        with self._unit_of_work_factory() as unit_of_work:
            if GlobalRole.admin in user.roles:
                projects: Sequence[AccessibleProject] = tuple(
                    AccessibleProject(
                        **project.model_dump(),
                        current_user_role=ProjectRole.operator,
                    )
                    for project in unit_of_work.projects.list_projects(
                        limit=limit + 1,
                        after_slug=after_slug,
                    )
                )
            else:
                projects = unit_of_work.access.list_member_projects(
                    user.id,
                    limit=limit + 1,
                    after_slug=after_slug,
                )
        has_more = len(projects) > limit
        items = list(projects[:limit])
        next_cursor = None
        if has_more:
            last_item = items[-1]
            next_cursor = self._cursor_codec.encode(
                resource=_PROJECT_LIST_RESOURCE,
                sort_values=(last_item.slug,),
                resource_id=last_item.id,
            )
        return CursorPage(items=items, next_cursor=next_cursor, has_more=has_more)

    def list_members(self, project_id: UUID) -> Sequence[ProjectMember]:
        """Return one project's members, or raise a not-found failure for an unknown project."""
        with self._unit_of_work_factory() as unit_of_work:
            if unit_of_work.projects.get_project(project_id) is None:
                msg = f"project {project_id} does not exist"
                raise ResourceNotFoundError(msg)
            return unit_of_work.access.list_members(project_id)

    def set_member_role(
        self,
        project_id: UUID,
        user_id: UUID,
        role: ProjectRole,
        *,
        actor_user_id: UUID | None,
    ) -> ProjectMember:
        """Grant or change one user's project role and commit it.

        Args:
            project_id: The project the role applies to.
            user_id: The member.
            role: The member's new role.
            actor_user_id: The administrator making the change, or ``None`` for the CLI.

        Returns:
            The persisted membership.

        Raises:
            ResourceNotFoundError: If the project or the user does not exist.
        """
        with self._unit_of_work_factory() as unit_of_work:
            member = unit_of_work.access.set_member_role(project_id, user_id, role)
            unit_of_work.commit()
        logger.info(
            "project %s membership of user %s set to %s by %s",
            project_id,
            user_id,
            role.value,
            _actor(actor_user_id),
        )
        return member

    def remove_member(
        self,
        project_id: UUID,
        user_id: UUID,
        *,
        actor_user_id: UUID | None,
    ) -> None:
        """Revoke one membership and commit it, or raise a not-found failure if absent."""
        with self._unit_of_work_factory() as unit_of_work:
            if not unit_of_work.access.remove_member(project_id, user_id):
                msg = f"user {user_id} is not a member of project {project_id}"
                raise ResourceNotFoundError(msg)
            unit_of_work.commit()
        logger.info(
            "project %s membership of user %s revoked by %s",
            project_id,
            user_id,
            _actor(actor_user_id),
        )


def _actor(actor_user_id: UUID | None) -> str:
    return "the CLI" if actor_user_id is None else f"user {actor_user_id}"
