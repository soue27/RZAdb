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
from app.domain.user import User


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


    @staticmethod
    def _ensure_task_is_active(task: Task) -> None:
        """Запрещает изменять архивное задание."""
        if task.deleted_at is not None:
            raise ValueError("Нельзя изменять удалённое задание.")

    async def _ensure_task_object_is_active(
        self, task: Task, actor_id: UUID
    ) -> None:
        has_access = (
            await self.access_service.can_modify_urza(actor_id, task.urza_id)
            if task.urza_id is not None
            else await self.access_service.can_modify_substation(
                actor_id, getattr(task, "substation_id", None)
            )
        )
        if not has_access:
            raise PermissionError("Нельзя изменять задание архивного объекта.")

    async def _lock_task_owner(self, task: Task) -> Task:
        original_urza_id = task.urza_id
        original_substation_id = getattr(task, "substation_id", None)

        if original_urza_id is not None:
            is_active = await self.access_service.urza_repository.lock_active_by_id(
                original_urza_id
            )
        elif original_substation_id is not None:
            is_active = await self.access_service.substation_repository.lock_active_by_id(
                original_substation_id
            )
        else:
            is_active = False

        if not is_active:
            raise PermissionError("Нельзя изменять задание архивного объекта.")

        refreshed_task = await self.task_repository.refresh_for_mutation(task)
        if (
            refreshed_task.urza_id != original_urza_id
            or getattr(refreshed_task, "substation_id", None)
            != original_substation_id
        ):
            raise PermissionError(
                "Объект задания изменился. Повторите операцию."
            )
        return refreshed_task

    async def _ensure_active_actor(self, actor_id: UUID) -> None:
        """Проверяет, что пользователь существует, активен и не удалён."""
        actor = await self.access_service.user_repository.get_by_id(actor_id)

        if actor is None:
            raise PermissionError("Пользователь не найден.")

        if not actor.active or actor.deleted_at is not None:
            raise PermissionError("Пользователь неактивен или удалён.")

    async def get_available_actions(
        self,
        *,
        task: Task,
        actor_id: UUID,
    ) -> set[str]:
        """Возвращает доступные действия с учётом статуса и прав пользователя."""
        if task.deleted_at is not None:
            return set()
        try:
            await self._ensure_task_object_is_active(task, actor_id)
        except PermissionError:
            return set()

        if task.status is TaskStatus.ASSIGNED:
            actions = set()

            if task.assigned_to == actor_id:
                actions.update({"accept_task", "reject_task"})

            if await self.can_issue_task(
                actor_id=actor_id,
                urza_id=task.urza_id,
                substation_id=getattr(task, "substation_id", None),
            ):
                actions.add("reassign_task")

            return actions

        if task.status is TaskStatus.IN_PROGRESS:
            if task.assigned_to == actor_id:
                actions = {"complete_task"}

                work_type = getattr(task, "work_type", None)
                if work_type is TaskWorkType.PROGRAM or (
                    getattr(task, "work_type", None) is TaskWorkType.MAINTENANCE
                    and await self.task_repository.get_to_record_by_task_id(task.id)
                    is None
                ) or (
                    work_type is TaskWorkType.OTD
                    and await self.task_repository.get_otd_version_by_task_id(
                        task.id
                    )
                    is None
                ):
                    actions.add("create_result")
                if getattr(task, "substation_id", None) is not None:
                    result = (
                        await self.task_repository.get_substation_instruction_version_by_task_id(task.id)
                        if work_type is TaskWorkType.INSTRUCTION
                        else await self.task_repository.get_selectivity_version_by_task_id(task.id)
                    )
                    if result is None:
                        actions.add("create_result")

                return actions

            return set()

        if task.status is TaskStatus.COMPLETED:
            if task.assigned_to == actor_id:
                return {"submit_for_review"}
            return set()

        if task.status is TaskStatus.UNDER_REVIEW:
            try:
                await self._check_reviewer_access(
                    task=task,
                    actor_id=actor_id,
                )
            except (PermissionError, ValueError):
                return set()

            return {"close_task", "return_for_revision"}

        return set()


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
        has_access = (
            await self.access_service.can_modify_urza(actor_id, task.urza_id)
            if task.urza_id is not None
            else await self.access_service.can_modify_substation(
                actor_id, getattr(task, "substation_id", None)
            )
        )
        if not has_access:
            raise PermissionError(
                "У MANAGER нет доступа к URZA, связанной с задачей."
            )

    async def can_issue_task(
        self,
        *,
        actor_id: UUID,
        urza_id: UUID | None = None,
        substation_id: UUID | None = None,
    ) -> bool:
        if (urza_id is None) == (substation_id is None):
            return False
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

        if substation_id is not None:
            substation = await self.access_service.substation_repository.get_by_id(
                substation_id
            )
            if substation is None or substation.deleted_at is not None:
                return False
            return await self.access_service.can_access_substation(
                actor_id, substation_id
            )
        urza = await self.access_service.urza_repository.get_by_id(urza_id)
        if urza is None or urza.deleted_at is not None:
            return False
        return await self.access_service.can_access_urza(actor_id, urza_id)

    async def get_available_assignees(
            self,
            *,
            actor_id: UUID,
            urza_id: UUID | None = None,
            substation_id: UUID | None = None,
    ) -> list[User]:
        if not await self.can_issue_task(
                actor_id=actor_id,
                urza_id=urza_id,
                substation_id=substation_id,
        ):
            raise PermissionError(
                "Пользователь не может выдавать задания для этого URZA."
            )

        if substation_id is not None:
            substation = await self.access_service.substation_repository.get_by_id(
                substation_id
            )
            if substation is None:
                raise ValueError("Подстанция не найдена.")
            enterprise_id = substation.enterprise_id
        else:
            urza = await self.access_service.urza_repository.get_by_id(urza_id)
            if urza is None:
                raise ValueError("URZA не найден.")
            enterprise_id = urza.connection.substation.enterprise_id

        return await (
            self.access_service.user_repository
            .get_active_engineers_by_enterprise(enterprise_id)
        )

    async def create_task(
        self,
        *,
        urza_id: UUID | None = None,
        substation_id: UUID | None = None,
        work_type: TaskWorkType,
        created_by: UUID,
        maintenance_type: MaintenanceType | None = None,
        description: str | None = None,
        deadline_at: datetime | None = None,
        now: datetime | None = None,
    ) -> Task:
        if urza_id is not None and substation_id is None:
            is_active = await self.access_service.urza_repository.lock_active_by_id(
                urza_id
            )
        elif substation_id is not None and urza_id is None:
            is_active = await self.access_service.substation_repository.lock_active_by_id(
                substation_id
            )
        else:
            is_active = False

        if not is_active:
            raise PermissionError(
                "Пользователь не может выдавать задания для этого URZA."
            )

        # Передаём время явно для тестируемости и фиксируем оба срока от одного момента.
        if not await self.can_issue_task(
                actor_id=created_by,
                urza_id=urza_id,
                substation_id=substation_id,
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

        if substation_id is not None and work_type not in {
            TaskWorkType.INSTRUCTION, TaskWorkType.SCHEMES
        }:
            raise ValueError("Для подстанции доступны только инструкции и схемы.")

        task = Task(
            urza_id=urza_id,
            substation_id=substation_id,
            work_type=work_type,
            maintenance_type=maintenance_type,
            description=description,
            created_by=created_by,
            updated_by=created_by,
            status=TaskStatus.CREATED,
            deadline_at=(
                deadline_at
                if deadline_at is not None
                else created_at + timedelta(days=7)
            ),
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
        task = await self._lock_task_owner(task)
        self._ensure_task_is_active(task)
        await self._ensure_task_object_is_active(task, actor_id)
        """Назначенный исполнитель передаёт завершённую задачу на проверку."""
        validate_transition(task.status, TaskStatus.UNDER_REVIEW)
        if task.deleted_at is not None:
            raise ValueError("Нельзя отправить удалённое задание на согласование.")
        if task.assigned_to != actor_id:
            raise ValueError(
                "Отправить задание на согласование может только назначенный исполнитель."
            )
        await self._ensure_active_actor(actor_id)

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
        task = await self._lock_task_owner(task)
        self._ensure_task_is_active(task)
        validate_transition(task.status, TaskStatus.CLOSED)
        await self._check_reviewer_access(task=task, actor_id=actor_id)

        if task.work_type is TaskWorkType.SCHEMES:
            if getattr(task, "substation_id", None) is not None:
                scheme_version = await self.task_repository.get_selectivity_version_by_task_id(task.id)
                if scheme_version is None or scheme_version.status is not DocumentStatus.APPROVED:
                    raise ValueError("Закрыть задачу можно после утверждения схемы селективности.")
            else:
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
            if getattr(task, "substation_id", None) is not None:
                instruction_version = await self.task_repository.get_substation_instruction_version_by_task_id(task.id)
                if instruction_version is None or instruction_version.status is not DocumentStatus.APPROVED:
                    raise ValueError("Закрыть задачу можно после утверждения инструкции РЗА.")
            else:
                instruction = await self.urza_instruction_repository.get_by_urza_id(task.urza_id)
                if instruction is None:
                    raise ValueError(
                        "Закрыть задачу по инструкции можно только при наличии инструкции."
                    )
                instruction_version = await self.urza_instruction_repository.get_latest_working_version(
                    instruction.id,
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
        task = await self._lock_task_owner(task)
        self._ensure_task_is_active(task)
        await self._ensure_task_object_is_active(task, actor_id)
        validate_transition(task.status, TaskStatus.IN_PROGRESS)
        await self._check_reviewer_access(task=task, actor_id=actor_id)
        validate_reason(comment)

        review_time = returned_at or datetime.now().astimezone()
        old_status = task.status
        task.status = TaskStatus.IN_PROGRESS
        task.completed_at = None
        task.updated_by = actor_id
        await self.task_repository.save(task)
        self.task_repository.session.add(
            TaskHistory(
                task_id=task.id,
                event_type="review_rejected",
                old_status=old_status,
                new_status=TaskStatus.IN_PROGRESS,
                actor_id=actor_id,
                comment=comment.strip(),
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
        task = await self._lock_task_owner(task)
        self._ensure_task_is_active(task)

        validate_transition(
            task.status,
            TaskStatus.ASSIGNED,
        )

        if not await self.can_issue_task(
                actor_id=actor_id,
                urza_id=task.urza_id,
                substation_id=getattr(task, "substation_id", None),
        ):
            raise PermissionError(
                "Пользователь не может выдавать задания для этого объекта."
            )

        available_assignees = await self.get_available_assignees(
            actor_id=actor_id,
            urza_id=task.urza_id,
            substation_id=getattr(task, "substation_id", None),
        )

        if assigned_to not in {
            engineer.id for engineer in available_assignees
        }:
            raise ValueError(
                "Выбранный исполнитель не является доступным "
                "активным инженером этого предприятия."
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
        task = await self._lock_task_owner(task)
        self._ensure_task_is_active(task)
        await self._ensure_task_object_is_active(task, actor_id)
        if task.assigned_to != actor_id:
            raise ValueError(
                "Принять задачу может только назначенный инженер."
            )

        await self._ensure_active_actor(actor_id)

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
        task = await self._lock_task_owner(task)
        self._ensure_task_is_active(task)
        await self._ensure_task_object_is_active(task, actor_id)
        if task.assigned_to != actor_id:
            raise ValueError(
                "Завершить задачу может только назначенный инженер."
            )

        await self._ensure_active_actor(actor_id)

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
            if getattr(task, "substation_id", None) is not None:
                if await self.task_repository.get_selectivity_version_by_task_id(task.id) is None:
                    raise ValueError("Сохраните результат схемы селективности для этой задачи.")
            else:
                schema_record = await self.task_repository.get_schema_record_by_task_id(task.id)
                if schema_record is None:
                    raise ValueError(
                        "Для завершения задачи по схемам необходимо сохранить результат схем."
                    )
                if schema_record.signed_form_file_id is None:
                    raise ValueError(
                        "Для завершения задачи по схемам необходим подписанный формуляр."
                    )
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

            if to_record.signed_form_file_id is None:
                raise ValueError(
                    "Для завершения задачи по ТО необходим скан подписанной формы."
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
            if getattr(task, "substation_id", None) is not None:
                if await self.task_repository.get_substation_instruction_version_by_task_id(task.id) is None:
                    raise ValueError("Создайте версию инструкции РЗА для этой задачи.")
            else:
                instruction = await self.urza_instruction_repository.get_by_urza_id(task.urza_id)
                if instruction is None:
                    raise ValueError("Для данного URZA не создана инструкция.")
                instruction_version = await self.urza_instruction_repository.get_latest_working_version(
                    instruction.id,
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
        task = await self._lock_task_owner(task)
        self._ensure_task_is_active(task)
        await self._ensure_task_object_is_active(task, actor_id)
        if task.assigned_to != actor_id:
            raise ValueError(
                "Отклонить задачу может только назначенный инженер."
            )

        await self._ensure_active_actor(actor_id)

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
        task = await self._lock_task_owner(task)
        self._ensure_task_is_active(task)
        if task.status != TaskStatus.ASSIGNED:
            raise ValueError(
                "Переназначить можно только назначенную задачу."
            )

        previous_assignee = task.assigned_to

        if previous_assignee == assigned_to:
            raise ValueError(
                "Новый исполнитель должен отличаться от текущего."
            )

        if not await self.can_issue_task(
                actor_id=actor_id,
                urza_id=task.urza_id,
                substation_id=getattr(task, "substation_id", None),
        ):
            raise PermissionError(
                "Пользователь не может переназначать задания для этого объекта."
            )

        available_assignees = await self.get_available_assignees(
            actor_id=actor_id,
            urza_id=task.urza_id,
            substation_id=getattr(task, "substation_id", None),
        )

        if assigned_to not in {
            engineer.id for engineer in available_assignees
        }:
            raise ValueError(
                "Выбранный исполнитель не является доступным "
                "активным инженером этого предприятия."
            )

        assignment_time = assigned_at or datetime.now().astimezone()

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
            previous_assignee_id=previous_assignee,
            new_assignee_id=assigned_to,
            comment=None,
            created_at=assignment_time,
        )

        self.task_repository.session.add(history)

        return task
