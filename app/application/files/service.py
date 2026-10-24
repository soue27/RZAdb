import logging
from datetime import UTC, datetime
from pathlib import PurePosixPath
from uuid import UUID

from uuid6 import uuid7

from app.application.files.repository import FileRepository
from app.domain.file import File
from app.infrastructure.storage.base import ObjectStorage

from app.application.files.validation import (
    MIME_TYPES_BY_EXTENSION,
    validate_upload,
)

logger = logging.getLogger(__name__)

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
        actor_id: UUID,
        content: bytes,
        original_name: str,
        display_name: str,
        extension: str,
        mime_type: str,
    ) -> File:
        uploaded_at = datetime.now(UTC)

        normalized_extension = validate_upload(
            filename=original_name,
            extension=extension,
            content_size=len(content),
        )

        extension = normalized_extension.lstrip(".")
        mime_type = MIME_TYPES_BY_EXTENSION[normalized_extension]

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
            created_by=actor_id,
            updated_by=actor_id,
        )

        try:
            await self.repository.add(file)
        except Exception:
            try:
                await self.storage.delete(key=key)
            except Exception:
                logger.exception(
                    "Не удалось удалить загруженный объект после "
                    "ошибки сохранения метаданных: key=%s",
                    key,
                )
            raise

        return file

    async def discard_upload(self, file: File) -> None:
        """Удаляет объект, загруженный неудачной операцией."""
        await self.storage.delete(key=file.s3_key)

    async def read(self, file: File) -> bytes:
        return await self.storage.download(key=file.s3_key)

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
        file.updated_by = user_id

        await self.repository.save(file)

        return file
