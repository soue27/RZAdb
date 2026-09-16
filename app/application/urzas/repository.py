from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.urza import URZA


class URZARepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(
        self,
        urza_id: UUID,
    ) -> URZA | None:
        return await self.session.get(URZA, urza_id)