import asyncio
from pathlib import Path
from uuid import UUID

import pytest
import pytest_asyncio
from dotenv import load_dotenv
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

load_dotenv(Path(".env.test"), override=True)

from app.core.config import get_settings
from app.domain.user import User
from app.infrastructure.database.engine import async_session_factory, engine


@pytest.fixture
def system_user_id() -> UUID:
    """Return the persisted technical user used by DB-backed test actors."""

    async def load_system_user_id() -> UUID:
        test_engine = create_async_engine(
            get_settings().database_url,
            poolclass=NullPool,
        )
        try:
            async with test_engine.connect() as connection:
                result = await connection.execute(
                    select(User.id).where(User.email == "system@rzadb.local")
                )
                return result.scalar_one()
        finally:
            await test_engine.dispose()

    return asyncio.run(load_system_user_id())


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
