from datetime import datetime, timedelta
from uuid import UUID

from app.application.access.service import AccessService
from app.application.tasks.repository import TaskRepository
from app.application.tasks.workflow import validate_reason, validate_transition
from app.application.urza_instructions.repository import URZAInstructionRepository
from app.domain.enums import (
    DocumentStatus,
    MaintenanceType,
    TaskStatus,
    TaskWorkType,
    UserRole,
)
from app.domain.task import Task
from app.domain.task_history import TaskHistory


class TaskService:
    """Сценарии работы с заданиями."""

    def __init__(
        self,
        task_repository: TaskRepository,
        access_service: AccessService,
        urza_instruction_repository: URZAInstructionRepository,
    ) -> None:
        self.task_repository = task_repository
        self.access_service = access_service
        self.urza_instruction_repository = urza_instruction_repository

    async def get_available_actions(
        self,
        *,
        task: Task,
        actor_id: UUID,
    ) -> set[str]:
        """Returns review actions the current actor can perform on a task."""
        if task.deleted_at is not None:
            return set()

        if task.status not in {
            TaskStatus.COMPLETED,
            TaskStatus.UNDER_REVIEW,
        }:
            return set()

        if task.status is TaskStatus.COMPLETED:
            return {"submit_for_review"} if task.assigned_to == actor_id else set()

        try:
            await self._check_reviewer_access(task=task, actor_id=actor_id)
        except (PermissionError, ValueError):
            return set()

        return {"close_task", "return_for_revision"}

    async def _check_reviewer_access(
        self,
        *,
        task: Task,
        actor_id: UUID,
    ) -> None:
        actor = await self.access_service.user_repository.get_by_id(actor_id)
        if actor is None:
            raise ValueError("Проверяющий пользователь не найден.")
        if not actor.active or actor.deleted_at is not None:
            raise PermissionError("Проверяющий пользователь неактивен.")
        if actor.role is not UserRole.MANAGER:
            raise PermissionError("Проверять задачу может только MANAGER.")
        if not await self.access_service.can_access_urza(actor_id, task.urza_id):
            raise PermissionError(
                "У MANAGER нет доступа к URZA, связанной с задачей."
            )

    async def can_issue_task(
        self,
        *,
        actor_id: UUID,
        urza_id: UUID,
    ) -> bool:
        actor = await self.access_service.user_repository.get_by_id(actor_id)

        if actor is None:
            return False

        if not actor.active or actor.deleted_at is not None:
            return False

        if actor.role not in {
            UserRole.MANAGER,
            UserRole.SUPERADMIN,
        }:
            return False

        return await self.access_service.can_access_urza(
            actor_id,
            urza_id,
        )

    async def create_task(
        self,
        *,
        urza_id: UUID,
        work_type: TaskWorkType,
        created_by: UUID,
        maintenance_type: MaintenanceType | None = None,
        description: str | None = None,
        now: datetime | None = None,
    ) -> Task:
        # Передаём время явно для тестируемости и фиксируем оба срока от одного момента.
        if not await self.can_issue_task(
                actor_id=created_by,
                urza_id=urza_id,
        ):
            raise PermissionError(
                "Пользователь не может выдавать задания для этого URZA."
            )
        created_at = now or datetime.now().astimezone()

        if work_type == TaskWorkType.MAINTENANCE and maintenance_type is None:
            raise ValueError(
                "Для задания на ТО необходимо указать maintenance_type."
            )

        if work_type != TaskWorkType.MAINTENANCE and maintenance_type is not None:
            raise ValueError(
                "maintenance_type указывается только для задания на ТО."
            )

        task = Task(
            urza_id=urza_id,
            work_type=work_type,
            maintenance_type=maintenance_type,
            description=description,
            created_by=created_by,
            updated_by=created_by,
            status=TaskStatus.CREATED,
            deadline_at=created_at + timedelta(days=7),
        )

        task.created_at = created_at

        await self.task_repository.create(task)

        history = TaskHistory(
            task_id=task.id,
            event_type="created",
            old_status=None,
            new_status=TaskStatus.CREATED,
            actor_id=created_by,
            comment=None,
            created_at=created_at,
        )

        self.task_repository.session.add(history)

        return task

    async def submit_for_review(
        self,
        *,
        task: Task,
        actor_id: UUID,
        submitted_at: datetime | None = None,
        comment: str | None = None,
    ) -> Task:
        """Назначенный исполнитель передаёт завершённую задачу на проверку."""
        validate_transition(task.status, TaskStatus.UNDER_REVIEW)
        if task.deleted_at is not None:
            raise ValueError("Нельзя отправить удалённое задание на согласование.")
        if task.assigned_to != actor_id:
            raise ValueError(
                "Отправить задание на согласование может только назначенный исполнитель."
            )

        review_time = submitted_at or datetime.now().astimezone()
        old_status = task.status
        task.status = TaskStatus.UNDER_REVIEW
        task.updated_by = actor_id

        await self.task_repository.save(task)
        self.task_repository.session.add(
            TaskHistory(
                task_id=task.id,
                event_type="sent_to_review",
                old_status=old_status,
                new_status=TaskStatus.UNDER_REVIEW,
                actor_id=actor_id,
                comment=comment.strip() if comment and comment.strip() else None,
                created_at=review_time,
            )
        )
        return task

    async def close_task(
        self,
        *,
        task: Task,
        actor_id: UUID,
        closed_at: datetime | None = None,
        comment: str | None = None,
    ) -> Task:
        """Закрывает задачу после проверки результата MANAGER."""
        validate_transition(task.status, TaskStatus.CLOSED)
        await self._check_reviewer_access(task=task, actor_id=actor_id)

        if task.work_type is TaskWorkType.SCHEMES:
            schema_record = await self.task_repository.get_schema_record_by_task_id(
                task.id
            )
            if (
                schema_record is None
                or schema_record.deleted_at is not None
                or schema_record.status is not DocumentStatus.APPROVED
            ):
                raise ValueError(
                    "Закрыть задачу по схемам можно только при наличии "
                    "активного утверждённого результата."
                )

        if task.work_type is TaskWorkType.INSTRUCTION:
            instruction = (
                await self.urza_instruction_repository.get_by_urza_id(
                    task.urza_id,
                )
            )

            if instruction is None:
                raise ValueError(
                    "Закрыть задачу по инструкции можно только при наличии инструкции."
                )

            instruction_version = (
                await self.urza_instruction_repository.get_latest_working_version(
                    instruction.id,
                )
            )

            if (
                    instruction_version is None
                    or instruction_version.created_at <= task.created_at
                    or instruction_version.status is not DocumentStatus.APPROVED
            ):
                raise ValueError(
                    "Закрыть задачу по инструкции можно только при наличии "
                    "активной утверждённой новой версии инструкции."
                )

        review_time = closed_at or datetime.now().astimezone()
        old_status = task.status
        task.status = TaskStatus.CLOSED
        task.closed_at = review_time
        task.updated_by = actor_id

        await self.task_repository.save(task)
        self.task_repository.session.add(
            TaskHistory(
                task_id=task.id,
                event_type="review_approved",
                old_status=old_status,
                new_status=TaskStatus.CLOSED,
                actor_id=actor_id,
                comment=comment.strip() if comment and comment.strip() else None,
                created_at=review_time,
            )
        )
        return task

    async def return_for_revision(
        self,
        *,
        task: Task,
        actor_id: UUID,
        returned_at: datetime | None = None,
        comment: str | None = None,
    ) -> Task:
        """Возвращает задачу исполнителю на доработку."""
        validate_transition(task.status, TaskStatus.IN_PROGRESS)
        await self._check_reviewer_access(task=task, actor_id=actor_id)

        review_time = returned_at or datetime.now().astimezone()
        old_status = task.status
        task.status = TaskStatus.IN_PROGRESS
        task.updated_by = actor_id

        await self.task_repository.save(task)
        self.task_repository.session.add(
            TaskHistory(
                task_id=task.id,
                event_type="review_rejected",
                old_status=old_status,
                new_status=TaskStatus.IN_PROGRESS,
                actor_id=actor_id,
                comment=comment.strip() if comment and comment.strip() else None,
                created_at=review_time,
            )
        )
        return task

    async def assign_task(
            self,
            *,
            task: Task,
            assigned_to: UUID,
            actor_id: UUID,
            assigned_at: datetime | None = None,
    ) -> Task:
        # Назначение возможно только из CREATED; переназначение обработаем отдельно.
        validate_transition(
            task.status,
            TaskStatus.ASSIGNED,
        )

        assignment_time = assigned_at or datetime.now().astimezone()

        task.assigned_to = assigned_to
        task.assigned_at = assignment_time
        task.acceptance_deadline_at = assignment_time + timedelta(days=1)
        task.status = TaskStatus.ASSIGNED
        task.updated_by = actor_id

        await self.task_repository.save(task)

        history = TaskHistory(
            task_id=task.id,
            event_type="assigned",
            old_status=TaskStatus.CREATED,
            new_status=TaskStatus.ASSIGNED,
            actor_id=actor_id,
            comment=None,
            created_at=assignment_time,
        )

        self.task_repository.session.add(history)

        return task


    async def accept_task(
        self,
        *,
        task: Task,
        actor_id: UUID,
        accepted_at: datetime | None = None,
    ) -> Task:
        # Принять задачу может только назначенный ей инженер.
        if task.assigned_to != actor_id:
            raise ValueError(
                "Принять задачу может только назначенный инженер."
            )

        validate_transition(
            task.status,
            TaskStatus.IN_PROGRESS,
        )

        acceptance_time = accepted_at or datetime.now().astimezone()

        old_status = task.status
        task.status = TaskStatus.IN_PROGRESS
        task.updated_by = actor_id

        await self.task_repository.save(task)

        # Сохраняем отдельное событие принятия, хотя статус меняется
        # только один раз: это позволяет восстановить реальную историю действий.
        accepted_history = TaskHistory(
            task_id=task.id,
            event_type="accepted",
            old_status=old_status,
            new_status=TaskStatus.IN_PROGRESS,
            actor_id=actor_id,
            comment=None,
            created_at=acceptance_time,
        )
        self.task_repository.session.add(accepted_history)

        started_history = TaskHistory(
            task_id=task.id,
            event_type="started",
            old_status=TaskStatus.IN_PROGRESS,
            new_status=TaskStatus.IN_PROGRESS,
            actor_id=actor_id,
            comment=None,
            created_at=acceptance_time,
        )
        self.task_repository.session.add(started_history)

        return task

    async def complete_task(
            self,
            *,
            task: Task,
            actor_id: UUID,
            completed_at: datetime | None = None,
    ) -> Task:
        """Завершает выполнение задачи после проверки результата работы."""
        # Завершить задачу может только назначенный ей инженер.
        if task.assigned_to != actor_id:
            raise ValueError(
                "Завершить задачу может только назначенный инженер."
            )

        # На этом этапе разрешён только переход IN_PROGRESS -> COMPLETED.
        validate_transition(
            task.status,
            TaskStatus.COMPLETED,
        )

        # Для ОТД результатом выполнения является новая версия ОТД,
        # созданная в рамках этой задачи.
        if task.work_type == TaskWorkType.OTD:
            otd_version = await self.task_repository.get_otd_version_by_task_id(
                task.id
            )

            if otd_version is None:
                raise ValueError(
                    "Для завершения задачи ОТД необходимо сохранить результат ОТД."
                )

        # Для схем результатом выполнения является SchemaRecord,
        # созданный в рамках этой задачи.
        if task.work_type == TaskWorkType.SCHEMES:
            schema_record = (
                await self.task_repository.get_schema_record_by_task_id(task.id)
            )

            if schema_record is None:
                raise ValueError(
                    "Для завершения задачи по схемам необходимо сохранить результат схем."
                )

            # Подписанный формуляр обязателен для завершения работы по схемам.
            if schema_record.signed_form_file_id is None:
                raise ValueError(
                    "Для завершения задачи по схемам необходим подписанный формуляр."
                )

            # Должен быть хотя бы один рабочий вариант схемы:
            # скан или редактируемый файл.
            if (
                    schema_record.scan_file_id is None
                    and schema_record.editable_file_id is None
            ):
                raise ValueError(
                    "Для завершения задачи по схемам необходим скан или редактируемый файл."
                )

        # Для уставок результатом выполнения является SettingsRecord,
        # созданный в рамках этой задачи.
        if task.work_type == TaskWorkType.SETTINGS:
            settings_record = (
                await self.task_repository.get_settings_record_by_task_id(task.id)
            )

            if settings_record is None:
                raise ValueError(
                    "Для завершения задачи по уставкам необходимо сохранить результат уставок."
                )

        # Для ТО результатом выполнения является TORecord,
        # созданный в рамках этой задачи.
        if task.work_type == TaskWorkType.MAINTENANCE:
            to_record = await self.task_repository.get_to_record_by_task_id(task.id)

            if to_record is None:
                raise ValueError(
                    "Для завершения задачи по ТО необходимо сохранить результат ТО."
                )

            # Результат должен соответствовать виду ТО, указанному в задаче.
            if to_record.maintenance_type != task.maintenance_type:
                raise ValueError(
                    "Вид ТО в результате не соответствует виду ТО в задаче."
                )

            # Для большинства видов ТО скан протокола обязателен.
            # ТК, О и ОСМ выполняются без протокола.
            protocol_not_required = {
                MaintenanceType.TK,
                MaintenanceType.O,
                MaintenanceType.OSM,
            }

            if (
                    task.maintenance_type not in protocol_not_required
                    and to_record.scan_protocol_id is None
            ):
                raise ValueError(
                    "Для завершения задачи по ТО необходим скан протокола."
                )

        # Для программы результатом выполнения является Program,
        # созданная в рамках этой задачи.
        if task.work_type == TaskWorkType.PROGRAM:
            program = await self.task_repository.get_program_by_task_id(task.id)

            if program is None:
                raise ValueError(
                    "Для завершения задачи по программе необходимо сохранить программу."
                )

        # Для инструкции результатом выполнения является новая версия
        # инструкции, созданная после выдачи задачи.
        if task.work_type == TaskWorkType.INSTRUCTION:
            instruction = (
                await self.urza_instruction_repository.get_by_urza_id(
                    task.urza_id,
                )
            )

            if instruction is None:
                raise ValueError(
                    "Для данного URZA не создана инструкция."
                )

            instruction_version = (
                await self.urza_instruction_repository.get_latest_working_version(
                    instruction.id,
                )
            )

            if instruction_version is None:
                raise ValueError(
                    "Для завершения задачи необходимо создать версию инструкции."
                )

            if instruction_version.created_at <= task.created_at:
                raise ValueError(
                    "Для завершения задачи необходимо создать новую версию инструкции."
                )

        completion_time = completed_at or datetime.now().astimezone()

        old_status = task.status
        task.status = TaskStatus.COMPLETED
        task.updated_by = actor_id
        task.completed_at = completion_time

        await self.task_repository.save(task)

        # История нужна для аудита действий и последующего отображения
        # хронологии работы с задачей.
        history = TaskHistory(
            task_id=task.id,
            event_type="completed",
            old_status=old_status,
            new_status=TaskStatus.COMPLETED,
            actor_id=actor_id,
            comment=None,
            created_at=completion_time,
        )

        self.task_repository.session.add(history)

        return task

    async def reject_task(
        self,
        *,
        task: Task,
        actor_id: UUID,
        reason: str,
        rejected_at: datetime | None = None,
    ) -> Task:
        # Отклонить задачу может только назначенный инженер.
        if task.assigned_to != actor_id:
            raise ValueError(
                "Отклонить задачу может только назначенный инженер."
            )

        validate_transition(
            task.status,
            TaskStatus.REJECTED,
        )
        validate_reason(reason)

        rejection_time = rejected_at or datetime.now().astimezone()

        old_status = task.status
        task.status = TaskStatus.REJECTED
        task.updated_by = actor_id

        await self.task_repository.save(task)

        history = TaskHistory(
            task_id=task.id,
            event_type="rejected",
            old_status=old_status,
            new_status=TaskStatus.REJECTED,
            actor_id=actor_id,
            comment=reason.strip(),
            created_at=rejection_time,
        )

        self.task_repository.session.add(history)

        return task


    async def reassign_task(
        self,
        *,
        task: Task,
        assigned_to: UUID,
        actor_id: UUID,
        assigned_at: datetime | None = None,
    ) -> Task:
        # Переназначение допустимо только для уже назначенной задачи.
        if task.status != TaskStatus.ASSIGNED:
            raise ValueError(
                "Переназначить можно только назначенную задачу."
            )

        assignment_time = assigned_at or datetime.now().astimezone()

        previous_assignee = task.assigned_to

        if previous_assignee == assigned_to:
            raise ValueError(
                "Новый исполнитель должен отличаться от текущего."
            )

        task.assigned_to = assigned_to
        task.assigned_at = assignment_time
        task.updated_by = actor_id

        # Основной deadline намеренно не меняем:
        # он считается от создания задачи и не зависит от переназначения.
        task.acceptance_deadline_at = assignment_time + timedelta(days=1)

        await self.task_repository.save(task)

        history = TaskHistory(
            task_id=task.id,
            event_type="reassigned",
            old_status=TaskStatus.ASSIGNED,
            new_status=TaskStatus.ASSIGNED,
            actor_id=actor_id,
            comment=None,
            created_at=assignment_time,
        )

        self.task_repository.session.add(history)

        return task
