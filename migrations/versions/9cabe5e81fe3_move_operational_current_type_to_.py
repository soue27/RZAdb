"""move operational current type to substations

Revision ID: 9cabe5e81fe3
Revises: 5fd04138bcdb
Create Date: 2026-09-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "9cabe5e81fe3"
down_revision: str | Sequence[str] | None = "5fd04138bcdb"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Используем уже существующий PostgreSQL enum
    # operational_current_type.
    operational_current_type = sa.Enum(
        "permanent",
        "rectified",
        "alternating",
        name="operational_current_type",
        create_type=False,
    )

    # Сначала добавляем nullable-колонку, чтобы можно было
    # заполнить существующие записи.
    op.add_column(
        "substations",
        sa.Column(
            "operational_current_type",
            operational_current_type,
            nullable=True,
        ),
    )

    # Тестовые данные: для каждой существующей ПС задаём
    # один тип оперативного тока.
    op.execute(
        """
        UPDATE substations
        SET operational_current_type = (
            CASE dispatch_name
                WHEN 'ПС Березниковская' THEN 'permanent'
                WHEN 'ПС Восточная' THEN 'rectified'
                WHEN 'ПС Каменская' THEN 'alternating'
                WHEN 'ПС Камская' THEN 'permanent'
                WHEN 'ПС Пермская' THEN 'rectified'
                WHEN 'ПС Свердловская' THEN 'alternating'
                WHEN 'ПС Северная' THEN 'permanent'
                WHEN 'ПС Уральская' THEN 'rectified'
            END
        )::operational_current_type
        WHERE dispatch_name IN (
            'ПС Березниковская',
            'ПС Восточная',
            'ПС Каменская',
            'ПС Камская',
            'ПС Пермская',
            'ПС Свердловская',
            'ПС Северная',
            'ПС Уральская'
        )
        """
    )

    # После заполнения существующих записей делаем поле обязательным.
    op.alter_column(
        "substations",
        "operational_current_type",
        nullable=False,
    )

    # Теперь старое поле Connection больше не нужно.
    op.drop_column(
        "connections",
        "operational_current_type",
    )


def downgrade() -> None:
    operational_current_type = sa.Enum(
        "permanent",
        "rectified",
        "alternating",
        name="operational_current_type",
        create_type=False,
    )

    # Возвращаем поле в connections.
    op.add_column(
        "connections",
        sa.Column(
            "operational_current_type",
            operational_current_type,
            nullable=True,
        ),
    )

    # Возвращаем значения из Substation в Connection.
    op.execute(
        """
        UPDATE connections AS c
        SET operational_current_type = s.operational_current_type
        FROM substations AS s
        WHERE c.substation_id = s.id
        """
    )

    op.alter_column(
        "connections",
        "operational_current_type",
        nullable=False,
    )

    # Удаляем новое поле из substations.
    op.drop_column(
        "substations",
        "operational_current_type",
    )