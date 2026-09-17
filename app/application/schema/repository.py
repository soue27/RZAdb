from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.schema import SchemaForm, SchemaRecord


class SchemaRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_form_by_id(
        self,
        schema_form_id: UUID,
    ) -> SchemaForm | None:
        return await self.session.get(
            SchemaForm,
            schema_form_id,
        )

    async def get_form_by_urza_id(
        self,
        urza_id: UUID,
    ) -> SchemaForm | None:
        query = select(SchemaForm).where(
            SchemaForm.urza_id == urza_id,
        )
        return await self.session.scalar(query)

    async def get_record_by_id(
        self,
        record_id: UUID,
    ) -> SchemaRecord | None:
        return await self.session.get(
            SchemaRecord,
            record_id,
        )

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