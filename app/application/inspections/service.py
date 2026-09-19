from datetime import date, datetime, timedelta
from uuid import UUID

from app.application.inspections.repository import InspectionTaskRepository
from app.application.inspections.workflow import validate_reason, validate_transition
from app.application.substations.repository import SubstationRepository
from app.application.users.repository import UserRepository
from app.domain.enums import TaskStatus, UserRole
from app.domain.inspection import Inspection
from app.domain.inspection_history import InspectionHistory
from app.domain.inspection_task import InspectionTask


class InspectionTaskService:
    """Бизнес-логика задач осмотра подстанций."""

    def __init__(
            self,
            repository: InspectionTaskRepository,
            user_repository: UserRepository,
            substation_repository: SubstationRepository,
    ) -> None:
        self.repository = repository
        self.user_repository = user_repository
        self.substation_repository = substation_repository

    async def create(
        self,
        *,
        substation_id: UUID,
        created_by: UUID,
        now: datetime | None = None,
    ) -> InspectionTask:
        """Создаёт новую задачу осмотра без назначения исполнителя."""

        creator = await self.user_repository.get_by_id(created_by)

        if creator is None:
            raise ValueError("Создатель задачи не найден.")

        # По принятой матрице создать задачу осмотра может только Manager.
        if creator.role != UserRole.MANAGER:
            raise ValueError(
                "Создавать задачи осмотра может только Manager."
            )

        current_time = now or datetime.now().astimezone()

        task = InspectionTask(
            substation_id=substation_id,
            created_by=created_by,
            assigned_to=None,
            status=TaskStatus.CREATED,
            deadline_at=current_time + timedelta(days=7),
        )

        return await self.repository.create(task)

    async def assign(
        self,
        task_id: UUID,
        *,
        actor_id: UUID,
        assignee_id: UUID,
        now: datetime | None = None,
    ) -> InspectionTask:
        """Назначает исполнителя на созданную задачу осмотра."""

        task = await self.repository.get_by_id(task_id)

        if task is None:
            raise ValueError("Задача осмотра не найдена.")

        actor = await self.user_repository.get_by_id(actor_id)

        if actor is None:
            raise ValueError(
                "Пользователь, выполняющий назначение, не найден."
            )

        # Назначать исполнителя может только Manager.
        if actor.role != UserRole.MANAGER:
            raise ValueError(
                "Назначать исполнителя может только Manager."
            )

        assignee = await self.user_repository.get_by_id(assignee_id)

        if assignee is None:
            raise ValueError("Исполнитель не найден.")

        # Для осмотра допустимы только Engineer и Manager.
        if assignee.role not in {
            UserRole.ENGINEER,
            UserRole.MANAGER,
        }:
            raise ValueError(
                "Исполнителем осмотра может быть только Engineer или Manager."
            )

        validate_transition(
            task.status,
            TaskStatus.ASSIGNED,
        )

        current_time = now or datetime.now().astimezone()

        task.assigned_to = assignee_id
        task.status = TaskStatus.ASSIGNED
        task.assigned_at = current_time
        task.acceptance_deadline_at = current_time + timedelta(days=1)

        await self.repository.save(task)

        history = InspectionHistory(
            inspection_task_id=task.id,
            event_type="assigned",
            old_status=TaskStatus.CREATED,
            new_status=TaskStatus.ASSIGNED,
            actor_id=actor_id,
            created_at=current_time,
        )

        await self.repository.add_history(history)

        return task

    async def accept(
        self,
        task_id: UUID,
        *,
        actor_id: UUID,
        now: datetime | None = None,
    ) -> InspectionTask:
        """Принимает назначенную задачу осмотра в работу."""

        task = await self.repository.get_by_id(task_id)

        if task is None:
            raise ValueError("Задача осмотра не найдена.")

        actor = await self.user_repository.get_by_id(actor_id)

        if actor is None:
            raise ValueError("Исполнитель не найден.")

        # Принять задачу может только Engineer или Manager.
        if actor.role not in {
            UserRole.ENGINEER,
            UserRole.MANAGER,
        }:
            raise ValueError(
                "Принять задачу осмотра может только Engineer или Manager."
            )

        if task.assigned_to != actor_id:
            raise ValueError(
                "Принять задачу может только назначенный исполнитель."
            )

        validate_transition(
            task.status,
            TaskStatus.IN_PROGRESS,
        )

        current_time = now or datetime.now().astimezone()

        old_status = task.status
        task.status = TaskStatus.IN_PROGRESS

        await self.repository.save(task)

        history = InspectionHistory(
            inspection_task_id=task.id,
            event_type="accepted",
            old_status=old_status,
            new_status=TaskStatus.IN_PROGRESS,
            actor_id=actor_id,
            created_at=current_time,
        )

        await self.repository.add_history(history)

        return task

    async def complete(
            self,
            task_id: UUID,
            *,
            actor_id: UUID,
            inspection_date: date,
            remarks: str,
            scan_file_id: UUID | None = None,
            editable_file_id: UUID | None = None,
            now: datetime | None = None,
    ) -> InspectionTask:
        """Завершает осмотр и сохраняет его результат."""

        task = await self.repository.get_by_id(task_id)

        if task is None:
            raise ValueError("Задача осмотра не найдена.")

        actor = await self.user_repository.get_by_id(actor_id)

        if actor is None:
            raise ValueError("Исполнитель не найден.")

        # Выполнить осмотр может только назначенный исполнитель.
        if task.assigned_to != actor_id:
            raise ValueError(
                "Завершить осмотр может только назначенный исполнитель."
            )

        if actor.role not in {
            UserRole.ENGINEER,
            UserRole.MANAGER,
        }:
            raise ValueError(
                "Выполнить осмотр может только Engineer или Manager."
            )

        validate_transition(
            task.status,
            TaskStatus.COMPLETED,
        )

        if not remarks or not remarks.strip():
            raise ValueError("Необходимо указать замечания по результатам осмотра.")

        current_time = now or datetime.now().astimezone()

        inspection = Inspection(
            substation_id=task.substation_id,
            inspection_task_id=task.id,
            inspection_date=inspection_date,
            remarks=remarks,
            scan_file_id=scan_file_id,
            editable_file_id=editable_file_id,
            created_by=actor_id,
        )

        await self.repository.create_inspection(inspection)

        old_status = task.status
        task.status = TaskStatus.COMPLETED
        task.completed_at = current_time

        await self.repository.save(task)

        history = InspectionHistory(
            inspection_task_id=task.id,
            event_type="completed",
            old_status=old_status,
            new_status=TaskStatus.COMPLETED,
            actor_id=actor_id,
            created_at=current_time,
        )

        await self.repository.add_history(history)

        return task

    async def send_to_review(
        self,
        task_id: UUID,
        *,
        actor_id: UUID,
        now: datetime | None = None,
    ) -> InspectionTask:
        """Передаёт завершённый осмотр на проверку Manager."""

        task = await self.repository.get_by_id(task_id)

        if task is None:
            raise ValueError("Задача осмотра не найдена.")

        actor = await self.user_repository.get_by_id(actor_id)

        if actor is None:
            raise ValueError("Исполнитель не найден.")

        # Только назначенный исполнитель может передать свою работу на проверку.
        if task.assigned_to != actor_id:
            raise ValueError(
                "Передать задачу на проверку может только назначенный исполнитель."
            )

        if actor.role not in {
            UserRole.ENGINEER,
            UserRole.MANAGER,
        }:
            raise ValueError(
                "Передать осмотр на проверку может только Engineer или Manager."
            )

        validate_transition(
            task.status,
            TaskStatus.UNDER_REVIEW,
        )

        current_time = now or datetime.now().astimezone()

        old_status = task.status
        task.status = TaskStatus.UNDER_REVIEW

        await self.repository.save(task)

        history = InspectionHistory(
            inspection_task_id=task.id,
            event_type="sent_to_review",
            old_status=old_status,
            new_status=TaskStatus.UNDER_REVIEW,
            actor_id=actor_id,
            created_at=current_time,
        )

        await self.repository.add_history(history)

        return task

    async def review(
            self,
            task_id: UUID,
            *,
            actor_id: UUID,
            approve: bool,
            reason: str | None = None,
            now: datetime | None = None,
    ) -> InspectionTask:
        """Проверяет результат осмотра и принимает или возвращает его."""

        task = await self.repository.get_by_id(task_id)

        if task is None:
            raise ValueError("Задача осмотра не найдена.")

        actor = await self.user_repository.get_by_id(actor_id)

        if actor is None:
            raise ValueError("Проверяющий пользователь не найден.")

        # Проверять результат осмотра может только Manager.
        if actor.role != UserRole.MANAGER:
            raise ValueError("Проверять результат осмотра может только Manager.")

        # Manager не может проверить осмотр, который выполнял он сам.
        if task.assigned_to == actor_id:
            raise ValueError(
                "Manager не может проверять собственный результат осмотра."
            )

        substation = await self.substation_repository.get_by_id(
            task.substation_id,
        )

        if substation is None:
            raise ValueError("Подстанция задачи не найдена.")

        # Проверяющий должен относиться к тому же производственному отделению,
        # что и подстанция.
        if actor.enterprise_id != substation.enterprise_id:
            raise ValueError(
                "Проверяющий Manager должен относиться к тому же "
                "производственному отделению."
            )

        new_status = (
            TaskStatus.CLOSED
            if approve
            else TaskStatus.IN_PROGRESS
        )

        validate_transition(task.status, new_status)

        if not approve:
            validate_reason(reason)

        current_time = now or datetime.now().astimezone()

        old_status = task.status
        task.status = new_status

        if approve:
            task.closed_at = current_time

        await self.repository.save(task)

        history = InspectionHistory(
            inspection_task_id=task.id,
            event_type="review_approved" if approve else "review_rejected",
            old_status=old_status,
            new_status=new_status,
            actor_id=actor_id,
            comment=reason,
            created_at=current_time,
        )

        await self.repository.add_history(history)

        return task