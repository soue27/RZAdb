"""allow tasks directly assigned to substation documents

Revision ID: a91e7d4c2b61
Revises: d3b8c47a1f20
Create Date: 2026-10-15
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a91e7d4c2b61"
down_revision: str | Sequence[str] | None = "d3b8c47a1f20"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("tasks", sa.Column("substation_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_tasks_substation_id_substations",
        "tasks",
        "substations",
        ["substation_id"],
        ["id"],
    )
    op.alter_column("tasks", "urza_id", existing_type=sa.Uuid(), nullable=True)
    op.create_check_constraint(
        "ck_tasks_exactly_one_parent",
        "tasks",
        "(urza_id IS NOT NULL AND substation_id IS NULL) OR "
        "(urza_id IS NULL AND substation_id IS NOT NULL)",
    )
    op.create_check_constraint(
        "ck_tasks_substation_work_type",
        "tasks",
        "substation_id IS NULL OR work_type IN ('instruction', 'schemes')",
    )
    op.create_index("ix_tasks_substation_id", "tasks", ["substation_id"])


def downgrade() -> None:
    bind = op.get_bind()
    has_substation_tasks = bind.execute(
        sa.text("SELECT EXISTS (SELECT 1 FROM tasks WHERE substation_id IS NOT NULL)")
    ).scalar_one()
    if has_substation_tasks:
        raise RuntimeError(
            "Cannot downgrade while substation tasks exist; migrate or remove them first."
        )
    op.drop_index("ix_tasks_substation_id", table_name="tasks")
    op.drop_constraint("ck_tasks_substation_work_type", "tasks", type_="check")
    op.drop_constraint("ck_tasks_exactly_one_parent", "tasks", type_="check")
    op.alter_column("tasks", "urza_id", existing_type=sa.Uuid(), nullable=False)
    op.drop_constraint("fk_tasks_substation_id_substations", "tasks", type_="foreignkey")
    op.drop_column("tasks", "substation_id")
