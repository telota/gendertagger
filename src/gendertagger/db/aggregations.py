"""Persistence-only aggregation execution and result mappings."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import JsonValue
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    PrimaryKeyConstraint,
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
from gendertagger.models.aggregation import AggregationOutcome, OverrideSource
from gendertagger.models.classification import AgreementTier, CanonicalLabel, CertaintyTier
from gendertagger.models.lifecycle import AggregationExecutionStatus


class AggregationExecutionRow(UuidPrimaryKeyMixin, CreatedAtMixin, Base):
    """Persistence row for one versioned aggregation over explicit method executions."""

    __tablename__ = "aggregation_executions"
    __table_args__ = (
        enum_check("status", AggregationExecutionStatus, name="status_allowed"),
        CheckConstraint(
            "strategy ~ '^[a-z][a-z0-9]*(_[a-z0-9]+)*$'",
            name="strategy_format",
        ),
        CheckConstraint(
            "config_sha256 ~ '^[0-9a-f]{64}$'",
            name="config_sha256_format",
        ),
        CheckConstraint(
            "finished_at IS NULL OR started_at IS NOT NULL",
            name="aggregation_timing_order_present",
        ),
        Index("ix_aggregation_executions_run_id_status", "run_id", "status"),
    )

    run_id: Mapped[UUID] = mapped_column(
        POSTGRESQL_UUID(as_uuid=True),
        ForeignKey("runs.id", ondelete="RESTRICT"),
        nullable=False,
    )
    strategy: Mapped[str] = mapped_column(String(100), nullable=False)
    resolved_config: Mapped[dict[str, JsonValue]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    config_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[AggregationExecutionStatus] = mapped_column(
        stored_enum(AggregationExecutionStatus, name="aggregation_execution_status"),
        nullable=False,
        default=AggregationExecutionStatus.pending,
        server_default=AggregationExecutionStatus.pending.value,
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failure_class: Mapped[str | None] = mapped_column(String(255))
    failure_diagnostic: Mapped[str | None] = mapped_column(Text)


class AggregationMethodExecutionRow(Base):
    """Exact ordered method-execution membership for an aggregation."""

    __tablename__ = "aggregation_method_executions"
    __table_args__ = (
        PrimaryKeyConstraint(
            "aggregation_execution_id",
            "method_execution_id",
            name="pk_aggregation_method_executions",
        ),
        UniqueConstraint(
            "aggregation_execution_id",
            "position",
            name="aggregation_position",
        ),
        CheckConstraint("position >= 0", name="position_nonnegative"),
    )

    aggregation_execution_id: Mapped[UUID] = mapped_column(
        POSTGRESQL_UUID(as_uuid=True),
        ForeignKey("aggregation_executions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    method_execution_id: Mapped[UUID] = mapped_column(
        POSTGRESQL_UUID(as_uuid=True),
        ForeignKey("method_executions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)


class AggregatedResultRow(UuidPrimaryKeyMixin, CreatedAtMixin, Base):
    """Immutable persistence row for one complete per-person aggregation result."""

    __tablename__ = "aggregated_results"
    __table_args__ = (
        enum_check("outcome", AggregationOutcome, name="outcome_allowed"),
        enum_check("label", CanonicalLabel, name="label_allowed"),
        enum_check("override_source", OverrideSource, name="override_source_allowed"),
        enum_check("agreement_tier", AgreementTier, name="agreement_tier_allowed"),
        enum_check("certainty_tier", CertaintyTier, name="certainty_tier_allowed"),
        UniqueConstraint(
            "aggregation_execution_id",
            "person_record_id",
            name="aggregation_person",
        ),
        CheckConstraint("male_vote_count >= 0", name="male_vote_count_nonnegative"),
        CheckConstraint("female_vote_count >= 0", name="female_vote_count_nonnegative"),
        CheckConstraint("unknown_vote_count >= 0", name="unknown_vote_count_nonnegative"),
        CheckConstraint(
            "institution_vote_count >= 0",
            name="institution_vote_count_nonnegative",
        ),
        CheckConstraint(
            "agreement_score IS NULL OR "
            "(agreement_score >= 0.0 AND agreement_score <= 1.0 AND "
            "agreement_score::text NOT IN ('NaN', 'Infinity', '-Infinity'))",
            name="agreement_score_range",
        ),
        CheckConstraint(
            "(outcome = 'decided' AND label IS NOT NULL AND cardinality(tied_labels) = 0) OR "
            "(outcome = 'unresolved_tie' AND label IS NULL AND cardinality(tied_labels) >= 2) OR "
            "(outcome = 'no_data' AND label IS NULL AND cardinality(tied_labels) = 0)",
            name="outcome_fields_consistent",
        ),
        CheckConstraint(
            "tied_labels <@ ARRAY['male', 'female', 'unknown', 'institution']::text[]",
            name="tied_labels_canonical",
        ),
        CheckConstraint(
            "(override_source IS NULL AND override_agreeing_count IS NULL AND "
            "override_comparison_count IS NULL) OR "
            "(override_source IS NOT NULL AND override_agreeing_count IS NOT NULL AND "
            "override_comparison_count IS NOT NULL AND override_agreeing_count >= 0 AND "
            "override_comparison_count >= override_agreeing_count)",
            name="override_counts_consistent",
        ),
        CheckConstraint(
            "outcome <> 'no_data' OR "
            "(male_vote_count = 0 AND female_vote_count = 0 AND unknown_vote_count = 0 AND "
            "institution_vote_count = 0 AND agreement_score IS NULL AND "
            "agreement_tier = 'no_answer' AND certainty_tier = 'no_data')",
            name="no_data_assessment_consistent",
        ),
        CheckConstraint(
            "outcome <> 'unresolved_tie' OR "
            "(agreement_tier = 'no_consensus' AND certainty_tier = 'contested')",
            name="tie_assessment_consistent",
        ),
        CheckConstraint(
            "override_source IS NULL OR certainty_tier = 'high'",
            name="override_certainty_high",
        ),
        Index("ix_aggregated_results_person_record_id_outcome", "person_record_id", "outcome"),
        Index(
            "ix_aggregated_results_aggregation_execution_id_certainty_tier",
            "aggregation_execution_id",
            "certainty_tier",
        ),
        Index(
            "ix_aggregated_results_aggregation_execution_id_agreement_tier",
            "aggregation_execution_id",
            "agreement_tier",
        ),
    )

    aggregation_execution_id: Mapped[UUID] = mapped_column(
        POSTGRESQL_UUID(as_uuid=True),
        ForeignKey("aggregation_executions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    person_record_id: Mapped[UUID] = mapped_column(
        POSTGRESQL_UUID(as_uuid=True),
        ForeignKey("person_records.id", ondelete="RESTRICT"),
        nullable=False,
    )
    outcome: Mapped[AggregationOutcome] = mapped_column(
        stored_enum(AggregationOutcome, name="aggregation_outcome"),
        nullable=False,
    )
    label: Mapped[CanonicalLabel | None] = mapped_column(
        stored_enum(CanonicalLabel, name="canonical_label"),
    )
    male_vote_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    female_vote_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    unknown_vote_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    institution_vote_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    tied_labels: Mapped[list[str]] = mapped_column(
        ARRAY(Text),
        nullable=False,
        default=list,
        server_default=text("'{}'::text[]"),
    )
    override_source: Mapped[OverrideSource | None] = mapped_column(
        stored_enum(OverrideSource, name="override_source"),
    )
    override_agreeing_count: Mapped[int | None] = mapped_column(Integer)
    override_comparison_count: Mapped[int | None] = mapped_column(Integer)
    has_prediction_error: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
    )
    agreement_score: Mapped[float | None] = mapped_column(Float)
    agreement_tier: Mapped[AgreementTier] = mapped_column(
        stored_enum(AgreementTier, name="agreement_tier"),
        nullable=False,
    )
    certainty_tier: Mapped[CertaintyTier] = mapped_column(
        stored_enum(CertaintyTier, name="certainty_tier"),
        nullable=False,
    )
    result_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
