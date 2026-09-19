from uuid import UUID

from app.application.access.service import AccessService
from app.application.programs.repository import ProgramRepository
from app.domain.enums import ProgramType
from app.domain.program import Program


class ProgramService:
    def __init__(
        self,
        repository: ProgramRepository,
        access_service: AccessService,
    ) -> None:
        self.repository = repository
        self.access_service = access_service

    async def get_by_urza(
        self,
        user_id: UUID,
        urza_id: UUID,
    ) -> list[Program]:
        if not await self.access_service.can_access_urza(
            user_id,
            urza_id,
        ):
            raise PermissionError("Доступ к URZA запрещён")

        return await self.repository.get_by_urza_id(
            urza_id,
        )

    async def get_by_id(
        self,
        user_id: UUID,
        program_id: UUID,
        urza_id: UUID,
    ) -> Program | None:
        if not await self.access_service.can_access_urza(
            user_id,
            urza_id,
        ):
            raise PermissionError("Доступ к URZA запрещён")

        return await self.repository.get_by_id(
            program_id,
        )

    async def get_by_task(
        self,
        user_id: UUID,
        task_id: UUID,
        urza_id: UUID,
    ) -> Program | None:
        if not await self.access_service.can_access_urza(
            user_id,
            urza_id,
        ):
            raise PermissionError("Доступ к URZA запрещён")

        return await self.repository.get_by_task_id(
            task_id,
        )

    async def create(
        self,
        user_id: UUID,
        urza_id: UUID,
        program_type: ProgramType,
        program_number: str,
        scan_file_id: UUID,
        editable_file_id: UUID | None = None,
        task_id: UUID | None = None,
    ) -> Program:
        if not await self.access_service.can_access_urza(
            user_id,
            urza_id,
        ):
            raise PermissionError("Доступ к URZA запрещён")

        program = Program(
            urza_id=urza_id,
            program_type=program_type,
            program_number=program_number,
            scan_file_id=scan_file_id,
            editable_file_id=editable_file_id,
            task_id=task_id,
        )

        await self.repository.add(program)

        return program