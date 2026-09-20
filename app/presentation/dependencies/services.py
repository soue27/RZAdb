from pathlib import Path
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.access.service import AccessService
from app.application.auth.password import PasswordService
from app.application.auth.service import AuthService
from app.application.connections.repository import ConnectionRepository
from app.application.enterprises.repository import EnterpriseRepository
from app.application.files.repository import FileRepository
from app.application.files.service import FileService
from app.application.substations.repository import SubstationRepository
from app.application.tree.service import TreeService
from app.application.urzas.repository import URZARepository
from app.application.users.repository import UserRepository
from app.infrastructure.database.session import get_session
from app.infrastructure.storage.base import ObjectStorage
from app.infrastructure.storage.local import LocalObjectStorage


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

def get_tree_service(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> TreeService:
    return TreeService(
        enterprise_repository=EnterpriseRepository(session),
        substation_repository=SubstationRepository(session),
        connection_repository=ConnectionRepository(session),
        urza_repository=URZARepository(session),
        access_service=AccessService(
            user_repository=UserRepository(session),
            substation_repository=SubstationRepository(session),
            enterprise_repository=EnterpriseRepository(session),
            connection_repository=ConnectionRepository(session),
            urza_repository=URZARepository(session),
        ),
    )