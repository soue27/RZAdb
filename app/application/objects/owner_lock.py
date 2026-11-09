from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.base import Base


async def lock_owner_row[Owner: Base](
    session: AsyncSession,
    model: type[Owner],
    owner_id: UUID,
) -> Owner | None:
    """Блокирует строку владельца и перечитывает её в текущей транзакции.

    Использует SELECT FOR UPDATE и populate_existing, чтобы после ожидания
    блокировки получить актуальное состояние ORM-объекта.

    Args:
        session: Асинхронная SQLAlchemy-сессия.
        model: ORM-модель владельца.
        owner_id: Идентификатор владельца.

    Returns:
        Актуальная заблокированная модель или None.
    """
    result = await session.scalars(
        select(model)
        .where(model.id == owner_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    return result.one_or_none()
