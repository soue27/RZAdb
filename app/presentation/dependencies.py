from pathlib import Path
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.files.repository import FileRepository
from app.application.files.service import FileService
from app.infrastructure.database.session import get_session
from app.infrastructure.storage.base import ObjectStorage
from app.infrastructure.storage.local import LocalObjectStorage


def get_object_storage() -> ObjectStorage:
    return LocalObjectStorage(
        root=Path("data/uploads"),
    )


def get_file_service(
    session: Annotated[AsyncSession, Depends(get_session)],
    storage: Annotated[ObjectStorage, Depends(get_object_storage)],
) -> FileService:
    repository = FileRepository(session)

    return FileService(
        repository=repository,
        storage=storage,
    )