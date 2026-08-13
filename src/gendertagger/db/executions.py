"""Persistence-only run, method execution, batch, and prediction mappings."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import JsonValue
from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as POSTGRESQL_UUID
from sqlalchemy.orm import Mapped, mapped_column

from gendertagger.db.base import (
    Base,
    CreatedAtMixin,
    UuidPrimaryKeyMixin,
    enum_check,
    stored_enum,
)
from gendertagger.models.classification import CanonicalLabel, PredictionStatus
from gendertagger.models.lifecycle import MethodExecutionStatus, RunStatus, TaskBatchStatus


class RunRow(UuidPrimaryKeyMixin, CreatedAtMixin, Base):
    """Persistence row for a reproducible run over one exact snapshot."""

    __tablename__ = "runs"
    __table_args__ = (
        enum_check("status", RunStatus, name="status_allowed"),
        CheckConstraint(
            "config_sha256 ~ '^[0-9a-f]{64}$'",
            name="config_sha256_format",
        ),
        CheckConstraint(
            "dependency_lock_sha256 IS NULL OR dependency_lock_sha256 ~ '^[0-9a-f]{64}$'",
            name="dependency_lock_sha256_format",
        ),
        CheckConstraint(
            "finished_at IS NULL OR started_at IS NOT NULL",
            name="run_timing_order_present",
        ),
        Index("ix_runs_dataset_snapshot_id_created_at", "dataset_snapshot_id", "created_at"),
        Index("ix_runs_status_created_at", "status", "created_at"),
    )

    dataset_snapshot_id: Mapped[UUID] = mapped_column(
        POSTGRESQL_UUID(as_uuid=True),
        ForeignKey("dataset_snapshots.id", ondelete="RESTRICT"),
        nullable=False,
    )
    status: Mapped[RunStatus] = mapped_column(
        stored_enum(RunStatus, name="run_status"),
        nullable=False,
        default=RunStatus.created,
        server_default=RunStatus.created.value,
    )
    resolved_config: Mapped[dict[str, JsonValue]] = mapped_column(JSONB, nullable=False)
    config_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    code_git_commit: Mapped[str] = mapped_column(String(100), nullable=False)
    application_version: Mapped[str] = mapped_column(String(100), nullable=False)
    container_image_digest: Mapped[str | None] = mapped_column(Text)
    python_version: Mapped[str] = mapped_column(String(100), nullable=False)
    dependency_lock_sha256: Mapped[str | None] = mapped_column(String(64))
    dependency_lock_artifact_id: Mapped[UUID | None] = mapped_column(
        POSTGRESQL_UUID(as_uuid=True),
        ForeignKey("artifacts.id", ondelete="RESTRICT", use_alter=True),
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failure_diagnostic: Mapped[str | None] = mapped_column(Text)


class MethodExecutionRow(UuidPrimaryKeyMixin, CreatedAtMixin, Base):
    """Persistence row for one versioned method execution within a run."""

    __tablename__ = "method_executions"
    __table_args__ = (
        enum_check("status", MethodExecutionStatus, name="status_allowed"),
        UniqueConstraint("run_id", "method_name", name="run_method_name"),
        CheckConstraint(
            "method_name ~ '^[a-z][a-z0-9]*(_[a-z0-9]+)*$'",
            name="method_name_format",
        ),
        CheckConstraint(
            "config_sha256 ~ '^[0-9a-f]{64}$'",
            name="config_sha256_format",
        ),
        CheckConstraint(
            "model_checksum IS NULL OR model_checksum ~ '^[0-9a-f]{64}$'",
            name="model_checksum_format",
        ),
        CheckConstraint("total_count IS NULL OR total_count >= 0", name="total_count_nonnegative"),
        CheckConstraint("completed_count >= 0", name="completed_count_nonnegative"),
        CheckConstraint("failed_count >= 0", name="failed_count_nonnegative"),
        CheckConstraint(
            "total_count IS NULL OR completed_count + failed_count <= total_count",
            name="progress_within_total",
        ),
        CheckConstraint(
            "finished_at IS NULL OR started_at IS NOT NULL",
            name="execution_timing_order_present",
        ),
        Index("ix_method_executions_run_id_status", "run_id", "status"),
    )

    run_id: Mapped[UUID] = mapped_column(
        POSTGRESQL_UUID(as_uuid=True),
        ForeignKey("runs.id", ondelete="RESTRICT"),
        nullable=False,
    )
    method_name: Mapped[str] = mapped_column(String(100), nullable=False)
    implementation_version: Mapped[str] = mapped_column(String(100), nullable=False)
    normalization_version: Mapped[str] = mapped_column(String(100), nullable=False)
    resolved_config: Mapped[dict[str, JsonValue]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    config_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[MethodExecutionStatus] = mapped_column(
        stored_enum(MethodExecutionStatus, name="method_execution_status"),
        nullable=False,
        default=MethodExecutionStatus.pending,
        server_default=MethodExecutionStatus.pending.value,
    )
    queue_name: Mapped[str] = mapped_column(String(100), nullable=False)
    model_identifier: Mapped[str | None] = mapped_column(Text)
    model_revision: Mapped[str | None] = mapped_column(Text)
    model_checksum: Mapped[str | None] = mapped_column(String(64))
    model_artifact_id: Mapped[UUID | None] = mapped_column(
        POSTGRESQL_UUID(as_uuid=True),
        ForeignKey("artifacts.id", ondelete="RESTRICT", use_alter=True),
    )
    data_artifact_id: Mapped[UUID | None] = mapped_column(
        POSTGRESQL_UUID(as_uuid=True),
        ForeignKey("artifacts.id", ondelete="RESTRICT", use_alter=True),
    )
    prompt_version: Mapped[str | None] = mapped_column(String(100))
    schema_version: Mapped[str | None] = mapped_column(String(100))
    worker_metadata: Mapped[dict[str, JsonValue]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    total_count: Mapped[int | None] = mapped_column(Integer)
    completed_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    failed_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failure_class: Mapped[str | None] = mapped_column(String(255))
    failure_diagnostic: Mapped[str | None] = mapped_column(Text)


class TaskBatchRow(UuidPrimaryKeyMixin, CreatedAtMixin, Base):
    """Persistence row for one retryable bounded execution batch."""

    __tablename__ = "task_batches"
    __table_args__ = (
        enum_check("status", TaskBatchStatus, name="status_allowed"),
        UniqueConstraint("method_execution_id", "batch_index", name="execution_batch_index"),
        CheckConstraint("batch_index >= 0", name="batch_index_nonnegative"),
        CheckConstraint("attempt_count >= 0", name="attempt_count_nonnegative"),
        CheckConstraint("success_count >= 0", name="success_count_nonnegative"),
        CheckConstraint("abstain_count >= 0", name="abstain_count_nonnegative"),
        CheckConstraint("error_count >= 0", name="error_count_nonnegative"),
        CheckConstraint("record_offset >= 0", name="record_offset_nonnegative"),
        CheckConstraint("record_count > 0", name="record_count_positive"),
        CheckConstraint(
            "finished_at IS NULL OR started_at IS NOT NULL",
            name="batch_timing_order_present",
        ),
        Index("ix_task_batches_method_execution_id_status", "method_execution_id", "status"),
    )

    method_execution_id: Mapped[UUID] = mapped_column(
        POSTGRESQL_UUID(as_uuid=True),
        ForeignKey("method_executions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    batch_index: Mapped[int] = mapped_column(Integer, nullable=False)
    record_offset: Mapped[int] = mapped_column(Integer, nullable=False)
    record_count: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[TaskBatchStatus] = mapped_column(
        stored_enum(TaskBatchStatus, name="task_batch_status"),
        nullable=False,
        default=TaskBatchStatus.pending,
        server_default=TaskBatchStatus.pending.value,
    )
    queue_name: Mapped[str] = mapped_column(String(100), nullable=False)
    worker_task_id: Mapped[str | None] = mapped_column(String(255))
    attempt_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    success_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    abstain_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    error_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failure_class: Mapped[str | None] = mapped_column(String(255))
    failure_diagnostic: Mapped[str | None] = mapped_column(Text)


class PredictionRow(UuidPrimaryKeyMixin, CreatedAtMixin, Base):
    """Immutable persistence row for one method output on one person."""

    __tablename__ = "predictions"
    __table_args__ = (
        enum_check("label", CanonicalLabel, name="label_allowed"),
        enum_check("status", PredictionStatus, name="status_allowed"),
        UniqueConstraint(
            "method_execution_id",
            "person_record_id",
            name="execution_person",
        ),
        CheckConstraint(
            "(status = 'success' AND label IS NOT NULL) OR "
            "(status IN ('abstain', 'error') AND label IS NULL)",
            name="status_label_consistent",
        ),
        CheckConstraint(
            "method_confidence IS NULL OR method_confidence::text "
            "NOT IN ('NaN', 'Infinity', '-Infinity')",
            name="method_confidence_finite",
        ),
        CheckConstraint(
            "input_fingerprint ~ '^[0-9a-f]{64}$'",
            name="input_fingerprint_format",
        ),
        Index("ix_predictions_person_record_id_status", "person_record_id", "status"),
        Index("ix_predictions_method_execution_id_status", "method_execution_id", "status"),
    )

    method_execution_id: Mapped[UUID] = mapped_column(
        POSTGRESQL_UUID(as_uuid=True),
        ForeignKey("method_executions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    person_record_id: Mapped[UUID] = mapped_column(
        POSTGRESQL_UUID(as_uuid=True),
        ForeignKey("person_records.id", ondelete="RESTRICT"),
        nullable=False,
    )
    task_batch_id: Mapped[UUID | None] = mapped_column(
        POSTGRESQL_UUID(as_uuid=True),
        ForeignKey("task_batches.id", ondelete="RESTRICT"),
    )
    label: Mapped[CanonicalLabel | None] = mapped_column(
        stored_enum(CanonicalLabel, name="canonical_label"),
    )
    status: Mapped[PredictionStatus] = mapped_column(
        stored_enum(PredictionStatus, name="prediction_status"),
        nullable=False,
    )
    method_confidence: Mapped[float | None] = mapped_column(Float)
    raw_label: Mapped[str | None] = mapped_column(Text)
    raw_output: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    prediction_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    input_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
