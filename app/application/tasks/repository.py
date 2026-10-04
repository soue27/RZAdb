from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.domain.maintenance import TORecord
from app.domain.program import Program
from app.domain.schema import SchemaRecord
from app.domain.settings_record import SettingsRecord
from app.domain.task import Task
from app.domain.task_history import TaskHistory


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

    async def get_active_by_id(self, task_id: UUID) -> Task | None:
        result = await self.session.execute(
            select(Task)
            .options(
                selectinload(Task.urza),
                selectinload(Task.created_by_user),
                selectinload(Task.assigned_to_user),
            )
            .where(Task.id == task_id, Task.deleted_at.is_(None))
        )
        return result.scalar_one_or_none()

    async def list_active(self) -> list[Task]:
        result = await self.session.execute(
            select(Task)
            .options(
                selectinload(Task.urza),
                selectinload(Task.created_by_user),
                selectinload(Task.assigned_to_user),
            )
            .where(Task.deleted_at.is_(None))
            .order_by(Task.created_at.desc(), Task.id.desc())
        )
        return list(result.scalars().all())

    async def get_history(self, task_id: UUID) -> list[TaskHistory]:
        result = await self.session.execute(
            select(TaskHistory)
            .options(selectinload(TaskHistory.actor))
            .where(TaskHistory.task_id == task_id)
            .order_by(TaskHistory.created_at.desc(), TaskHistory.id.desc())
        )
        return list(result.scalars().all())

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

    async def get_schema_record_by_task_id(
            self,
            task_id: UUID,
    ) -> SchemaRecord | None:
        """Находит запись схем, созданную в рамках указанной задачи."""
        result = await self.session.execute(
            select(SchemaRecord).where(
                SchemaRecord.task_id == task_id,
                SchemaRecord.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def get_program_by_task_id(
            self,
            task_id: UUID,
    ) -> Program | None:
        """Находит программу, созданную в рамках указанной задачи."""
        result = await self.session.execute(
            select(Program).where(Program.task_id == task_id)
        )
        return result.scalar_one_or_none()

    async def get_to_record_by_task_id(
            self,
            task_id: UUID,
    ) -> TORecord | None:
        """Находит запись ТО, созданную в рамках указанной задачи."""
        result = await self.session.execute(
            select(TORecord).where(TORecord.task_id == task_id)
        )
        return result.scalar_one_or_none()
