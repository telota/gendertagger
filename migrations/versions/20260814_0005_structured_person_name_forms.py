"""structured person name forms

Revision ID: 20260814_0005
Revises: 20260814_0004
Created: 2026-08-14 18:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260814_0005"
down_revision: str | None = "20260814_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add optional source-rich names without rewriting immutable legacy rows."""
    op.add_column(
        "person_records",
        sa.Column(
            "name_forms",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )
    op.create_check_constraint(
        op.f("ck_person_records_name_forms_array"),
        "person_records",
        "name_forms IS NULL OR jsonb_typeof(name_forms) = 'array'",
    )


def downgrade() -> None:
    """Remove source-rich name forms while retaining flat name projections."""
    op.drop_constraint(
        op.f("ck_person_records_name_forms_array"),
        "person_records",
        type_="check",
    )
    op.drop_column("person_records", "name_forms")
