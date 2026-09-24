"""Application use cases for project-scoped authorization and memberships (ADR-0033)."""

import logging
from collections.abc import Sequence
from uuid import UUID

from gendertagger.models.api import CursorPage
from gendertagger.models.project import (
    AccessibleProject,
    Project,
    ProjectEligibleUser,
    ProjectManagerUpdate,
    ProjectMember,
    ProjectMembershipState,
)
from gendertagger.models.user import CurrentUser, GlobalRole, ProjectRole
from gendertagger.services.pagination import CursorCodec
from gendertagger.services.ports.persistence_errors import ResourceNotFoundError
from gendertagger.services.ports.project_access_repository import (
    EligibleUserCursor,
    ProjectScope,
)
from gendertagger.services.ports.unit_of_work import UnitOfWork, UnitOfWorkFactory

logger = logging.getLogger(__name__)

_PROJECT_LIST_RESOURCE = "projects"



class ProjectManagerConflictError(RuntimeError):
    """Raised when optimistic manager transfer state is stale."""


class ManagerReplacementRequiredError(RuntimeError):
    """Raised when removing an account would leave a project without its manager."""


class TeamMembershipConflictError(RuntimeError):
    """Raised when a valid target loses a concurrent race to direct-team removal."""

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
                        current_user_can_manage_members=True,
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

    def can_manage_members(self, user: CurrentUser, project_id: UUID) -> bool:
        """Return whether a global administrator or assigned manager may administer a roster."""
        with self._unit_of_work_factory() as unit_of_work:
            project = unit_of_work.projects.get_project(project_id)
            if project is None:
                return False
            return GlobalRole.admin in user.roles or project.manager_user_id == user.id

    def list_members(self, project_id: UUID) -> ProjectMembershipState:
        """Return one project's manager assignment and explicit role roster."""
        with self._unit_of_work_factory() as unit_of_work:
            return unit_of_work.access.list_members(project_id)

    def list_eligible_users(
        self,
        project_id: UUID,
        *,
        query: str | None,
        limit: int,
        cursor: str | None,
    ) -> CursorPage[ProjectEligibleUser]:
        """Return an opaque-cursor page of active direct-team-member candidates."""
        if limit <= 0:
            msg = "limit must be positive"
            raise ValueError(msg)
        normalized_query = query.strip() if query is not None and query.strip() else None
        with self._unit_of_work_factory() as unit_of_work:
            project = unit_of_work.projects.get_project(project_id)
            if project is None:
                msg = f"project {project_id} does not exist"
                raise ResourceNotFoundError(msg)
            resource = f"project_eligible_users:{project_id}:{normalized_query or ''}"
            position = (
                self._cursor_codec.decode(cursor, expected_resource=resource)
                if cursor is not None
                else None
            )
            candidates = unit_of_work.access.list_eligible_users(
                project.team.id,
                search=normalized_query,
                limit=limit + 1,
                after=(
                    EligibleUserCursor(
                        normalized_display_name=position.sort_values[0],
                        user_id=position.id,
                    )
                    if position is not None
                    else None
                ),
            )
        has_more = len(candidates) > limit
        items = list(candidates[:limit])
        next_cursor = None
        if has_more:
            last_item = items[-1]
            next_cursor = self._cursor_codec.encode(
                resource=resource,
                sort_values=(last_item.display_name.lower(),),
                resource_id=last_item.id,
            )
        return CursorPage(items=items, next_cursor=next_cursor, has_more=has_more)

    def set_member_role(
        self,
        project_id: UUID,
        user_id: UUID,
        role: ProjectRole,
        *,
        actor_user_id: UUID | None,
    ) -> ProjectMember:
        """Grant or change an eligible direct-team-member's project role."""
        with self._unit_of_work_factory() as unit_of_work:
            before = unit_of_work.projects.get_project(project_id)
            was_eligible = (
                before is not None
                and unit_of_work.teams.get_member(before.team.id, user_id) is not None
            )
            project = self._lock_managed_project(
                unit_of_work,
                project_id=project_id,
                actor_user_id=actor_user_id,
                target_user_id=user_id,
            )
            try:
                self._require_active_team_member(unit_of_work, project.team.id, user_id)
            except ResourceNotFoundError as error:
                if was_eligible:
                    raise TeamMembershipConflictError("the team membership changed") from error
                raise
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
        """Revoke an eligible direct-team-member's explicit project role."""
        with self._unit_of_work_factory() as unit_of_work:
            before = unit_of_work.projects.get_project(project_id)
            was_eligible = (
                before is not None
                and unit_of_work.teams.get_member(before.team.id, user_id) is not None
            )
            project = self._lock_managed_project(
                unit_of_work,
                project_id=project_id,
                actor_user_id=actor_user_id,
                target_user_id=user_id,
            )
            try:
                self._require_active_team_member(unit_of_work, project.team.id, user_id)
            except ResourceNotFoundError as error:
                if was_eligible:
                    raise TeamMembershipConflictError("the team membership changed") from error
                raise
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

    def transfer_manager(
        self,
        project_id: UUID,
        command: ProjectManagerUpdate,
        *,
        actor_user_id: UUID | None,
    ) -> ProjectMembershipState:
        """Transfer manager authority without changing either user's ordinary project role."""
        with self._unit_of_work_factory() as unit_of_work:
            before = unit_of_work.projects.get_project(project_id)
            was_eligible = (
                before is not None
                and unit_of_work.teams.get_member(before.team.id, command.manager_user_id) is not None
            )
            project = self._lock_managed_project(
                unit_of_work,
                project_id=project_id,
                actor_user_id=actor_user_id,
                target_user_id=command.manager_user_id,
            )
            if project.manager_user_id != command.expected_manager_user_id:
                raise ProjectManagerConflictError("the project manager changed")
            try:
                self._require_active_team_member(
                    unit_of_work,
                    project.team.id,
                    command.manager_user_id,
                )
            except ResourceNotFoundError as error:
                if was_eligible:
                    raise TeamMembershipConflictError("the team membership changed") from error
                raise
            unit_of_work.access.set_manager(project_id, command.manager_user_id)
            state = unit_of_work.access.list_members(project_id)
            unit_of_work.commit()
        logger.info(
            "project %s manager transferred to user %s by %s",
            project_id,
            command.manager_user_id,
            _actor(actor_user_id),
        )
        return state

    def _lock_managed_project(
        self,
        unit_of_work: UnitOfWork,
        *,
        project_id: UUID,
        actor_user_id: UUID | None,
        target_user_id: UUID,
    ) -> Project:
        """Lock a roster mutation in user, team, then project order and revalidate authority."""
        lock_user_ids = {target_user_id}
        if actor_user_id is not None:
            lock_user_ids.add(actor_user_id)
        for user_id in sorted(lock_user_ids, key=lambda value: value.bytes):
            unit_of_work.users.lock_membership_updates(user_id)
        actor = (
            unit_of_work.users.get_user_for_update(actor_user_id)
            if actor_user_id is not None
            else None
        )
        if actor_user_id is not None and (actor is None or not actor.is_active):
            msg = f"project {project_id} does not exist"
            raise ResourceNotFoundError(msg)
        project = unit_of_work.projects.get_project(project_id)
        if project is None:
            msg = f"project {project_id} does not exist"
            raise ResourceNotFoundError(msg)
        unit_of_work.teams.lock_team(project.team.id)
        project = unit_of_work.projects.get_project_for_update(project_id)
        if project is None:
            msg = f"project {project_id} does not exist"
            raise ResourceNotFoundError(msg)
        if (
            actor is not None
            and GlobalRole.admin not in actor.roles
            and project.manager_user_id != actor_user_id
        ):
            msg = f"project {project_id} does not exist"
            raise ResourceNotFoundError(msg)
        return project

    @staticmethod
    def _require_active_team_member(unit_of_work: UnitOfWork, team_id: UUID, user_id: UUID) -> None:
        """Require the target to remain an active direct member after serialization locks."""
        target = unit_of_work.users.get_user_for_update(user_id)
        membership = unit_of_work.teams.get_member(team_id, user_id)
        if target is None or not target.is_active or membership is None or not membership.is_active:
            msg = f"user {user_id} does not exist"
            raise ResourceNotFoundError(msg)


def _actor(actor_user_id: UUID | None) -> str:
    return "the CLI" if actor_user_id is None else f"user {actor_user_id}"
