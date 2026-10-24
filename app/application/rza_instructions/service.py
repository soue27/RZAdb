from datetime import date
from uuid import UUID

from app.application.access.service import AccessService
from app.application.rza_instructions.repository import (
    RZAInstructionRepository,
)
from app.application.rza_instructions.schemas import (
    RZAInstructionDetails,
    RZAInstructionVersionDetails,
)
from app.domain.enums import DocumentStatus, UserRole
from app.domain.rza_instruction import (
    RZAInstruction,
    RZAInstructionVersion,
)


class RZAInstructionService:
    def __init__(
        self,
        repository: RZAInstructionRepository,
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
        raise PermissionError("Создавать инструкцию с текущей ролью запрещено.")

    def _to_version_details(
            self,
            version: RZAInstructionVersion,
    ) -> RZAInstructionVersionDetails:
        return RZAInstructionVersionDetails(
            id=version.id,
            version_number=version.version_number,
            effective_date=version.effective_date,
            change_description=version.change_description,
            change_justification=version.change_justification,
            created_at=version.created_at,
            created_by_full_name=(
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

    async def get_by_substation(
        self,
        user_id: UUID,
        substation_id: UUID,
    ) -> RZAInstruction | None:
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
        effective_date: date,
        scan_file_id: UUID,
        editable_file_id: UUID | None = None,
        change_description: str | None = None,
        change_justification: str | None = None,
        task_id: UUID | None = None,
    ) -> RZAInstruction:
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
                "Инструкция РЗА для данной подстанции уже существует"
            )

        instruction = RZAInstruction(
            substation_id=substation_id,
            created_by=user_id,
            updated_by=user_id,
        )
        initial_status = await self._status_for_creator(user_id)

        await self.repository.add_instruction(instruction)

        version = RZAInstructionVersion(
            rza_instruction_id=instruction.id,
            version_number=1,
            status=initial_status,
            task_id=task_id,
            effective_date=effective_date,
            change_description=change_description,
            change_justification=change_justification,
            created_by=user_id,
            updated_by=user_id,
            scan_file_id=scan_file_id,
            editable_file_id=editable_file_id,
        )

        await self.repository.add_version(version)

        return instruction

    async def get_current_version(
        self,
        user_id: UUID,
        substation_id: UUID,
    ) -> RZAInstructionVersion | None:
        if not await self.access_service.can_access_substation(
            user_id,
            substation_id,
        ):
            raise PermissionError("Доступ к подстанции запрещён")

        instruction = await self.repository.get_by_substation_id(
            substation_id,
        )

        if instruction is None:
            return None

        return await self.repository.get_current_version(
            instruction.id,
        )

    async def get_versions(
            self,
            user_id: UUID,
            substation_id: UUID,
    ) -> list[RZAInstructionVersionDetails]:
        if not await self.access_service.can_access_substation(
                user_id,
                substation_id,
        ):
            raise PermissionError("Доступ к подстанции запрещён")

        instruction = await self.repository.get_by_substation_id(
            substation_id,
        )

        if instruction is None:
            return []

        versions = await self.repository.get_versions(
            instruction.id,
        )

        return [
            self._to_version_details(version)
            for version in versions
        ]

    async def create_version(
        self,
        user_id: UUID,
        instruction_id: UUID,
        effective_date: date,
        scan_file_id: UUID,
        editable_file_id: UUID | None = None,
        change_description: str | None = None,
        change_justification: str | None = None,
        task_id: UUID | None = None,
    ) -> RZAInstructionVersion:
        instruction = await self.repository.get_by_id(
            instruction_id,
        )

        if instruction is None:
            raise ValueError("Инструкция РЗА не найдена")

        if not await self.access_service.can_modify_substation(
            user_id,
            instruction.substation_id,
        ):
            raise PermissionError("Изменение архивной подстанции запрещено")

        current_version = await self.repository.get_current_version(
            instruction_id,
        )

        if current_version is not None and current_version.status is DocumentStatus.UNDER_REVIEW:
            raise ValueError("Новая версия недоступна, пока текущая находится на согласовании.")
        initial_status = await self._status_for_creator(user_id)

        version_number = (
            current_version.version_number + 1
            if current_version is not None
            else 1
        )

        version = RZAInstructionVersion(
            rza_instruction_id=instruction_id,
            version_number=version_number,
            status=initial_status,
            task_id=task_id,
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
    ) -> RZAInstructionDetails | None:
        instruction = await self.get_by_substation(
            user_id=user_id,
            substation_id=substation_id,
        )

        if instruction is None:
            return None

        version = await self.repository.get_current_version(
            instruction.id,
        )

        if version is None:
            return None

        return RZAInstructionDetails(
            instruction_id=instruction.id,
            version_id=version.id,
            version_number=version.version_number,
            effective_date=version.effective_date,
            change_description=version.change_description,
            change_justification=version.change_justification,
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

    async def _get_accessible_version(
        self, user_id: UUID, version_id: UUID, substation_id: UUID
    ) -> RZAInstructionVersion:
        version = await self.repository.get_version_by_id(version_id)
        if version is None or version.deleted_at is not None:
            raise ValueError("Версия инструкции не найдена.")
        instruction = await self.repository.get_by_id(version.rza_instruction_id)
        if instruction is None or instruction.substation_id != substation_id:
            raise ValueError("Инструкция не принадлежит указанной подстанции.")
        if not await self.access_service.can_modify_substation(user_id, substation_id):
            raise PermissionError("Изменение архивной подстанции запрещено.")
        return version

    async def _check_reviewer(self, user_id: UUID, substation_id: UUID) -> None:
        user = await self.access_service.user_repository.get_by_id(user_id)
        substation = await self.access_service.substation_repository.get_by_id(substation_id)
        if user is None or not user.active or user.deleted_at is not None:
            raise PermissionError("Пользователь неактивен.")
        if user.role is not UserRole.MANAGER:
            raise PermissionError("Согласовывать инструкцию может только MANAGER.")
        if substation is None:
            raise ValueError("Подстанция не найдена.")
        if user.enterprise_id != substation.enterprise_id:
            raise PermissionError("MANAGER не отвечает за данную подстанцию.")
        if not await self.access_service.can_access_substation(user_id, substation_id):
            raise PermissionError("Доступ к подстанции запрещён.")

    async def submit_for_review(
        self, user_id: UUID, substation_id: UUID, version_id: UUID
    ) -> RZAInstructionVersion:
        version = await self._get_accessible_version(user_id, version_id, substation_id)
        user = await self.access_service.user_repository.get_by_id(user_id)
        if version.status is not DocumentStatus.DRAFT:
            raise ValueError("На согласование можно отправить только черновик.")
        if user is None or user.role not in {UserRole.ENGINEER, UserRole.ADMIN, UserRole.SUPERADMIN}:
            raise PermissionError("Отправить инструкцию может только автор документа.")
        if version.created_by != user_id:
            raise PermissionError("Отправить инструкцию может только её автор.")
        version.status = DocumentStatus.UNDER_REVIEW
        version.updated_by = user_id
        return await self.repository.save(version)

    async def review(
        self, user_id: UUID, substation_id: UUID, version_id: UUID, *, approve: bool
    ) -> RZAInstructionVersion:
        version = await self._get_accessible_version(user_id, version_id, substation_id)
        if version.status is not DocumentStatus.UNDER_REVIEW:
            raise ValueError("Решение доступно только для версии на согласовании.")
        await self._check_reviewer(user_id, substation_id)
        version.status = DocumentStatus.APPROVED if approve else DocumentStatus.DRAFT
        version.updated_by = user_id
        return await self.repository.save(version)

    async def get_available_actions(
        self, user_id: UUID, version: RZAInstructionVersion
    ) -> set[str]:
        user = await self.access_service.user_repository.get_by_id(user_id)
        if user is None or not user.active or user.deleted_at is not None:
            return set()
        version_record = await self.repository.get_version_by_id(version.id)
        if version_record is None or version_record.deleted_at is not None:
            return set()
        instruction = await self.repository.get_by_id(
            version_record.rza_instruction_id
        )
        if (
            instruction is None
            or instruction.deleted_at is not None
            or not await self.access_service.can_modify_substation(
                user_id, instruction.substation_id
            )
        ):
            return set()
        if version_record.status is DocumentStatus.DRAFT:
            return {"submit", "new_version"} if version_record.created_by == user_id and user.role in {
                UserRole.ENGINEER, UserRole.ADMIN, UserRole.SUPERADMIN
            } else set()
        if version_record.status is DocumentStatus.UNDER_REVIEW:
            try:
                await self._check_reviewer(user_id, instruction.substation_id)
            except (PermissionError, ValueError):
                return set()
            return {"approve", "return"}
        return {"new_version"} if user.role in {
            UserRole.ENGINEER, UserRole.ADMIN, UserRole.SUPERADMIN, UserRole.MANAGER
        } else set()
