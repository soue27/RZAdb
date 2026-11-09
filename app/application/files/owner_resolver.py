from uuid import UUID

from app.application.files.exceptions import AmbiguousFileOwnershipError
from app.application.files.owner_repository import FileOwnerRepository
from app.application.files.owners import FileOwner


class FileOwnerResolver:
    """Определяет единственного доменного владельца файла по существующим FK-связям.
    """
    def __init__(self, repository: FileOwnerRepository) -> None:
        """Сохраняет репозиторий для поиска ссылок на файл.

        Args:
            repository: Репозиторий владельцев файлов.
        """
        self.repository = repository

    async def resolve(self, file_id: UUID) -> FileOwner | None:
        """Возвращает единственного владельца файла или None, если ссылок нет.

        Если файл связан с несколькими разными владельцами, выбрасывает исключение,
        поскольку однозначно определить область доступа невозможно.

        Args:
            file_id: Идентификатор файла.

        Returns:
            Единственный владелец или None.

        Raises:
            AmbiguousFileOwnershipError: Если найдено несколько разных владельцев.
        """

        owners = await self.repository.get_owners_by_file_id(file_id)
        unique_owners = {
            (owner.owner_type, owner.owner_id): owner
            for owner in owners
        }

        if not unique_owners:
            return None

        if len(unique_owners) > 1:
            raise AmbiguousFileOwnershipError(file_id)

        return next(iter(unique_owners.values()))
