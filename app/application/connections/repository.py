from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.objects.owner_lock import lock_owner_row
from app.domain.connection import Connection
from app.domain.substation import Substation


class ConnectionRepository:
    """Работа с присоединениями через SQLAlchemy."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(
        self,
        connection_id: UUID,
    ) -> Connection | None:
        return await self.session.get(Connection, connection_id)

    async def exists_by_name(
            self,
            substation_id: UUID,
            dispatch_name: str,
            *,
            exclude_connection_id: UUID | None = None,
    ) -> bool:
        query = select(Connection.id).where(
            Connection.substation_id == substation_id,
            func.btrim(Connection.dispatch_name) == dispatch_name.strip(),
        )

        if exclude_connection_id is not None:
            query = query.where(Connection.id != exclude_connection_id)

        result = await self.session.scalar(query.limit(1))
        return result is not None

    async def has_active_substation(self, substation_id: UUID) -> bool:
        result = await self.session.scalar(
            select(Substation.id).where(
                Substation.id == substation_id,
                Substation.deleted_at.is_(None),
            )
        )
        return result is not None

    async def lock_active_substation(self, substation_id: UUID) -> bool:
        substation = await lock_owner_row(
            self.session,
            Substation,
            substation_id,
        )
        return substation is not None and substation.deleted_at is None

    async def add(self, connection: Connection) -> Connection:
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
        """Возвращает присоединения указанных подстанций."""

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
        await self.session.flush()
        return connection
