"""add document status to programs

Revision ID: 0820d2344d72
Revises: 58c670f1dc59
Create Date: 2026-10-04 12:50:58.556581

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0820d2344d72"
down_revision: Union[str, Sequence[str], None] = "58c670f1dc59"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    document_status = sa.Enum(
        "draft",
        "under_review",
        "approved",
        name="document_status",
    )
    document_status.create(op.get_bind(), checkfirst=True)

    op.add_column(
        "programs",
        sa.Column(
            "status",
            document_status,
            nullable=True,
        ),
    )

    op.execute(
        sa.text(
            "UPDATE programs "
            "SET status = 'approved' "
            "WHERE status IS NULL"
        )
    )

    op.alter_column(
        "programs",
        "status",
        nullable=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("programs", "status")

    document_status = sa.Enum(
        "draft",
        "under_review",
        "approved",
        name="document_status",
    )
    document_status.drop(op.get_bind(), checkfirst=True)