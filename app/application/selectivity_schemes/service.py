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
from app.domain.enums import DocumentStatus, UserRole
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

    async def _status_for_creator(self, user_id: UUID) -> DocumentStatus:
        user = await self.access_service.user_repository.get_by_id(user_id)
        if user is None or not user.active or user.deleted_at is not None:
            raise ValueError("Пользователь не найден или неактивен.")
        if user.role is UserRole.MANAGER:
            return DocumentStatus.APPROVED
        if user.role in {UserRole.ENGINEER, UserRole.ADMIN, UserRole.SUPERADMIN}:
            return DocumentStatus.DRAFT
        raise PermissionError("Создавать схему с текущей ролью запрещено.")

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
        task_id: UUID | None = None,
    ) -> SelectivityScheme:
        if not await self.access_service.can_modify_substation(
            user_id,
            substation_id,
        ):
            raise PermissionError("Изменение архивной подстанции запрещено")

        existing = await self.repository.get_by_substation_id(
            substation_id,
        )

        if existing is not None:
            raise ValueError(
                "Схема селективности для данной подстанции уже существует"
            )

        scheme = SelectivityScheme(
            substation_id=substation_id,
            created_by=user_id,
            updated_by=user_id,
        )
        initial_status = await self._status_for_creator(user_id)

        await self.repository.add_scheme(scheme)

        version = SelectivitySchemeVersion(
            selectivity_scheme_id=scheme.id,
            version_number=1,
            status=initial_status,
            task_id=task_id,
            number=number,
            name=name,
            effective_date=effective_date,
            change_description=change_description,
            change_justification=change_justification,
            created_by=user_id,
            updated_by=user_id,
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
        task_id: UUID | None = None,
    ) -> SelectivitySchemeVersion:
        scheme = await self.repository.get_by_id(
            scheme_id,
        )

        if scheme is None:
            raise ValueError("Схема селективности не найдена")

        if not await self.access_service.can_modify_substation(
            user_id,
            scheme.substation_id,
        ):
            raise PermissionError("Изменение архивной подстанции запрещено")

        current_version = await self.repository.get_current_version(
            scheme_id,
        )

        if current_version is not None and current_version.status is DocumentStatus.UNDER_REVIEW:
            raise ValueError("Новая версия недоступна, пока текущая находится на согласовании.")
        initial_status = await self._status_for_creator(user_id)

        version_number = (
            current_version.version_number + 1
            if current_version is not None
            else 1
        )

        version = SelectivitySchemeVersion(
            selectivity_scheme_id=scheme_id,
            version_number=version_number,
            status=initial_status,
            task_id=task_id,
            number=number,
            name=name,
            effective_date=effective_date,
            change_description=change_description,
            change_justification=change_justification,
            created_by=user_id,
            updated_by=user_id,
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
                status=version.status if isinstance(version.status, DocumentStatus) else DocumentStatus.DRAFT,
            )
            for version in versions
        ]

    async def _get_accessible_version(
        self, user_id: UUID, substation_id: UUID, version_id: UUID
    ) -> SelectivitySchemeVersion:
        version = await self.repository.get_version_by_id(version_id)
        if version is None or version.deleted_at is not None:
            raise ValueError("Версия схемы селективности не найдена.")
        scheme = await self.repository.get_by_id(version.selectivity_scheme_id)
        if scheme is None or scheme.substation_id != substation_id:
            raise ValueError("Схема не принадлежит указанной подстанции.")
        if not await self.access_service.can_modify_substation(user_id, substation_id):
            raise PermissionError("Изменение архивной подстанции запрещено.")
        return version

    async def _check_reviewer(self, user_id: UUID, substation_id: UUID) -> None:
        user = await self.access_service.user_repository.get_by_id(user_id)
        substation = await self.access_service.substation_repository.get_by_id(substation_id)
        if user is None or not user.active or user.deleted_at is not None:
            raise PermissionError("Пользователь неактивен.")
        if user.role is not UserRole.MANAGER:
            raise PermissionError("Согласовывать схему может только MANAGER.")
        if substation is None:
            raise ValueError("Подстанция не найдена.")
        if user.enterprise_id != substation.enterprise_id:
            raise PermissionError("MANAGER не отвечает за данную подстанцию.")
        if not await self.access_service.can_access_substation(user_id, substation_id):
            raise PermissionError("Доступ к подстанции запрещён.")

    async def submit_for_review(
        self, user_id: UUID, substation_id: UUID, version_id: UUID
    ) -> SelectivitySchemeVersion:
        version = await self._get_accessible_version(user_id, substation_id, version_id)
        user = await self.access_service.user_repository.get_by_id(user_id)
        if version.status is not DocumentStatus.DRAFT:
            raise ValueError("На согласование можно отправить только черновик.")
        if (
            user is None
            or user.role not in {UserRole.ENGINEER, UserRole.ADMIN, UserRole.SUPERADMIN}
            or version.created_by != user_id
        ):
            raise PermissionError("Отправить схему может только её автор.")
        version.status = DocumentStatus.UNDER_REVIEW
        version.updated_by = user_id
        return await self.repository.save(version)

    async def review(
        self, user_id: UUID, substation_id: UUID, version_id: UUID, *, approve: bool
    ) -> SelectivitySchemeVersion:
        version = await self._get_accessible_version(user_id, substation_id, version_id)
        if version.status is not DocumentStatus.UNDER_REVIEW:
            raise ValueError("Решение доступно только для версии на согласовании.")
        await self._check_reviewer(user_id, substation_id)
        version.status = DocumentStatus.APPROVED if approve else DocumentStatus.DRAFT
        version.updated_by = user_id
        return await self.repository.save(version)

    async def get_available_actions(
        self, user_id: UUID, version: SelectivitySchemeVersion
    ) -> set[str]:
        user = await self.access_service.user_repository.get_by_id(user_id)
        if user is None or not user.active or user.deleted_at is not None:
            return set()
        scheme = await self.repository.get_by_id(version.selectivity_scheme_id)
        if scheme is None or not await self.access_service.can_modify_substation(
            user_id, scheme.substation_id
        ):
            return set()
        if version.status is DocumentStatus.DRAFT:
            return {"submit", "new_version"} if version.created_by == user_id and user.role in {
                UserRole.ENGINEER, UserRole.ADMIN, UserRole.SUPERADMIN
            } else set()
        if version.status is DocumentStatus.UNDER_REVIEW:
            try:
                await self._check_reviewer(user_id, scheme.substation_id)
            except (PermissionError, ValueError):
                return set()
            return {"approve", "return"}
        return {"new_version"} if user.role in {
            UserRole.ENGINEER, UserRole.ADMIN, UserRole.SUPERADMIN, UserRole.MANAGER
        } else set()
