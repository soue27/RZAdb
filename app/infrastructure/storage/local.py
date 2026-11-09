from pathlib import Path

from app.infrastructure.storage.base import ObjectStorage


class LocalObjectStorage(ObjectStorage):
    """Локальное файловое хранилище для разработки и тестов."""

    def __init__(self, root: Path) -> None:
        """Сохраняет корневой каталог локального объектного хранилища.

        Args:
            root: Каталог, за пределы которого ключи объектов выходить не должны.
        """
        self.root = root

    def _get_path(self, key: str) -> Path:
        """Разрешает ключ объекта в абсолютный путь и защищает от path traversal.

        Args:
            key: Относительный ключ объекта.

        Returns:
            Абсолютный путь внутри корневого каталога.

        Raises:
            ValueError: Если путь выходит за пределы root.
        """
        path = (self.root / key).resolve()

        if not path.is_relative_to(self.root.resolve()):
            raise ValueError("Некорректный ключ объекта.")

        return path

    async def upload(
        self,
        *,
        key: str,
        content: bytes,
    ) -> None:
        """Сохраняет бинарное содержимое по ключу, создавая необходимые каталоги.

        Args:
            key: Ключ объекта.
            content: Содержимое файла.
        """
        path = self._get_path(key)

        path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        path.write_bytes(content)

    async def download(
        self,
        *,
        key: str,
    ) -> bytes:
        """Читает объект по ключу.

        Args:
            key: Ключ объекта.

        Returns:
            Содержимое файла.

        Raises:
            FileNotFoundError: Если объект отсутствует.
        """
        path = self._get_path(key)

        if not path.exists():
            raise FileNotFoundError(key)

        return path.read_bytes()

    async def delete(
        self,
        *,
        key: str,
    ) -> None:
        """Удаляет объект, если он существует.

        Args:
            key: Ключ объекта.
        """
        path = self._get_path(key)

        if path.exists():
            path.unlink()

    async def move(self, *, source_key: str, target_key: str) -> None:
        """Перемещает объект на новый ключ в пределах корневого каталога.

        Args:
            source_key: Исходный ключ.
            target_key: Целевой ключ.

        Raises:
            FileNotFoundError: Если исходный объект отсутствует.
        """
        source = self._get_path(source_key)
        target = self._get_path(target_key)
        if not source.is_file():
            raise FileNotFoundError(source_key)
        target.parent.mkdir(parents=True, exist_ok=True)
        source.replace(target)

    async def exists(
        self,
        *,
        key: str,
    ) -> bool:
        """Проверяет, что ключ соответствует существующему файлу.

        Args:
            key: Ключ объекта.

        Returns:
            True, если объект существует и является файлом.
        """
        return self._get_path(key).is_file()
