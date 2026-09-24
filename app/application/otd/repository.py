from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.otd import OTD, OTDVersion


class OTDRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(
        self,
        otd_id: UUID,
    ) -> OTD | None:
        return await self.session.get(OTD, otd_id)

    async def get_by_urza_id(
        self,
        urza_id: UUID,
    ) -> OTD | None:
        query = select(OTD).where(OTD.urza_id == urza_id)
        return await self.session.scalar(query)

    async def get_version_by_id(
        self,
        version_id: UUID,
    ) -> OTDVersion | None:
        return await self.session.get(OTDVersion, version_id)

    async def add(
            self,
            otd: OTD,
    ) -> OTD:
        self.session.add(otd)
        await self.session.flush()
        return otd

    async def add_version(
            self,
            version: OTDVersion,
    ) -> OTDVersion:
        self.session.add(version)
        await self.session.flush()
        return version

    async def get_current_version(
            self,
            otd_id: UUID,
    ) -> OTDVersion | None:
        query = (
            select(OTDVersion)
            .where(OTDVersion.otd_id == otd_id)
            .order_by(OTDVersion.version_number.desc())
            .limit(1)
        )

        return await self.session.scalar(query)

    async def get_versions(self, otd_id: UUID) -> list[OTDVersion]:
        query = (
            select(OTDVersion)
            .where(OTDVersion.otd_id == otd_id)
            .order_by(OTDVersion.version_number.desc())
        )
        result = await self.session.scalars(query)
        return list(result.all())

