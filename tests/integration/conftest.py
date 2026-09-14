import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.engine import async_session_factory


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    """Даёт тесту отдельную транзакцию и всегда откатывает её после теста."""

    async with async_session_factory() as session:
        transaction = await session.begin()

        try:
            yield session
        finally:
            await transaction.rollback()