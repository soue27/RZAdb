from pathlib import Path

import pytest

from app.infrastructure.storage.local import LocalObjectStorage


@pytest.fixture
def storage(tmp_path: Path) -> LocalObjectStorage:
    return LocalObjectStorage(tmp_path)


@pytest.mark.asyncio
async def test_upload_and_download(
    storage: LocalObjectStorage,
) -> None:
    content = b"hello RZAdb"

    await storage.upload(
        key="documents/test.txt",
        content=content,
    )

    result = await storage.download(
        key="documents/test.txt",
    )

    assert result == content


@pytest.mark.asyncio
async def test_exists(
    storage: LocalObjectStorage,
) -> None:
    key = "documents/test.txt"

    assert await storage.exists(key=key) is False

    await storage.upload(
        key=key,
        content=b"test",
    )

    assert await storage.exists(key=key) is True


@pytest.mark.asyncio
async def test_delete(
    storage: LocalObjectStorage,
) -> None:
    key = "documents/test.txt"

    await storage.upload(
        key=key,
        content=b"test",
    )

    assert await storage.exists(key=key) is True

    await storage.delete(key=key)

    assert await storage.exists(key=key) is False


@pytest.mark.asyncio
async def test_download_missing_file(
    storage: LocalObjectStorage,
) -> None:
    with pytest.raises(FileNotFoundError):
        await storage.download(
            key="documents/missing.txt",
        )


@pytest.mark.asyncio
async def test_rejects_path_traversal(
    storage: LocalObjectStorage,
) -> None:
    with pytest.raises(ValueError, match="Некорректный ключ"):
        await storage.upload(
            key="../../secret.txt",
            content=b"secret",
        )

@pytest.mark.asyncio
async def test_rejects_absolute_path(
    storage: LocalObjectStorage,
) -> None:
    with pytest.raises(ValueError, match="Некорректный ключ"):
        await storage.upload(
            key="/tmp/secret.txt",
            content=b"secret",
        )