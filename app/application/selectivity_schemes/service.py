from datetime import date
from uuid import UUID

from app.application.access.service import AccessService
from app.application.selectivity_schemes.repository import (
    SelectivitySchemeRepository,
)
from app.application.selectivity_schemes.schemas import (
    SelectivitySchemeDetails,
    SelectivitySchemeVersionListItem,
)
from app.domain.selectivity_scheme import (
    SelectivityScheme,
    SelectivitySchemeVersion,
)


class SelectivitySchemeService:
    def __init__(
        self,
        repository: SelectivitySchemeRepository,
        access_service: AccessService,
    ) -> None:
        self.repository = repository
        self.access_service = access_service

    async def get_by_substation(
        self,
        user_id: UUID,
        substation_id: UUID,
    ) -> SelectivityScheme | None:
        if not await self.access_service.can_access_substation(
            user_id,
            substation_id,
        ):
            raise PermissionError("Доступ к подстанции запрещён")

        return await self.repository.get_by_substation_id(
            substation_id,
        )

    async def create(
        self,
        user_id: UUID,
        substation_id: UUID,
        number: str,
        name: str,
        effective_date: date,
        scan_file_id: UUID,
        editable_file_id: UUID | None = None,
        change_description: str | None = None,
        change_justification: str | None = None,
    ) -> SelectivityScheme:
        if not await self.access_service.can_access_substation(
            user_id,
            substation_id,
        ):
            raise PermissionError("Доступ к подстанции запрещён")

        existing = await self.repository.get_by_substation_id(
            substation_id,
        )

        if existing is not None:
            raise ValueError(
                "Схема селективности для данной подстанции уже существует"
            )

        scheme = SelectivityScheme(
            substation_id=substation_id,
        )

        await self.repository.add_scheme(scheme)

        version = SelectivitySchemeVersion(
            selectivity_scheme_id=scheme.id,
            version_number=1,
            number=number,
            name=name,
            effective_date=effective_date,
            change_description=change_description,
            change_justification=change_justification,
            created_by=user_id,
            scan_file_id=scan_file_id,
            editable_file_id=editable_file_id,
        )

        await self.repository.add_version(version)

        return scheme

    async def get_current_version(
        self,
        user_id: UUID,
        substation_id: UUID,
    ) -> SelectivitySchemeVersion | None:
        if not await self.access_service.can_access_substation(
            user_id,
            substation_id,
        ):
            raise PermissionError("Доступ к подстанции запрещён")

        scheme = await self.repository.get_by_substation_id(
            substation_id,
        )

        if scheme is None:
            return None

        return await self.repository.get_current_version(
            scheme.id,
        )

    async def get_versions(
        self,
        user_id: UUID,
        substation_id: UUID,
    ) -> list[SelectivitySchemeVersion]:
        if not await self.access_service.can_access_substation(
            user_id,
            substation_id,
        ):
            raise PermissionError("Доступ к подстанции запрещён")

        scheme = await self.repository.get_by_substation_id(
            substation_id,
        )

        if scheme is None:
            return []

        return await self.repository.get_versions(
            scheme.id,
        )

    async def create_version(
        self,
        user_id: UUID,
        scheme_id: UUID,
        number: str,
        name: str,
        effective_date: date,
        scan_file_id: UUID,
        editable_file_id: UUID | None = None,
        change_description: str | None = None,
        change_justification: str | None = None,
    ) -> SelectivitySchemeVersion:
        scheme = await self.repository.get_by_id(
            scheme_id,
        )

        if scheme is None:
            raise ValueError("Схема селективности не найдена")

        if not await self.access_service.can_access_substation(
            user_id,
            scheme.substation_id,
        ):
            raise PermissionError("Доступ к подстанции запрещён")

        current_version = await self.repository.get_current_version(
            scheme_id,
        )

        version_number = (
            current_version.version_number + 1
            if current_version is not None
            else 1
        )

        version = SelectivitySchemeVersion(
            selectivity_scheme_id=scheme_id,
            version_number=version_number,
            number=number,
            name=name,
            effective_date=effective_date,
            change_description=change_description,
            change_justification=change_justification,
            created_by=user_id,
            scan_file_id=scan_file_id,
            editable_file_id=editable_file_id,
        )

        await self.repository.add_version(version)

        return version

    async def get_details(
        self,
        user_id: UUID,
        substation_id: UUID,
    ) -> SelectivitySchemeDetails | None:
        scheme = await self.get_by_substation(
            user_id=user_id,
            substation_id=substation_id,
        )

        if scheme is None:
            return None

        version = await self.repository.get_current_version(
            scheme.id,
        )

        if version is None:
            return None

        return SelectivitySchemeDetails(
            scheme_id=scheme.id,
            version_id=version.id,
            version_number=version.version_number,
            number=version.number,
            name=version.name,
            effective_date=version.effective_date,
            change_description=version.change_description,
            change_justification=version.change_justification,
            created_by=version.created_by,
            creator_name=(
                version.creator.full_name
                if version.creator is not None
                else None
            ),
            scan_file_id=version.scan_file_id,
            scan_file_name=(
                version.scan_file.display_name
                if version.scan_file is not None
                else None
            ),
            editable_file_id=version.editable_file_id,
            editable_file_name=(
                version.editable_file.display_name
                if version.editable_file is not None
                else None
            ),
        )

    async def get_version_list(
        self,
        user_id: UUID,
        substation_id: UUID,
    ) -> list[SelectivitySchemeVersionListItem]:
        versions = await self.get_versions(
            user_id=user_id,
            substation_id=substation_id,
        )

        return [
            SelectivitySchemeVersionListItem(
                version_id=version.id,
                version_number=version.version_number,
                number=version.number,
                name=version.name,
                effective_date=version.effective_date,
                change_description=version.change_description,
                change_justification=version.change_justification,
                created_by=version.created_by,
                creator_name=(
                    version.creator.full_name
                    if version.creator is not None
                    else None
                ),
                scan_file_id=version.scan_file_id,
                scan_file_name=(
                    version.scan_file.display_name
                    if version.scan_file is not None
                    else None
                ),
                editable_file_id=version.editable_file_id,
                editable_file_name=(
                    version.editable_file.display_name
                    if version.editable_file is not None
                    else None
                ),
            )
            for version in versions
        ]