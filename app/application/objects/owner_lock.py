from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.base import Base


async def lock_owner_row[Owner: Base](
    session: AsyncSession,
    model: type[Owner],
    owner_id: UUID,
) -> Owner | None:
    """Lock and refresh an owner row in the current transaction."""
    result = await session.scalars(
        select(model)
        .where(model.id == owner_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    return result.one_or_none()
