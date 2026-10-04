"""Add document workflow status and active-record indexes to Settings.

Revision ID: c54df31d7a20
Revises: 9b7f3a1c2d45
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "c54df31d7a20"
down_revision: Union[str, Sequence[str], None] = "9b7f3a1c2d45"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    document_status = postgresql.ENUM(
        "draft",
        "under_review",
        "approved",
        name="document_status",
        create_type=False,
    )
    op.add_column(
        "settings_records",
        sa.Column("status", document_status, nullable=True),
    )
    op.execute(
        sa.text(
            "UPDATE settings_records SET status = 'approved' "
            "WHERE status IS NULL"
        )
    )
    op.alter_column(
        "settings_records",
        "status",
        nullable=False,
    )

    op.create_index(
        "uq_settings_records_one_active_unfinished_per_form",
        "settings_records",
        ["settings_form_id"],
        unique=True,
        postgresql_where=sa.text(
            "deleted_at IS NULL AND status IN ('draft', 'under_review')"
        ),
    )
    op.create_index(
        "ix_settings_records_active_form_change_date",
        "settings_records",
        [
            "settings_form_id",
            sa.text("change_date DESC"),
            sa.text("created_at DESC"),
            sa.text("id DESC"),
        ],
        postgresql_where=sa.text("deleted_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "ix_settings_records_active_form_change_date",
        table_name="settings_records",
    )
    op.drop_index(
        "uq_settings_records_one_active_unfinished_per_form",
        table_name="settings_records",
    )
    op.drop_column("settings_records", "status")
