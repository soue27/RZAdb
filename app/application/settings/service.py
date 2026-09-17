from uuid import UUID
from datetime import date

from app.application.access.service import AccessService
from app.application.settings.repository import SettingsRepository
from app.domain.rza_settings import SettingsForm
from app.domain.settings_record import SettingsRecord


class SettingsService:
    def __init__(
        self,
        repository: SettingsRepository,
        access_service: AccessService,
    ) -> None:
        self.repository = repository
        self.access_service = access_service

    async def get_by_urza(
        self,
        user_id: UUID,
        urza_id: UUID,
    ) -> SettingsForm | None:
        if not await self.access_service.can_access_urza(
            user_id,
            urza_id,
        ):
            return None

        return await self.repository.get_form_by_urza_id(urza_id)

    async def create_form(
            self,
            user_id: UUID,
            urza_id: UUID,
    ) -> SettingsForm:
        if not await self.access_service.can_access_urza(
                user_id,
                urza_id,
        ):
            raise PermissionError("Доступ к URZA запрещён")

        existing_form = await self.repository.get_form_by_urza_id(
            urza_id,
        )

        if existing_form is not None:
            raise ValueError(
                "Форма уставок для данного URZA уже существует"
            )

        settings_form = SettingsForm(
            urza_id=urza_id,
        )

        await self.repository.add_form(settings_form)

        return settings_form

    async def create_record(
            self,
            user_id: UUID,
            urza_id: UUID,
            change_date: date,
            parameter_name: str,
            initial_setting: str,
            new_setting: str,
            change_reason: str,
            signed_form_file_id: UUID,
            task_id: UUID | None = None,
    ) -> SettingsRecord:
        if not await self.access_service.can_access_urza(
                user_id,
                urza_id,
        ):
            raise PermissionError("Доступ к URZA запрещён")

        settings_form = await self.repository.get_form_by_urza_id(
            urza_id,
        )

        if settings_form is None:
            raise ValueError(
                "Форма уставок для данного URZA не существует"
            )

        record = SettingsRecord(
            settings_form_id=settings_form.id,
            change_date=change_date,
            parameter_name=parameter_name,
            initial_setting=initial_setting,
            new_setting=new_setting,
            change_reason=change_reason,
            created_by=user_id,
            signed_form_file_id=signed_form_file_id,
            task_id=task_id,
        )

        await self.repository.add_record(record)

        return record

