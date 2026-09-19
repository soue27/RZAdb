from unittest.mock import AsyncMock, MagicMock

from datetime import UTC, datetime
from uuid6 import uuid7

import pytest

from app.application.files.service import FileService
from app.domain.file import File


@pytest.fixture
def repository():
    repository = MagicMock()
    repository.add = AsyncMock()
    return repository


@pytest.fixture
def storage():
    storage = MagicMock()
    storage.upload = AsyncMock()
    return storage


@pytest.fixture
def service(repository, storage):
    return FileService(
        repository=repository,
        storage=storage,
    )


@pytest.mark.asyncio
async def test_upload_file(
    service,
    repository,
    storage,
):
    content = b"test file content"

    result = await service.upload(
        content=content,
        original_name="scan.pdf",
        display_name="Скан протокола.pdf",
        extension=".pdf",
        mime_type="application/pdf",
    )

    assert isinstance(result, File)
    assert result.original_name == "scan.pdf"
    assert result.display_name == "Скан протокола.pdf"
    assert result.extension == ".pdf"
    assert result.mime_type == "application/pdf"
    assert result.size == len(content)

    assert result.s3_key.startswith("files/")
    assert result.s3_key.endswith(".pdf")

    storage.upload.assert_awaited_once_with(
        key=result.s3_key,
        content=content,
    )

    repository.add.assert_awaited_once_with(result)


@pytest.mark.asyncio
async def test_upload_normalizes_extension(
    service,
    repository,
    storage,
):
    content = b"test"

    result = await service.upload(
        content=content,
        original_name="scan.PDF",
        display_name="Скан.pdf",
        extension=".PDF",
        mime_type="application/pdf",
    )

    assert result.extension == ".pdf"
    assert result.s3_key.endswith(".pdf")


@pytest.mark.asyncio
async def test_upload_accepts_extension_without_dot(
    service,
    repository,
    storage,
):
    content = b"test"

    result = await service.upload(
        content=content,
        original_name="scan.pdf",
        display_name="Скан.pdf",
        extension="PDF",
        mime_type="application/pdf",
    )

    assert result.extension == ".pdf"
    assert result.s3_key.endswith(".pdf")


@pytest.mark.asyncio
async def test_upload_stores_exact_content(
    service,
    repository,
    storage,
):
    content = b"\x00\x01\x02\x03test"

    result = await service.upload(
        content=content,
        original_name="data.bin",
        display_name="Данные",
        extension=".bin",
        mime_type="application/octet-stream",
    )

    storage.upload.assert_awaited_once_with(
        key=result.s3_key,
        content=content,
    )


@pytest.mark.asyncio
async def test_upload_sets_file_size_from_content(
    service,
    repository,
    storage,
):
    content = b"123456789"

    result = await service.upload(
        content=content,
        original_name="test.txt",
        display_name="Тест",
        extension=".txt",
        mime_type="text/plain",
    )

    assert result.size == 9

@pytest.mark.asyncio
async def test_download_file(
    service,
    repository,
    storage,
):
    file = File(
        s3_key="files/2026/09/test.pdf",
        original_name="test.pdf",
        display_name="Тестовый файл.pdf",
        extension=".pdf",
        size=4,
        mime_type="application/pdf",
        uploaded_at=datetime.now(UTC),
    )

    file_id = uuid7()
    file.id = file_id

    content = b"test"

    repository.get_by_id = AsyncMock(
        return_value=file,
    )
    storage.download = AsyncMock(
        return_value=content,
    )

    result = await service.download(
        file_id=file_id,
    )

    assert result == content

    repository.get_by_id.assert_awaited_once_with(
        file_id,
    )

    storage.download.assert_awaited_once_with(
        key=file.s3_key,
    )


@pytest.mark.asyncio
async def test_download_file_not_found(
    service,
    repository,
    storage,
):
    file_id = uuid7()

    repository.get_by_id = AsyncMock(
        return_value=None,
    )
    storage.download = AsyncMock()

    with pytest.raises(
        FileNotFoundError,
    ):
        await service.download(
            file_id=file_id,
        )

    repository.get_by_id.assert_awaited_once_with(
        file_id,
    )

    storage.download.assert_not_awaited()

@pytest.mark.asyncio
async def test_archive_file(
    service,
    repository,
    storage,
):
    file_id = uuid7()
    user_id = uuid7()

    file = File(
        s3_key="files/2026/09/test.pdf",
        original_name="test.pdf",
        display_name="Тестовый файл.pdf",
        extension=".pdf",
        size=4,
        mime_type="application/pdf",
        uploaded_at=datetime.now(UTC),
    )
    file.id = file_id

    repository.get_by_id = AsyncMock(
        return_value=file,
    )
    repository.save = AsyncMock()

    result = await service.archive(
        file_id=file_id,
        user_id=user_id,
    )

    assert result is file
    assert result.deleted_at is not None
    assert result.deleted_by == user_id

    repository.get_by_id.assert_awaited_once_with(
        file_id,
    )
    repository.save.assert_awaited_once_with(
        file,
    )
    storage.delete.assert_not_called()


@pytest.mark.asyncio
async def test_archive_missing_file(
    service,
    repository,
    storage,
):
    file_id = uuid7()
    user_id = uuid7()

    repository.get_by_id = AsyncMock(
        return_value=None,
    )
    repository.save = AsyncMock()

    with pytest.raises(
            FileNotFoundError,
    ):
        await service.archive(
            file_id=file_id,
            user_id=user_id,
        )

    repository.save.assert_not_awaited()
    storage.delete.assert_not_called()


@pytest.mark.asyncio
async def test_archive_already_archived_file(
    service,
    repository,
    storage,
):
    file_id = uuid7()
    user_id = uuid7()

    file = File(
        s3_key="files/2026/09/test.pdf",
        original_name="test.pdf",
        display_name="Тестовый файл.pdf",
        extension=".pdf",
        size=4,
        mime_type="application/pdf",
        uploaded_at=datetime.now(UTC),
    )
    file.id = file_id
    file.deleted_at = datetime.now(UTC)
    file.deleted_by = uuid7()

    repository.get_by_id = AsyncMock(
        return_value=file,
    )
    repository.save = AsyncMock()

    with pytest.raises(
            ValueError,
            match="уже находится в архиве",
    ):
        await service.archive(
            file_id=file_id,
            user_id=user_id,
        )

    repository.save.assert_not_awaited()
    storage.delete.assert_not_called()