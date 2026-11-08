from datetime import date
from uuid import UUID

from app.application.access.service import AccessService
from app.application.maintenance.repository import TORecordRepository
from app.application.tasks.repository import TaskRepository
from app.application.tasks.service import TaskService
from app.application.urzas.repository import URZARepository
from app.application.users.repository import UserRepository
from app.domain.enums import (
    DocumentStatus,
    MaintenanceType,
    TaskStatus,
    TaskWorkType,
    UserRole,
)
from app.domain.maintenance import TORecord

_SUBMIT_ROLES = {UserRole.ENGINEER, UserRole.ADMIN, UserRole.SUPERADMIN}
_OPTIONAL_PROTOCOL_TYPES = {
    MaintenanceType.TK,
    MaintenanceType.O,
    MaintenanceType.OSM,
}


class TORecordService:
    def __init__(
        self,
        repository: TORecordRepository,
        access_service: AccessService,
        task_repository: TaskRepository,
        user_repository: UserRepository,
        urza_repository: URZARepository,
        task_service: TaskService,
    ) -> None:
        self.repository = repository
        self.access_service = access_service
        self.task_repository = task_repository
        self.user_repository = user_repository
        self.urza_repository = urza_repository
        self.task_service = task_service

    async def _get_active_user(self, user_id: UUID):
        user = await self.user_repository.get_by_id(user_id)
        if user is None:
            raise PermissionError("Пользователь не найден.")
        if not user.active or user.deleted_at is not None:
            raise PermissionError("Пользователь неактивен или удалён.")
        return user

    async def _ensure_modify_access(self, user_id: UUID, urza_id: UUID) -> None:
        if not await self.access_service.can_modify_urza(user_id, urza_id):
            raise PermissionError("Изменение архивной URZA запрещено.")

    async def _get_record_for_urza(
        self,
        user_id: UUID,
        record_id: UUID,
        urza_id: UUID,
        *,
        for_update: bool = False,
    ) -> TORecord:
        if not await self.access_service.can_access_urza(user_id, urza_id):
            raise PermissionError("Доступ к URZA запрещён.")
        record = (
            await self.repository.get_by_id_for_update(record_id)
            if for_update
            else await self.repository.get_by_id(record_id)
        )
        if record is None:
            raise ValueError("Запись ТО не найдена.")
        if record.urza_id != urza_id:
            raise ValueError("Запись ТО не принадлежит указанной URZA.")
        return record

    async def _check_manager_reviewer(
        self,
        user_id: UUID,
        urza_id: UUID,
    ) -> None:
        user = await self._get_active_user(user_id)
        if user.role is not UserRole.MANAGER:
            raise PermissionError("Согласовывать ТО может только руководитель.")
        urza = await self.urza_repository.get_by_id(urza_id)
        if urza is None or urza.connection is None or urza.connection.substation is None:
            raise ValueError("Не удалось определить производственное отделение УРЗА.")
        if user.enterprise_id != urza.connection.substation.enterprise_id:
            raise PermissionError(
                "Руководитель не отвечает за производственное отделение данного УРЗА."
            )

    async def _get_linked_task(
        self,
        *,
        user_id: UUID,
        urza_id: UUID,
        record: TORecord,
    ):
        if record.task_id is None:
            return None
        task = await self.task_repository.get_by_id(record.task_id)
        if task is None or task.deleted_at is not None:
            raise ValueError("Связанное активное задание не найдено.")
        if task.work_type is not TaskWorkType.MAINTENANCE:
            raise ValueError("Связанное задание не предназначено для ТО.")
        if task.urza_id != urza_id:
            raise ValueError("Связанное задание относится к другому УРЗА.")
        if task.assigned_to != user_id and task.status is not TaskStatus.UNDER_REVIEW:
            raise PermissionError("Действие доступно только назначенному исполнителю.")
        return task

    async def validate_task_for_result(
        self,
        user_id: UUID,
        urza_id: UUID,
        task_id: UUID,
    ):
        await self._ensure_modify_access(user_id, urza_id)
        user = await self._get_active_user(user_id)
        if user.role not in _SUBMIT_ROLES:
            raise PermissionError("Создавать запись ТО с текущей ролью запрещено.")
        task = await self.task_repository.get_by_id(task_id)
        if task is None or task.deleted_at is not None:
            raise ValueError("Активное задание не найдено.")
        if task.work_type is not TaskWorkType.MAINTENANCE:
            raise ValueError("Задание не предназначено для работы по ТО.")
        if task.urza_id != urza_id:
            raise ValueError("Задание относится к другому устройству РЗА.")
        if task.assigned_to != user_id:
            raise PermissionError(
                "Создать результат может только назначенный исполнитель задачи."
            )
        if task.status is not TaskStatus.IN_PROGRESS:
            raise ValueError("Создавать результат можно только по задаче в работе.")
        if await self.repository.get_by_task_id(task_id) is not None:
            raise ValueError("Для задачи уже существует активная запись ТО.")
        return task

    async def get_by_urza(
        self,
        user_id: UUID,
        urza_id: UUID,
    ) -> list[TORecord]:
        if not await self.access_service.can_access_urza(user_id, urza_id):
            raise PermissionError("Доступ к URZA запрещён.")
        return await self.repository.get_by_urza_id(urza_id)

    async def get_current_approved(
        self,
        user_id: UUID,
        urza_id: UUID,
    ) -> TORecord | None:
        if not await self.access_service.can_access_urza(user_id, urza_id):
            raise PermissionError("Доступ к URZA запрещён.")
        return await self.repository.get_current_approved(urza_id)

    async def get_by_task(
        self,
        user_id: UUID,
        task_id: UUID,
        urza_id: UUID,
    ) -> TORecord | None:
        if not await self.access_service.can_access_urza(user_id, urza_id):
            raise PermissionError("Доступ к URZA запрещён.")
        record = await self.repository.get_by_task_id(task_id)
        if record is not None and record.urza_id != urza_id:
            raise ValueError("Запись ТО не принадлежит указанной URZA.")
        return record

    async def create(
        self,
        user_id: UUID,
        urza_id: UUID,
        maintenance_date: date,
        maintenance_type: MaintenanceType,
        signed_form_file_id: UUID,
        scan_protocol_id: UUID | None = None,
        editable_protocol_id: UUID | None = None,
        detected_deviations: str = "Не выявлено",
        measures_taken: str = "Не требуется",
        historical_data: bool = False,
        task_id: UUID | None = None,
    ) -> TORecord:
        await self._ensure_modify_access(user_id, urza_id)
        user = await self._get_active_user(user_id)
        if user.role not in {
            UserRole.MANAGER,
            UserRole.ENGINEER,
            UserRole.ADMIN,
            UserRole.SUPERADMIN,
        }:
            raise PermissionError("Создавать записи ТО с текущей ролью запрещено.")
        if signed_form_file_id is None:
            raise ValueError("Для записи ТО необходим скан подписанной формы.")
        if maintenance_type not in _OPTIONAL_PROTOCOL_TYPES and scan_protocol_id is None:
            raise ValueError("Для данного типа ТО требуется протокол (скан протокола).")
        if task_id is not None:
            await self.validate_task_for_result(user_id, urza_id, task_id)

        record = TORecord(
            urza_id=urza_id,
            historical_data=historical_data,
            maintenance_date=maintenance_date,
            maintenance_type=maintenance_type,
            detected_deviations=detected_deviations,
            measures_taken=measures_taken,
            status=(
                DocumentStatus.APPROVED
                if user.role is UserRole.MANAGER
                else DocumentStatus.DRAFT
            ),
            created_by=user_id,
            updated_by=user_id,
            scan_protocol_id=scan_protocol_id,
            editable_protocol_id=editable_protocol_id,
            signed_form_file_id=signed_form_file_id,
            task_id=task_id,
        )
        await self.repository.add(record)
        return record

    async def get_by_id(
        self,
        user_id: UUID,
        record_id: UUID,
        urza_id: UUID,
    ) -> TORecord | None:
        if not await self.access_service.can_access_urza(user_id, urza_id):
            raise PermissionError("Доступ к URZA запрещён.")
        record = await self.repository.get_by_id(record_id)
        if record is not None and record.urza_id != urza_id:
            raise ValueError("Запись ТО не принадлежит указанной URZA.")
        return record

    async def update(
        self,
        user_id: UUID,
        urza_id: UUID,
        record_id: UUID,
        maintenance_date: date,
        maintenance_type: MaintenanceType,
        signed_form_file_id: UUID | None = None,
        scan_protocol_id: UUID | None = None,
        editable_protocol_id: UUID | None = None,
        detected_deviations: str = "Не выявлено",
        measures_taken: str = "Не требуется",
        historical_data: bool = False,
    ) -> TORecord:
        await self._ensure_modify_access(user_id, urza_id)
        record = await self._get_record_for_urza(
            user_id, record_id, urza_id, for_update=True
        )
        user = await self._get_active_user(user_id)
        if user.role not in _SUBMIT_ROLES:
            raise PermissionError("Редактировать запись ТО с текущей ролью запрещено.")
        if user.role is UserRole.ENGINEER and record.created_by != user_id:
            raise PermissionError("Редактировать можно только собственный черновик ТО.")
        if record.status is not DocumentStatus.DRAFT:
            raise ValueError("Редактировать можно только черновик ТО.")
        effective_signed_form = signed_form_file_id or record.signed_form_file_id
        effective_scan_protocol = scan_protocol_id or record.scan_protocol_id
        effective_editable_protocol = editable_protocol_id or record.editable_protocol_id
        if effective_signed_form is None:
            raise ValueError("Для записи ТО необходим скан подписанной формы.")
        if (
            maintenance_type not in _OPTIONAL_PROTOCOL_TYPES
            and effective_scan_protocol is None
        ):
            raise ValueError("Для данного типа ТО требуется протокол (скан протокола).")
        record.maintenance_date = maintenance_date
        record.maintenance_type = maintenance_type
        record.signed_form_file_id = effective_signed_form
        record.scan_protocol_id = effective_scan_protocol
        record.editable_protocol_id = effective_editable_protocol
        record.detected_deviations = detected_deviations
        record.measures_taken = measures_taken
        record.historical_data = historical_data
        record.updated_by = user_id
        await self.repository.save(record)
        return record

    async def get_available_actions(
        self,
        user_id: UUID,
        record: TORecord,
    ) -> set[str]:
        if record.deleted_at is not None:
            return set()
        try:
            await self._ensure_modify_access(user_id, record.urza_id)
            user = await self._get_active_user(user_id)
        except PermissionError:
            return set()
        if record.status is DocumentStatus.DRAFT:
            if user.role in _SUBMIT_ROLES and (
                user.role is not UserRole.ENGINEER or record.created_by == user_id
            ):
                return {"edit", "submit"}
            return set()
        if record.status is DocumentStatus.UNDER_REVIEW and user.role is UserRole.MANAGER:
            try:
                await self._check_manager_reviewer(user_id, record.urza_id)
            except (PermissionError, ValueError):
                return set()
            return {"approve", "return"}
        return set()

    async def submit_for_review(
        self,
        user_id: UUID,
        record_id: UUID,
        urza_id: UUID,
    ) -> TORecord:
        await self._ensure_modify_access(user_id, urza_id)
        record = await self._get_record_for_urza(
            user_id, record_id, urza_id, for_update=True
        )
        user = await self._get_active_user(user_id)
        if user.role not in _SUBMIT_ROLES:
            raise PermissionError("Отправлять ТО на согласование запрещено.")
        if user.role is UserRole.ENGINEER and record.created_by != user_id:
            raise PermissionError("Отправить можно только собственный черновик ТО.")
        if record.status is not DocumentStatus.DRAFT:
            raise ValueError("На согласование можно отправить только черновик ТО.")
        if record.signed_form_file_id is None:
            raise ValueError("Для отправки ТО необходим скан подписанной формы.")
        if record.maintenance_type not in _OPTIONAL_PROTOCOL_TYPES and record.scan_protocol_id is None:
            raise ValueError("Для данного типа ТО требуется протокол (скан протокола).")

        try:
            task = await self._get_linked_task(
                user_id=user_id,
                urza_id=urza_id,
                record=record,
            )
            if task is not None:
                if task.status is not TaskStatus.IN_PROGRESS:
                    raise ValueError("Связанное задание должно быть в работе.")
                await self.task_service.complete_task(task=task, actor_id=user_id)
                await self.task_service.submit_for_review(task=task, actor_id=user_id)
            record.status = DocumentStatus.UNDER_REVIEW
            record.updated_by = user_id
            await self.repository.save(record)
        except Exception:
            await self.repository.session.rollback()
            raise
        return record

    async def approve(
        self,
        user_id: UUID,
        record_id: UUID,
        urza_id: UUID,
    ) -> TORecord:
        await self._ensure_modify_access(user_id, urza_id)
        record = await self._get_record_for_urza(
            user_id, record_id, urza_id, for_update=True
        )
        if record.status is not DocumentStatus.UNDER_REVIEW:
            raise ValueError("Утвердить можно только запись ТО на согласовании.")
        await self._check_manager_reviewer(user_id, urza_id)
        if record.signed_form_file_id is None:
            raise ValueError("Для утверждения ТО необходима подписанная форма.")
        try:
            task = await self._get_linked_task(
                user_id=user_id,
                urza_id=urza_id,
                record=record,
            )
            record.status = DocumentStatus.APPROVED
            record.updated_by = user_id
            await self.repository.save(record)
            if task is not None:
                if task.status is not TaskStatus.UNDER_REVIEW:
                    raise ValueError("Связанное задание должно быть на проверке.")
                await self.task_service.close_task(task=task, actor_id=user_id)
        except Exception:
            await self.repository.session.rollback()
            raise
        return record

    async def return_to_draft(
        self,
        user_id: UUID,
        record_id: UUID,
        urza_id: UUID,
        comment: str,
    ) -> TORecord:
        await self._ensure_modify_access(user_id, urza_id)
        record = await self._get_record_for_urza(
            user_id, record_id, urza_id, for_update=True
        )
        if record.status is not DocumentStatus.UNDER_REVIEW:
            raise ValueError("Вернуть на доработку можно только ТО на согласовании.")
        await self._check_manager_reviewer(user_id, urza_id)
        if not comment or not comment.strip():
            raise ValueError("Укажите причину возврата на доработку.")
        try:
            task = await self._get_linked_task(
                user_id=user_id,
                urza_id=urza_id,
                record=record,
            )
            if task is not None:
                if task.status is not TaskStatus.UNDER_REVIEW:
                    raise ValueError("Связанное задание должно быть на проверке.")
                await self.task_service.return_for_revision(
                    task=task,
                    actor_id=user_id,
                    comment=comment,
                )
            record.status = DocumentStatus.DRAFT
            record.updated_by = user_id
            await self.repository.save(record)
        except Exception:
            await self.repository.session.rollback()
            raise
        return record

    async def list_standalone_under_review(
        self,
        user_id: UUID,
    ) -> list[TORecord]:
        try:
            user = await self._get_active_user(user_id)
        except PermissionError:
            return []
        if user.role is not UserRole.MANAGER:
            return []
        visible = []
        for record in await self.repository.list_standalone_under_review():
            if not await self.access_service.can_access_urza(user_id, record.urza_id):
                continue
            try:
                await self._check_manager_reviewer(user_id, record.urza_id)
            except (PermissionError, ValueError):
                continue
            visible.append(record)
        return visible

    async def list_standalone_work_items(
        self,
        user_id: UUID,
    ) -> list[TORecord]:
        try:
            await self._get_active_user(user_id)
        except PermissionError:
            return []
        items = []
        for record in await self.repository.list_standalone_work_items():
            if record.status is DocumentStatus.DRAFT and record.created_by != user_id:
                continue
            if not await self.access_service.can_access_urza(user_id, record.urza_id):
                continue
            actions = await self.get_available_actions(user_id, record)
            if record.status is DocumentStatus.DRAFT and not actions.intersection(
                {"edit", "submit"}
            ):
                continue
            if (
                record.status is DocumentStatus.UNDER_REVIEW
                and not actions.intersection({"approve", "return"})
                and record.created_by != user_id
            ):
                continue
            items.append(record)
        return items
