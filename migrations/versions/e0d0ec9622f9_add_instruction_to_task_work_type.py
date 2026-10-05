"""add instruction to task work type

Revision ID: e0d0ec9622f9
Revises: 7f3a9c2d5e10
"""

from collections.abc import Sequence

from alembic import op


revision: str = "e0d0ec9622f9"
down_revision: str | Sequence[str] | None = "7f3a9c2d5e10"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "ALTER TYPE task_work_type ADD VALUE IF NOT EXISTS 'instruction'"
    )


def downgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM tasks
                WHERE work_type = 'instruction'
            ) THEN
                RAISE EXCEPTION
                    'Cannot downgrade task_work_type: '
                    'tasks with work_type=instruction exist';
            END IF;
        END
        $$;
        """
    )

    op.execute(
        """
        ALTER TYPE task_work_type RENAME TO task_work_type_old
        """
    )

    op.execute(
        """
        CREATE TYPE task_work_type AS ENUM (
            'otd',
            'settings',
            'schemes',
            'maintenance',
            'program'
        )
        """
    )

    op.execute(
        """
        ALTER TABLE tasks
        ALTER COLUMN work_type
        TYPE task_work_type
        USING work_type::text::task_work_type
        """
    )

    op.execute("DROP TYPE task_work_type_old")