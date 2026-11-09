import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import PurePosixPath
from uuid import UUID

from uuid6 import uuid7

from app.application.files.repository import FileRepository
from app.application.files.validation import (
    MIME_TYPES_BY_EXTENSION,
    validate_upload,
)
from app.domain.file import File
from app.infrastructure.storage.base import ObjectStorage

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class QuarantinedObject:
    """Описывает перемещение объекта из исходного ключа в карантин хранилища.
    """
    original_key: str
    quarantine_key: str


class FileQuarantine:
    """Временно изолирует объекты хранилища до фиксации удаления в базе данных."""

    def __init__(self, storage: ObjectStorage) -> None:
        """Сохраняет адаптер объектного хранилища.

        Args:
            storage: Хранилище, поддерживающее проверку, перемещение и удаление объектов.
        """
        self.storage = storage

    async def prepare(self, keys: list[str]) -> list[QuarantinedObject]:
        """Перемещает уникальные объекты в карантин до фиксации удаления в базе данных.

        Если перемещение любого объекта завершается ошибкой, ранее перемещённые
        объекты восстанавливаются.

        Args:
            keys: Ключи объектов, которые требуется временно изолировать.

        Returns:
            Список соответствий исходных и карантинных ключей.
        """
        moved: list[QuarantinedObject] = []
        try:
            for key in dict.fromkeys(keys):
                if not await self.storage.exists(key=key):
                    raise FileNotFoundError("Связанный файл не найден.")
                target = f".quarantine/{uuid7()}/{PurePosixPath(key).name}"
                item = QuarantinedObject(key, target)
                await self.storage.move(source_key=key, target_key=target)
                moved.append(item)
        except Exception:
            await self.restore(moved)
            raise
        return moved

    async def restore(self, items: list[QuarantinedObject]) -> None:
        """Возвращает объекты из карантина на исходные ключи в обратном порядке.

        Args:
            items: Результат предварительного перемещения.
        """
        for item in reversed(items):
            try:
                if await self.storage.exists(key=item.quarantine_key):
                    await self.storage.move(
                        source_key=item.quarantine_key,
                        target_key=item.original_key,
                    )
            except Exception:
                logger.exception("Не удалось восстановить файл из карантина.")
                raise

    async def purge(self, items: list[QuarantinedObject]) -> None:
        """Окончательно удаляет объекты из карантина.

        Вызывается после успешной фиксации удаления метаданных в базе данных.

        Args:
            items: Объекты, которые требуется удалить из карантина.
        """
        for item in items:
            try:
                await self.storage.delete(key=item.quarantine_key)
            except Exception:
                logger.exception("Не удалось очистить карантин файла.")
                raise

class FileService:
    """Управляет загрузкой, чтением и архивированием файловых объектов и их метаданных.
    """
    def __init__(
        self,
        repository: FileRepository,
        storage: ObjectStorage,
    ) -> None:
        """Сохраняет репозиторий метаданных и адаптер объектного хранилища.

        Args:
            repository: Репозиторий файлов.
            storage: Объектное хранилище бинарного содержимого.
        """
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
        """Проверяет и загружает файл в хранилище, затем создаёт его метаданные.

        Ключ формируется приложением. Если загрузка или сохранение метаданных
        завершается ошибкой, выполняется попытка удалить загруженный объект.

        Args:
            actor_id: Идентификатор пользователя, загрузившего файл.
            content: Бинарное содержимое.
            original_name: Исходное имя файла.
            display_name: Имя для отображения в интерфейсе.
            extension: Заявленное расширение.
            mime_type: Переданный MIME-тип; фактический тип определяется по разрешённому расширению.

        Returns:
            Созданные метаданные файла.

        Raises:
            FileUploadValidationError: Если расширение или размер не допускаются.
            Exception: Если хранилище или репозиторий не смогли завершить операцию.
        """
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

        try:
            await self.storage.upload(
                key=key,
                content=content,
            )
        except Exception:
            try:
                await self.storage.delete(key=key)
            except Exception:
                logger.exception(
                    "Не удалось удалить объект после ошибки загрузки: key=%s",
                    key,
                )
            raise

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
        """Скачивает бинарное содержимое файла из объектного хранилища.

        Args:
            file: Метаданные файла.

        Returns:
            Содержимое файла в байтах.
        """
        return await self.storage.download(key=file.s3_key)

    async def archive(
        self,
        *,
        file_id: UUID,
        user_id: UUID,
    ) -> File:
        """Помечает метаданные файла как архивные без физического удаления объекта.

        Args:
            file_id: Идентификатор файла.
            user_id: Идентификатор пользователя, выполняющего архивирование.

        Returns:
            Обновлённые метаданные файла.

        Raises:
            FileNotFoundError: Если файл не найден.
            ValueError: Если файл уже находится в архиве.
        """
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
