from pathlib import Path

from app.infrastructure.storage.base import ObjectStorage


class LocalObjectStorage(ObjectStorage):
    """Локальное файловое хранилище для разработки и тестов."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def _get_path(self, key: str) -> Path:
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
        path = self._get_path(key)

        if not path.exists():
            raise FileNotFoundError(key)

        return path.read_bytes()

    async def delete(
        self,
        *,
        key: str,
    ) -> None:
        path = self._get_path(key)

        if path.exists():
            path.unlink()

    async def exists(
        self,
        *,
        key: str,
    ) -> bool:
        return self._get_path(key).is_file()