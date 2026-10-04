from datetime import date
from uuid import UUID

from app.application.access.service import AccessService
from app.application.urza_instructions.repository import URZAInstructionRepository
from app.application.urzas.repository import URZARepository
from app.application.users.repository import UserRepository
from app.domain.enums import DocumentStatus, UserRole
from app.domain.urza_instruction import URZAInstruction, URZAInstructionVersion


_AUTHOR_ROLES = {UserRole.ENGINEER, UserRole.ADMIN, UserRole.SUPERADMIN}


class URZAInstructionService:
    def __init__(
        self,
        repository: URZAInstructionRepository,
        access_service: AccessService,
        user_repository: UserRepository,
        urza_repository: URZARepository,
    ) -> None:
        self.repository = repository
        self.access_service = access_service
        self.user_repository = user_repository
        self.urza_repository = urza_repository

    async def _status_for_creator(self, user_id: UUID) -> DocumentStatus:
        user = await self.user_repository.get_by_id(user_id)
        if user is None:
            raise ValueError("Пользователь не найден.")
        if user.role is UserRole.MANAGER:
            return DocumentStatus.APPROVED
        if user.role in _AUTHOR_ROLES:
            return DocumentStatus.DRAFT
        raise PermissionError("Создавать инструкции с текущей ролью запрещено.")

    async def _check_manager_reviewer(self, user_id: UUID, urza_id: UUID) -> None:
        user = await self.user_repository.get_by_id(user_id)
        if user is None:
            raise ValueError("Пользователь не найден.")
        if not user.active or user.deleted_at is not None:
            raise PermissionError("Пользователь неактивен.")
        if user.role is not UserRole.MANAGER:
            raise PermissionError("Согласовывать инструкцию может только Manager.")
        urza = await self.urza_repository.get_by_id(urza_id)
        if urza is None:
            raise ValueError("URZA не найден.")
        if urza.connection is None or urza.connection.substation is None:
            raise ValueError("Не удалось определить Production Department URZA.")
        if user.enterprise_id != urza.connection.substation.enterprise_id:
            raise PermissionError("Manager не отвечает за данный Production Department.")

    async def _get_accessible_instruction(self, user_id: UUID, instruction_id: UUID) -> URZAInstruction:
        instruction = await self.repository.get_by_id(instruction_id)
        if instruction is None:
            raise ValueError("Инструкция РЗА не найдена.")
        if not await self.access_service.can_access_urza(user_id, instruction.urza_id):
            raise PermissionError("Доступ к URZA запрещён")
        return instruction

    async def get_by_urza(self, user_id: UUID, urza_id: UUID) -> URZAInstruction | None:
        if not await self.access_service.can_access_urza(user_id, urza_id):
            raise PermissionError("Доступ к URZA запрещён")
        return await self.repository.get_by_urza_id(urza_id)

    async def create(
        self, user_id: UUID, urza_id: UUID, effective_date: date,
        scan_file_id: UUID, editable_file_id: UUID | None = None,
        change_description: str | None = None,
        change_justification: str | None = None,
    ) -> URZAInstruction:
        if not await self.access_service.can_access_urza(user_id, urza_id):
            raise PermissionError("Доступ к URZA запрещён")
        status = await self._status_for_creator(user_id)
        if await self.repository.get_by_urza_id(urza_id) is not None:
            raise ValueError("Инструкция РЗА для данного URZA уже существует")
        instruction = URZAInstruction(urza_id=urza_id, created_by=user_id, updated_by=user_id)
        await self.repository.add_instruction(instruction)
        await self.repository.add_version(URZAInstructionVersion(
            urza_instruction_id=instruction.id, version_number=1, status=status,
            effective_date=effective_date, change_description=change_description,
            change_justification=change_justification, created_by=user_id,
            updated_by=user_id, scan_file_id=scan_file_id,
            editable_file_id=editable_file_id,
        ))
        return instruction

    async def get_current_version(self, user_id: UUID, urza_id: UUID) -> URZAInstructionVersion | None:
        instruction = await self.get_by_urza(user_id, urza_id)
        if instruction is None:
            return None
        return await self.repository.get_current_version(instruction.id)

    async def get_versions(self, user_id: UUID, urza_id: UUID) -> list[URZAInstructionVersion]:
        instruction = await self.get_by_urza(user_id, urza_id)
        if instruction is None:
            return []
        return await self.repository.get_versions(instruction.id)

    async def get_version_by_id(self, user_id: UUID, version_id: UUID) -> URZAInstructionVersion | None:
        version = await self.repository.get_version_by_id(version_id)
        if version is None:
            return None
        instruction = await self.repository.get_by_id(version.urza_instruction_id)
        if instruction is None:
            return None
        if not await self.access_service.can_access_urza(user_id, instruction.urza_id):
            raise PermissionError("Доступ к URZA запрещён")
        return version

    async def create_version(
        self, user_id: UUID, instruction_id: UUID, effective_date: date,
        scan_file_id: UUID, editable_file_id: UUID | None = None,
        change_description: str | None = None,
        change_justification: str | None = None,
    ) -> URZAInstructionVersion:
        instruction = await self._get_accessible_instruction(user_id, instruction_id)
        status = await self._status_for_creator(user_id)
        max_version = await self.repository.get_max_version_number(instruction_id)
        version = URZAInstructionVersion(
            urza_instruction_id=instruction.id,
            version_number=(max_version or 0) + 1,
            status=status,
            effective_date=effective_date,
            change_description=change_description,
            change_justification=change_justification,
            created_by=user_id,
            updated_by=user_id,
            scan_file_id=scan_file_id,
            editable_file_id=editable_file_id,
        )
        return await self.repository.add_version(version)

    async def submit_for_review(self, user_id: UUID, version_id: UUID, urza_id: UUID) -> URZAInstructionVersion:
        version = await self._get_accessible_version(user_id, version_id, urza_id)
        if version.status is not DocumentStatus.DRAFT:
            raise ValueError("На согласование можно отправить только черновик.")
        user = await self.user_repository.get_by_id(user_id)
        if user is None:
            raise ValueError("Пользователь не найден.")
        if user.role not in _AUTHOR_ROLES:
            raise PermissionError("Отправлять инструкцию на согласование может только ENGINEER, ADMIN или SUPERADMIN.")
        version.status = DocumentStatus.UNDER_REVIEW
        version.updated_by = user_id
        await self.repository.save(version)
        return version

    async def approve(self, user_id: UUID, version_id: UUID, urza_id: UUID) -> URZAInstructionVersion:
        version = await self._get_accessible_version(user_id, version_id, urza_id)
        if version.status is not DocumentStatus.UNDER_REVIEW:
            raise ValueError("Утвердить можно только версию на согласовании.")
        await self._check_manager_reviewer(user_id, urza_id)
        version.status = DocumentStatus.APPROVED
        version.updated_by = user_id
        await self.repository.save(version)
        return version

    async def return_to_draft(self, user_id: UUID, version_id: UUID, urza_id: UUID) -> URZAInstructionVersion:
        version = await self._get_accessible_version(user_id, version_id, urza_id)
        if version.status is not DocumentStatus.UNDER_REVIEW:
            raise ValueError("Вернуть в черновик можно только версию на согласовании.")
        await self._check_manager_reviewer(user_id, urza_id)
        version.status = DocumentStatus.DRAFT
        version.updated_by = user_id
        await self.repository.save(version)
        return version

    async def _get_accessible_version(self, user_id: UUID, version_id: UUID, urza_id: UUID) -> URZAInstructionVersion:
        version = await self.repository.get_version_by_id(version_id)
        if version is None:
            raise ValueError("Версия инструкции не найдена.")
        instruction = await self.repository.get_by_id(version.urza_instruction_id)
        if instruction is None:
            raise ValueError("Инструкция РЗА не найдена.")
        if instruction.urza_id != urza_id:
            raise ValueError("Инструкция не принадлежит указанной URZA.")
        if not await self.access_service.can_access_urza(user_id, urza_id):
            raise PermissionError("Доступ к URZA запрещён")
        return version

    async def get_available_actions(self, user_id: UUID, version: URZAInstructionVersion) -> set[str]:
        user = await self.user_repository.get_by_id(user_id)
        if user is None or not user.active or user.deleted_at is not None:
            return set()
        if version.status is DocumentStatus.DRAFT:
            return {"submit"} if user.role in _AUTHOR_ROLES else set()
        if version.status is DocumentStatus.UNDER_REVIEW and user.role is UserRole.MANAGER:
            try:
                instruction = await self.repository.get_by_id(version.urza_instruction_id)
                if instruction is None:
                    return set()
                await self._check_manager_reviewer(user_id, instruction.urza_id)
            except (PermissionError, ValueError):
                return set()
            return {"approve", "return"}
        if version.status is DocumentStatus.APPROVED:
            return {"new_version"} if user.role in _AUTHOR_ROLES | {UserRole.MANAGER} else set()
        return set()
