"""Composition point that registers every persistence mapping."""

from sqlalchemy import MetaData

from gendertagger.db.aggregations import (
    AggregatedResultRow,
    AggregationExecutionRow,
    AggregationMethodExecutionRow,
)
from gendertagger.db.artifacts import ArtifactRow
from gendertagger.db.base import Base
from gendertagger.db.dispatches import BatchDispatchRow
from gendertagger.db.evaluations import EvaluationExecutionRow, EvaluationMethodExecutionRow
from gendertagger.db.executions import MethodExecutionRow, PredictionRow, RunRow, TaskBatchRow
from gendertagger.db.exports import ExportExecutionRow
from gendertagger.db.projects import (
    DatasetSnapshotRow,
    PersonExternalIdRow,
    PersonRecordRow,
    ProjectRow,
    SnapshotSourceMemberRow,
)
from gendertagger.db.reviews import AnnotationRow, ReviewStateRow, UserRoleRow, UserRow

ORM_ROW_TYPES: tuple[type[Base], ...] = (
    ProjectRow,
    DatasetSnapshotRow,
    SnapshotSourceMemberRow,
    PersonRecordRow,
    PersonExternalIdRow,
    RunRow,
    MethodExecutionRow,
    TaskBatchRow,
    BatchDispatchRow,
    PredictionRow,
    AggregationExecutionRow,
    AggregationMethodExecutionRow,
    AggregatedResultRow,
    EvaluationExecutionRow,
    EvaluationMethodExecutionRow,
    ExportExecutionRow,
    UserRow,
    UserRoleRow,
    AnnotationRow,
    ReviewStateRow,
    ArtifactRow,
)

metadata: MetaData = Base.metadata
