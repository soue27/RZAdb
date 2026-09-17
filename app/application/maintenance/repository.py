from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.maintenance import TORecord


class TORecordRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(
        self,
        record_id: UUID,
    ) -> TORecord | None:
        return await self.session.get(
            TORecord,
            record_id,
        )

    async def get_by_urza_id(
        self,
        urza_id: UUID,
    ) -> list[TORecord]:
        query = (
            select(TORecord)
            .where(
                TORecord.urza_id == urza_id,
            )
            .order_by(
                TORecord.maintenance_date.desc(),
            )
        )

        result = await self.session.scalars(query)

        return list(result.all())

    async def get_by_task_id(
        self,
        task_id: UUID,
    ) -> TORecord | None:
        query = select(TORecord).where(
            TORecord.task_id == task_id,
        )

        return await self.session.scalar(query)

    async def add(
        self,
        record: TORecord,
    ) -> TORecord:
        self.session.add(record)
        await self.session.flush()

        return record
