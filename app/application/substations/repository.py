from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.objects.owner_lock import lock_owner_row
from app.domain.substation import Substation


class SubstationRepository:
    """Работа с подстанциями через SQLAlchemy."""

    def __init__(self, session: AsyncSession) -> None:
        """Сохраняет сессию для запросов к подстанциям.
            
            Args:
            session: Асинхронная SQLAlchemy-сессия текущей транзакции.
        """
        self.session = session

    async def get_by_id(
        self,
        substation_id: UUID,
    ) -> Substation | None:
        """Находит подстанцию по идентификатору, включая архивные записи.
            
            Args:
            substation_id: Идентификатор подстанции.
            
            Returns:
            Подстанция или None, если запись отсутствует.
        """
        return await self.session.get(Substation, substation_id)

    async def lock_active_by_id(self, substation_id: UUID) -> bool:
        """Блокирует строку подстанции и проверяет, что она не архивирована.
            
            Блокировка защищает последующие операции с владельцем от конкурентного
            архивирования в рамках текущей транзакции.
            
            Args:
            substation_id: Идентификатор подстанции.
            
            Returns:
            True, если активная подстанция найдена и заблокирована.
        """
        substation = await lock_owner_row(
            self.session,
            Substation,
            substation_id,
        )
        return substation is not None and substation.deleted_at is None

    async def save(self, substation: Substation) -> Substation:
        """Добавляет или сохраняет подстанцию и выполняет flush.
            
            Транзакция не фиксируется.
            
            Args:
            substation: Модель подстанции.
            
            Returns:
            Та же модель подстанции.
        """
        self.session.add(substation)
        await self.session.flush()
        return substation

    async def get_all_active(self) -> list[Substation]:
        """Возвращает все неудалённые подстанции."""
        result = await self.session.scalars(
            select(Substation)
            .where(Substation.deleted_at.is_(None))
            .order_by(Substation.dispatch_name)
        )

        return list(result)

    async def get_by_enterprise_ids(
        self,
        enterprise_ids: set[UUID],
        *,
        include_archived: bool = False,
    ) -> list[Substation]:
        """Возвращает подстанции выбранных предприятий.
            
            Args:
            enterprise_ids: Идентификаторы предприятий.
            include_archived: Включать ли архивированные подстанции.
            
            Returns:
            Подстанции, отсортированные по диспетчерскому наименованию.
            При пустом наборе идентификаторов возвращает пустой список.
        """

        if not enterprise_ids:
            return []

        query = select(Substation).where(
            Substation.enterprise_id.in_(enterprise_ids),
        )
        if not include_archived:
            query = query.where(Substation.deleted_at.is_(None))
        result = await self.session.scalars(
            query
            .order_by(Substation.dispatch_name)
        )

        return list(result)
