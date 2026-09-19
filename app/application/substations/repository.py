from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.substation import Substation


class SubstationRepository:
    """Работа с подстанциями через SQLAlchemy."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(
        self,
        substation_id: UUID,
    ) -> Substation | None:
        return await self.session.get(Substation, substation_id)

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
    ) -> list[Substation]:
        """Возвращает подстанции указанных предприятий."""

        if not enterprise_ids:
            return []

        result = await self.session.scalars(
            select(Substation)
            .where(
                Substation.enterprise_id.in_(enterprise_ids),
                Substation.deleted_at.is_(None),
            )
            .order_by(Substation.dispatch_name)
        )

        return list(result)