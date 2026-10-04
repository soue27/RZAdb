"""add workflow to URZA instruction versions

Revision ID: 9b7f3a1c2d45
Revises: 0820d2344d72
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "9b7f3a1c2d45"
down_revision: Union[str, Sequence[str], None] = "0820d2344d72"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


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
