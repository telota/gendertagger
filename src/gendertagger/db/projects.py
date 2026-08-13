"""Persistence-only project, snapshot, and person mappings."""

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
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.dialects.postgresql import UUID as POSTGRESQL_UUID
from sqlalchemy.orm import Mapped, mapped_column

from gendertagger.db.base import (
    Base,
    CreatedAtMixin,
    UuidPrimaryKeyMixin,
    enum_check,
    stored_enum,
)
from gendertagger.models.lifecycle import DatasetSnapshotStatus


class ProjectRow(UuidPrimaryKeyMixin, CreatedAtMixin, Base):
    """Persistence row for a long-lived editorial project."""

    __tablename__ = "projects"
    __table_args__ = (
        CheckConstraint(
            "slug ~ '^[a-z][a-z0-9]*(-[a-z0-9]+)*$'",
            name="slug_format",
        ),
    )

    slug: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)


class DatasetSnapshotRow(UuidPrimaryKeyMixin, CreatedAtMixin, Base):
    """Persistence row for one imported, immutable-when-ready dataset snapshot."""

    __tablename__ = "dataset_snapshots"
    __table_args__ = (
        enum_check("status", DatasetSnapshotStatus, name="status_allowed"),
        CheckConstraint(
            "source_sha256 ~ '^[0-9a-f]{64}$'",
            name="source_sha256_format",
        ),
        CheckConstraint(
            "record_count IS NULL OR record_count >= 0",
            name="record_count_nonnegative",
        ),
        CheckConstraint(
            "status <> 'ready' OR (record_count IS NOT NULL AND ready_at IS NOT NULL)",
            name="ready_metadata_present",
        ),
        Index("ix_dataset_snapshots_project_id_created_at", "project_id", "created_at"),
    )

    project_id: Mapped[UUID] = mapped_column(
        POSTGRESQL_UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="RESTRICT"),
        nullable=False,
    )
    source_artifact_id: Mapped[UUID] = mapped_column(
        POSTGRESQL_UUID(as_uuid=True),
        ForeignKey("artifacts.id", ondelete="RESTRICT", use_alter=True),
        nullable=False,
    )
    status: Mapped[DatasetSnapshotStatus] = mapped_column(
        stored_enum(DatasetSnapshotStatus, name="dataset_snapshot_status"),
        nullable=False,
        default=DatasetSnapshotStatus.pending,
        server_default=DatasetSnapshotStatus.pending.value,
    )
    source_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    parser_version: Mapped[str] = mapped_column(String(100), nullable=False)
    import_config: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    record_count: Mapped[int | None] = mapped_column(Integer)
    ready_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failure_diagnostic: Mapped[str | None] = mapped_column(Text)


class PersonRecordRow(UuidPrimaryKeyMixin, CreatedAtMixin, Base):
    """Persistence row for one TEI person occurrence in a snapshot."""

    __tablename__ = "person_records"
    __table_args__ = (
        UniqueConstraint(
            "dataset_snapshot_id",
            "tei_id",
            name="snapshot_tei_id",
        ),
        UniqueConstraint(
            "id",
            "dataset_snapshot_id",
            name="id_snapshot",
        ),
        CheckConstraint("btrim(tei_id) <> ''", name="tei_id_nonblank"),
        Index("ix_person_records_dataset_snapshot_id_surname", "dataset_snapshot_id", "surname"),
    )

    dataset_snapshot_id: Mapped[UUID] = mapped_column(
        POSTGRESQL_UUID(as_uuid=True),
        ForeignKey("dataset_snapshots.id", ondelete="RESTRICT"),
        nullable=False,
    )
    tei_id: Mapped[str] = mapped_column(Text, nullable=False)
    surname: Mapped[str | None] = mapped_column(Text)
    forenames: Mapped[list[str]] = mapped_column(
        ARRAY(Text),
        nullable=False,
        default=list,
        server_default=text("'{}'::text[]"),
    )
    birth: Mapped[str | None] = mapped_column(Text)
    death: Mapped[str | None] = mapped_column(Text)
    note: Mapped[str | None] = mapped_column(Text)
    alt_names: Mapped[list[str]] = mapped_column(
        ARRAY(Text),
        nullable=False,
        default=list,
        server_default=text("'{}'::text[]"),
    )


class PersonExternalIdRow(UuidPrimaryKeyMixin, CreatedAtMixin, Base):
    """Persistence row for one source-preserved external person identifier."""

    __tablename__ = "person_external_ids"
    __table_args__ = (
        UniqueConstraint("person_record_id", "scheme", name="person_scheme"),
        CheckConstraint(
            "scheme ~ '^[a-z][a-z0-9]*(_[a-z0-9]+)*$'",
            name="scheme_format",
        ),
        CheckConstraint("btrim(value) <> ''", name="value_nonblank"),
        Index("ix_person_external_ids_scheme_value", "scheme", "value"),
    )

    person_record_id: Mapped[UUID] = mapped_column(
        POSTGRESQL_UUID(as_uuid=True),
        ForeignKey("person_records.id", ondelete="RESTRICT"),
        nullable=False,
    )
    scheme: Mapped[str] = mapped_column(String(100), nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)
