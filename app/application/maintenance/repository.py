from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.domain.enums import DocumentStatus
from app.domain.maintenance import TORecord


class TORecordRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(
        self,
        record_id: UUID,
    ) -> TORecord | None:
        return await self.session.scalar(
            select(TORecord).where(
                TORecord.id == record_id,
                TORecord.deleted_at.is_(None),
            ).options(
                selectinload(TORecord.creator),
                selectinload(TORecord.signed_form_file),
                selectinload(TORecord.scan_protocol),
                selectinload(TORecord.editable_protocol),
                selectinload(TORecord.task),
            )
        )

    async def get_by_id_for_update(self, record_id: UUID) -> TORecord | None:
        statement = (
            select(TORecord)
            .options(
                selectinload(TORecord.creator),
                selectinload(TORecord.signed_form_file),
                selectinload(TORecord.scan_protocol),
                selectinload(TORecord.editable_protocol),
                selectinload(TORecord.task),
            )
            .where(
                TORecord.id == record_id,
                TORecord.deleted_at.is_(None),
            )
            .with_for_update()
        )
        return await self.session.scalar(statement)

    async def get_by_urza_id(
        self,
        urza_id: UUID,
    ) -> list[TORecord]:
        query = (
            select(TORecord)
            .options(
                selectinload(TORecord.creator),
                selectinload(TORecord.signed_form_file),
            )
            .where(
                TORecord.urza_id == urza_id,
                TORecord.deleted_at.is_(None),
            )
            .order_by(
                TORecord.maintenance_date.desc(),
            )
        )

        result = await self.session.scalars(query)

        return list(result.all())

    async def list_standalone_under_review(self) -> list[TORecord]:
        statement = (
            select(TORecord)
            .options(
                selectinload(TORecord.creator),
                selectinload(TORecord.urza),
            )
            .where(
                TORecord.deleted_at.is_(None),
                TORecord.task_id.is_(None),
                TORecord.status == DocumentStatus.UNDER_REVIEW,
            )
            .order_by(
                TORecord.created_at.desc(),
                TORecord.id.desc(),
            )
        )
        result = await self.session.scalars(statement)
        return list(result.all())

    async def list_standalone_work_items(self) -> list[TORecord]:
        statement = (
            select(TORecord)
            .options(
                selectinload(TORecord.creator),
                selectinload(TORecord.urza),
            )
            .where(
                TORecord.deleted_at.is_(None),
                TORecord.task_id.is_(None),
                TORecord.status.in_(
                    (
                        DocumentStatus.DRAFT,
                        DocumentStatus.UNDER_REVIEW,
                        DocumentStatus.APPROVED,
                    )
                ),
            )
            .order_by(
                TORecord.created_at.desc(),
                TORecord.id.desc(),
            )
        )
        result = await self.session.scalars(statement)
        return list(result.all())

    async def get_current_approved(self, urza_id: UUID) -> TORecord | None:
        statement = (
            select(TORecord)
            .options(selectinload(TORecord.signed_form_file))
            .where(
                TORecord.urza_id == urza_id,
                TORecord.deleted_at.is_(None),
                TORecord.status == DocumentStatus.APPROVED,
            )
            .order_by(
                TORecord.maintenance_date.desc(),
                TORecord.created_at.desc(),
                TORecord.id.desc(),
            )
            .limit(1)
        )
        return await self.session.scalar(statement)

    async def get_by_task_id(
        self,
        task_id: UUID,
    ) -> TORecord | None:
        query = select(TORecord).where(
            TORecord.task_id == task_id,
            TORecord.deleted_at.is_(None),
        )

        return await self.session.scalar(query)

    async def add(
        self,
        record: TORecord,
    ) -> TORecord:
        self.session.add(record)
        await self.session.flush()

        return record

    async def save(self, record: TORecord) -> TORecord:
        await self.session.flush()
        return record
