"""Composition point that registers every persistence mapping."""

from sqlalchemy import MetaData

from gendertagger.db.base import Base
from gendertagger.db.rows.aggregations import (
    AggregatedResultRow,
    AggregationExecutionRow,
    AggregationMethodExecutionRow,
)
from gendertagger.db.rows.artifacts import ArtifactRow
from gendertagger.db.rows.auth import UserCredentialRow, UserSessionRow
from gendertagger.db.rows.dispatches import DispatchOutboxRow
from gendertagger.db.rows.evaluations import EvaluationExecutionRow, EvaluationMethodExecutionRow
from gendertagger.db.rows.executions import MethodExecutionRow, PredictionRow, RunRow, TaskBatchRow
from gendertagger.db.rows.exports import ExportExecutionRow
from gendertagger.db.rows.projects import (
    DatasetSnapshotRow,
    PersonExternalIdRow,
    PersonRecordRow,
    ProjectRow,
    SnapshotSourceMemberRow,
)
from gendertagger.db.rows.reviews import AnnotationRow, ReviewStateRow
from gendertagger.db.rows.settings import DeploymentSettingsRow
from gendertagger.db.rows.teams import TeamMembershipRow, TeamRow
from gendertagger.db.rows.user_preferences import UserPreferencesRow
from gendertagger.db.rows.users import ProjectMembershipRow, UserRoleRow, UserRow

ORM_ROW_TYPES: tuple[type[Base], ...] = (
    ProjectRow,
    DatasetSnapshotRow,
    SnapshotSourceMemberRow,
    PersonRecordRow,
    PersonExternalIdRow,
    RunRow,
    MethodExecutionRow,
    TaskBatchRow,
    DispatchOutboxRow,
    PredictionRow,
    AggregationExecutionRow,
    AggregationMethodExecutionRow,
    AggregatedResultRow,
    EvaluationExecutionRow,
    EvaluationMethodExecutionRow,
    ExportExecutionRow,
    UserRow,
    UserRoleRow,
    ProjectMembershipRow,
    UserCredentialRow,
    TeamRow,
    TeamMembershipRow,
    UserSessionRow,
    UserPreferencesRow,
    AnnotationRow,
    ReviewStateRow,
    ArtifactRow,
    DeploymentSettingsRow,
)

metadata: MetaData = Base.metadata
