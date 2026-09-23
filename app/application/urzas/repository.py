from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.urza import URZA


class URZARepository:
    """Работа с устройствами РЗА через SQLAlchemy."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(
            self,
            urza_id: UUID,
    ) -> URZA | None:
        result = await self.session.scalars(
            select(URZA).where(
                URZA.id == urza_id,
                URZA.deleted_at.is_(None),
            )
        )

        return result.one_or_none()

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
    ) -> list[URZA]:
        """Возвращает УРЗА указанных присоединений."""

        if not connection_ids:
            return []

        result = await self.session.scalars(
            select(URZA)
            .where(
                URZA.connection_id.in_(connection_ids),
                URZA.deleted_at.is_(None),
            )
            .order_by(URZA.dispatch_name)
        )

        return list(result)