from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.file import File


class FileRepository:
    """Выполняет операции чтения и сохранения метаданных файлов.
    """
    def __init__(self, session: AsyncSession) -> None:
        """Сохраняет асинхронную SQLAlchemy-сессию.

        Args:
            session: Сессия текущей транзакции.
        """
        self.session = session

    async def get_by_id(
        self,
        file_id: UUID,
    ) -> File | None:
        """Находит метаданные файла по идентификатору.

        Args:
            file_id: Идентификатор файла.

        Returns:
        Файл или None.
        """
        return await self.session.get(
            File,
            file_id,
        )

    async def get_by_s3_key(
        self,
        s3_key: str,
    ) -> File | None:
        """Находит метаданные файла по ключу объекта в хранилище.

        Args:
            s3_key: Ключ объекта.

        Returns:
        Файл или None.
        """
        query = select(File).where(
            File.s3_key == s3_key,
        )

        return await self.session.scalar(query)

    async def add(
        self,
        file: File,
    ) -> File:
        """Добавляет метаданные нового файла и выполняет flush без commit.

        Args:
            file: Создаваемая модель файла.

        Returns:
        Добавленная модель файла.
        """
        self.session.add(file)
        await self.session.flush()

        return file

    async def save(
            self,
            file: File,
    ) -> File:
        """Синхронизирует изменения метаданных файла с базой данных без commit.

        Args:
            file: Изменённая модель файла.

        Returns:
        Та же модель файла.
        """
        await self.session.flush()
        return file