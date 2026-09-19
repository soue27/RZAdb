from pathlib import Path

from app.infrastructure.storage.base import ObjectStorage
from app.infrastructure.storage.local import LocalObjectStorage


def get_object_storage() -> ObjectStorage:
    return LocalObjectStorage(
        root=Path("data/uploads"),
    )

