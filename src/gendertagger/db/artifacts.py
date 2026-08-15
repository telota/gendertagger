"""Persistence-only checksummed artifact mapping."""

from typing import Any
from uuid import UUID

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, Index, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as POSTGRESQL_UUID
from sqlalchemy.orm import Mapped, mapped_column

from gendertagger.db.base import Base, CreatedAtMixin, UuidPrimaryKeyMixin


class ArtifactRow(UuidPrimaryKeyMixin, CreatedAtMixin, Base):
    """Immutable metadata reference to bytes held outside PostgreSQL."""

    __tablename__ = "artifacts"
    __table_args__ = (
        CheckConstraint(
            "logical_type ~ '^[a-z][a-z0-9]*(_[a-z0-9]+)*$'",
            name="logical_type_format",
        ),
        CheckConstraint(
            "sha256 ~ '^[0-9a-f]{64}$'",
            name="sha256_format",
        ),
        CheckConstraint("byte_size >= 0", name="byte_size_nonnegative"),
        CheckConstraint("btrim(storage_uri) <> ''", name="storage_uri_nonblank"),
        CheckConstraint("btrim(media_type) <> ''", name="media_type_nonblank"),
        Index("ix_artifacts_sha256", "sha256"),
        Index(
            "ix_artifacts_dataset_snapshot_id_logical_type", "dataset_snapshot_id", "logical_type"
        ),
        Index("ix_artifacts_run_id_logical_type", "run_id", "logical_type"),
    )

    logical_type: Mapped[str] = mapped_column(String(100), nullable=False)
    storage_uri: Mapped[str] = mapped_column(Text, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    byte_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    media_type: Mapped[str] = mapped_column(String(255), nullable=False)
    project_id: Mapped[UUID | None] = mapped_column(
        POSTGRESQL_UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="RESTRICT", use_alter=True),
    )
    dataset_snapshot_id: Mapped[UUID | None] = mapped_column(
        POSTGRESQL_UUID(as_uuid=True),
        ForeignKey("dataset_snapshots.id", ondelete="RESTRICT", use_alter=True),
    )
    run_id: Mapped[UUID | None] = mapped_column(
        POSTGRESQL_UUID(as_uuid=True),
        ForeignKey("runs.id", ondelete="RESTRICT", use_alter=True),
    )
    method_execution_id: Mapped[UUID | None] = mapped_column(
        POSTGRESQL_UUID(as_uuid=True),
        ForeignKey("method_executions.id", ondelete="RESTRICT", use_alter=True),
    )
    aggregation_execution_id: Mapped[UUID | None] = mapped_column(
        POSTGRESQL_UUID(as_uuid=True),
        ForeignKey("aggregation_executions.id", ondelete="RESTRICT", use_alter=True),
    )
    evaluation_execution_id: Mapped[UUID | None] = mapped_column(
        POSTGRESQL_UUID(as_uuid=True),
        ForeignKey("evaluation_executions.id", ondelete="RESTRICT", use_alter=True),
    )
    export_id: Mapped[UUID | None] = mapped_column(
        POSTGRESQL_UUID(as_uuid=True),
        ForeignKey("export_executions.id", ondelete="RESTRICT", use_alter=True),
    )
    artifact_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
