"""reserve connection dispatch names per substation

Revision ID: d3b8c47a1f20
Revises: 831c73d5bb7f
Create Date: 2026-10-15

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d3b8c47a1f20"
down_revision: str | Sequence[str] | None = "831c73d5bb7f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

INDEX_NAME = "uq_connections_substation_dispatch_name"


def upgrade() -> None:
    duplicates = op.get_bind().execute(
        sa.text(
            """
            SELECT substation_id,
                   btrim(dispatch_name) AS normalized_name,
                   array_agg(id ORDER BY id) AS connection_ids,
                   array_agg(dispatch_name ORDER BY id) AS stored_names
            FROM connections
            GROUP BY substation_id, btrim(dispatch_name)
            HAVING count(*) > 1
            ORDER BY substation_id, normalized_name
            """
        )
    ).mappings().all()
    if duplicates:
        details = "\n".join(
            "substation_id={substation_id}, name={name!r}, "
            "ids={ids}, stored_names={stored_names}".format(
                substation_id=row["substation_id"],
                name=row["normalized_name"],
                ids=row["connection_ids"],
                stored_names=row["stored_names"],
            )
            for row in duplicates
        )
        raise RuntimeError(
            "Cannot reserve duplicate connection dispatch names. "
            "Resolve these records manually before migration:\n" + details
        )

    op.create_index(
        INDEX_NAME,
        "connections",
        ["substation_id", sa.text("btrim(dispatch_name)")],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(INDEX_NAME, table_name="connections")
