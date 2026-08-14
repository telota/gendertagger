"""Persistence-only durable task-dispatch mapping."""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as POSTGRESQL_UUID
from sqlalchemy.orm import Mapped, mapped_column

from gendertagger.db.base import (
    Base,
    CreatedAtMixin,
    UpdatedAtMixin,
    UuidPrimaryKeyMixin,
    enum_check,
    stored_enum,
)
from gendertagger.models.dispatch import BatchDispatchStatus


class BatchDispatchRow(UuidPrimaryKeyMixin, CreatedAtMixin, UpdatedAtMixin, Base):
    """Mutable outbox delivery state for one unique application-work target."""

    __tablename__ = "batch_dispatches"
    __table_args__ = (
        enum_check("status", BatchDispatchStatus, name="status_allowed"),
        UniqueConstraint("task_batch_id", name="task_batch_single_dispatch"),
        UniqueConstraint(
            "aggregation_execution_id",
            name="aggregation_execution_single_dispatch",
        ),
        CheckConstraint(
            "(task_batch_id IS NOT NULL) <> (aggregation_execution_id IS NOT NULL)",
            name="exactly_one_target",
        ),
        CheckConstraint(
            "queue_name ~ '^[a-z][a-z0-9]*(_[a-z0-9]+)*$'",
            name="queue_name_format",
        ),
        CheckConstraint("attempt_count >= 0", name="attempt_count_nonnegative"),
        CheckConstraint(
            "(lease_owner IS NULL AND lease_until IS NULL) OR "
            "(status = 'pending' AND lease_owner IS NOT NULL AND lease_until IS NOT NULL)",
            name="lease_consistent",
        ),
        CheckConstraint(
            "lease_owner IS NULL OR btrim(lease_owner) <> ''",
            name="lease_owner_nonblank",
        ),
        CheckConstraint(
            "(status = 'pending' AND published_at IS NULL) OR "
            "(status = 'published' AND published_at IS NOT NULL)",
            name="publication_consistent",
        ),
        Index("ix_batch_dispatches_status_available_at", "status", "available_at"),
        Index("ix_batch_dispatches_status_published_at", "status", "published_at"),
    )

    task_batch_id: Mapped[UUID | None] = mapped_column(
        POSTGRESQL_UUID(as_uuid=True),
        ForeignKey("task_batches.id", ondelete="RESTRICT"),
    )
    aggregation_execution_id: Mapped[UUID | None] = mapped_column(
        POSTGRESQL_UUID(as_uuid=True),
        ForeignKey("aggregation_executions.id", ondelete="RESTRICT"),
    )
    queue_name: Mapped[str] = mapped_column(String(100), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    status: Mapped[BatchDispatchStatus] = mapped_column(
        stored_enum(BatchDispatchStatus, name="batch_dispatch_status"),
        nullable=False,
        default=BatchDispatchStatus.pending,
        server_default=BatchDispatchStatus.pending.value,
    )
    attempt_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    lease_owner: Mapped[str | None] = mapped_column(String(255))
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
