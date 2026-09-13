"""add task history

Revision ID: 9600d57ceeaa
Revises: c975778a2356
Create Date: 2026-09-13 07:59:48.756846

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "9600d57ceeaa"
down_revision: Union[str, Sequence[str], None] = "c975778a2356"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create task history table using the existing task_status enum."""
    task_status_enum = postgresql.ENUM(
        "created",
        "assigned",
        "in_progress",
        "completed",
        "under_review",
        "closed",
        "rejected",
        name="task_status",
        create_type=False,
    )

    op.create_table(
        "task_history",
        sa.Column("task_id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("old_status", task_status_enum, nullable=True),
        sa.Column("new_status", task_status_enum, nullable=True),
        sa.Column("actor_id", sa.Uuid(), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["actor_id"],
            ["users.id"],
        ),
        sa.ForeignKeyConstraint(
            ["task_id"],
            ["tasks.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    """Drop task history table."""
    op.drop_table("task_history")