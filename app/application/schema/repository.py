from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.domain.enums import DocumentStatus
from app.domain.schema import SchemaForm, SchemaRecord


class SchemaRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_form_by_id(
        self,
        schema_form_id: UUID,
    ) -> SchemaForm | None:
        statement = select(SchemaForm).where(
            SchemaForm.id == schema_form_id,
            SchemaForm.deleted_at.is_(None),
        )
        return await self.session.scalar(statement)

    async def get_form_by_urza_id(
        self,
        urza_id: UUID,
    ) -> SchemaForm | None:
        statement = select(SchemaForm).where(
            SchemaForm.urza_id == urza_id,
            SchemaForm.deleted_at.is_(None),
        )
        return await self.session.scalar(statement)

    async def get_by_id(
        self,
        record_id: UUID,
    ) -> SchemaRecord | None:
        statement = (
            select(SchemaRecord)
            .options(selectinload(SchemaRecord.creator))
            .where(
                SchemaRecord.id == record_id,
                SchemaRecord.deleted_at.is_(None),
            )
        )
        return await self.session.scalar(statement)

    async def get_record_by_id(
        self,
        record_id: UUID,
    ) -> SchemaRecord | None:
        return await self.get_by_id(record_id)

    async def list_active(
        self,
        schema_form_id: UUID,
    ) -> list[SchemaRecord]:
        statement = (
            select(SchemaRecord)
            .options(
                selectinload(SchemaRecord.creator),
                selectinload(SchemaRecord.scan_file),
                selectinload(SchemaRecord.editable_file),
                selectinload(SchemaRecord.signed_form_file),
            )
            .where(
                SchemaRecord.schema_form_id == schema_form_id,
                SchemaRecord.deleted_at.is_(None),
            )
            .order_by(
                SchemaRecord.upload_date.desc(),
                SchemaRecord.created_at.desc(),
                SchemaRecord.id.desc(),
            )
        )
        result = await self.session.scalars(statement)
        return list(result.all())

    async def get_by_form(
        self,
        schema_form_id: UUID,
    ) -> list[SchemaRecord]:
        return await self.list_active(schema_form_id)

    async def get_records_by_form_id(
        self,
        schema_form_id: UUID,
    ) -> list[SchemaRecord]:
        return await self.list_active(schema_form_id)

    async def get_current_approved(
        self,
        schema_form_id: UUID,
    ) -> SchemaRecord | None:
        statement = (
            select(SchemaRecord)
            .options(
                selectinload(SchemaRecord.creator),
                selectinload(SchemaRecord.signed_form_file),
            )
            .where(
                SchemaRecord.schema_form_id == schema_form_id,
                SchemaRecord.deleted_at.is_(None),
                SchemaRecord.status == DocumentStatus.APPROVED,
            )
            .order_by(
                SchemaRecord.upload_date.desc(),
                SchemaRecord.created_at.desc(),
                SchemaRecord.id.desc(),
            )
            .limit(1)
        )
        return await self.session.scalar(statement)

    async def get_unfinished(
        self,
        schema_form_id: UUID,
    ) -> SchemaRecord | None:
        statement = (
            select(SchemaRecord)
            .where(
                SchemaRecord.schema_form_id == schema_form_id,
                SchemaRecord.deleted_at.is_(None),
                SchemaRecord.status.in_(
                    (DocumentStatus.DRAFT, DocumentStatus.UNDER_REVIEW)
                ),
            )
            .limit(1)
        )
        return await self.session.scalar(statement)

    async def add_form(
        self,
        schema_form: SchemaForm,
    ) -> SchemaForm:
        self.session.add(schema_form)
        await self.session.flush()
        return schema_form

    async def add_record(
        self,
        record: SchemaRecord,
    ) -> SchemaRecord:
        self.session.add(record)
        await self.session.flush()
        return record

    async def save(
        self,
        record: SchemaRecord,
    ) -> SchemaRecord:
        await self.session.flush()
        return record

    async def soft_delete(
        self,
        record: SchemaRecord,
        user_id: UUID,
    ) -> SchemaRecord:
        now = datetime.now(timezone.utc)
        record.deleted_at = now
        record.deleted_by = user_id
        record.updated_at = now
        record.updated_by = user_id
        await self.session.flush()
        return record
