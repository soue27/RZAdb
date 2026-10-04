"""Add document workflow status and unfinished-record constraint to Schemes.

Revision ID: e712a85c04f1
Revises: c54df31d7a20
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "e712a85c04f1"
down_revision: Union[str, Sequence[str], None] = "c54df31d7a20"
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
        "schema_records",
        sa.Column("status", document_status, nullable=True),
    )
    op.execute(
        sa.text(
            "UPDATE schema_records SET status = 'approved' "
            "WHERE status IS NULL"
        )
    )
    op.alter_column(
        "schema_records",
        "status",
        nullable=False,
    )
    op.create_index(
        "uq_schema_records_one_active_unfinished_per_form",
        "schema_records",
        ["schema_form_id"],
        unique=True,
        postgresql_where=sa.text(
            "deleted_at IS NULL AND status IN ('draft', 'under_review')"
        ),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_schema_records_one_active_unfinished_per_form",
        table_name="schema_records",
    )
    op.drop_column("schema_records", "status")
