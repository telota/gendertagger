"""aggregated result prediction errors

Revision ID: 20260814_0009
Revises: 20260814_0008
Created: 2026-08-15 09:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260814_0009"
down_revision: str | None = "20260814_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_BACKFILL_PREDICTION_ERRORS = """
UPDATE aggregated_results AS result
SET has_prediction_error = true
WHERE EXISTS (
    SELECT 1
    FROM aggregation_method_executions AS membership
    JOIN predictions AS prediction
        ON prediction.method_execution_id = membership.method_execution_id
    WHERE membership.aggregation_execution_id = result.aggregation_execution_id
      AND prediction.person_record_id = result.person_record_id
      AND prediction.status = 'error'
)
"""


def upgrade() -> None:
    """Project immutable prediction errors onto results for review triage."""
    op.add_column(
        "aggregated_results",
        sa.Column(
            "has_prediction_error",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.execute(sa.text(_BACKFILL_PREDICTION_ERRORS))


def downgrade() -> None:
    """Remove the projection and fall back to per-query error derivation."""
    op.drop_column("aggregated_results", "has_prediction_error")
