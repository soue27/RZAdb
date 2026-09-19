from abc import ABC, abstractmethod


class ObjectStorage(ABC):
    """Абстракция объектного хранилища."""

    @abstractmethod
    async def upload(
        self,
        *,
        key: str,
        content: bytes,
    ) -> None:
        """Сохранить объект."""
        raise NotImplementedError

    @abstractmethod
    async def download(
        self,
        *,
        key: str,
    ) -> bytes:
        """Получить объект."""
        raise NotImplementedError

    @abstractmethod
    async def delete(
        self,
        *,
        key: str,
    ) -> None:
        """Удалить объект."""
        raise NotImplementedError

    @abstractmethod
    async def exists(
        self,
        *,
        key: str,
    ) -> bool:
        """Проверить существование объекта."""
        raise NotImplementedError