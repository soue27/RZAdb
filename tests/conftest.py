from pathlib import Path

import pytest_asyncio
from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import AsyncSession

load_dotenv(Path(".env.test"), override=True)

from app.infrastructure.database.engine import async_session_factory, engine


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    """Даёт тесту отдельную транзакцию и откатывает её после теста."""

    async with async_session_factory() as session:
        transaction = await session.begin()

        try:
            yield session
        finally:
            await transaction.rollback()


@pytest_asyncio.fixture(autouse=True)
async def dispose_engine():
    yield
    await engine.dispose()