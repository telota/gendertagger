"""SQLAlchemy repository for teams and direct memberships (ADR-0041 slice 1)."""

import hashlib
from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import Select, and_, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from gendertagger.db.rows.teams import TeamMembershipRow, TeamRow
from gendertagger.db.rows.users import UserRow
from gendertagger.models.team import TeamCreate, TeamMember, TeamSummary
from gendertagger.services.ports.persistence_errors import DuplicateTeamSlugError
from gendertagger.services.ports.team_repository import TeamCursor, TeamMemberCursor

_TEAM_SLUG_UNIQUE_CONSTRAINT = "uq_teams_slug"


class SqlAlchemyTeamRepository:
    """Map team contracts to rows within a caller-owned SQLAlchemy session."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def lock_team(self, team_id: UUID) -> None:
        """Acquire a transaction-scoped advisory lock for one team UUID."""
        self._session.execute(select(func.pg_advisory_xact_lock(_team_lock_key(team_id))))

    def add_team(self, command: TeamCreate) -> TeamSummary:
        """Persist and flush a new team without committing."""
        row = TeamRow(slug=command.slug, display_name=command.display_name)
        self._session.add(row)
        try:
            self._session.flush()
        except IntegrityError as error:
            constraint_name = getattr(getattr(error.orig, "diag", None), "constraint_name", None)
            if constraint_name == _TEAM_SLUG_UNIQUE_CONSTRAINT:
                raise DuplicateTeamSlugError(command.slug) from error
            raise
        return _team_from_row(row)

    def get_team(self, team_id: UUID) -> TeamSummary | None:
        """Return one team summary, or ``None`` when absent."""
        row = self._session.get(TeamRow, team_id)
        return None if row is None else _team_from_row(row)

    def get_team_by_slug(self, slug: str) -> TeamSummary | None:
        """Return one team by canonical slug, or ``None`` when absent."""
        row = self._session.scalar(select(TeamRow).where(TeamRow.slug == slug))
        return None if row is None else _team_from_row(row)

    def get_team_for_update(self, team_id: UUID) -> TeamSummary | None:
        """Return one team summary under a write lock, or ``None`` when absent."""
        row = self._session.get(TeamRow, team_id, with_for_update=True)
        return None if row is None else _team_from_row(row)

    def update_team_display_name(self, team_id: UUID, display_name: str) -> TeamSummary:
        """Update one team's display name and flush without committing."""
        row = self._session.get(TeamRow, team_id, with_for_update=True)
        if row is None:
            msg = f"team {team_id} does not exist"
            raise LookupError(msg)
        row.display_name = display_name
        self._session.flush()
        return _team_from_row(row)

    def delete_team(self, team_id: UUID) -> None:
        """Delete one locked empty team and flush without committing."""
        row = self._session.get(TeamRow, team_id, with_for_update=True)
        if row is None:
            msg = f"team {team_id} does not exist"
            raise LookupError(msg)
        self._session.delete(row)
        self._session.flush()

    def has_members(self, team_id: UUID) -> bool:
        """Return whether one team has any direct members."""
        return (
            self._session.scalar(
                select(TeamMembershipRow.team_id)
                .where(TeamMembershipRow.team_id == team_id)
                .limit(1)
            )
            is not None
        )

    def list_teams(
        self,
        *,
        search: str | None,
        limit: int,
        after: TeamCursor | None,
    ) -> Sequence[TeamSummary]:
        """Return one filtered slug-ordered keyset slice of every team."""
        statement = select(TeamRow)
        statement = _filter_teams(statement, search)
        statement = _after_team(statement, after)
        rows = self._session.scalars(
            statement.order_by(TeamRow.slug, TeamRow.id).limit(limit)
        ).all()
        return tuple(_team_from_row(row) for row in rows)

    def list_member_teams(
        self,
        user_id: UUID,
        *,
        search: str | None,
        limit: int,
        after: TeamCursor | None,
    ) -> Sequence[TeamSummary]:
        """Return one filtered slug-ordered keyset slice of a user's direct teams."""
        statement = select(TeamRow).join(
            TeamMembershipRow,
            TeamMembershipRow.team_id == TeamRow.id,
        )
        statement = statement.where(TeamMembershipRow.user_id == user_id)
        statement = _filter_teams(statement, search)
        statement = _after_team(statement, after)
        rows = self._session.scalars(
            statement.order_by(TeamRow.slug, TeamRow.id).limit(limit)
        ).all()
        return tuple(_team_from_row(row) for row in rows)

    def list_members(
        self,
        team_id: UUID,
        *,
        search: str | None,
        limit: int,
        after: TeamMemberCursor | None,
    ) -> Sequence[TeamMember]:
        """Return one filtered display-name-ordered roster slice for one team."""
        normalized_display_name = func.lower(UserRow.display_name)
        statement = (
            select(TeamMembershipRow, UserRow)
            .join(UserRow, UserRow.id == TeamMembershipRow.user_id)
            .where(TeamMembershipRow.team_id == team_id)
        )
        if search is not None:
            statement = statement.where(UserRow.display_name.icontains(search, autoescape=True))
        if after is not None:
            statement = statement.where(
                or_(
                    normalized_display_name > after.normalized_display_name,
                    and_(
                        normalized_display_name == after.normalized_display_name,
                        UserRow.id > after.user_id,
                    ),
                )
            )
        rows = self._session.execute(
            statement.order_by(normalized_display_name, UserRow.id).limit(limit)
        ).all()
        return tuple(_member_from_rows(membership, user) for membership, user in rows)

    def get_member(self, team_id: UUID, user_id: UUID) -> TeamMember | None:
        """Return one direct membership, or ``None`` when absent."""
        row = self._session.execute(
            select(TeamMembershipRow, UserRow)
            .join(UserRow, UserRow.id == TeamMembershipRow.user_id)
            .where(
                TeamMembershipRow.team_id == team_id,
                TeamMembershipRow.user_id == user_id,
            )
        ).one_or_none()
        return None if row is None else _member_from_rows(*row)

    def add_member(self, team_id: UUID, user_id: UUID) -> TeamMember:
        """Persist and flush one direct membership without committing."""
        membership = TeamMembershipRow(team_id=team_id, user_id=user_id)
        self._session.add(membership)
        self._session.flush()
        user = self._session.get(UserRow, user_id)
        if user is None:
            msg = f"user {user_id} does not exist"
            raise LookupError(msg)
        return _member_from_rows(membership, user)

    def remove_member(self, team_id: UUID, user_id: UUID) -> bool:
        """Remove one direct membership and report whether it existed."""
        membership = self._session.get(TeamMembershipRow, (team_id, user_id))
        if membership is None:
            return False
        self._session.delete(membership)
        self._session.flush()
        return True


