from datetime import date
from uuid import UUID

from app.application.access.service import AccessService
from app.application.urza_instructions.repository import (
    URZAInstructionRepository,
)
from app.domain.urza_instruction import (
    URZAInstruction,
    URZAInstructionVersion,
)


class URZAInstructionService:
    def __init__(
        self,
        repository: URZAInstructionRepository,
        access_service: AccessService,
    ) -> None:
        self.repository = repository
        self.access_service = access_service

    async def get_by_urza(
        self,
        user_id: UUID,
        urza_id: UUID,
    ) -> URZAInstruction | None:
        if not await self.access_service.can_access_urza(
            user_id,
            urza_id,
        ):
            raise PermissionError("Доступ к URZA запрещён")

        return await self.repository.get_by_urza_id(
            urza_id,
        )

    async def create(
        self,
        user_id: UUID,
        urza_id: UUID,
        effective_date: date,
        scan_file_id: UUID,
        editable_file_id: UUID | None = None,
        change_description: str | None = None,
        change_justification: str | None = None,
    ) -> URZAInstruction:
        if not await self.access_service.can_access_urza(
            user_id,
            urza_id,
        ):
            raise PermissionError("Доступ к URZA запрещён")

        existing = await self.repository.get_by_urza_id(
            urza_id,
        )

        if existing is not None:
            raise ValueError(
                "Инструкция РЗА для данного URZA уже существует"
            )

        instruction = URZAInstruction(
            urza_id=urza_id,
        )

        await self.repository.add_instruction(instruction)

        version = URZAInstructionVersion(
            urza_instruction_id=instruction.id,
            version_number=1,
            effective_date=effective_date,
            change_description=change_description,
            change_justification=change_justification,
            created_by=user_id,
            scan_file_id=scan_file_id,
            editable_file_id=editable_file_id,
        )

        await self.repository.add_version(version)

        return instruction

    async def get_current_version(
        self,
        user_id: UUID,
        urza_id: UUID,
    ) -> URZAInstructionVersion | None:
        if not await self.access_service.can_access_urza(
            user_id,
            urza_id,
        ):
            raise PermissionError("Доступ к URZA запрещён")

        instruction = await self.repository.get_by_urza_id(
            urza_id,
        )

        if instruction is None:
            return None

        return await self.repository.get_current_version(
            instruction.id,
        )

    async def create_version(
        self,
        user_id: UUID,
        instruction_id: UUID,
        effective_date: date,
        scan_file_id: UUID,
        editable_file_id: UUID | None = None,
        change_description: str | None = None,
        change_justification: str | None = None,
    ) -> URZAInstructionVersion:
        instruction = await self.repository.get_by_id(
            instruction_id,
        )

        if instruction is None:
            raise ValueError("Инструкция РЗА не найдена")

        if not await self.access_service.can_access_urza(
            user_id,
            instruction.urza_id,
        ):
            raise PermissionError("Доступ к URZA запрещён")

        current_version = await self.repository.get_current_version(
            instruction_id,
        )

        version_number = (
            current_version.version_number + 1
            if current_version is not None
            else 1
        )

        version = URZAInstructionVersion(
            urza_instruction_id=instruction_id,
            version_number=version_number,
            effective_date=effective_date,
            change_description=change_description,
            change_justification=change_justification,
            created_by=user_id,
            scan_file_id=scan_file_id,
            editable_file_id=editable_file_id,
        )

        await self.repository.add_version(version)

        return version
