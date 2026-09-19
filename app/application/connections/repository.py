from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.connection import Connection


class ConnectionRepository:
    """Работа с присоединениями через SQLAlchemy."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(
        self,
        connection_id: UUID,
    ) -> Connection | None:
        return await self.session.get(Connection, connection_id)

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
    ) -> list[Connection]:
        """Возвращает присоединения указанных подстанций."""

        if not substation_ids:
            return []

        result = await self.session.scalars(
            select(Connection)
            .where(
                Connection.substation_id.in_(substation_ids),
                Connection.deleted_at.is_(None),
            )
            .order_by(Connection.dispatch_name)
        )

        return list(result)