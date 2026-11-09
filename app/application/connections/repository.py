from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.objects.owner_lock import lock_owner_row
from app.domain.connection import Connection
from app.domain.substation import Substation


class ConnectionRepository:
    """Работа с присоединениями через SQLAlchemy."""

    def __init__(self, session: AsyncSession) -> None:
        """Сохраняет сессию для запросов к присоединениям.

        Args:
        session: Асинхронная SQLAlchemy-сессия текущей транзакции.

        """
        self.session = session

    async def get_by_id(
        self,
        connection_id: UUID,
    ) -> Connection | None:
        """Находит присоединение по идентификатору, включая архивные записи.

        Args:
        connection_id: Идентификатор присоединения.

        Returns:
        Присоединение или None, если запись отсутствует.

        """
        return await self.session.get(Connection, connection_id)

    async def exists_by_name(
            self,
            substation_id: UUID,
            dispatch_name: str,
            *,
            exclude_connection_id: UUID | None = None,
    ) -> bool:
        """Проверяет занятость диспетчерского имени в пределах подстанции.

        Сравнение выполняется после удаления пробелов по краям. При обновлении
        можно исключить из проверки текущее присоединение.

        Args:
        substation_id: Идентификатор подстанции.
        dispatch_name: Проверяемое диспетчерское наименование.
        exclude_connection_id: Идентификатор записи, исключаемой из поиска.

        Returns:
        True, если такое имя уже используется, иначе False.

        """
        query = select(Connection.id).where(
            Connection.substation_id == substation_id,
            func.btrim(Connection.dispatch_name) == dispatch_name.strip(),
        )

        if exclude_connection_id is not None:
            query = query.where(Connection.id != exclude_connection_id)

        result = await self.session.scalar(query.limit(1))
        return result is not None

    async def has_active_substation(self, substation_id: UUID) -> bool:
        """Проверяет наличие неархивированной подстанции.

        Args:
        substation_id: Идентификатор подстанции.

        Returns:
        True, если активная подстанция существует.

        """
        result = await self.session.scalar(
            select(Substation.id).where(
                Substation.id == substation_id,
                Substation.deleted_at.is_(None),
            )
        )
        return result is not None

    async def lock_active_substation(self, substation_id: UUID) -> bool:
        """Блокирует подстанцию и проверяет её активность перед созданием связи.

        Args:
        substation_id: Идентификатор подстанции.

        Returns:
        True, если подстанция существует, не архивирована и заблокирована.

        """
        substation = await lock_owner_row(
            self.session,
            Substation,
            substation_id,
        )
        return substation is not None and substation.deleted_at is None

    async def add(self, connection: Connection) -> Connection:
        """Добавляет присоединение в отдельной вложенной транзакции.

        Выполняет flush до выхода из savepoint, но не фиксирует внешнюю
        транзакцию.

        Args:
        connection: Создаваемая модель присоединения.

        Returns:
        Добавленная модель присоединения.

        """
        async with self.session.begin_nested():
            self.session.add(connection)
            await self.session.flush()
        return connection

    async def get_all_active(self) -> list[Connection]:
        """Возвращает все неудалённые присоединения."""
        result = await self.session.scalars(
            select(Connection)
            .where(Connection.deleted_at.is_(None))
            .order_by(Connection.dispatch_name)
        )

        return list(result)

    async def get_by_substation_ids(
        self,
        substation_ids: set[UUID],
        *,
        include_archived: bool = False,
    ) -> list[Connection]:
        """Возвращает присоединения выбранных подстанций.

        Args:
        substation_ids: Идентификаторы подстанций.
        include_archived: Включать ли архивированные присоединения.

        Returns:
        Присоединения, отсортированные по диспетчерскому наименованию.
        При пустом наборе идентификаторов возвращает пустой список.

        """

        if not substation_ids:
            return []

        query = select(Connection).where(
            Connection.substation_id.in_(substation_ids),
        )
        if not include_archived:
            query = query.where(Connection.deleted_at.is_(None))
        result = await self.session.scalars(
            query
            .order_by(Connection.dispatch_name)
        )

        return list(result)

    async def update(self, connection: Connection) -> Connection:
        """Синхронизирует изменения присоединения с базой данных.

        Транзакция не фиксируется.

        Args:
        connection: Изменённая модель присоединения.

        Returns:
        Та же модель присоединения.

        """
        await self.session.flush()
        return connection
