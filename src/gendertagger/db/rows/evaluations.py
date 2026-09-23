"""Persistence-only evaluation execution mappings."""

from datetime import datetime
from uuid import UUID

from pydantic import JsonValue
from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    PrimaryKeyConstraint,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as POSTGRESQL_UUID
from sqlalchemy.orm import Mapped, mapped_column

from gendertagger.db.base import Base, CreatedAtMixin, UuidPrimaryKeyMixin, enum_check, stored_enum
from gendertagger.models.lifecycle import EvaluationExecutionStatus


class EvaluationExecutionRow(UuidPrimaryKeyMixin, CreatedAtMixin, Base):
    """Persistence row for one versioned evaluation over explicit method executions."""

    __tablename__ = "evaluation_executions"
    __table_args__ = (
        enum_check("status", EvaluationExecutionStatus, name="status_allowed"),
        CheckConstraint(
            "definition ~ '^[a-z][a-z0-9]*(_[a-z0-9]+)*$'",
            name="definition_format",
        ),
        CheckConstraint(
            "config_sha256 ~ '^[0-9a-f]{64}$'",
            name="config_sha256_format",
        ),
        CheckConstraint(
            "finished_at IS NULL OR started_at IS NOT NULL",
            name="evaluation_timing_order_present",
        ),
        CheckConstraint(
            "status <> 'completed' OR report_artifact_id IS NOT NULL",
            name="completed_evaluation_has_report",
        ),
        CheckConstraint(
            "status = 'completed' OR report_artifact_id IS NULL",
            name="only_completed_evaluation_has_report",
        ),
        Index("ix_evaluation_executions_run_id_status", "run_id", "status"),
    )

    run_id: Mapped[UUID] = mapped_column(
        POSTGRESQL_UUID(as_uuid=True),
        ForeignKey("runs.id", ondelete="RESTRICT"),
        nullable=False,
    )
    aggregation_execution_id: Mapped[UUID | None] = mapped_column(
        POSTGRESQL_UUID(as_uuid=True),
        ForeignKey("aggregation_executions.id", ondelete="RESTRICT"),
    )
    definition: Mapped[str] = mapped_column(String(100), nullable=False)
    resolved_config: Mapped[dict[str, JsonValue]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    config_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[EvaluationExecutionStatus] = mapped_column(
        stored_enum(EvaluationExecutionStatus, name="evaluation_execution_status"),
        nullable=False,
        default=EvaluationExecutionStatus.pending,
        server_default=EvaluationExecutionStatus.pending.value,
    )
    report_artifact_id: Mapped[UUID | None] = mapped_column(
        POSTGRESQL_UUID(as_uuid=True),
        ForeignKey("artifacts.id", ondelete="RESTRICT", use_alter=True),
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failure_class: Mapped[str | None] = mapped_column(String(255))
    failure_diagnostic: Mapped[str | None] = mapped_column(Text)


class EvaluationMethodExecutionRow(Base):
    """Exact ordered method-execution membership for an evaluation."""

    __tablename__ = "evaluation_method_executions"
    __table_args__ = (
        PrimaryKeyConstraint(
            "evaluation_execution_id",
            "method_execution_id",
            name="pk_evaluation_method_executions",
        ),
        UniqueConstraint(
            "evaluation_execution_id",
            "position",
            name="evaluation_position",
        ),
        CheckConstraint("position >= 0", name="position_nonnegative"),
    )

    evaluation_execution_id: Mapped[UUID] = mapped_column(
        POSTGRESQL_UUID(as_uuid=True),
        ForeignKey("evaluation_executions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    method_execution_id: Mapped[UUID] = mapped_column(
        POSTGRESQL_UUID(as_uuid=True),
        ForeignKey("method_executions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
