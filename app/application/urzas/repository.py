from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.application.objects.owner_lock import lock_owner_row
from app.domain.connection import Connection
from app.domain.substation import Substation
from app.domain.urza import URZA


class URZARepository:
    """Работа с устройствами РЗА через SQLAlchemy."""

    def __init__(self, session: AsyncSession) -> None:
        """Сохраняет асинхронную SQLAlchemy-сессию для запросов к устройствам РЗА.
        
        Args:
            session: Сессия текущей транзакции."""
        self.session = session

    async def get_by_id(
            self,
            urza_id: UUID,
    ) -> URZA | None:
        """Находит активное устройство с загруженной цепочкой владельца.
        
        Связи с присоединением и подстанцией загружаются заранее для построения
        DTO и проверок доступа без дополнительных обращений к сессии.
        
        Args:
            urza_id: Идентификатор устройства РЗА.
        
        Returns:
            Активное устройство или None."""
        result = await self.session.scalars(
            select(URZA)
            .options(
                selectinload(URZA.connection).selectinload(
                    Connection.substation,
                ),
            )
            .where(
                URZA.id == urza_id,
                URZA.deleted_at.is_(None),
            )
        )

        return result.one_or_none()

    async def get_by_id_including_deleted(
            self,
            urza_id: UUID,
    ) -> URZA | None:
        """Находит устройство с загруженной цепочкой владельца, включая архивное.
        
        Args:
            urza_id: Идентификатор устройства РЗА.
        
        Returns:
            Устройство независимо от признака архивирования или None."""
        result = await self.session.scalars(
            select(URZA)
            .options(
                selectinload(URZA.connection).selectinload(
                    Connection.substation,
                ),
            )
            .where(URZA.id == urza_id)
        )

        return result.one_or_none()

    async def lock_active_by_id(self, urza_id: UUID) -> bool:
        """Блокирует устройство и проверяет, что оно не архивировано.
        
        Args:
            urza_id: Идентификатор устройства РЗА.
        
        Returns:
            True, если активное устройство найдено и заблокировано."""
        urza = await lock_owner_row(self.session, URZA, urza_id)
        return urza is not None and urza.deleted_at is None

    async def lock_active_connection(self, connection_id: UUID) -> bool:
        """Блокирует присоединение и проверяет его активность.
        
        Args:
            connection_id: Идентификатор присоединения.
        
        Returns:
            True, если активное присоединение найдено и заблокировано."""
        connection = await lock_owner_row(
            self.session,
            Connection,
            connection_id,
        )
        return connection is not None and connection.deleted_at is None

    async def get_all_active(self) -> list[URZA]:
        """Возвращает все неудалённые устройства РЗА."""

        result = await self.session.scalars(
            select(URZA)
            .where(URZA.deleted_at.is_(None))
            .order_by(URZA.dispatch_name)
        )

        return list(result)

    async def get_by_connection_ids(
        self,
        connection_ids: set[UUID],
        *,
        include_archived: bool = False,
    ) -> list[URZA]:
        """Возвращает УРЗА указанных присоединений."""

        if not connection_ids:
            return []

        query = select(URZA).where(
            URZA.connection_id.in_(connection_ids),
        )
        if not include_archived:
            query = query.where(URZA.deleted_at.is_(None))
        result = await self.session.scalars(
            query
            .order_by(URZA.dispatch_name)
        )
        return list(result)

    async def add(self, urza: URZA) -> URZA:
        """Добавляет устройство в отдельной вложенной транзакции.
        
        Выполняет flush внутри savepoint, не фиксируя внешнюю транзакцию.
        
        Args:
            urza: Создаваемая модель устройства РЗА.
        
        Returns:
            Добавленная модель устройства."""
        async with self.session.begin_nested():
            self.session.add(urza)
            await self.session.flush()
        return urza

    async def update(self, urza: URZA) -> URZA:
        """Синхронизирует изменения устройства с базой данных без commit.
        
        Args:
            urza: Изменённая модель устройства РЗА.
        
        Returns:
            Та же модель устройства."""
        await self.session.flush()
        return urza

    async def exists_by_name(
        self,
        connection_id: UUID,
        dispatch_name: str,
        *,
        exclude_id: UUID | None = None,
    ) -> bool:
        """Проверяет уникальность диспетчерского имени в пределах присоединения.
        
        Архивные устройства не занимают имя. При обновлении текущую запись
        можно исключить из проверки.
        
        Args:
            connection_id: Идентификатор присоединения.
            dispatch_name: Проверяемое диспетчерское наименование.
            exclude_id: Идентификатор исключаемого устройства.
        
        Returns:
            True, если имя уже занято активным устройством."""
        query = select(URZA.id).where(
            URZA.connection_id == connection_id,
            func.btrim(URZA.dispatch_name) == dispatch_name.strip(),
            URZA.deleted_at.is_(None),
        )

        if exclude_id is not None:
            query = query.where(URZA.id != exclude_id)

        result = await self.session.scalar(query.limit(1))
        return result is not None

    async def has_active_connection(self, connection_id: UUID) -> bool:
        """Проверяет активность присоединения и его подстанции.
        
        Args:
            connection_id: Идентификатор присоединения.
        
        Returns:
            True, если оба объекта существуют и не архивированы."""
        result = await self.session.scalar(
            select(Connection.id)
            .join(Substation, Connection.substation_id == Substation.id)
            .where(
                Connection.id == connection_id,
                Connection.deleted_at.is_(None),
                Substation.deleted_at.is_(None),
            )
        )
        return result is not None
