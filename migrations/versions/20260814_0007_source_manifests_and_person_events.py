"""source manifests and person event provenance

Revision ID: 20260814_0007
Revises: 20260814_0006
Created: 2026-08-14 23:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260814_0007"
down_revision: str | None = "20260814_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add ordered source members and person-level source metadata."""
    op.create_table(
        "snapshot_source_members",
        sa.Column("dataset_snapshot_id", sa.UUID(), nullable=False),
        sa.Column("artifact_id", sa.UUID(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("logical_name", sa.String(length=1024), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("byte_size", sa.BigInteger(), nullable=False),
        sa.Column("media_type", sa.String(length=255), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "byte_size >= 0",
            name=op.f("ck_snapshot_source_members_byte_size_nonnegative"),
        ),
        sa.CheckConstraint(
            "btrim(logical_name) <> ''",
            name=op.f("ck_snapshot_source_members_logical_name_nonblank"),
        ),
        sa.CheckConstraint(
            "btrim(media_type) <> ''",
            name=op.f("ck_snapshot_source_members_media_type_nonblank"),
        ),
        sa.CheckConstraint(
            "ordinal >= 0",
            name=op.f("ck_snapshot_source_members_ordinal_nonnegative"),
        ),
        sa.CheckConstraint(
            "sha256 ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_snapshot_source_members_sha256_format"),
        ),
        sa.ForeignKeyConstraint(
            ["artifact_id"],
            ["artifacts.id"],
            name=op.f("fk_snapshot_source_members_artifact_id_artifacts"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["dataset_snapshot_id"],
            ["dataset_snapshots.id"],
            name=op.f("fk_snapshot_source_members_dataset_snapshot_id_dataset_snapshots"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_snapshot_source_members")),
        sa.UniqueConstraint(
            "dataset_snapshot_id",
            "logical_name",
            name="snapshot_source_member_logical_name",
        ),
        sa.UniqueConstraint(
            "dataset_snapshot_id",
            "ordinal",
            name="snapshot_source_member_ordinal",
        ),
    )

    op.add_column(
        "person_records",
        sa.Column(
            "events",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )
    op.add_column(
        "person_records",
        sa.Column("source_member_name", sa.String(length=1024), nullable=True),
    )
    op.add_column(
        "person_records",
        sa.Column("source_record_locator", sa.Text(), nullable=True),
    )
    op.create_check_constraint(
        op.f("ck_person_records_events_array"),
        "person_records",
        "jsonb_typeof(events) = 'array'",
    )
    op.create_check_constraint(
        op.f("ck_person_records_source_provenance_complete"),
        "person_records",
        "(source_member_name IS NULL) = (source_record_locator IS NULL)",
    )
    op.create_check_constraint(
        op.f("ck_person_records_source_member_name_nonblank"),
        "person_records",
        "source_member_name IS NULL OR btrim(source_member_name) <> ''",
    )
    op.create_check_constraint(
        op.f("ck_person_records_source_record_locator_nonblank"),
        "person_records",
        "source_record_locator IS NULL OR btrim(source_record_locator) <> ''",
    )

    op.execute(
        """
        CREATE FUNCTION gendertagger_protect_ready_source_member()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        DECLARE
            protected_snapshot_id uuid;
        BEGIN
            IF TG_OP = 'INSERT' THEN
                protected_snapshot_id := NEW.dataset_snapshot_id;
            ELSIF TG_OP = 'DELETE' THEN
                protected_snapshot_id := OLD.dataset_snapshot_id;
            ELSE
                IF EXISTS (
                    SELECT 1
                    FROM dataset_snapshots
                    WHERE id IN (OLD.dataset_snapshot_id, NEW.dataset_snapshot_id)
                      AND status = 'ready'
                ) THEN
                    RAISE EXCEPTION USING
                        ERRCODE = '55000',
                        MESSAGE = 'source members in ready snapshots are immutable';
                END IF;
                RETURN NEW;
            END IF;

            IF EXISTS (
                SELECT 1
                FROM dataset_snapshots
                WHERE id = protected_snapshot_id AND status = 'ready'
            ) THEN
                RAISE EXCEPTION USING
                    ERRCODE = '55000',
                    MESSAGE = 'source members in ready snapshots are immutable';
            END IF;
            IF TG_OP = 'DELETE' THEN
                RETURN OLD;
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        """CREATE TRIGGER trg_snapshot_source_members_immutable_ready_snapshot
        BEFORE INSERT OR UPDATE OR DELETE ON snapshot_source_members
        FOR EACH ROW EXECUTE FUNCTION gendertagger_protect_ready_source_member()"""
    )


def downgrade() -> None:
    """Remove source manifests and additive person source metadata."""
    op.execute(
        "DROP TRIGGER trg_snapshot_source_members_immutable_ready_snapshot "
        "ON snapshot_source_members"
    )
    op.execute("DROP FUNCTION gendertagger_protect_ready_source_member()")
    op.drop_table("snapshot_source_members")

    op.drop_constraint(
        op.f("ck_person_records_source_record_locator_nonblank"),
        "person_records",
        type_="check",
    )
    op.drop_constraint(
        op.f("ck_person_records_source_member_name_nonblank"),
        "person_records",
        type_="check",
    )
    op.drop_constraint(
        op.f("ck_person_records_source_provenance_complete"),
        "person_records",
        type_="check",
    )
    op.drop_constraint(
        op.f("ck_person_records_events_array"),
        "person_records",
        type_="check",
    )
    op.drop_column("person_records", "source_record_locator")
    op.drop_column("person_records", "source_member_name")
    op.drop_column("person_records", "events")
