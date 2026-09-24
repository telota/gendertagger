"""Persistence mapping for the ADR-0040 deployment-settings singleton."""

from typing import Any

from sqlalchemy import CheckConstraint, Integer, text
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
