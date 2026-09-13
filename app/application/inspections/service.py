from datetime import datetime, timedelta
from uuid import UUID

from app.application.inspections.repository import InspectionTaskRepository
from app.domain.enums import TaskStatus, UserRole
from app.domain.inspection_task import InspectionTask


class InspectionTaskService:
    """Бизнес-логика задач осмотра подстанций."""

    def __init__(self, repository: InspectionTaskRepository) -> None:
        self.repository = repository

    async def create(
        self,
        *,
        substation_id: UUID,
        created_by: UUID,
        creator_role: UserRole,
        now: datetime | None = None,
    ) -> InspectionTask:
        """Создаёт новую задачу осмотра без назначения исполнителя."""

        # Создавать задачи осмотра по принятой матрице может только Manager.
        if creator_role != UserRole.MANAGER:
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