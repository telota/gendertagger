"""Team and direct-roster application services (ADR-0041 slice 1)."""

import hashlib
import logging
from collections.abc import Callable, Sequence
from typing import TypeVar, cast
from uuid import UUID

from gendertagger.models.api import CursorPage
from gendertagger.models.team import (
    TeamCreate,
    TeamMember,
    TeamMemberAdd,
    TeamSummary,
    TeamUpdate,
    normalize_team_slug,
)
from gendertagger.models.user import CurrentUser, GlobalRole
from gendertagger.services.pagination import CursorCodec, CursorPosition, InvalidCursorError
from gendertagger.services.ports.persistence_errors import ResourceNotFoundError
from gendertagger.services.ports.team_repository import TeamCursor, TeamMemberCursor
from gendertagger.services.ports.unit_of_work import UnitOfWorkFactory
from gendertagger.services.project_access import ManagerReplacementRequiredError

logger = logging.getLogger(__name__)


class TeamNotEmptyError(RuntimeError):
    """Raised when a requested team deletion would orphan direct memberships."""


class TeamInUseError(RuntimeError):
    """Raised when a team still owns one or more projects."""


class InactiveUserError(RuntimeError):
    """Raised when a roster-add command targets a currently inactive account."""


class TeamService:
    """Administer direct teams without granting project access (ADR-0041 slice 1)."""

    def __init__(
        self,
        *,
        unit_of_work_factory: UnitOfWorkFactory,
        cursor_codec: CursorCodec,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._cursor_codec = cursor_codec

    def list_visible_teams(
        self,
        user: CurrentUser,
        *,
        query: str | None,
        limit: int,
        cursor: str | None,
    ) -> CursorPage[TeamSummary]:
        """Return a caller-scoped page of direct teams, or every team for an administrator."""
        if GlobalRole.admin in user.roles:
            return self._list_teams(
                search=query,
                limit=limit,
                cursor=cursor,
                resource_scope="visible:admin",
                user_id=None,
            )
        return self._list_teams(
            search=query,
            limit=limit,
            cursor=cursor,
            resource_scope=f"visible:direct:{user.id}",
            user_id=user.id,
        )

    def list_admin_teams(
        self,
        *,
        query: str | None,
        limit: int,
        cursor: str | None,
    ) -> CursorPage[TeamSummary]:
        """Return one global-administrator page of all teams."""
        return self._list_teams(
            search=query,
            limit=limit,
            cursor=cursor,
            resource_scope="admin",
            user_id=None,
        )

    def create_team(
        self,
        command: TeamCreate,
        *,
        actor_user_id: UUID | None,
        request_id: str | None,
    ) -> TeamSummary:
        """Create one team and commit it as an administrator or CLI mutation."""
        with self._unit_of_work_factory() as unit_of_work:
            team = unit_of_work.teams.add_team(command)
            unit_of_work.commit()
        logger.info(
            "team %s created by %s (request %s; slug=%s display_name=%s)",
            team.id,
            _actor(actor_user_id),
            _request(request_id),
            team.slug,
            team.display_name,
        )
        return team

    def update_team(
        self,
        team_id: UUID,
        command: TeamUpdate,
        *,
        actor_user_id: UUID | None,
        request_id: str | None,
    ) -> TeamSummary:
        """Apply a display-name-only team patch under the team's serialization lock."""
        with self._unit_of_work_factory() as unit_of_work:
            unit_of_work.teams.lock_team(team_id)
            team = unit_of_work.teams.get_team_for_update(team_id)
            if team is None:
                msg = f"team {team_id} does not exist"
                raise ResourceNotFoundError(msg)
            if "display_name" not in command.model_fields_set:
                return team
            display_name = cast(str, command.display_name)
            if display_name == team.display_name:
                return team
            updated = unit_of_work.teams.update_team_display_name(team_id, display_name)
            unit_of_work.commit()
        logger.info(
            "team %s updated by %s (request %s; fields=display_name)",
            team_id,
            _actor(actor_user_id),
            _request(request_id),
        )
        return updated

    def delete_team(
        self,
        team_id: UUID,
        *,
        actor_user_id: UUID | None,
        request_id: str | None,
    ) -> None:
        """Delete an empty team after serializing concurrent roster writes."""
        with self._unit_of_work_factory() as unit_of_work:
            unit_of_work.teams.lock_team(team_id)
            if unit_of_work.teams.get_team_for_update(team_id) is None:
                msg = f"team {team_id} does not exist"
                raise ResourceNotFoundError(msg)
            if unit_of_work.teams.has_members(team_id):
                raise TeamNotEmptyError("a team with direct members cannot be deleted")
            if unit_of_work.teams.has_projects(team_id):
                raise TeamInUseError("a team with assigned projects cannot be deleted")
            unit_of_work.teams.delete_team(team_id)
            unit_of_work.commit()
        logger.info(
            "team %s deleted by %s (request %s)",
            team_id,
            _actor(actor_user_id),
            _request(request_id),
        )

    def list_members(
        self,
        team_id: UUID,
        *,
        query: str | None,
        limit: int,
        cursor: str | None,
    ) -> CursorPage[TeamMember]:
        """Return one roster page after verifying the enclosing team exists."""
        if limit <= 0:
            msg = "limit must be positive"
            raise ValueError(msg)
        search = _normalize_query(query)
        resource = _collection_resource(f"members:{team_id}", search)
        position = (
            self._cursor_codec.decode(cursor, expected_resource=resource)
            if cursor is not None
            else None
        )
        after = (
            TeamMemberCursor(
                normalized_display_name=position.sort_values[0],
                user_id=position.id,
            )
            if position is not None
            else None
        )
        with self._unit_of_work_factory() as unit_of_work:
            if unit_of_work.teams.get_team(team_id) is None:
                msg = f"team {team_id} does not exist"
                raise ResourceNotFoundError(msg)
            members = unit_of_work.teams.list_members(
                team_id,
                search=search,
                limit=limit + 1,
                after=after,
            )
        return _page(
            self._cursor_codec,
            members,
            limit=limit,
            item_id=lambda member: member.user_id,
            resource=resource,
            sort_value=lambda member: member.display_name.lower(),
        )

    def add_member(
        self,
        team_id: UUID,
        command: TeamMemberAdd,
        *,
        actor_user_id: UUID | None,
        request_id: str | None,
    ) -> tuple[TeamMember, bool]:
        """Add one active account to a team, returning the membership and whether it was new."""
        with self._unit_of_work_factory() as unit_of_work:
            unit_of_work.users.lock_membership_updates(command.user_id)
            unit_of_work.teams.lock_team(team_id)
            if unit_of_work.teams.get_team_for_update(team_id) is None:
                msg = f"team {team_id} does not exist"
                raise ResourceNotFoundError(msg)
            target = unit_of_work.users.get_user_for_update(command.user_id)
            if target is None:
                msg = f"user {command.user_id} does not exist"
                raise ResourceNotFoundError(msg)
            if not target.is_active:
                raise InactiveUserError("an inactive account cannot be added to a team")
            existing = unit_of_work.teams.get_member(team_id, command.user_id)
            if existing is not None:
                return existing, False
            member = unit_of_work.teams.add_member(team_id, command.user_id)
            unit_of_work.commit()
        logger.info(
            "team %s membership of user %s added by %s (request %s)",
            team_id,
            command.user_id,
            _actor(actor_user_id),
            _request(request_id),
        )
        return member, True

    def remove_member(
        self,
        team_id: UUID,
        user_id: UUID,
        *,
        actor_user_id: UUID | None,
        request_id: str | None,
    ) -> None:
        """Remove team membership and all derived project roles atomically."""
        with self._unit_of_work_factory() as unit_of_work:
            unit_of_work.users.lock_membership_updates(user_id)
            unit_of_work.teams.lock_team(team_id)
            if unit_of_work.teams.get_team_for_update(team_id) is None:
                msg = f"team {team_id} does not exist"
                raise ResourceNotFoundError(msg)
            if unit_of_work.users.get_user_for_update(user_id) is None:
                msg = f"user {user_id} does not exist"
                raise ResourceNotFoundError(msg)
            managed_project_ids = unit_of_work.access.list_managed_project_ids(team_id, user_id)
            for project_id in managed_project_ids:
                unit_of_work.projects.get_project_for_update(project_id)
            if managed_project_ids:
                raise ManagerReplacementRequiredError(
                    "a manager must be replaced before removing team membership"
                )
            if not unit_of_work.teams.get_member(team_id, user_id):
                msg = f"user {user_id} is not a member of team {team_id}"
                raise ResourceNotFoundError(msg)
            unit_of_work.access.remove_team_member_project_memberships(team_id, user_id)
            unit_of_work.teams.remove_member(team_id, user_id)
            unit_of_work.commit()
        logger.info(
            "team %s membership of user %s removed by %s (request %s)",
            team_id,
            user_id,
            _actor(actor_user_id),
            _request(request_id),
        )

    def get_team_by_slug(self, slug: str) -> TeamSummary | None:
        """Resolve a canonical team slug for the administrative CLI."""
        with self._unit_of_work_factory() as unit_of_work:
            return unit_of_work.teams.get_team_by_slug(normalize_team_slug(slug))

    def _list_teams(
        self,
        *,
        search: str | None,
        limit: int,
        cursor: str | None,
        resource_scope: str,
        user_id: UUID | None,
    ) -> CursorPage[TeamSummary]:
        """Load one cursor page from the selected administrator or direct-member scope."""
        if limit <= 0:
            msg = "limit must be positive"
            raise ValueError(msg)
        normalized_search = _normalize_query(search)
        resource = _collection_resource(resource_scope, normalized_search)
        position = (
            self._cursor_codec.decode(cursor, expected_resource=resource)
            if cursor is not None
            else None
        )
        after = _team_after(position) if position is not None else None
        with self._unit_of_work_factory() as unit_of_work:
            teams = (
                unit_of_work.teams.list_teams(
                    search=normalized_search,
                    limit=limit + 1,
                    after=after,
                )
                if user_id is None
                else unit_of_work.teams.list_member_teams(
                    user_id,
                    search=normalized_search,
                    limit=limit + 1,
                    after=after,
                )
            )
        return _page(
            self._cursor_codec,
            teams,
            limit=limit,
            resource=resource,
            sort_value=lambda team: team.slug,
            item_id=lambda team: team.id,
        )


ItemT = TypeVar("ItemT", TeamSummary, TeamMember)


def _page(
    cursor_codec: CursorCodec,
    items: Sequence[ItemT],
    *,
    limit: int,
    resource: str,
    sort_value: Callable[[ItemT], str],
    item_id: Callable[[ItemT], UUID],
) -> CursorPage[ItemT]:
    """Build a cursor page from a repository's ``limit + 1`` keyset result."""
    has_more = len(items) > limit
    page_items = list(items[:limit])
    next_cursor = None
    if has_more:
        last_item = page_items[-1]
        next_cursor = cursor_codec.encode(
            resource=resource,
            sort_values=(sort_value(last_item),),
            resource_id=item_id(last_item),
        )
    return CursorPage(items=page_items, next_cursor=next_cursor, has_more=has_more)


def _team_after(position: CursorPosition) -> TeamCursor:
    """Validate a decoded team cursor position before using it in a SQL keyset predicate."""
    try:
        return TeamCursor(slug=normalize_team_slug(position.sort_values[0]), team_id=position.id)
    except (IndexError, ValueError) as error:
        raise InvalidCursorError("cursor team slug is invalid") from error


def _normalize_query(query: str | None) -> str | None:
    """Normalize an optional collection-search value without changing blank-query semantics."""
    if query is None:
        return None
    normalized = query.strip().casefold()
    return normalized or None


def _collection_resource(scope: str, search: str | None) -> str:
    """Bind an opaque cursor to its complete authorization scope and normalized filter."""
    search_sha256 = hashlib.sha256((search or "").encode("utf-8")).hexdigest()
    return f"teams:{scope}:{search_sha256}"


def _actor(actor_user_id: UUID | None) -> str:
    """Render a safe operator identity for an operational log message."""
    return "cli" if actor_user_id is None else f"user {actor_user_id}"


def _request(request_id: str | None) -> str:
    """Render an optional HTTP request identifier without inventing one for CLI work."""
    return "none" if request_id is None else request_id
