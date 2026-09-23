"""Persistence-only project, snapshot, and person mappings."""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    BigInteger,
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
    # Forward reference: `projects` is created before `aggregation_executions` in the baseline
    # migration, so this column needs `use_alter=True`, like every other forward FK in
    # db/artifacts.py. The repository enforces that the referenced aggregation belongs to a run
    # of this project's own snapshot and is completed (ADR-0035); the database does not.
    working_aggregation_execution_id: Mapped[UUID | None] = mapped_column(
        POSTGRESQL_UUID(as_uuid=True),
        ForeignKey("aggregation_executions.id", ondelete="RESTRICT", use_alter=True),
    )


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
        CheckConstraint(
            "failure_class IS NULL OR status = 'failed'",
            name="failure_class_requires_failed",
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
    failure_class: Mapped[str | None] = mapped_column(String(255))
    failure_diagnostic: Mapped[str | None] = mapped_column(Text)


class SnapshotSourceMemberRow(UuidPrimaryKeyMixin, CreatedAtMixin, Base):
    """Persistence row for one ordered exact member of a snapshot source."""

    __tablename__ = "snapshot_source_members"
    __table_args__ = (
        UniqueConstraint(
            "dataset_snapshot_id",
            "ordinal",
            name="snapshot_source_member_ordinal",
        ),
        UniqueConstraint(
            "dataset_snapshot_id",
            "logical_name",
            name="snapshot_source_member_logical_name",
        ),
        CheckConstraint("ordinal >= 0", name="ordinal_nonnegative"),
        CheckConstraint("btrim(logical_name) <> ''", name="logical_name_nonblank"),
        CheckConstraint(
            "sha256 ~ '^[0-9a-f]{64}$'",
            name="sha256_format",
        ),
        CheckConstraint("byte_size >= 0", name="byte_size_nonnegative"),
        CheckConstraint("btrim(media_type) <> ''", name="media_type_nonblank"),
    )

    dataset_snapshot_id: Mapped[UUID] = mapped_column(
        POSTGRESQL_UUID(as_uuid=True),
        ForeignKey("dataset_snapshots.id", ondelete="RESTRICT"),
        nullable=False,
    )
    artifact_id: Mapped[UUID] = mapped_column(
        POSTGRESQL_UUID(as_uuid=True),
        ForeignKey("artifacts.id", ondelete="RESTRICT"),
        nullable=False,
    )
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    logical_name: Mapped[str] = mapped_column(String(1024), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    byte_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    media_type: Mapped[str] = mapped_column(String(255), nullable=False)


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
        CheckConstraint(
            "name_forms IS NULL OR jsonb_typeof(name_forms) = 'array'",
            name="name_forms_array",
        ),
        CheckConstraint("jsonb_typeof(events) = 'array'", name="events_array"),
        CheckConstraint("btrim(source_member_name) <> ''", name="source_member_name_nonblank"),
        CheckConstraint(
            "btrim(source_record_locator) <> ''",
            name="source_record_locator_nonblank",
        ),
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
    events: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default=text("'[]'::jsonb"),
    )
    alt_names: Mapped[list[str]] = mapped_column(
        ARRAY(Text),
        nullable=False,
        default=list,
        server_default=text("'{}'::text[]"),
    )
    name_forms: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB(none_as_null=True))
    source_member_name: Mapped[str] = mapped_column(String(1024), nullable=False)
    source_record_locator: Mapped[str] = mapped_column(Text, nullable=False)


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
