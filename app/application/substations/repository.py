from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.substation import Substation


class SubstationRepository:
    """Работа с подстанциями через SQLAlchemy."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, substation_id: UUID) -> Substation | None:
        # Для проверки прав достаточно получить подстанцию по PK
        # и использовать её enterprise_id как идентификатор ПО.
        return await self.session.get(Substation, substation_id)