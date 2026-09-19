from datetime import UTC, datetime
from pathlib import PurePosixPath
from uuid import UUID

from uuid6 import uuid7

from app.application.files.repository import FileRepository
from app.domain.file import File
from app.infrastructure.storage.base import ObjectStorage


class FileService:
    def __init__(
        self,
        repository: FileRepository,
        storage: ObjectStorage,
    ) -> None:
        self.repository = repository
        self.storage = storage

    async def upload(
        self,
        *,
        content: bytes,
        original_name: str,
        display_name: str,
        extension: str,
        mime_type: str,
    ) -> File:
        uploaded_at = datetime.now(UTC)

        extension = extension.lstrip(".").lower()

        key = str(
            PurePosixPath(
                "files",
                str(uploaded_at.year),
                f"{uploaded_at.month:02d}",
                f"{uuid7()}.{extension}",
            )
        )

        await self.storage.upload(
            key=key,
            content=content,
        )

        file = File(
            s3_key=key,
            original_name=original_name,
            display_name=display_name,
            extension=f".{extension}",
            size=len(content),
            mime_type=mime_type,
            uploaded_at=uploaded_at,
        )

        await self.repository.add(file)

        return file

    async def download(
            self,
            *,
            file_id: UUID,
    ) -> bytes:
        file = await self.repository.get_by_id(file_id)

        if file is None:
            raise FileNotFoundError(file_id)

        return await self.storage.download(
            key=file.s3_key,
        )

    async def archive(
        self,
        *,
        file_id: UUID,
        user_id: UUID,
    ) -> File:
        file = await self.repository.get_by_id(file_id)

        if file is None:
            raise FileNotFoundError(file_id)

        if file.deleted_at is not None:
            raise ValueError("Файл уже находится в архиве.")

        file.deleted_at = datetime.now(UTC)
        file.deleted_by = user_id

        await self.repository.save(file)

        return file