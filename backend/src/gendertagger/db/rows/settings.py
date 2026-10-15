"""Persistence mapping for the deployment-settings singleton (ADR-0040, ADR-0051)."""

from typing import Any

from sqlalchemy import Boolean, CheckConstraint, Integer, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from gendertagger.db.base import Base, UpdatedAtMixin


class DeploymentSettingsRow(UpdatedAtMixin, Base):
    """The only deployment-wide mutable settings row, fixed at identifier ``1``."""

    __tablename__ = "deployment_settings"
    __table_args__ = (
        CheckConstraint("id = 1", name="singleton_id"),
        CheckConstraint("revision >= 0", name="revision_nonnegative"),
        CheckConstraint(
            "jsonb_typeof(branding_overrides) = 'object'",
            name="branding_overrides_object",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    branding_overrides: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    # ADR-0051: whether `reference_partial_v1` aggregations may be created at all — unrelated to
    # branding, kept on this same singleton row rather than a second one-row table.
    allow_partial_reference_aggregation: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("true"),
    )
