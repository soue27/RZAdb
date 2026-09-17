from datetime import date
from uuid import UUID

from app.application.access.service import AccessService
from app.application.rza_instructions.repository import (
    RZAInstructionRepository,
)
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
    ) -> RZAInstruction:
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
                "Инструкция РЗА для данной подстанции уже существует"
            )

        instruction = RZAInstruction(
            substation_id=substation_id,
        )

        await self.repository.add_instruction(instruction)

        version = RZAInstructionVersion(
            rza_instruction_id=instruction.id,
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

    async def create_version(
        self,
        user_id: UUID,
        instruction_id: UUID,
        effective_date: date,
        scan_file_id: UUID,
        editable_file_id: UUID | None = None,
        change_description: str | None = None,
        change_justification: str | None = None,
    ) -> RZAInstructionVersion:
        instruction = await self.repository.get_by_id(
            instruction_id,
        )

        if instruction is None:
            raise ValueError("Инструкция РЗА не найдена")

        if not await self.access_service.can_access_substation(
            user_id,
            instruction.substation_id,
        ):
            raise PermissionError("Доступ к подстанции запрещён")

        current_version = await self.repository.get_current_version(
            instruction_id,
        )

        version_number = (
            current_version.version_number + 1
            if current_version is not None
            else 1
        )

        version = RZAInstructionVersion(
            rza_instruction_id=instruction_id,
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