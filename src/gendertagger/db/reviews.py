"""Persistence-only user, annotation, and review-state mappings."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    PrimaryKeyConstraint,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as POSTGRESQL_UUID
from sqlalchemy.orm import Mapped, mapped_column

from gendertagger.db.base import (
    Base,
    CreatedAtMixin,
    UpdatedAtMixin,
    UuidPrimaryKeyMixin,
    stored_enum,
)
from gendertagger.models.classification import CanonicalLabel
from gendertagger.models.review import ReviewAction, ReviewWorkflowState
from gendertagger.models.user import Role


class UserRow(UuidPrimaryKeyMixin, CreatedAtMixin, UpdatedAtMixin, Base):
    """Provider-neutral persistence row for an attributable user."""

    __tablename__ = "users"
    __table_args__ = (CheckConstraint("btrim(display_name) <> ''", name="display_name_nonblank"),)

    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )


class UserRoleRow(Base):
    """Persistence row assigning one global authorization role to a user."""

    __tablename__ = "user_roles"
    __table_args__ = (PrimaryKeyConstraint("user_id", "role", name="pk_user_roles"),)

    user_id: Mapped[UUID] = mapped_column(
        POSTGRESQL_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    role: Mapped[Role] = mapped_column(
        stored_enum(Role, name="user_role"),
        nullable=False,
    )


class AnnotationRow(UuidPrimaryKeyMixin, CreatedAtMixin, Base):
    """Immutable append-only persistence row for one human review action."""

    __tablename__ = "annotations"
    __table_args__ = (
        ForeignKeyConstraint(
            ["person_record_id", "dataset_snapshot_id"],
            ["person_records.id", "person_records.dataset_snapshot_id"],
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "dataset_snapshot_id",
            "person_record_id",
            "resulting_revision",
            name="review_stream_revision",
        ),
        CheckConstraint("resulting_revision > 0", name="resulting_revision_positive"),
        CheckConstraint(
            "(action IN ('verify', 'correct') AND label IS NOT NULL) OR "
            "(action = 'defer' AND label IS NULL)",
            name="action_label_consistent",
        ),
        CheckConstraint(
            "supersedes_annotation_id IS NULL OR supersedes_annotation_id <> id",
            name="does_not_supersede_self",
        ),
        Index("ix_annotations_person_record_id_created_at", "person_record_id", "created_at"),
        Index("ix_annotations_reviewer_user_id_created_at", "reviewer_user_id", "created_at"),
    )

    dataset_snapshot_id: Mapped[UUID] = mapped_column(POSTGRESQL_UUID(as_uuid=True), nullable=False)
    person_record_id: Mapped[UUID] = mapped_column(POSTGRESQL_UUID(as_uuid=True), nullable=False)
    action: Mapped[ReviewAction] = mapped_column(
        stored_enum(ReviewAction, name="review_action"),
        nullable=False,
    )
    label: Mapped[CanonicalLabel | None] = mapped_column(
        stored_enum(CanonicalLabel, name="canonical_label"),
    )
    reviewer_user_id: Mapped[UUID] = mapped_column(
        POSTGRESQL_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    comment: Mapped[str | None] = mapped_column(Text)
    aggregated_result_id: Mapped[UUID | None] = mapped_column(
        POSTGRESQL_UUID(as_uuid=True),
        ForeignKey("aggregated_results.id", ondelete="RESTRICT"),
    )
    supersedes_annotation_id: Mapped[UUID | None] = mapped_column(
        POSTGRESQL_UUID(as_uuid=True),
        ForeignKey("annotations.id", ondelete="RESTRICT"),
    )
    resulting_revision: Mapped[int] = mapped_column(Integer, nullable=False)


class ReviewStateRow(UpdatedAtMixin, Base):
    """Mutable, rebuildable review concurrency and workflow projection."""

    __tablename__ = "review_states"
    __table_args__ = (
        PrimaryKeyConstraint(
            "dataset_snapshot_id",
            "person_record_id",
            name="pk_review_states",
        ),
        ForeignKeyConstraint(
            ["person_record_id", "dataset_snapshot_id"],
            ["person_records.id", "person_records.dataset_snapshot_id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint("revision >= 0", name="revision_nonnegative"),
        CheckConstraint(
            "(revision = 0 AND current_annotation_id IS NULL AND workflow_state = 'unreviewed') OR "
            "(revision > 0 AND current_annotation_id IS NOT NULL AND "
            "workflow_state IN ('reviewed', 'deferred'))",
            name="revision_head_consistent",
        ),
        Index("ix_review_states_workflow_state_updated_at", "workflow_state", "updated_at"),
    )

    dataset_snapshot_id: Mapped[UUID] = mapped_column(POSTGRESQL_UUID(as_uuid=True), nullable=False)
    person_record_id: Mapped[UUID] = mapped_column(POSTGRESQL_UUID(as_uuid=True), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    current_annotation_id: Mapped[UUID | None] = mapped_column(
        POSTGRESQL_UUID(as_uuid=True),
        ForeignKey("annotations.id", ondelete="RESTRICT", use_alter=True),
    )
    workflow_state: Mapped[ReviewWorkflowState] = mapped_column(
        stored_enum(ReviewWorkflowState, name="review_workflow_state"),
        nullable=False,
        default=ReviewWorkflowState.unreviewed,
        server_default=ReviewWorkflowState.unreviewed.value,
    )
    updated_at: Mapped[datetime]
