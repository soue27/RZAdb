"""add document status to programs

Revision ID: 58c670f1dc59
Revises: a74c1d8f2b90
Create Date: 2026-10-04 12:50:44.455519

"""
from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = '58c670f1dc59'
down_revision: str | Sequence[str] | None = 'a74c1d8f2b90'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""


def downgrade() -> None:
    """Downgrade schema."""
