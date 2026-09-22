"""SQLAlchemy repository for project ownership resolution and memberships (ADR-0033)."""

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import Select, delete, exists, select
from sqlalchemy.orm import Session

from gendertagger.db.aggregations import AggregationExecutionRow
from gendertagger.db.evaluations import EvaluationExecutionRow
from gendertagger.db.executions import RunRow
from gendertagger.db.exports import ExportExecutionRow
from gendertagger.db.projects import DatasetSnapshotRow, ProjectRow
from gendertagger.db.reviews import ProjectMembershipRow, UserRow
from gendertagger.models.project import AccessibleProject, ProjectMember
from gendertagger.models.user import ProjectRole
from gendertagger.services.persistence_errors import ResourceNotFoundError
from gendertagger.services.project_access_repository import ProjectScope


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
            select(ProjectRow, ProjectMembershipRow.role)
            .join(ProjectMembershipRow, ProjectMembershipRow.project_id == ProjectRow.id)
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
                created_at=project.created_at,
                working_aggregation_execution_id=project.working_aggregation_execution_id,
                current_user_role=role,
            )
            for project, role in rows
        )

    def list_members(self, project_id: UUID) -> Sequence[ProjectMember]:
        """Return a project's members ordered by display name, then user ID."""
        rows = self._session.execute(
            select(ProjectMembershipRow, UserRow.display_name)
            .join(UserRow, UserRow.id == ProjectMembershipRow.user_id)
            .where(ProjectMembershipRow.project_id == project_id)
            .order_by(UserRow.display_name, UserRow.id)
        )
        return tuple(self._member_from_row(row, display_name) for row, display_name in rows)

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
        return self._member_from_row(row, user.display_name)

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
    def _member_from_row(row: ProjectMembershipRow, display_name: str) -> ProjectMember:
        return ProjectMember(
            project_id=row.project_id,
            user_id=row.user_id,
            display_name=display_name,
            role=row.role,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )
