from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.objects.owner_lock import lock_owner_row
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

    async def lock_active_by_id(self, substation_id: UUID) -> bool:
        substation = await lock_owner_row(
            self.session,
            Substation,
            substation_id,
        )
        return substation is not None and substation.deleted_at is None

    async def save(self, substation: Substation) -> Substation:
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
        """Возвращает подстанции указанных предприятий."""

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
