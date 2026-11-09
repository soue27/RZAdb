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
        """Сохраняет асинхронную SQLAlchemy-сессию для работы с задачами осмотров.

        Args:
            session: Сессия текущей транзакции.
        """
        self.session = session

    async def create(self, task: InspectionTask) -> InspectionTask:
        """Добавляет задачу осмотра и выполняет flush с обновлением серверных полей.

        Args:
            task: Создаваемая задача осмотра.

        Returns:
            Сохранённая модель задачи. Транзакция остаётся открытой.
        """
        # Репозиторий сохраняет сущность, но не содержит бизнес-правил.
        self.session.add(task)
        await self.session.flush()
        await self.session.refresh(task)
        return task

    async def get_by_id(self, task_id: UUID) -> InspectionTask | None:
        """Находит задачу осмотра по идентификатору без фильтрации по архивному статусу.

        Args:
            task_id: Идентификатор задачи.

        Returns:
            Задача осмотра или None.
        """
        return await self.session.get(InspectionTask, task_id)

    async def refresh_for_mutation(
        self,
        task: InspectionTask,
    ) -> InspectionTask:
        """Reload task state after its substation row has been locked."""
        await self.session.refresh(task)
        return task

    async def get_active_by_id(self, task_id: UUID) -> InspectionTask | None:
        """Находит активную задачу осмотра и загружает связанные объекты и пользователей.

        Args:
            task_id: Идентификатор задачи.

        Returns:
            Активная задача с загруженными связями или None.
        """
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
        """Возвращает активные задачи осмотра с данными подстанций и участников.

        Returns:
            Список задач осмотра.
        """
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
        """Возвращает задачи осмотра указанной подстанции.

        Args:
            substation_id: Идентификатор подстанции.

        Returns:
            Задачи подстанции в порядке, заданном запросом.
        """
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
        """Подсчитывает задачи осмотра по статусам и число просроченных задач для панели.

        Args:
            user_id: Идентификатор пользователя.
            role: Роль пользователя.
            enterprise_ids: Доступные предприятия.
            now: Момент времени для расчёта просрочки.

        Returns:
            Словарь количества задач по статусам и число просроченных задач.
        """
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
        """Возвращает историю изменений задачи осмотра.

        Args:
            task_id: Идентификатор задачи.

        Returns:
            События истории в порядке, заданном запросом.
        """
        result = await self.session.scalars(
            select(InspectionHistory)
            .options(selectinload(InspectionHistory.actor))
            .where(InspectionHistory.inspection_task_id == task_id)
            .order_by(InspectionHistory.created_at.desc())
        )
        return list(result.all())

    async def save(self, task: InspectionTask) -> InspectionTask:
        """Синхронизирует изменения задачи осмотра с базой данных без commit.

        Args:
            task: Изменённая задача.

        Returns:
            Та же модель задачи.
        """
        # flush сохраняет изменения в текущей транзакции; commit выполняет сервис.
        await self.session.flush()
        await self.session.refresh(task)
        return task

    async def add_history(self, history: InspectionHistory) -> InspectionHistory:
        """Добавляет событие истории задачи осмотра и выполняет flush без commit.

        Args:
            history: Создаваемое событие истории.

        Returns:
            Добавленное событие.
        """
        # История нужна для аудита каждого изменения состояния задачи.
        self.session.add(history)
        await self.session.flush()
        return history

    async def create_inspection(
            self,
            inspection: Inspection,
    ) -> Inspection:
        """Добавляет результат осмотра и выполняет flush без commit.

        Args:
            inspection: Создаваемый результат осмотра.

        Returns:
            Добавленная запись осмотра.
        """
        # Результат осмотра сохраняем вместе с задачей в одной транзакции.
        self.session.add(inspection)
        await self.session.flush()
        await self.session.refresh(inspection)
        return inspection

    async def list_reviewed_task_ids(
            self,
            actor_id: UUID,
    ) -> set[UUID]:
        """Возвращает идентификаторы задач осмотра, по которым пользователь уже принимал решение проверки.

        Args:
            actor_id: Идентификатор проверяющего.

        Returns:
            Множество идентификаторов проверенных задач.
        """
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

