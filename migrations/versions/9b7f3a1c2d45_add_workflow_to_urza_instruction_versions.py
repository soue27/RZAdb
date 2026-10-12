"""add workflow to URZA instruction versions

Revision ID: 9b7f3a1c2d45
Revises: 0820d2344d72
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "9b7f3a1c2d45"
down_revision: str | Sequence[str] | None = "0820d2344d72"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    document_status = sa.Enum(
        "draft", "under_review", "approved", name="document_status",
    )
    document_status.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "urza_instruction_versions",
        sa.Column("status", document_status, nullable=True),
    )
    op.execute(
        "UPDATE urza_instruction_versions SET status = 'approved' WHERE status IS NULL"
    )
    op.alter_column("urza_instruction_versions", "status", nullable=False)
    op.create_unique_constraint(
        "uq_urza_instruction_versions_parent_version",
        "urza_instruction_versions",
        ["urza_instruction_id", "version_number"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_urza_instruction_versions_parent_version",
        "urza_instruction_versions",
        type_="unique",
    )
    op.drop_column("urza_instruction_versions", "status")
