from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.application.objects.owner_lock import lock_owner_row
from app.domain.archive_event import ArchiveEvent
from app.domain.connection import Connection
from app.domain.enums import TaskStatus
from app.domain.inspection_task import InspectionTask
from app.domain.substation import Substation
from app.domain.task import Task
from app.domain.urza import URZA

_TERMINAL_STATUSES = {TaskStatus.CLOSED, TaskStatus.REJECTED}


class ArchiveRepository:
    """Database queries used by archive application use cases."""

    def __init__(self, session: AsyncSession) -> None:
        """Сохраняет асинхронную SQLAlchemy-сессию.

        Args:
            session: Сессия текущей транзакции.
        """
        self.session = session

    async def get_object(self, object_type: str, object_id: UUID):
        """Возвращает модель объекта по типу и идентификатору.

        Args:
            object_type: Тип архивируемого объекта.
            object_id: Идентификатор объекта.

        Returns:
            Найденная модель или None.
        """
        model = self._model_for(object_type)
        return await self.session.get(model, object_id)

    async def lock_object(self, object_type: str, object_id: UUID):
        """Блокирует строку объекта для безопасного архивирования или восстановления.

        Args:
            object_type: Тип объекта.
            object_id: Идентификатор объекта.

        Returns:
            Заблокированная модель или None.
        """
        return await lock_owner_row(
            self.session, self._model_for(object_type), object_id
        )

    async def get_active_connections(self, substation_id: UUID) -> list[Connection]:
        """Возвращает активные присоединения подстанции.

        Args:
            substation_id: Идентификатор подстанции.

        Returns:
            Присоединения, отсортированные по идентификатору.
        """
        result = await self.session.scalars(
            select(Connection)
            .where(
                Connection.substation_id == substation_id,
                Connection.deleted_at.is_(None),
            )
            .order_by(Connection.id)
        )
        return list(result.all())

    async def get_active_urzas(self, connection_ids: list[UUID]) -> list[URZA]:
        """Возвращает активные устройства выбранных присоединений.

        Args:
            connection_ids: Идентификаторы присоединений.

        Returns:
            Устройства РЗА; при пустом наборе возвращает пустой список.
        """
        if not connection_ids:
            return []
        result = await self.session.scalars(
            select(URZA)
            .where(
                URZA.connection_id.in_(connection_ids),
                URZA.deleted_at.is_(None),
            )
            .order_by(URZA.id)
        )
        return list(result.all())

    async def get_blocking_processes(
        self,
        *,
        substation_id: UUID | None = None,
        urza_ids: list[UUID] | None = None,
        include_inspections: bool = False,
    ) -> list[tuple[str, UUID, TaskStatus]]:
        """Находит незавершённые задачи и процессы осмотра, блокирующие архивирование.

        Args:
            substation_id: Необязательный идентификатор подстанции.
            urza_ids: Необязательные идентификаторы устройств.
            include_inspections: Учитывать ли процессы осмотра подстанций.

        Returns:
            Список пар типа процесса, идентификатора и текущего статуса.
        """
        predicates = []
        if substation_id is not None:
            predicates.append(Task.substation_id == substation_id)
        if urza_ids:
            predicates.append(Task.urza_id.in_(urza_ids))

        blockers: list[tuple[str, UUID, TaskStatus]] = []
        if predicates:
            tasks = await self.session.scalars(
                select(Task)
                .where(
                    Task.status.not_in(_TERMINAL_STATUSES),
                    or_(*predicates),
                )
                .order_by(Task.id)
            )
            blockers.extend(("task", task.id, task.status) for task in tasks.all())

        if include_inspections and substation_id is not None:
            inspections = await self.session.scalars(
                select(InspectionTask)
                .where(
                    InspectionTask.substation_id == substation_id,
                    InspectionTask.status.not_in(_TERMINAL_STATUSES),
                )
                .order_by(InspectionTask.id)
            )
            blockers.extend(
                ("inspection", task.id, task.status) for task in inspections.all()
            )
        return blockers

    async def add_events(self, events: list[ArchiveEvent]) -> None:
        """Добавляет события архивирования/восстановления в текущую транзакцию.

        Args:
            events: События append-only истории.
        """
        self.session.add_all(events)
        await self.session.flush()

    async def get_history(
        self,
        object_type: str,
        object_id: UUID,
    ) -> list[ArchiveEvent]:
        """Возвращает историю архивных событий указанного объекта.

        Args:
            object_type: Тип объекта.
            object_id: Идентификатор объекта.

        Returns:
            События истории в хронологическом порядке.
        """
        fk_column = {
            "substation": ArchiveEvent.substation_id,
            "connection": ArchiveEvent.connection_id,
            "urza": ArchiveEvent.urza_id,
        }[object_type]
        result = await self.session.scalars(
            select(ArchiveEvent)
            .options(selectinload(ArchiveEvent.actor))
            .where(fk_column == object_id)
            .order_by(ArchiveEvent.occurred_at, ArchiveEvent.id)
        )
        return list(result.all())

    @staticmethod
    def _model_for(object_type: str):
        """Возвращает ORM-модель для поддерживаемого типа архивируемого объекта.

        Args:
            object_type: Строковый тип объекта.

        Returns:
            Класс ORM-модели.

        Raises:
            ValueError: Если тип объекта не поддерживается.
        """
        return {
            "substation": Substation,
            "connection": Connection,
            "urza": URZA,
        }[object_type]
