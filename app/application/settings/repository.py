from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.domain.enums import DocumentStatus
from app.domain.rza_settings import SettingsForm
from app.domain.settings_record import SettingsRecord


class SettingsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_form_by_id(self, form_id: UUID) -> SettingsForm | None:
        statement = select(SettingsForm).where(
            SettingsForm.id == form_id,
            SettingsForm.deleted_at.is_(None),
        )
        return await self.session.scalar(statement)

    async def get_form_by_urza_id(self, urza_id: UUID) -> SettingsForm | None:
        statement = select(SettingsForm).where(
            SettingsForm.urza_id == urza_id,
            SettingsForm.deleted_at.is_(None),
        )
        return await self.session.scalar(statement)

    async def get_record_by_id(self, record_id: UUID) -> SettingsRecord | None:
        statement = select(SettingsRecord).where(
            SettingsRecord.id == record_id,
            SettingsRecord.deleted_at.is_(None),
        )
        return await self.session.scalar(statement)

    async def get_records(self, form_id: UUID) -> list[SettingsRecord]:
        statement = (
            select(SettingsRecord)
            .where(
                SettingsRecord.settings_form_id == form_id,
                SettingsRecord.deleted_at.is_(None),
            )
            .options(selectinload(SettingsRecord.creator))
            .order_by(
                SettingsRecord.change_date.desc(),
                SettingsRecord.created_at.desc(),
                SettingsRecord.id.desc(),
            )
        )
        result = await self.session.scalars(statement)
        return list(result.all())

    async def get_records_by_form_id(
        self,
        form_id: UUID,
    ) -> list[SettingsRecord]:
        return await self.get_records(form_id)

    async def get_current_approved(
        self,
        form_id: UUID,
    ) -> SettingsRecord | None:
        statement = (
            select(SettingsRecord)
            .where(
                SettingsRecord.settings_form_id == form_id,
                SettingsRecord.deleted_at.is_(None),
                SettingsRecord.status == DocumentStatus.APPROVED,
            )
            .options(
                selectinload(SettingsRecord.creator),
                selectinload(SettingsRecord.signed_form_file),
            )
            .order_by(
                SettingsRecord.change_date.desc(),
                SettingsRecord.created_at.desc(),
                SettingsRecord.id.desc(),
            )
            .limit(1)
        )
        return await self.session.scalar(statement)

    async def get_unfinished(self, form_id: UUID) -> SettingsRecord | None:
        statement = (
            select(SettingsRecord)
            .where(
                SettingsRecord.settings_form_id == form_id,
                SettingsRecord.deleted_at.is_(None),
                SettingsRecord.status.in_(
                    (DocumentStatus.DRAFT, DocumentStatus.UNDER_REVIEW)
                ),
            )
            .limit(1)
        )
        return await self.session.scalar(statement)

    async def add_form(self, settings_form: SettingsForm) -> SettingsForm:
        self.session.add(settings_form)
        await self.session.flush()
        return settings_form

    async def add_record(self, settings_record: SettingsRecord) -> SettingsRecord:
        self.session.add(settings_record)
        await self.session.flush()
        return settings_record

    async def save(self, settings_record: SettingsRecord) -> SettingsRecord:
        await self.session.flush()
        return settings_record

    async def flush(self) -> None:
        await self.session.flush()
