from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.task import Task
from app.domain.settings_record import SettingsRecord


class TaskRepository:
    """Работа с задачами через SQLAlchemy."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, task: Task) -> Task:
        # Репозиторий только сохраняет сущность; бизнес-правила находятся в сервисе.
        self.session.add(task)
        await self.session.flush()
        await self.session.refresh(task)
        return task

    async def get_by_id(self, task_id: UUID) -> Task | None:
        return await self.session.get(Task, task_id)

    async def save(self, task: Task) -> Task:
        # flush фиксирует изменения в текущей транзакции, но commit остаётся за сервисом.
        await self.session.flush()
        await self.session.refresh(task)
        return task

    async def get_otd_version_by_task_id(self, task_id: UUID):
        """Находит версию ОТД, созданную в рамках указанной задачи."""
        from app.domain.otd import OTDVersion

        result = await self.session.execute(
            select(OTDVersion).where(OTDVersion.task_id == task_id)
        )

        return result.scalar_one_or_none()

    async def get_settings_record_by_task_id(
            self,
            task_id: UUID,
    ) -> SettingsRecord | None:
        """Находит запись уставок, созданную в рамках указанной задачи."""
        result = await self.session.execute(
            select(SettingsRecord).where(
                SettingsRecord.task_id == task_id,
            )
        )

        return result.scalar_one_or_none()