def _filter_teams(statement: Select[tuple[TeamRow]], search: str | None) -> Select[tuple[TeamRow]]:
    """Apply the canonical team search filter to a selectable statement."""
    if search is None:
        return statement
    return statement.where(
        or_(
            TeamRow.slug.icontains(search, autoescape=True),
            TeamRow.display_name.icontains(search, autoescape=True),
        )
    )


def _after_team(
    statement: Select[tuple[TeamRow]], after: TeamCursor | None
) -> Select[tuple[TeamRow]]:
    """Apply one slug-and-UUID keyset continuation predicate."""
    if after is None:
        return statement
    return statement.where(
        or_(
            TeamRow.slug > after.slug,
            and_(TeamRow.slug == after.slug, TeamRow.id > after.team_id),
        )
    )


def _team_lock_key(team_id: UUID) -> int:
    """Derive a stable signed PostgreSQL advisory-lock key from one team UUID."""
    digest = hashlib.blake2b(team_id.bytes, digest_size=8, person=b"gendertagger").digest()
    return int.from_bytes(digest, byteorder="big", signed=True)


def _team_from_row(row: TeamRow) -> TeamSummary:
    """Map one persistence row into its canonical team summary."""
    return TeamSummary(
        id=row.id,
        slug=row.slug,
        display_name=row.display_name,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _member_from_rows(membership: TeamMembershipRow, user: UserRow) -> TeamMember:
    """Map joined membership and user rows into one canonical roster record."""
    return TeamMember(
        team_id=membership.team_id,
        user_id=membership.user_id,
        display_name=user.display_name,
        is_active=user.is_active,
        created_at=membership.created_at,
    )
