from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.inspection import Inspection


class InspectionRepository:
    """Работа с результатами осмотров через SQLAlchemy."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(
        self,
        inspection_id: UUID,
    ) -> Inspection | None:
        return await self.session.get(Inspection, inspection_id)

    async def get_by_substation_id(
        self,
        substation_id: UUID,
    ) -> list[Inspection]:
        """Возвращает результаты осмотров указанной подстанции."""

        result = await self.session.scalars(
            select(Inspection)
            .where(
                Inspection.substation_id == substation_id,
            )
            .order_by(Inspection.inspection_date.desc())
        )

        return list(result)