from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

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

    async def get_active_by_id(self, task_id: UUID) -> InspectionTask | None:
        result = await self.session.execute(
            select(InspectionTask)
            .options(
                selectinload(InspectionTask.substation),
                selectinload(InspectionTask.created_by_user),
                selectinload(InspectionTask.assigned_to_user),
                selectinload(InspectionTask.inspection),
            )
            .where(InspectionTask.id == task_id, InspectionTask.deleted_at.is_(None))
        )
        return result.scalar_one_or_none()

    async def list_active(self) -> list[InspectionTask]:
        result = await self.session.scalars(
            select(InspectionTask)
            .options(
                selectinload(InspectionTask.substation),
                selectinload(InspectionTask.created_by_user),
                selectinload(InspectionTask.assigned_to_user),
            )
            .where(InspectionTask.deleted_at.is_(None))
            .order_by(InspectionTask.created_at.desc())
        )
        return list(result.all())

    async def list_by_substation(self, substation_id: UUID) -> list[InspectionTask]:
        result = await self.session.scalars(
            select(InspectionTask)
            .options(
                selectinload(InspectionTask.created_by_user),
                selectinload(InspectionTask.assigned_to_user),
                selectinload(InspectionTask.inspection),
            )
            .where(
                InspectionTask.substation_id == substation_id,
                InspectionTask.deleted_at.is_(None),
            )
            .order_by(InspectionTask.created_at.desc())
        )
        return list(result.all())

    async def get_history(self, task_id: UUID) -> list[InspectionHistory]:
        result = await self.session.scalars(
            select(InspectionHistory)
            .options(selectinload(InspectionHistory.actor))
            .where(InspectionHistory.inspection_task_id == task_id)
            .order_by(InspectionHistory.created_at.desc())
        )
        return list(result.all())

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

