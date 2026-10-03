"""Persistence-only anonymous classification job mapping."""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, Index, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as POSTGRESQL_UUID
from sqlalchemy.orm import Mapped, mapped_column

from gendertagger.db.base import Base, CreatedAtMixin, UuidPrimaryKeyMixin, enum_check, stored_enum
from gendertagger.models.public_classification import PublicClassificationStatus


class PublicClassificationJobRow(UuidPrimaryKeyMixin, CreatedAtMixin, Base):
    """Durable job inputs, provenance, worker lease, and terminal response."""

    __tablename__ = "public_classification_jobs"
    __table_args__ = (
        enum_check("status", PublicClassificationStatus, name="status_allowed"),
        CheckConstraint(
            "retrieval_token_sha256 ~ '^[0-9a-f]{64}$'",
            name="retrieval_token_sha256_format",
        ),
        CheckConstraint(
            "queue_name ~ '^[a-z][a-z0-9]*(_[a-z0-9]+)*$'",
            name="queue_name_format",
        ),
        CheckConstraint(
            "(status = 'running' AND lease_id IS NOT NULL AND lease_until IS NOT NULL) OR "
            "(status <> 'running' AND lease_id IS NULL AND lease_until IS NULL)",
            name="lease_consistent",
        ),
        CheckConstraint(
            "(status = 'queued' AND started_at IS NULL AND completed_at IS NULL) OR "
            "(status = 'running' AND started_at IS NOT NULL AND completed_at IS NULL) OR "
            "(status IN ('completed', 'failed') AND started_at IS NOT NULL "
            "AND completed_at IS NOT NULL)",
            name="timestamps_consistent",
        ),
        CheckConstraint(
            "(status = 'completed' AND response IS NOT NULL AND raw_predictions IS NOT NULL "
            "AND failure_code IS NULL) OR "
            "(status = 'failed' AND response IS NULL AND raw_predictions IS NULL "
            "AND failure_code = 'classification_failed') OR "
            "(status IN ('queued', 'running') AND response IS NULL AND raw_predictions IS NULL "
            "AND failure_code IS NULL)",
            name="result_consistent",
        ),
        Index("ix_public_classification_jobs_status_created_at", "status", "created_at"),
        Index("ix_public_classification_jobs_status_lease_until", "status", "lease_until"),
    )

    retrieval_token_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    queue_name: Mapped[str] = mapped_column(
        String(100), nullable=False, default="cpu", server_default="cpu"
    )
    names: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    methods: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    resolved_method_configs: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    provenance: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    status: Mapped[PublicClassificationStatus] = mapped_column(
        stored_enum(PublicClassificationStatus, name="public_classification_status"),
        nullable=False,
        default=PublicClassificationStatus.queued,
        server_default=PublicClassificationStatus.queued.value,
    )
    response: Mapped[dict[str, Any] | None] = mapped_column(JSONB(none_as_null=True))
    raw_predictions: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB(none_as_null=True))
    failure_code: Mapped[str | None] = mapped_column(String(64))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease_id: Mapped[UUID | None] = mapped_column(POSTGRESQL_UUID(as_uuid=True))
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
