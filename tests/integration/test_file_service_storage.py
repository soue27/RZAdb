from pathlib import Path
from uuid6 import uuid7

import pytest

from app.application.files.repository import FileRepository
from app.application.files.service import FileService
from app.infrastructure.database.engine import async_session_factory
from app.infrastructure.storage.local import LocalObjectStorage


@pytest.mark.asyncio
async def test_file_service_uploads_content_to_local_storage(
    tmp_path: Path,
) -> None:
    storage = LocalObjectStorage(tmp_path)

    async with async_session_factory() as session:
        repository = FileRepository(session)

        service = FileService(
            repository=repository,
            storage=storage,
        )

        content = b"RZAdb test file content"

        file = await service.upload(
            content=content,
            original_name="test.pdf",
            display_name="Тестовый файл.pdf",
            extension=".pdf",
            mime_type="application/pdf",
        )

        stored_content = await storage.download(
            key=file.s3_key,
        )

        assert stored_content == content

        assert await storage.exists(
            key=file.s3_key,
        )

        await session.rollback()

@pytest.mark.asyncio
async def test_file_service_archive_keeps_content_in_storage(
    tmp_path: Path,
) -> None:
    storage = LocalObjectStorage(tmp_path)

    async with async_session_factory() as session:
        repository = FileRepository(session)

        service = FileService(
            repository=repository,
            storage=storage,
        )

        content = b"RZAdb archive test"

        file = await service.upload(
            content=content,
            original_name="archive.pdf",
            display_name="Архивный файл.pdf",
            extension=".pdf",
            mime_type="application/pdf",
        )

        user_id = uuid7()

        await service.archive(
            file_id=file.id,
            user_id=user_id,
        )

        await session.commit()

        stored_content = await storage.download(
            key=file.s3_key,
        )

        assert stored_content == content

        assert file.deleted_at is not None
        assert file.deleted_by == user_id