"""Application repository contract for teams and direct memberships (ADR-0041 slice 1)."""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from gendertagger.models.team import TeamCreate, TeamMember, TeamSummary


@dataclass(frozen=True, slots=True)
class TeamCursor:
    """Keyset position for slug-ordered team summaries."""

    slug: str
    team_id: UUID


@dataclass(frozen=True, slots=True)
class TeamMemberCursor:
    """Keyset position for normalized-display-name-ordered team members."""

    normalized_display_name: str
    user_id: UUID


class TeamRepository(Protocol):
    """Persist team contracts within the caller-owned transaction."""

    def lock_team(self, team_id: UUID) -> None:
        """Serialize mutations whose validity depends on one team's roster."""
        ...

    def add_team(self, command: TeamCreate) -> TeamSummary:
        """Persist and flush a new team without committing."""
        ...

    def get_team(self, team_id: UUID) -> TeamSummary | None:
        """Return one team summary, or ``None`` when absent."""
        ...

    def get_team_by_slug(self, slug: str) -> TeamSummary | None:
        """Return one team by canonical slug, or ``None`` when absent."""
        ...

    def get_team_for_update(self, team_id: UUID) -> TeamSummary | None:
        """Return one team summary under a write lock, or ``None`` when absent."""
        ...

    def update_team_display_name(self, team_id: UUID, display_name: str) -> TeamSummary:
        """Update one team's display name and flush without committing."""
        ...

    def delete_team(self, team_id: UUID) -> None:
        """Delete one locked empty team and flush without committing."""
        ...

    def has_members(self, team_id: UUID) -> bool:
        """Return whether one team has any direct members."""
        ...

    def list_teams(
        self,
        *,
        search: str | None,
        limit: int,
        after: TeamCursor | None,
    ) -> Sequence[TeamSummary]:
        """Return one filtered slug-ordered keyset slice of every team."""
        ...

    def list_member_teams(
        self,
        user_id: UUID,
        *,
        search: str | None,
        limit: int,
        after: TeamCursor | None,
    ) -> Sequence[TeamSummary]:
        """Return one filtered slug-ordered keyset slice of a user's direct teams."""
        ...

    def list_members(
        self,
        team_id: UUID,
        *,
        search: str | None,
        limit: int,
        after: TeamMemberCursor | None,
    ) -> Sequence[TeamMember]:
        """Return one filtered display-name-ordered roster slice for one team."""
        ...

    def get_member(self, team_id: UUID, user_id: UUID) -> TeamMember | None:
        """Return one direct membership, or ``None`` when absent."""
        ...

    def add_member(self, team_id: UUID, user_id: UUID) -> TeamMember:
        """Persist and flush one direct membership without committing."""
        ...

    def remove_member(self, team_id: UUID, user_id: UUID) -> bool:
        """Remove one direct membership and return whether it existed."""
        ...
