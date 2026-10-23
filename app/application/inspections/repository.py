from datetime import datetime
from uuid import UUID

from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.domain.enums import TaskStatus, UserRole
from app.domain.inspection import Inspection
from app.domain.inspection_history import InspectionHistory
from app.domain.inspection_task import InspectionTask
from app.domain.substation import Substation


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

    async def count_dashboard_statuses(
        self,
        *,
        user_id: UUID,
        role: UserRole,
        enterprise_ids: set[UUID],
        now: datetime,
    ) -> tuple[dict[TaskStatus, int], int]:
        if not enterprise_ids:
            return {}, 0

        statuses = (
            TaskStatus.CREATED,
            TaskStatus.ASSIGNED,
            TaskStatus.IN_PROGRESS,
            TaskStatus.UNDER_REVIEW,
            TaskStatus.COMPLETED,
            TaskStatus.CLOSED,
            TaskStatus.REJECTED,
        )
        status_counts = [
            func.count(case((InspectionTask.status == status, InspectionTask.id)))
            for status in statuses
        ]
        overdue = func.count(
            case(
                (
                    and_(
                        InspectionTask.deadline_at.is_not(None),
                        InspectionTask.deadline_at < now,
                        InspectionTask.status.not_in({TaskStatus.CLOSED, TaskStatus.REJECTED}),
                    ),
                    InspectionTask.id,
                )
            )
        )
        query = (
            select(*status_counts, overdue)
            .join(Substation, InspectionTask.substation_id == Substation.id)
            .where(
                InspectionTask.deleted_at.is_(None),
                Substation.enterprise_id.in_(enterprise_ids),
            )
        )
        if role is UserRole.ENGINEER:
            query = query.where(InspectionTask.assigned_to == user_id)
        elif role is UserRole.SUPERADMIN:
            reviewed = select(InspectionHistory.id).where(
                InspectionHistory.inspection_task_id == InspectionTask.id,
                InspectionHistory.actor_id == user_id,
                InspectionHistory.event_type.in_({"review_approved", "review_rejected"}),
            ).exists()
            query = query.where(
                or_(
                    InspectionTask.created_by == user_id,
                    InspectionTask.assigned_to == user_id,
                    reviewed,
                )
            )

        row = (await self.session.execute(query)).one()
        return dict(zip(statuses, row[:-1], strict=True)), row[-1]
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

    async def list_reviewed_task_ids(
            self,
            actor_id: UUID,
    ) -> set[UUID]:
        result = await self.session.scalars(
            select(InspectionHistory.inspection_task_id)
            .where(
                InspectionHistory.actor_id == actor_id,
                InspectionHistory.event_type.in_(
                    {"review_approved", "review_rejected"}
                ),
            )
            .distinct()
        )
        return set(result.all())

