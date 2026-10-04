from uuid import UUID

from app.application.access.service import AccessService
from app.application.programs.repository import ProgramRepository
from app.application.users.repository import UserRepository
from app.application.urzas.repository import URZARepository
from app.domain.enums import DocumentStatus, ProgramType, UserRole
from app.domain.program import Program


class ProgramService:
    def __init__(
            self,
            repository: ProgramRepository,
            access_service: AccessService,
            user_repository: UserRepository,
            urza_repository: URZARepository,
    ) -> None:
        self.repository = repository
        self.access_service = access_service
        self.user_repository = user_repository
        self.urza_repository = urza_repository

    async def _check_manager_reviewer(
            self,
            user_id: UUID,
            urza_id: UUID,
    ) -> None:
        user = await self.user_repository.get_by_id(user_id)

        if user is None:
            raise ValueError("Пользователь не найден.")

        if not user.active or user.deleted_at is not None:
            raise PermissionError("Пользователь неактивен.")

        if user.role is not UserRole.MANAGER:
            raise PermissionError(
                "Согласовывать программы может только Manager."
            )

        urza = await self.urza_repository.get_by_id(urza_id)

        if urza is None:
            raise ValueError("URZA не найден.")

        if (
                urza.connection is None
                or urza.connection.substation is None
        ):
            raise ValueError(
                "Не удалось определить Production Department URZA."
            )

        if user.enterprise_id != urza.connection.substation.enterprise_id:
            raise PermissionError(
                "Manager не отвечает за данный Production Department."
            )

    async def get_available_actions(
        self,
        user_id: UUID,
        program: Program,
    ) -> set[str]:
        user = await self.user_repository.get_by_id(user_id)
        if user is None or not user.active or user.deleted_at is not None:
            return set()

        actions: set[str] = set()

        if program.status is DocumentStatus.DRAFT:
            if user.role in {
                UserRole.ENGINEER,
                UserRole.ADMIN,
                UserRole.SUPERADMIN,
            }:
                actions.add("submit")

        elif program.status is DocumentStatus.UNDER_REVIEW:
            if user.role is UserRole.MANAGER:
                try:
                    await self._check_manager_reviewer(
                        user_id=user_id,
                        urza_id=program.urza_id,
                    )
                except (PermissionError, ValueError):
                    pass
                else:
                    actions.update({"approve", "return"})

        return actions

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
        user = await self.user_repository.get_by_id(user_id)

        if user is None:
            raise ValueError("Пользователь не найден.")

        if user.role is UserRole.MANAGER:
            status = DocumentStatus.APPROVED
        elif user.role in {
            UserRole.ENGINEER,
            UserRole.ADMIN,
            UserRole.SUPERADMIN,
        }:
            status = DocumentStatus.DRAFT
        else:
            raise PermissionError(
                "Создавать программы с текущей ролью запрещено."
            )

        program = Program(
            urza_id=urza_id,
            program_type=program_type,
            program_number=program_number,
            status=status,
            scan_file_id=scan_file_id,
            editable_file_id=editable_file_id,
            task_id=task_id,
            created_by=user_id,
            updated_by=user_id,
        )

        await self.repository.add(program)

        return program

    async def submit_for_review(
        self,
        user_id: UUID,
        program_id: UUID,
        urza_id: UUID,
    ) -> Program:
        if not await self.access_service.can_access_urza(
            user_id,
            urza_id,
        ):
            raise PermissionError("Доступ к URZA запрещён")

        program = await self.repository.get_by_id(program_id)

        if program is None:
            raise ValueError("Программа не найдена.")

        if program.urza_id != urza_id:
            raise ValueError(
                "Программа не принадлежит указанной URZA."
            )

        if program.status is not DocumentStatus.DRAFT:
            raise ValueError(
                "На согласование можно отправить только черновик."
            )

        user = await self.user_repository.get_by_id(user_id)

        if user is None:
            raise ValueError("Пользователь не найден.")

        if user.role not in {
            UserRole.ENGINEER,
            UserRole.ADMIN,
            UserRole.SUPERADMIN,
        }:
            raise PermissionError(
                "Отправлять программу на согласование "
                "может только ENGINEER, ADMIN или SUPERADMIN."
            )

        program.status = DocumentStatus.UNDER_REVIEW
        program.updated_by = user_id

        await self.repository.save(program)

        return program

    async def approve(
        self,
        user_id: UUID,
        program_id: UUID,
        urza_id: UUID,
    ) -> Program:
        if not await self.access_service.can_access_urza(
            user_id,
            urza_id,
        ):
            raise PermissionError("Доступ к URZA запрещён")

        program = await self.repository.get_by_id(program_id)

        if program is None:
            raise ValueError("Программа не найдена.")

        if program.urza_id != urza_id:
            raise ValueError(
                "Программа не принадлежит указанной URZA."
            )

        if program.status is not DocumentStatus.UNDER_REVIEW:
            raise ValueError(
                "Утвердить можно только программу "
                "на согласовании."
            )

        await self._check_manager_reviewer(
            user_id,
            urza_id,
        )

        program.status = DocumentStatus.APPROVED
        program.updated_by = user_id

        await self.repository.save(program)

        return program

    async def return_to_draft(
        self,
        user_id: UUID,
        program_id: UUID,
        urza_id: UUID,
    ) -> Program:
        if not await self.access_service.can_access_urza(
            user_id,
            urza_id,
        ):
            raise PermissionError("Доступ к URZA запрещён")

        program = await self.repository.get_by_id(program_id)

        if program is None:
            raise ValueError("Программа не найдена.")

        if program.urza_id != urza_id:
            raise ValueError(
                "Программа не принадлежит указанной URZA."
            )

        if program.status is not DocumentStatus.UNDER_REVIEW:
            raise ValueError(
                "Вернуть на доработку можно только программу "
                "на согласовании."
            )

        await self._check_manager_reviewer(
            user_id,
            urza_id,
        )

        program.status = DocumentStatus.DRAFT
        program.updated_by = user_id

        await self.repository.save(program)

        return program