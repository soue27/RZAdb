from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.domain.selectivity_scheme import (
    SelectivityScheme,
    SelectivitySchemeVersion,
)


class SelectivitySchemeRepository:
    """Работа со схемами селективности через SQLAlchemy."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(
        self,
        scheme_id: UUID,
    ) -> SelectivityScheme | None:
        return await self.session.get(
            SelectivityScheme,
            scheme_id,
        )

    async def get_by_substation_id(
        self,
        substation_id: UUID,
    ) -> SelectivityScheme | None:
        query = (
            select(SelectivityScheme)
            .where(
                SelectivityScheme.substation_id == substation_id,
            )
        )
        return await self.session.scalar(query)

    async def get_version_by_id(
        self,
        version_id: UUID,
    ) -> SelectivitySchemeVersion | None:
        return await self.session.get(
            SelectivitySchemeVersion,
            version_id,
        )

    async def get_current_version(
        self,
        scheme_id: UUID,
    ) -> SelectivitySchemeVersion | None:
        query = (
            select(SelectivitySchemeVersion)
            .options(
                selectinload(SelectivitySchemeVersion.scan_file),
                selectinload(SelectivitySchemeVersion.editable_file),
                selectinload(SelectivitySchemeVersion.creator),
            )
            .where(
                SelectivitySchemeVersion.selectivity_scheme_id == scheme_id,
            )
            .order_by(
                SelectivitySchemeVersion.version_number.desc(),
            )
            .limit(1)
        )
        return await self.session.scalar(query)

    async def get_versions(
        self,
        scheme_id: UUID,
    ) -> list[SelectivitySchemeVersion]:
        query = (
            select(SelectivitySchemeVersion)
            .options(
                selectinload(SelectivitySchemeVersion.scan_file),
                selectinload(SelectivitySchemeVersion.editable_file),
                selectinload(SelectivitySchemeVersion.creator),
            )
            .where(
                SelectivitySchemeVersion.selectivity_scheme_id == scheme_id,
            )
            .order_by(
                SelectivitySchemeVersion.version_number.desc(),
            )
        )
        result = await self.session.scalars(query)
        return list(result)

    async def add_scheme(
        self,
        scheme: SelectivityScheme,
    ) -> SelectivityScheme:
        self.session.add(scheme)
        await self.session.flush()
        return scheme

    async def add_version(
        self,
        version: SelectivitySchemeVersion,
    ) -> SelectivitySchemeVersion:
        self.session.add(version)
        await self.session.flush()
        return version