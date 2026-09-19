from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.inspection import Inspection
from app.domain.inspection_history import InspectionHistory
from app.domain.inspection_task import InspectionTask


class InspectionTaskRepository:
    """Работа с задачами осмотров через SQLAlchemy."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, task: InspectionTask) -> InspectionTask:
        # Репозиторий сохраняет сущность, но не содержит бизнес-правил.
        self.session.add(task)
        await self.session.flush()
        await self.session.refresh(task)
        return task

    async def get_by_id(self, task_id: UUID) -> InspectionTask | None:
        return await self.session.get(InspectionTask, task_id)

    async def save(self, task: InspectionTask) -> InspectionTask:
        # flush сохраняет изменения в текущей транзакции; commit выполняет сервис.
        await self.session.flush()
        await self.session.refresh(task)
        return task

    async def add_history(self, history: InspectionHistory) -> InspectionHistory:
        # История нужна для аудита каждого изменения состояния задачи.
        self.session.add(history)
        await self.session.flush()
        return history

    async def create_inspection(
            self,
            inspection: Inspection,
    ) -> Inspection:
        # Результат осмотра сохраняем вместе с задачей в одной транзакции.
        self.session.add(inspection)
        await self.session.flush()
        await self.session.refresh(inspection)
        return inspection

