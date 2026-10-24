
from uuid import UUID

from app.application.access.service import AccessService
from app.application.programs.repository import ProgramRepository
from app.application.tasks.repository import TaskRepository
from app.application.tasks.service import TaskService
from app.application.urzas.repository import URZARepository
from app.application.users.repository import UserRepository
from app.domain.enums import (
    DocumentStatus,
    ProgramType,
    TaskStatus,
    TaskWorkType,
    UserRole,
)
from app.domain.program import Program


class ProgramService:
    def __init__(
        self,
        repository: ProgramRepository,
        access_service: AccessService,
        user_repository: UserRepository,
        urza_repository: URZARepository,
        task_repository: TaskRepository,
        task_service: TaskService,
    ) -> None:
        self.repository = repository
        self.access_service = access_service
        self.user_repository = user_repository
        self.urza_repository = urza_repository
        self.task_repository = task_repository
        self.task_service = task_service

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
        if not await self.access_service.can_modify_urza(user_id, program.urza_id):
            return set()

        actions: set[str] = set()

        if program.status is DocumentStatus.DRAFT:
            if user.role in {
                UserRole.ENGINEER,
                UserRole.ADMIN,
                UserRole.SUPERADMIN,
            }:
                actions.update({"submit", "edit"})

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


    async def _validate_task_for_result(
        self,
        user_id: UUID,
        urza_id: UUID,
        task_id: UUID,
    ):
        """Проверяет, можно ли создать программу по указанной задаче."""
        task = await self.task_repository.get_by_id(task_id)

        if task is None or task.deleted_at is not None:
            raise ValueError("Активная задача не найдена.")

        if task.work_type is not TaskWorkType.PROGRAM:
            raise ValueError(
                "Задача не предназначена для создания программы."
            )

        if task.urza_id != urza_id:
            raise ValueError("Задача относится к другому устройству РЗА.")

        if task.assigned_to != user_id:
            raise PermissionError(
                "Создать результат может только назначенный исполнитель задачи."
            )

        if task.status is not TaskStatus.IN_PROGRESS:
            raise ValueError(
                "Создавать результат можно только по задаче в работе."
            )

        existing_program = await self.repository.get_by_task_id(task_id)

        if existing_program is not None:
            raise ValueError("Для задачи уже существует программа.")

        return task

    async def validate_task_for_result(
        self,
        user_id: UUID,
        urza_id: UUID,
        task_id: UUID,
    ):
        """Проверяет доступ пользователя и допустимость создания результата."""
        if not await self.access_service.can_access_urza(
            user_id,
            urza_id,
        ):
            raise PermissionError(
                "Нет доступа к устройству РЗА."
            )

        return await self._validate_task_for_result(
            user_id=user_id,
            urza_id=urza_id,
            task_id=task_id,
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
        if not await self.access_service.can_modify_urza(
            user_id,
            urza_id,
        ):
            raise PermissionError("Изменение архивной URZA запрещено")
        user = await self.user_repository.get_by_id(user_id)

        if task_id is not None:
            await self._validate_task_for_result(
                user_id=user_id,
                urza_id=urza_id,
                task_id=task_id,
            )

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


    async def update(
        self,
        user_id: UUID,
        program_id: UUID,
        urza_id: UUID,
        program_type: ProgramType,
        program_number: str,
        scan_file_id: UUID | None = None,
        editable_file_id: UUID | None = None,
        remove_editable_file: bool = False,
    ) -> Program:
        """Обновляет черновик программы без изменения связанного задания."""
        if not await self.access_service.can_modify_urza(
            user_id,
            urza_id,
        ):
            raise PermissionError("Изменение архивной URZA запрещено")

        program = await self.repository.get_by_id(program_id)

        if program is None:
            raise ValueError("Программа не найдена.")

        if program.urza_id != urza_id:
            raise ValueError("Программа не принадлежит указанной URZA.")

        if program.status is not DocumentStatus.DRAFT:
            raise ValueError(
                "Редактировать можно только программу в статусе «Черновик»."
            )

        user = await self.user_repository.get_by_id(user_id)

        if user is None:
            raise ValueError("Пользователь не найден.")

        if not user.active or user.deleted_at is not None:
            raise PermissionError("Пользователь неактивен.")

        if user.role not in {
            UserRole.ENGINEER,
            UserRole.ADMIN,
            UserRole.SUPERADMIN,
        }:
            raise PermissionError(
                "Редактировать программу с текущей ролью запрещено."
            )

        normalized_number = program_number.strip()
        if not normalized_number:
            raise ValueError("Номер программы не может быть пустым.")

        if len(normalized_number) > 255:
            raise ValueError("Номер программы не должен превышать 255 символов.")

        program.program_type = program_type
        program.program_number = normalized_number

        if scan_file_id is not None:
            program.scan_file_id = scan_file_id

        if remove_editable_file:
            program.editable_file_id = None
        elif editable_file_id is not None:
            program.editable_file_id = editable_file_id

        program.updated_by = user_id

        await self.repository.save(program)

        return program


    async def submit_for_review(
            self,
            user_id: UUID,
            program_id: UUID,
            urza_id: UUID,
    ) -> Program:
        if not await self.access_service.can_modify_urza(user_id, urza_id):
            raise PermissionError("Изменение архивной URZA запрещено")

        program = await self.repository.get_by_id(program_id)

        if program is None:
            raise ValueError("Программа не найдена.")

        if program.urza_id != urza_id:
            raise ValueError("Программа не принадлежит указанной URZA.")

        if program.status is not DocumentStatus.DRAFT:
            raise ValueError("На согласование можно отправить только черновик.")

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

        # Если программа связана с заданием, синхронизируем workflow задания.
        if program.task_id is not None:
            task = await self.task_repository.get_by_id(program.task_id)

            if task is None or task.deleted_at is not None:
                raise ValueError("Связанное активное задание не найдено.")

            if task.work_type is not TaskWorkType.PROGRAM:
                raise ValueError("Связанное задание не предназначено для программы.")

            if task.urza_id != urza_id:
                raise ValueError("Задание относится к другому устройству РЗА.")

            if task.assigned_to != user_id:
                raise PermissionError(
                    "Отправить программу на согласование может "
                    "только назначенный исполнитель."
                )

            await self.task_service.complete_task(
                task=task,
                actor_id=user_id,
            )
            await self.task_service.submit_for_review(
                task=task,
                actor_id=user_id,
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
        if not await self.access_service.can_modify_urza(user_id, urza_id):
            raise PermissionError("Изменение архивной URZA запрещено")

        program = await self.repository.get_by_id(program_id)

        if program is None:
            raise ValueError("Программа не найдена.")

        if program.urza_id != urza_id:
            raise ValueError("Программа не принадлежит указанной URZA.")

        if program.status is not DocumentStatus.UNDER_REVIEW:
            raise ValueError(
                "Утвердить можно только программу на согласовании."
            )

        await self._check_manager_reviewer(user_id, urza_id)

        # Сначала утверждаем результат, затем закрываем связанное задание.
        program.status = DocumentStatus.APPROVED
        program.updated_by = user_id

        await self.repository.save(program)

        if program.task_id is not None:
            task = await self.task_repository.get_by_id(program.task_id)

            if task is None or task.deleted_at is not None:
                raise ValueError("Связанное активное задание не найдено.")

            if task.work_type is not TaskWorkType.PROGRAM:
                raise ValueError("Связанное задание не предназначено для программы.")

            if task.urza_id != urza_id:
                raise ValueError("Задание относится к другому устройству РЗА.")

            await self.task_service.close_task(
                task=task,
                actor_id=user_id,
            )

        return program

    async def return_to_draft(
            self,
            user_id: UUID,
            program_id: UUID,
            urza_id: UUID,
            comment: str | None = None,
    ) -> Program:
        if not await self.access_service.can_modify_urza(user_id, urza_id):
            raise PermissionError("Изменение архивной URZA запрещено")

        program = await self.repository.get_by_id(program_id)

        if program is None:
            raise ValueError("Программа не найдена.")

        if program.urza_id != urza_id:
            raise ValueError("Программа не принадлежит указанной URZA.")

        if program.status is not DocumentStatus.UNDER_REVIEW:
            raise ValueError(
                "Вернуть на доработку можно только программу на согласовании."
            )

        await self._check_manager_reviewer(user_id, urza_id)

        # Причина нужна для истории связанного задания.
        if program.task_id is not None:
            if not comment or not comment.strip():
                raise ValueError("Укажите причину возврата на доработку.")

            task = await self.task_repository.get_by_id(program.task_id)

            if task is None or task.deleted_at is not None:
                raise ValueError("Связанное активное задание не найдено.")

            if task.work_type is not TaskWorkType.PROGRAM:
                raise ValueError("Связанное задание не предназначено для программы.")

            if task.urza_id != urza_id:
                raise ValueError("Задание относится к другому устройству РЗА.")

            await self.task_service.return_for_revision(
                task=task,
                actor_id=user_id,
                comment=comment,
            )

        program.status = DocumentStatus.DRAFT
        program.updated_by = user_id

        await self.repository.save(program)

        return program

    async def list_standalone_under_review(
        self,
        user_id: UUID,
    ) -> list[Program]:
        user = await self.user_repository.get_by_id(user_id)

        if user is None or not user.active or user.deleted_at is not None:
            return []

        if user.role is not UserRole.MANAGER:
            return []

        programs = await self.repository.list_standalone_under_review()
        visible_programs = []

        for program in programs:
            if not await self.access_service.can_access_urza(
                user_id,
                program.urza_id,
            ):
                continue

            try:
                await self._check_manager_reviewer(
                    user_id=user_id,
                    urza_id=program.urza_id,
                )
            except (PermissionError, ValueError):
                continue

            visible_programs.append(program)

        return visible_programs

    async def list_standalone_work_items(
        self,
        user_id: UUID,
    ) -> list[Program]:
        user = await self.user_repository.get_by_id(user_id)
        if user is None or not user.active or user.deleted_at is not None:
            return []

        visible_programs = []
        for program in await self.repository.list_standalone_work_items():
            if program.status is DocumentStatus.DRAFT and program.created_by != user_id:
                continue
            if not await self.access_service.can_access_urza(user_id, program.urza_id):
                continue
            actions = await self.get_available_actions(user_id, program)

            if program.status is DocumentStatus.DRAFT and not actions.intersection(
                {"edit", "submit"}
            ):
                continue
            visible_programs.append(program)
        return visible_programs
