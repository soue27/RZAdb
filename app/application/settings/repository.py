from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.rza_settings import SettingsForm
from app.domain.settings_record import SettingsRecord


class SettingsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_form_by_id(
        self,
        settings_form_id: UUID,
    ) -> SettingsForm | None:
        return await self.session.get(SettingsForm, settings_form_id)

    async def get_form_by_urza_id(
        self,
        urza_id: UUID,
    ) -> SettingsForm | None:
        query = select(SettingsForm).where(
            SettingsForm.urza_id == urza_id,
        )
        return await self.session.scalar(query)

    async def get_record_by_id(
        self,
        record_id: UUID,
    ) -> SettingsRecord | None:
        return await self.session.get(SettingsRecord, record_id)

    async def add_form(
            self,
            settings_form: SettingsForm,
    ) -> SettingsForm:
        self.session.add(settings_form)
        await self.session.flush()
        return settings_form

    async def add_record(
            self,
            record: SettingsRecord,
    ) -> SettingsRecord:
        self.session.add(record)
        await self.session.flush()
        return record