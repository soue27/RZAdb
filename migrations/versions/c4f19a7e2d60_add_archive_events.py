"""add archive events

Revision ID: c4f19a7e2d60
Revises: f1a6c9d2e407
Create Date: 2026-10-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c4f19a7e2d60"
down_revision: str | Sequence[str] | None = "f1a6c9d2e407"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    archive_event_type = postgresql.ENUM(
        "archived",
        "restored",
        name="archive_event_type",
        create_type=False,
    )
    archive_event_type.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "archive_events",
        sa.Column("operation_id", sa.Uuid(), nullable=False),
        sa.Column("event_type", archive_event_type, nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("substation_id", sa.Uuid(), nullable=True),
        sa.Column("connection_id", sa.Uuid(), nullable=True),
        sa.Column("urza_id", sa.Uuid(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "(CASE WHEN substation_id IS NOT NULL THEN 1 ELSE 0 END) + "
            "(CASE WHEN connection_id IS NOT NULL THEN 1 ELSE 0 END) + "
            "(CASE WHEN urza_id IS NOT NULL THEN 1 ELSE 0 END) = 1",
            name="ck_archive_events_exactly_one_object",
        ),
        sa.CheckConstraint(
            "reason IS NULL OR char_length(reason) <= 2000",
            name="ck_archive_events_reason_max_length",
        ),
        sa.CheckConstraint(
            "event_type != 'archived' OR "
            "(reason IS NOT NULL AND char_length(btrim(reason)) > 0)",
            name="ck_archive_events_archived_reason_required",
        ),
        sa.ForeignKeyConstraint(
            ["actor_id"],
            ["users.id"],
            name="fk_archive_events_actor_id_users",
        ),
        sa.ForeignKeyConstraint(
            ["substation_id"],
            ["substations.id"],
            name="fk_archive_events_substation_id_substations",
        ),
        sa.ForeignKeyConstraint(
            ["connection_id"],
            ["connections.id"],
            name="fk_archive_events_connection_id_connections",
        ),
        sa.ForeignKeyConstraint(
            ["urza_id"],
            ["urzas.id"],
            name="fk_archive_events_urza_id_urzas",
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        "ix_archive_events_operation_id",
        "archive_events",
        ["operation_id"],
    )
    op.create_index(
        "ix_archive_events_substation_history",
        "archive_events",
        ["substation_id", "occurred_at"],
        postgresql_where=sa.text("substation_id IS NOT NULL"),
    )
    op.create_index(
        "ix_archive_events_connection_history",
        "archive_events",
        ["connection_id", "occurred_at"],
        postgresql_where=sa.text("connection_id IS NOT NULL"),
    )
    op.create_index(
        "ix_archive_events_urza_history",
        "archive_events",
        ["urza_id", "occurred_at"],
        postgresql_where=sa.text("urza_id IS NOT NULL"),
    )
    op.create_index(
        "uq_archive_events_operation_substation",
        "archive_events",
        ["operation_id", "substation_id"],
        unique=True,
        postgresql_where=sa.text("substation_id IS NOT NULL"),
    )
    op.create_index(
        "uq_archive_events_operation_connection",
        "archive_events",
        ["operation_id", "connection_id"],
        unique=True,
        postgresql_where=sa.text("connection_id IS NOT NULL"),
    )
    op.create_index(
        "uq_archive_events_operation_urza",
        "archive_events",
        ["operation_id", "urza_id"],
        unique=True,
        postgresql_where=sa.text("urza_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_table("archive_events")

    archive_event_type = postgresql.ENUM(
        "archived",
        "restored",
        name="archive_event_type",
        create_type=False,
    )
    archive_event_type.drop(op.get_bind(), checkfirst=True)
