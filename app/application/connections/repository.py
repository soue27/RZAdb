from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.connection import Connection


class ConnectionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(
        self,
        connection_id: UUID,
    ) -> Connection | None:
        return await self.session.get(Connection, connection_id)