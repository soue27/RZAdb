import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.infrastructure.database.engine import engine


@pytest.mark.asyncio
async def test_database_connection() -> None:
    async with engine.connect() as connection:
        result = await connection.execute(text("SELECT 1"))

    assert result.scalar_one() == 1


@pytest.fixture(scope="session", autouse=True)
async def dispose_engine() -> None:
    yield
    await engine.dispose()