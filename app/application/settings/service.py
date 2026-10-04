from datetime import date, datetime, timezone
from uuid import UUID

from sqlalchemy.exc import IntegrityError

from app.application.access.service import AccessService
from app.application.settings.repository import SettingsRepository
from app.domain.enums import DocumentStatus, UserRole
from app.domain.rza_settings import SettingsForm
from app.domain.settings_record import SettingsRecord


_RECORD_ROLES = {
    UserRole.ENGINEER,
    UserRole.MANAGER,
    UserRole.ADMIN,
    UserRole.SUPERADMIN,
}
_UNFINISHED_INDEX = "uq_settings_records_one_active_unfinished_per_form"


class SettingsService:
    def __init__(
        self,
        repository: SettingsRepository,
        access_service: AccessService,
    ) -> None:
        self.repository = repository
        self.access_service = access_service

    async def _get_user(self, user_id: UUID):
        user = await self.access_service.user_repository.get_by_id(user_id)
        if user is None:
            raise ValueError("Пользователь не найден.")
        if not user.active or user.deleted_at is not None:
            raise PermissionError("Пользователь неактивен.")
        return user

    async def _ensure_access(self, user_id: UUID, urza_id: UUID) -> None:
        if not await self.access_service.can_access_urza(user_id, urza_id):
            raise PermissionError("Доступ к URZA запрещён")

    async def _get_record_for_urza(
        self,
        user_id: UUID,
        urza_id: UUID,
        record_id: UUID,
    ) -> SettingsRecord:
        await self._ensure_access(user_id, urza_id)
        record = await self.repository.get_record_by_id(record_id)
        if record is None:
            raise ValueError("Запись уставок не найдена")
        settings_form = await self.repository.get_form_by_id(
            record.settings_form_id
        )
        if settings_form is None:
            raise ValueError("Формуляр уставок не найден")
        if settings_form.urza_id != urza_id:
            raise ValueError("Запись уставок не принадлежит данному URZA")
        return record

    async def _check_manager_reviewer(
        self,
        user_id: UUID,
        urza_id: UUID,
    ) -> None:
        user = await self._get_user(user_id)
        if user.role is not UserRole.MANAGER:
            raise PermissionError("Согласовывать уставки может только Manager.")
        await self._ensure_access(user_id, urza_id)

    async def get_by_urza(
        self,
        user_id: UUID,
        urza_id: UUID,
    ) -> SettingsForm | None:
        if not await self.access_service.can_access_urza(user_id, urza_id):
            return None
        return await self.repository.get_form_by_urza_id(urza_id)

    async def get_details(
        self,
        user_id: UUID,
        urza_id: UUID,
    ) -> tuple[SettingsForm | None, list[SettingsRecord]]:
        if not await self.access_service.can_access_urza(user_id, urza_id):
            return None, []
        settings_form = await self.repository.get_form_by_urza_id(urza_id)
        if settings_form is None:
            return None, []
        records = await self.repository.get_records_by_form_id(settings_form.id)
        return settings_form, records

    async def get_current_approved(
        self,
        user_id: UUID,
        urza_id: UUID,
    ) -> SettingsRecord | None:
        await self._ensure_access(user_id, urza_id)
        settings_form = await self.repository.get_form_by_urza_id(urza_id)
        if settings_form is None:
            return None
        return await self.repository.get_current_approved(settings_form.id)

    async def create_form(
        self,
        user_id: UUID,
        urza_id: UUID,
    ) -> SettingsForm:
        await self._ensure_access(user_id, urza_id)
        existing_form = await self.repository.get_form_by_urza_id(urza_id)
        if existing_form is not None:
            raise ValueError("Форма уставок для данного URZA уже существует")
        settings_form = SettingsForm(
            urza_id=urza_id,
            created_by=user_id,
            updated_by=user_id,
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
        await self._ensure_access(user_id, urza_id)
        if signed_form_file_id is None:
            raise ValueError("Подписанный формуляр уставок обязателен.")
        user = await self._get_user(user_id)
        if user.role not in _RECORD_ROLES:
            raise PermissionError("Создавать уставки с текущей ролью запрещено.")

        settings_form = await self.repository.get_form_by_urza_id(urza_id)
        if settings_form is None:
            settings_form = SettingsForm(
                urza_id=urza_id,
                created_by=user_id,
                updated_by=user_id,
            )
            await self.repository.add_form(settings_form)

        if await self.repository.get_unfinished(settings_form.id) is not None:
            raise ValueError("Для данного формуляра уже существует незавершённая запись уставок.")

        status = (
            DocumentStatus.APPROVED
            if user.role is UserRole.MANAGER
            else DocumentStatus.DRAFT
        )
        record = SettingsRecord(
            settings_form_id=settings_form.id,
            change_date=change_date,
            parameter_name=parameter_name,
            initial_setting=initial_setting,
            new_setting=new_setting,
            change_reason=change_reason,
            status=status,
            created_by=user_id,
            updated_by=user_id,
            signed_form_file_id=signed_form_file_id,
            task_id=task_id,
        )
        try:
            await self.repository.add_record(record)
        except IntegrityError as exc:
            if _UNFINISHED_INDEX in str(exc.orig):
                raise ValueError(
                    "Для данного формуляра уже существует незавершённая запись уставок."
                ) from exc
            raise
        return record

    async def update_draft(
        self,
        user_id: UUID,
        urza_id: UUID,
        record_id: UUID,
        change_date: date,
        parameter_name: str,
        initial_setting: str,
        new_setting: str,
        change_reason: str,
        signed_form_file_id: UUID | None = None,
    ) -> SettingsRecord:
        record = await self._get_record_for_urza(user_id, urza_id, record_id)
        user = await self._get_user(user_id)
        if user.role not in _RECORD_ROLES:
            raise PermissionError("Редактировать уставки с текущей ролью запрещено.")
        if record.status is not DocumentStatus.DRAFT:
            raise ValueError("Изменять можно только черновик уставок.")
        effective_file_id = signed_form_file_id or record.signed_form_file_id
        if effective_file_id is None:
            raise ValueError("Подписанный формуляр уставок обязателен.")
        record.change_date = change_date
        record.parameter_name = parameter_name
        record.initial_setting = initial_setting
        record.new_setting = new_setting
        record.change_reason = change_reason
        record.signed_form_file_id = effective_file_id
        record.updated_by = user_id
        await self.repository.save(record)
        return record

    async def submit_for_review(
        self,
        user_id: UUID,
        urza_id: UUID,
        record_id: UUID,
    ) -> SettingsRecord:
        record = await self._get_record_for_urza(user_id, urza_id, record_id)
        user = await self._get_user(user_id)
        if user.role not in _RECORD_ROLES:
            raise PermissionError("Отправлять уставки на согласование запрещено.")
        if record.status is not DocumentStatus.DRAFT:
            raise ValueError("На согласование можно отправить только черновик.")
        if record.signed_form_file_id is None:
            raise ValueError("Подписанный формуляр уставок обязателен.")
        record.status = DocumentStatus.UNDER_REVIEW
        record.updated_by = user_id
        await self.repository.save(record)
        return record

    async def approve(
        self,
        user_id: UUID,
        urza_id: UUID,
        record_id: UUID,
    ) -> SettingsRecord:
        record = await self._get_record_for_urza(user_id, urza_id, record_id)
        if record.status is not DocumentStatus.UNDER_REVIEW:
            raise ValueError("Утвердить можно только запись на согласовании.")
        await self._check_manager_reviewer(user_id, urza_id)
        if record.signed_form_file_id is None:
            raise ValueError("Подписанный формуляр уставок обязателен.")
        record.status = DocumentStatus.APPROVED
        record.updated_by = user_id
        await self.repository.save(record)
        return record

    async def return_to_draft(
        self,
        user_id: UUID,
        urza_id: UUID,
        record_id: UUID,
    ) -> SettingsRecord:
        record = await self._get_record_for_urza(user_id, urza_id, record_id)
        if record.status is not DocumentStatus.UNDER_REVIEW:
            raise ValueError("Вернуть в черновик можно только запись на согласовании.")
        await self._check_manager_reviewer(user_id, urza_id)
        record.status = DocumentStatus.DRAFT
        record.updated_by = user_id
        await self.repository.save(record)
        return record

    async def delete_record(
        self,
        user_id: UUID,
        urza_id: UUID,
        record_id: UUID,
    ) -> None:
        record = await self._get_record_for_urza(user_id, urza_id, record_id)
        user = await self._get_user(user_id)
        if user.role not in {UserRole.ADMIN, UserRole.SUPERADMIN}:
            raise PermissionError("Удалять записи уставок может только ADMIN или SUPERADMIN.")
        record.deleted_at = datetime.now(timezone.utc)
        record.deleted_by = user_id
        record.updated_by = user_id
        await self.repository.save(record)

    async def get_available_actions(
        self,
        user_id: UUID,
        record: SettingsRecord,
    ) -> set[str]:
        if record.deleted_at is not None:
            return set()
        try:
            user = await self._get_user(user_id)
            settings_form = await self.repository.get_form_by_id(record.settings_form_id)
            if settings_form is None or not await self.access_service.can_access_urza(
                user_id, settings_form.urza_id
            ):
                return set()
        except (PermissionError, ValueError):
            return set()

        actions: set[str] = set()
        if record.status is DocumentStatus.DRAFT and user.role in _RECORD_ROLES:
            actions.update({"edit", "submit"})
        elif record.status is DocumentStatus.UNDER_REVIEW and user.role is UserRole.MANAGER:
            try:
                await self._check_manager_reviewer(user_id, settings_form.urza_id)
            except (PermissionError, ValueError):
                pass
            else:
                actions.update({"approve", "return"})
        if user.role in {UserRole.ADMIN, UserRole.SUPERADMIN}:
            actions.add("delete")
        return actions
