"""SQLAlchemy repository for project ownership resolution and memberships (ADR-0033)."""

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import Select, delete, exists, func, select
from sqlalchemy.orm import Session

from gendertagger.db.rows.aggregations import AggregationExecutionRow
from gendertagger.db.rows.evaluations import EvaluationExecutionRow
from gendertagger.db.rows.executions import RunRow
from gendertagger.db.rows.exports import ExportExecutionRow
from gendertagger.db.rows.projects import DatasetSnapshotRow, ProjectRow
from gendertagger.db.rows.teams import TeamMembershipRow, TeamRow
from gendertagger.db.rows.users import ProjectMembershipRow, UserRow
from gendertagger.models.project import (
    AccessibleProject,
    ManagedProjectSummary,
    ProjectEligibleUser,
    ProjectManager,
    ProjectMember,
    ProjectMembershipState,
)
from gendertagger.models.team import TeamSummary
from gendertagger.models.user import ProjectRole
from gendertagger.services.ports.persistence_errors import ResourceNotFoundError
from gendertagger.services.ports.project_access_repository import (
    EligibleUserCursor,
    ProjectScope,
)


def _owning_project_statement(scope: ProjectScope, resource_id: UUID) -> Select[tuple[UUID]]:
    """Build the single-path ownership query for one resource type."""
    if scope is ProjectScope.project:
        return select(ProjectRow.id).where(ProjectRow.id == resource_id)
    if scope is ProjectScope.snapshot:
        return select(DatasetSnapshotRow.project_id).where(DatasetSnapshotRow.id == resource_id)
    through_run = select(DatasetSnapshotRow.project_id).join(
        RunRow, RunRow.dataset_snapshot_id == DatasetSnapshotRow.id
    )
    if scope is ProjectScope.run:
        return through_run.where(RunRow.id == resource_id)
    if scope is ProjectScope.aggregation:
        return through_run.join(
            AggregationExecutionRow, AggregationExecutionRow.run_id == RunRow.id
        ).where(AggregationExecutionRow.id == resource_id)
    if scope is ProjectScope.evaluation:
        return through_run.join(
            EvaluationExecutionRow, EvaluationExecutionRow.run_id == RunRow.id
        ).where(EvaluationExecutionRow.id == resource_id)
    return through_run.join(ExportExecutionRow, ExportExecutionRow.run_id == RunRow.id).where(
        ExportExecutionRow.id == resource_id
    )


