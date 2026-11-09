from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.engine import async_session_factory


async def get_session() -> AsyncGenerator[AsyncSession]:
    """Предоставляет SQLAlchemy-сессию и управляет commit/rollback запроса.

    При успешном завершении зависимость фиксирует транзакцию. При исключении
    откатывает её и повторно выбрасывает исходную ошибку.
    """
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
