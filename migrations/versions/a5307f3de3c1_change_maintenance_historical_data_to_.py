
"""change maintenance historical data to boolean

Revision ID: a5307f3de3c1
Revises: e0d0ec9622f9
"""

from alembic import op
import sqlalchemy as sa


revision = "a5307f3de3c1"
down_revision = "e0d0ec9622f9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE to_records
        ALTER COLUMN historical_data TYPE BOOLEAN
        USING FALSE
        """
    )

    op.alter_column(
        "to_records",
        "historical_data",
        existing_type=sa.Boolean(),
        nullable=False,
        server_default=sa.false(),
    )


def downgrade() -> None:
    op.alter_column(
        "to_records",
        "historical_data",
        existing_type=sa.Boolean(),
        nullable=True,
        server_default=None,
    )

    op.execute(
        """
        ALTER TABLE to_records
        ALTER COLUMN historical_data TYPE TEXT
        USING CASE
            WHEN historical_data THEN 'true'
            ELSE NULL
        END
        """
    )