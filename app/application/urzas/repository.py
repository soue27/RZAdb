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
        self.session = session

    async def get_by_id(
            self,
            urza_id: UUID,
    ) -> URZA | None:
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
        urza = await lock_owner_row(self.session, URZA, urza_id)
        return urza is not None and urza.deleted_at is None

    async def lock_active_connection(self, connection_id: UUID) -> bool:
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
        async with self.session.begin_nested():
            self.session.add(urza)
            await self.session.flush()
        return urza

    async def update(self, urza: URZA) -> URZA:
        await self.session.flush()
        return urza

    async def exists_by_name(
        self,
        connection_id: UUID,
        dispatch_name: str,
        *,
        exclude_id: UUID | None = None,
    ) -> bool:
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
