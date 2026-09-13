from datetime import datetime, timedelta
from uuid import UUID

from app.application.tasks.repository import TaskRepository
from app.domain.enums import MaintenanceType, TaskStatus, TaskWorkType
from app.domain.task import Task
from app.domain.task_history import TaskHistory


class TaskService:
    """Сценарии работы с заданиями."""

    def __init__(
        self,
        task_repository: TaskRepository,
    ) -> None:
        self.task_repository = task_repository

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