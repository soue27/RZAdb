"""add reassignment assignees to task history

Revision ID: f1a6c9d2e407
Revises: a91e7d4c2b61
Create Date: 2026-10-22 00:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f1a6c9d2e407"
down_revision: str | Sequence[str] | None = "a91e7d4c2b61"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "task_history",
        sa.Column("previous_assignee_id", sa.Uuid(), nullable=True),
    )
    op.add_column(
        "task_history",
        sa.Column("new_assignee_id", sa.Uuid(), nullable=True),
    )
    op.create_foreign_key(
        "fk_task_history_previous_assignee_id_users",
        "task_history",
        "users",
        ["previous_assignee_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_task_history_new_assignee_id_users",
        "task_history",
        "users",
        ["new_assignee_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_task_history_new_assignee_id_users",
        "task_history",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_task_history_previous_assignee_id_users",
        "task_history",
        type_="foreignkey",
    )
    op.drop_column("task_history", "new_assignee_id")
    op.drop_column("task_history", "previous_assignee_id")
