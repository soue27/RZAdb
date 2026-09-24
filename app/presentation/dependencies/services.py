from pathlib import Path
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.access.service import AccessService
from app.application.auth.password import PasswordService
from app.application.auth.service import AuthService
from app.application.connections.repository import ConnectionRepository
from app.application.connections.service import ConnectionService
from app.application.enterprises.repository import EnterpriseRepository
from app.application.files.repository import FileRepository
from app.application.files.service import FileService
from app.application.inspections.inspection_repository import InspectionRepository
from app.application.inspections.inspection_service import InspectionService
from app.application.objects.resolver import ObjectResolver
from app.application.objects.service import ObjectService
from app.application.rza_instructions.repository import RZAInstructionRepository
from app.application.rza_instructions.service import RZAInstructionService
from app.application.selectivity_schemes.repository import (
    SelectivitySchemeRepository,
)
from app.application.selectivity_schemes.service import (
    SelectivitySchemeService,
)
from app.application.substations.repository import SubstationRepository
from app.application.substations.service import SubstationService
from app.application.tree.service import TreeService
from app.application.urzas.repository import URZARepository
from app.application.urzas.service import URZAService
from app.application.users.repository import UserRepository
from app.application.otd.repository import OTDRepository
from app.application.otd.service import OTDService
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

def get_access_service(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> AccessService:
    return AccessService(
        user_repository=UserRepository(session),
        substation_repository=SubstationRepository(session),
        enterprise_repository=EnterpriseRepository(session),
        connection_repository=ConnectionRepository(session),
        urza_repository=URZARepository(session),
    )


def get_tree_service(
    session: Annotated[AsyncSession, Depends(get_session)],
    access_service: Annotated[AccessService, Depends(get_access_service)],
) -> TreeService:
    return TreeService(
        enterprise_repository=EnterpriseRepository(session),
        substation_repository=SubstationRepository(session),
        connection_repository=ConnectionRepository(session),
        urza_repository=URZARepository(session),
        access_service=access_service,
    )


def get_object_resolver(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ObjectResolver:
    return ObjectResolver(
        substation_repository=SubstationRepository(session),
        connection_repository=ConnectionRepository(session),
        urza_repository=URZARepository(session),
    )


def get_object_service(
    session: Annotated[AsyncSession, Depends(get_session)],
    access_service: Annotated[AccessService, Depends(get_access_service)],
) -> ObjectService:
    return ObjectService(
        access_service=access_service,
        object_resolver=ObjectResolver(
            substation_repository=SubstationRepository(session),
            connection_repository=ConnectionRepository(session),
            urza_repository=URZARepository(session),
        ),
    )


def get_substation_service(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> SubstationService:
    return SubstationService(
        repository=SubstationRepository(session),
    )


def get_connection_service(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ConnectionService:
    return ConnectionService(
        repository=ConnectionRepository(session),
    )


def get_urza_service(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> URZAService:
    return URZAService(
        repository=URZARepository(session),
    )


def get_inspection_service(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> InspectionService:
    return InspectionService(
        repository=InspectionRepository(session),
    )


def get_rza_instruction_service(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> RZAInstructionService:
    return RZAInstructionService(
        repository=RZAInstructionRepository(session),
        access_service=AccessService(
            user_repository=UserRepository(session),
            enterprise_repository=EnterpriseRepository(session),
            substation_repository=SubstationRepository(session),
            connection_repository=ConnectionRepository(session),
            urza_repository=URZARepository(session),
        ),
    )


def get_selectivity_scheme_service(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> SelectivitySchemeService:
    return SelectivitySchemeService(
        repository=SelectivitySchemeRepository(session),
        access_service=AccessService(
            user_repository=UserRepository(session),
            enterprise_repository=EnterpriseRepository(session),
            substation_repository=SubstationRepository(session),
            connection_repository=ConnectionRepository(session),
            urza_repository=URZARepository(session),
        ),
    )


def get_otd_service(
    session: Annotated[AsyncSession, Depends(get_session)],
    access_service: Annotated[AccessService, Depends(get_access_service)],
) -> OTDService:
    return OTDService(
        repository=OTDRepository(session),
        access_service=access_service,
    )