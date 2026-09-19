from typing import Annotated
from pathlib import Path

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.auth.password import PasswordService
from app.application.auth.service import AuthService
from app.application.users.repository import UserRepository
from app.infrastructure.database.session import get_session
from app.infrastructure.storage.base import ObjectStorage
from app.infrastructure.storage.local import LocalObjectStorage
from app.application.files.repository import FileRepository
from app.application.files.service import FileService


def get_object_storage() -> ObjectStorage:
    return LocalObjectStorage(root=Path("data/uploads"))

def get_file_service(
    session: Annotated[AsyncSession, Depends(get_session)],
    storage: Annotated[ObjectStorage, Depends(get_object_storage)],
) -> FileService:
    repository = FileRepository(session)

    return FileService(
        repository=repository,
        storage=storage,
    )

def get_password_service() -> PasswordService:
    return PasswordService()


def get_auth_service(
    session: Annotated[AsyncSession, Depends(get_session)],
    password_service: Annotated[PasswordService, Depends(get_password_service)],
) -> AuthService:
    return AuthService(
        user_repository=UserRepository(session),
        password_service=password_service,
    )