from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.application.files.repository import FileRepository
from app.domain.file import File
from app.infrastructure.database.engine import async_session_factory


def create_file() -> File:
    return File(
        s3_key=f"files/test/{uuid4()}.pdf",
        original_name="document.pdf",
        display_name="Тестовый документ.pdf",
        extension=".pdf",
        size=1024,
        mime_type="application/pdf",
        uploaded_at=datetime.now(timezone.utc),
    )


@pytest.mark.asyncio
async def test_add_file() -> None:
    async with async_session_factory() as session:
        repository = FileRepository(session)

        file = create_file()

        result = await repository.add(file)

        assert result is file
        assert result.id is not None
        assert result.s3_key == file.s3_key


@pytest.mark.asyncio
async def test_get_by_id() -> None:
    async with async_session_factory() as session:
        repository = FileRepository(session)

        file = create_file()
        await repository.add(file)

        result = await repository.get_by_id(file.id)

        assert result is not None
        assert result.id == file.id
        assert result.s3_key == file.s3_key


@pytest.mark.asyncio
async def test_get_by_id_returns_none_for_missing_file() -> None:
    async with async_session_factory() as session:
        repository = FileRepository(session)

        result = await repository.get_by_id(uuid4())

        assert result is None


@pytest.mark.asyncio
async def test_get_by_s3_key() -> None:
    async with async_session_factory() as session:
        repository = FileRepository(session)

        file = create_file()
        await repository.add(file)

        result = await repository.get_by_s3_key(file.s3_key)

        assert result is not None
        assert result.id == file.id
        assert result.s3_key == file.s3_key


@pytest.mark.asyncio
async def test_get_by_s3_key_returns_none_for_missing_file() -> None:
    async with async_session_factory() as session:
        repository = FileRepository(session)

        result = await repository.get_by_s3_key(
            f"files/test/{uuid4()}.pdf",
        )

        assert result is None