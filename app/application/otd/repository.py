from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.domain.otd import OTD, OTDVersion


class OTDRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(
        self,
        otd_id: UUID,
    ) -> OTD | None:
        query = select(OTD).where(
            OTD.id == otd_id,
            OTD.deleted_at.is_(None),
        )
        return await self.session.scalar(query)

    async def get_by_urza_id(
        self,
        urza_id: UUID,
    ) -> OTD | None:
        query = select(OTD).where(
            OTD.urza_id == urza_id,
            OTD.deleted_at.is_(None),
        )
        return await self.session.scalar(query)

    async def get_version_by_id(
            self,
            version_id: UUID,
    ) -> OTDVersion | None:
        query = (
            select(OTDVersion)
            .options(selectinload(OTDVersion.created_by_user))
            .where(
                OTDVersion.id == version_id,
                OTDVersion.deleted_at.is_(None),
            )
        )

        return await self.session.scalar(query)

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

    async def save_version(self, version: OTDVersion) -> OTDVersion:
        await self.session.flush()
        await self.session.refresh(version)
        return version

    async def get_current_version(
            self,
            otd_id: UUID,
    ) -> OTDVersion | None:
        query = (
            select(OTDVersion)
            .options(selectinload(OTDVersion.created_by_user))
            .where(
                OTDVersion.otd_id == otd_id,
                OTDVersion.deleted_at.is_(None),
            )
            .order_by(OTDVersion.version_number.desc())
        )

        return await self.session.scalar(query)

    async def get_versions(self, otd_id: UUID) -> list[OTDVersion]:
        query = (
            select(OTDVersion)
            .options(selectinload(OTDVersion.created_by_user))
            .where(
                OTDVersion.otd_id == otd_id,
                OTDVersion.deleted_at.is_(None),
            )
            .order_by(OTDVersion.version_number.desc())
        )
        result = await self.session.scalars(query)
        return list(result.all())

    async def get_max_version_number(self, otd_id: UUID) -> int | None:
        query = select(func.max(OTDVersion.version_number)).where(
            OTDVersion.otd_id == otd_id
        )
        return await self.session.scalar(query)

    async def get_version_by_task_id(self, task_id: UUID) -> OTDVersion | None:
        query = select(OTDVersion).where(
            OTDVersion.task_id == task_id,
            OTDVersion.deleted_at.is_(None),
        )
        return await self.session.scalar(query)

    async def list_standalone_work_items(self) -> list[OTDVersion]:
        query = (
            select(OTDVersion)
            .options(
                selectinload(OTDVersion.created_by_user),
                selectinload(OTDVersion.otd).selectinload(OTD.urza),
            )
            .join(OTD, OTDVersion.otd_id == OTD.id)
            .where(
                OTDVersion.task_id.is_(None),
                OTDVersion.deleted_at.is_(None),
                OTD.deleted_at.is_(None),
            )
            .order_by(OTDVersion.created_at.desc())
        )
        result = await self.session.scalars(query)
        return list(result.all())

