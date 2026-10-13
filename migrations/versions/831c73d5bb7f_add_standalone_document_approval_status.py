
"""add standalone document approval status

Revision ID: 831c73d5bb7f
Revises: a5307f3de3c1
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = '831c73d5bb7f'
down_revision: str | Sequence[str] | None = "a5307f3de3c1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


document_status = postgresql.ENUM(
    "draft",
    "under_review",
    "approved",
    name="document_status",
    create_type=False,
)


def upgrade() -> None:
    # Добавляем nullable-колонки, чтобы заполнить существующие записи.
    for table in (
        "to_records",
        "otd_versions",
        "rza_instruction_versions",
        "selectivity_scheme_versions",
    ):
        op.add_column(
            table,
            sa.Column("status", document_status, nullable=True),
        )

    # Сохраняем действующий статус существующих документов:
    # они не должны внезапно оказаться черновиками или на проверке.
    for table in (
        "to_records",
        "otd_versions",
        "rza_instruction_versions",
        "selectivity_scheme_versions",
    ):
        op.execute(
            sa.text(
                f"UPDATE {table} SET status = 'approved' "
                "WHERE status IS NULL"
            )
        )
        op.alter_column(
            table,
            "status",
            existing_type=document_status,
            nullable=False,
            server_default=sa.text("'draft'"),
        )

    # Связь версии инструкции и версии схемы с заданием.
    op.add_column(
        "rza_instruction_versions",
        sa.Column("task_id", sa.Uuid(), nullable=True),
    )
    op.create_foreign_key(
        "fk_rza_instruction_versions_task_id_tasks",
        "rza_instruction_versions",
        "tasks",
        ["task_id"],
        ["id"],
    )

    op.add_column(
        "selectivity_scheme_versions",
        sa.Column("task_id", sa.Uuid(), nullable=True),
    )
    op.create_foreign_key(
        "fk_selectivity_scheme_versions_task_id_tasks",
        "selectivity_scheme_versions",
        "tasks",
        ["task_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_selectivity_scheme_versions_task_id_tasks",
        "selectivity_scheme_versions",
        type_="foreignkey",
    )
    op.drop_column("selectivity_scheme_versions", "task_id")

    op.drop_constraint(
        "fk_rza_instruction_versions_task_id_tasks",
        "rza_instruction_versions",
        type_="foreignkey",
    )
    op.drop_column("rza_instruction_versions", "task_id")

    for table in (
        "selectivity_scheme_versions",
        "rza_instruction_versions",
        "otd_versions",
        "to_records",
    ):
        op.drop_column(table, "status")
