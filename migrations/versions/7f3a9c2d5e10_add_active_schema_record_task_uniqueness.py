"""Ensure one active schema result per task.

Revision ID: 7f3a9c2d5e10
Revises: e712a85c04f1
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "7f3a9c2d5e10"
down_revision: str | Sequence[str] | None = "e712a85c04f1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


INDEX_NAME = "uq_schema_records_one_active_per_task"


def upgrade() -> None:
    connection = op.get_bind()
    conflicts = connection.execute(
        sa.text(
            "SELECT task_id::text, count(*) "
            "FROM schema_records "
            "WHERE task_id IS NOT NULL AND deleted_at IS NULL "
            "GROUP BY task_id "
            "HAVING count(*) > 1 "
            "ORDER BY task_id"
        )
    ).all()
    if conflicts:
        details = ", ".join(f"{task_id} ({count})" for task_id, count in conflicts)
        raise RuntimeError(
            "Cannot add one-active-SchemaRecord-per-Task index; "
            f"duplicate active task links exist: {details}"
        )

    op.create_index(
        INDEX_NAME,
        "schema_records",
        ["task_id"],
        unique=True,
        postgresql_where=sa.text(
            "task_id IS NOT NULL AND deleted_at IS NULL"
        ),
    )


def downgrade() -> None:
    op.drop_index(INDEX_NAME, table_name="schema_records")
