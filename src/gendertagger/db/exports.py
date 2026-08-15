"""Persistence-only export execution mapping."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID as POSTGRESQL_UUID
from sqlalchemy.orm import Mapped, mapped_column

from gendertagger.db.base import Base, CreatedAtMixin, UuidPrimaryKeyMixin, enum_check, stored_enum
from gendertagger.models.export import ExportFormat, LabelSourcePolicy, TeiExportProfile
from gendertagger.models.lifecycle import ExportExecutionStatus


class ExportExecutionRow(UuidPrimaryKeyMixin, CreatedAtMixin, Base):
    """Persistence row for one versioned export over one completed aggregation."""

    __tablename__ = "export_executions"
    __table_args__ = (
        enum_check("status", ExportExecutionStatus, name="status_allowed"),
        enum_check("format", ExportFormat, name="format_allowed"),
        enum_check("label_source_policy", LabelSourcePolicy, name="label_source_policy_allowed"),
        CheckConstraint(
            "tei_profile IS NULL OR format = 'tei'",
            name="tei_profile_requires_tei_format",
        ),
        CheckConstraint(
            "format <> 'tei' OR tei_profile IS NOT NULL",
            name="tei_format_requires_tei_profile",
        ),
        CheckConstraint(
            "finished_at IS NULL OR started_at IS NOT NULL",
            name="export_timing_order_present",
        ),
        CheckConstraint(
            "status <> 'completed' OR manifest_artifact_id IS NOT NULL",
            name="completed_export_has_manifest",
        ),
        CheckConstraint(
            "status = 'completed' OR manifest_artifact_id IS NULL",
            name="only_completed_export_has_manifest",
        ),
        Index("ix_export_executions_run_id_status", "run_id", "status"),
    )

    run_id: Mapped[UUID] = mapped_column(
        POSTGRESQL_UUID(as_uuid=True),
        ForeignKey("runs.id", ondelete="RESTRICT"),
        nullable=False,
    )
    aggregation_execution_id: Mapped[UUID] = mapped_column(
        POSTGRESQL_UUID(as_uuid=True),
        ForeignKey("aggregation_executions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    format: Mapped[ExportFormat] = mapped_column(
        stored_enum(ExportFormat, name="export_format"),
        nullable=False,
    )
    label_source_policy: Mapped[LabelSourcePolicy] = mapped_column(
        stored_enum(LabelSourcePolicy, name="export_label_source_policy"),
        nullable=False,
        default=LabelSourcePolicy.machine_aggregation,
        server_default=LabelSourcePolicy.machine_aggregation.value,
    )
    tei_profile: Mapped[TeiExportProfile | None] = mapped_column(
        stored_enum(TeiExportProfile, name="tei_export_profile"),
    )
    human_resp_id: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[ExportExecutionStatus] = mapped_column(
        stored_enum(ExportExecutionStatus, name="export_execution_status"),
        nullable=False,
        default=ExportExecutionStatus.pending,
        server_default=ExportExecutionStatus.pending.value,
    )
    manifest_artifact_id: Mapped[UUID | None] = mapped_column(
        POSTGRESQL_UUID(as_uuid=True),
        ForeignKey("artifacts.id", ondelete="RESTRICT", use_alter=True),
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failure_class: Mapped[str | None] = mapped_column(String(255))
    failure_diagnostic: Mapped[str | None] = mapped_column(Text)