class SqlAlchemyProjectAccessRepository:
    """Map ownership and membership queries to rows within a caller-owned session."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get_owning_project_id(self, scope: ProjectScope, resource_id: UUID) -> UUID | None:
        """Return the project that owns one resource, or ``None`` when the resource is absent."""
        return self._session.scalar(_owning_project_statement(scope, resource_id))

    def get_member_role(self, project_id: UUID, user_id: UUID) -> ProjectRole | None:
        """Return a user's membership role in one project, or ``None`` when not a member."""
        return self._session.scalar(
            select(ProjectMembershipRow.role).where(
                ProjectMembershipRow.project_id == project_id,
                ProjectMembershipRow.user_id == user_id,
            )
        )

    def has_any_membership(self, user_id: UUID) -> bool:
        """Return whether a user is a member of at least one project."""
        return bool(
            self._session.scalar(select(exists().where(ProjectMembershipRow.user_id == user_id)))
        )

    def list_member_projects(
        self,
        user_id: UUID,
        *,
        limit: int,
        after_slug: str | None = None,
    ) -> Sequence[AccessibleProject]:
        """Return a member's projects in unique-slug order with the member's role."""
        if limit <= 0:
            msg = "limit must be positive"
            raise ValueError(msg)
        statement = (
            select(ProjectRow, ProjectMembershipRow.role, TeamRow)
            .join(ProjectMembershipRow, ProjectMembershipRow.project_id == ProjectRow.id)
            .join(TeamRow, TeamRow.id == ProjectRow.team_id)
            .where(ProjectMembershipRow.user_id == user_id)
        )
        if after_slug is not None:
            statement = statement.where(ProjectRow.slug > after_slug)
        rows = self._session.execute(statement.order_by(ProjectRow.slug).limit(limit))
        return tuple(
            AccessibleProject(
                id=project.id,
                slug=project.slug,
                display_name=project.display_name,
                description=project.description,
                team=_team_from_row(team),
                manager_user_id=project.manager_user_id,
                created_by_user_id=project.created_by_user_id,
                created_at=project.created_at,
                working_aggregation_execution_id=project.working_aggregation_execution_id,
                current_user_role=role,
                current_user_can_manage_members=project.manager_user_id == user_id,
            )
            for project, role, team in rows
        )

    def list_managed_projects(
        self,
        user_id: UUID,
        *,
        limit: int,
        after_slug: str | None = None,
    ) -> Sequence[ManagedProjectSummary]:
        """Return one manager's non-scientific project identities in unique-slug order."""
        if limit <= 0:
            msg = "limit must be positive"
            raise ValueError(msg)
        statement = (
            select(ProjectRow, TeamRow)
            .join(TeamRow, TeamRow.id == ProjectRow.team_id)
            .where(ProjectRow.manager_user_id == user_id)
        )
        if after_slug is not None:
            statement = statement.where(ProjectRow.slug > after_slug)
        rows = self._session.execute(statement.order_by(ProjectRow.slug).limit(limit))
        return tuple(
            ManagedProjectSummary(
                id=project.id,
                slug=project.slug,
                display_name=project.display_name,
                team=_team_from_row(team),
            )
            for project, team in rows
        )

    def list_members(self, project_id: UUID) -> ProjectMembershipState:
        """Return a project's manager assignment and members ordered by display name."""
        manager = self._session.execute(
            select(ProjectRow.manager_user_id, UserRow.display_name, ProjectMembershipRow.role)
            .join(UserRow, UserRow.id == ProjectRow.manager_user_id)
            .outerjoin(
                ProjectMembershipRow,
                (ProjectMembershipRow.project_id == ProjectRow.id)
                & (ProjectMembershipRow.user_id == ProjectRow.manager_user_id),
            )
            .where(ProjectRow.id == project_id)
        ).one_or_none()
        if manager is None:
            msg = f"project {project_id} does not exist"
            raise ResourceNotFoundError(msg)
        rows = self._session.execute(
            select(ProjectMembershipRow, UserRow.display_name)
            .join(UserRow, UserRow.id == ProjectMembershipRow.user_id)
            .where(ProjectMembershipRow.project_id == project_id)
            .order_by(UserRow.display_name, UserRow.id)
        )
        manager_user_id, manager_display_name, manager_role = manager
        return ProjectMembershipState(
            manager=ProjectManager(
                user_id=manager_user_id,
                display_name=manager_display_name,
                project_role=manager_role,
            ),
            members=[
                self._member_from_row(
                    row,
                    display_name,
                    is_manager=row.user_id == manager_user_id,
                )
                for row, display_name in rows
            ],
        )

    def is_manager(self, project_id: UUID, user_id: UUID) -> bool:
        """Return whether a user is currently assigned as one project's manager."""
        return bool(
            self._session.scalar(
                select(ProjectRow.id).where(
                    ProjectRow.id == project_id, ProjectRow.manager_user_id == user_id
                )
            )
        )

    def list_eligible_users(
        self,
        team_id: UUID,
        *,
        search: str | None,
        limit: int,
        after: EligibleUserCursor | None,
    ) -> Sequence[ProjectEligibleUser]:
        """Return active direct-team-member candidates in a stable keyset order."""
        normalized_display_name = func.lower(UserRow.display_name)
        statement = (
            select(UserRow.id, UserRow.display_name)
            .join(TeamMembershipRow, TeamMembershipRow.user_id == UserRow.id)
            .where(TeamMembershipRow.team_id == team_id, UserRow.is_active.is_(True))
        )
        if search is not None:
            statement = statement.where(UserRow.display_name.icontains(search, autoescape=True))
        if after is not None:
            statement = statement.where(
                (normalized_display_name > after.normalized_display_name)
                | (
                    (normalized_display_name == after.normalized_display_name)
                    & (UserRow.id > after.user_id)
                )
            )
        rows = self._session.execute(
            statement.order_by(normalized_display_name, UserRow.id).limit(limit)
        )
        return tuple(
            ProjectEligibleUser(id=user_id, display_name=display_name)
            for user_id, display_name in rows
        )

    def set_manager(self, project_id: UUID, user_id: UUID) -> None:
        """Replace one project's manager assignment and flush without committing."""
        row = self._session.get(ProjectRow, project_id, with_for_update=True)
        if row is None:
            msg = f"project {project_id} does not exist"
            raise ResourceNotFoundError(msg)
        row.manager_user_id = user_id
        self._session.flush()

    def list_managed_project_ids(self, team_id: UUID, user_id: UUID) -> Sequence[UUID]:
        """Return managed projects deterministically for one team member."""
        return tuple(
            self._session.scalars(
                select(ProjectRow.id)
                .where(ProjectRow.team_id == team_id, ProjectRow.manager_user_id == user_id)
                .order_by(ProjectRow.id)
            )
        )

    def remove_team_member_project_memberships(self, team_id: UUID, user_id: UUID) -> None:
        """Remove the user's explicit memberships in every project owned by one team."""
        self._session.execute(
            delete(ProjectMembershipRow).where(
                ProjectMembershipRow.user_id == user_id,
                ProjectMembershipRow.project_id.in_(
                    select(ProjectRow.id).where(ProjectRow.team_id == team_id)
                ),
            )
        )
        self._session.flush()

    def set_member_role(self, project_id: UUID, user_id: UUID, role: ProjectRole) -> ProjectMember:
        """Grant or change one user's role in a project and flush without committing."""
        if self._session.get(ProjectRow, project_id) is None:
            msg = f"project {project_id} does not exist"
            raise ResourceNotFoundError(msg)
        user = self._session.get(UserRow, user_id)
        if user is None:
            msg = f"user {user_id} does not exist"
            raise ResourceNotFoundError(msg)
        row = self._session.get(ProjectMembershipRow, (project_id, user_id))
        if row is None:
            row = ProjectMembershipRow(project_id=project_id, user_id=user_id, role=role)
            self._session.add(row)
        else:
            row.role = role
        self._session.flush()
        self._session.refresh(row)
        manager_user_id = self._session.scalar(
            select(ProjectRow.manager_user_id).where(ProjectRow.id == project_id)
        )
        return self._member_from_row(
            row, user.display_name, is_manager=row.user_id == manager_user_id
        )

    def remove_member(self, project_id: UUID, user_id: UUID) -> bool:
        """Revoke one membership, flush without committing, and return whether it existed."""
        result = self._session.execute(
            delete(ProjectMembershipRow)
            .where(
                ProjectMembershipRow.project_id == project_id,
                ProjectMembershipRow.user_id == user_id,
            )
            .returning(ProjectMembershipRow.user_id)
        )
        return result.first() is not None

    @staticmethod
    def _member_from_row(
        row: ProjectMembershipRow,
        display_name: str,
        *,
        is_manager: bool,
    ) -> ProjectMember:
        return ProjectMember(
            project_id=row.project_id,
            user_id=row.user_id,
            display_name=display_name,
            role=row.role,
            is_manager=is_manager,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )


def _team_from_row(row: TeamRow) -> TeamSummary:
    """Map a team row into the roster-free project response representation."""
    return TeamSummary(
        id=row.id,
        slug=row.slug,
        display_name=row.display_name,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )
