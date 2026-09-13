from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

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

