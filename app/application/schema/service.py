from datetime import date
from uuid import UUID

from sqlalchemy.exc import IntegrityError

from app.application.access.service import AccessService
from app.application.schema.repository import SchemaRepository
from app.application.tasks.repository import TaskRepository
from app.domain.enums import DocumentStatus, TaskStatus, TaskWorkType, UserRole
from app.domain.schema import SchemaForm, SchemaRecord
from app.domain.task import Task

_RECORD_ROLES = {
    UserRole.ENGINEER,
    UserRole.MANAGER,
    UserRole.ADMIN,
    UserRole.SUPERADMIN,
}
_UNFINISHED_INDEX = "uq_schema_records_one_active_unfinished_per_form"
_TASK_RECORD_INDEX = "uq_schema_records_one_active_per_task"


class SchemaService:
    """Управляет формуляром схем УРЗА, записями схем и процессом согласования.
    """
    def __init__(
        self,
        repository: SchemaRepository,
        access_service: AccessService,
        task_repository: TaskRepository,
    ) -> None:
        """Сохраняет репозиторий схем, сервис проверки доступа и репозиторий задач.

        Args:
            repository: Репозиторий формуляров и записей схем.
            access_service: Централизованный сервис проверки доступа.
            task_repository: Репозиторий задач.
        """
        self.repository = repository
        self.access_service = access_service
        self.task_repository = task_repository

    async def _get_user(self, user_id: UUID):
        """Возвращает активного пользователя.

        Args:
            user_id: Идентификатор пользователя.

        Raises:
            ValueError: Если пользователь не найден.
            PermissionError: Если пользователь неактивен.
        """
        user = await self.access_service.user_repository.get_by_id(user_id)
        if user is None:
            raise ValueError("Пользователь не найден.")
        if not user.active or user.deleted_at is not None:
            raise PermissionError("Пользователь неактивен.")
        return user

    async def _ensure_access(self, user_id: UUID, urza_id: UUID) -> None:
        """Проверяет право пользователя изменять схемы указанного УРЗА.
        """
        if not await self.access_service.can_modify_urza(user_id, urza_id):
            raise PermissionError("Изменение архивной URZA запрещено")

    async def _validate_task_for_result(
        self,
        user_id: UUID,
        urza_id: UUID,
        task_id: UUID,
    ) -> Task:
        """Проверяет, что задача может быть связана с создаваемым результатом схем.

        Args:
            user_id: Идентификатор исполнителя.
            urza_id: Идентификатор устройства.
            task_id: Идентификатор задачи.

        Returns:
            Проверенная задача.

        Raises:
            ValueError: Если задача не подходит по типу, владельцу или статусу.
            PermissionError: Если пользователь не является назначенным исполнителем.
        """
        task = await self.task_repository.get_by_id(task_id)
        if task is None or task.deleted_at is not None:
            raise ValueError("Активная задача не найдена.")
        if task.work_type is not TaskWorkType.SCHEMES:
            raise ValueError("Задача не предназначена для работы со схемами.")
        if task.urza_id != urza_id:
            raise ValueError("Задача относится к другой URZA.")
        if task.assigned_to != user_id:
            raise PermissionError(
                "Создать результат может только назначенный исполнитель задачи."
            )
        if task.status is not TaskStatus.IN_PROGRESS:
            raise ValueError("Создавать результат можно только по задаче в работе.")
        if (
            await self.task_repository.get_schema_record_by_task_id(task_id)
            is not None
        ):
            raise ValueError("Для задачи уже существует активный результат схем.")
        return task

    async def validate_task_for_result(
        self,
        user_id: UUID,
        urza_id: UUID,
        task_id: UUID,
    ) -> Task:
        """Проверяет Task-контекст перед показом формы результата Schemes."""
        await self._ensure_access(user_id, urza_id)
        return await self._validate_task_for_result(user_id, urza_id, task_id)

    async def _get_record_for_urza(
        self,
        user_id: UUID,
        urza_id: UUID,
        record_id: UUID,
    ) -> SchemaRecord:
        """Находит запись схем и проверяет принадлежность формуляра указанному УРЗА.
        """
        await self._ensure_access(user_id, urza_id)
        record = await self.repository.get_by_id(record_id)
        if record is None:
            raise ValueError("Запись схемы не найдена.")
        schema_form = await self.repository.get_form_by_id(record.schema_form_id)
        if schema_form is None:
            raise ValueError("Формуляр схем не найден.")
        if schema_form.urza_id != urza_id:
            raise ValueError("Запись схемы не принадлежит указанной URZA.")
        return record

    async def _check_manager_reviewer(
        self,
        user_id: UUID,
        urza_id: UUID,
    ) -> None:
        """Проверяет, что согласование выполняет активный MANAGER с доступом к УРЗА.
        """
        user = await self._get_user(user_id)
        if user.role is not UserRole.MANAGER:
            raise PermissionError("Согласовывать схемы может только MANAGER.")
        await self._ensure_access(user_id, urza_id)

    @staticmethod
    def _is_unfinished_conflict(error: IntegrityError) -> bool:
        """Определяет, вызвана ли ошибка целостности ограничением одной незавершённой записи на формуляр.

        Args:
            error: Ошибка SQLAlchemy IntegrityError.

        Returns:
            True, если нарушено ограничение незавершённой записи.
        """
        original = error.orig
        constraint_name = getattr(original, "constraint_name", None)
        return (
            constraint_name == _UNFINISHED_INDEX
            or _UNFINISHED_INDEX in str(original)
        )

    async def get_by_urza(
        self,
        user_id: UUID,
        urza_id: UUID,
    ) -> SchemaForm | None:
        """Возвращает формуляр схем устройства при наличии права чтения.

        Args:
            user_id: Идентификатор пользователя.
            urza_id: Идентификатор устройства.

        Returns:
            Формуляр схем или None.
        """
        if not await self.access_service.can_access_urza(user_id, urza_id):
            return None
        return await self.repository.get_form_by_urza_id(urza_id)

    async def get_form(
        self,
        user_id: UUID,
        urza_id: UUID,
    ) -> SchemaForm | None:
        """Возвращает формуляр схем устройства после проверки доступа.

        Args:
            user_id: Идентификатор пользователя.
            urza_id: Идентификатор устройства.

        Returns:
            Формуляр схем или None.
        """
        await self._ensure_access(user_id, urza_id)
        return await self.repository.get_form_by_urza_id(urza_id)

    async def get_records(
        self,
        user_id: UUID,
        urza_id: UUID,
    ) -> list[SchemaRecord]:
        """Возвращает активные записи схем устройства.

        Args:
            user_id: Идентификатор пользователя.
            urza_id: Идентификатор устройства.

        Returns:
            Список записей схем.
        """
        if not await self.access_service.can_access_urza(user_id, urza_id):
            return []
        schema_form = await self.repository.get_form_by_urza_id(urza_id)
        if schema_form is None:
            return []
        return await self.repository.list_active(schema_form.id)

    async def get_current(
        self,
        user_id: UUID,
        urza_id: UUID,
    ) -> SchemaRecord | None:
        """Возвращает текущую утверждённую запись схем устройства.

        Args:
            user_id: Идентификатор пользователя.
            urza_id: Идентификатор устройства.

        Returns:
            Последняя утверждённая запись или None.
        """
        await self._ensure_access(user_id, urza_id)
        schema_form = await self.repository.get_form_by_urza_id(urza_id)
        if schema_form is None:
            return None
        return await self.repository.get_current_approved(schema_form.id)

    async def get_unfinished(
        self,
        user_id: UUID,
        urza_id: UUID,
    ) -> SchemaRecord | None:
        """Возвращает незавершённую запись формуляра схем.

        Args:
            user_id: Идентификатор пользователя.
            urza_id: Идентификатор устройства.

        Returns:
            Запись в статусе DRAFT или UNDER_REVIEW либо None.
        """
        await self._ensure_access(user_id, urza_id)
        schema_form = await self.repository.get_form_by_urza_id(urza_id)
        if schema_form is None:
            return None
        return await self.repository.get_unfinished(schema_form.id)

    async def get_details(
        self,
        user_id: UUID,
        urza_id: UUID,
    ) -> tuple[SchemaForm | None, list[SchemaRecord]]:
        """Возвращает формуляр схем и список его записей.

        Args:
            user_id: Идентификатор пользователя.
            urza_id: Идентификатор устройства.

        Returns:
            Пара из формуляра (или None) и списка записей.
        """
        if not await self.access_service.can_access_urza(user_id, urza_id):
            return None, []
        schema_form = await self.repository.get_form_by_urza_id(urza_id)
        if schema_form is None:
            return None, []
        records = await self.repository.list_active(schema_form.id)
        return schema_form, records

    async def create_form(
        self,
        user_id: UUID,
        urza_id: UUID,
    ) -> SchemaForm:
        """Создаёт формуляр схем для устройства.

        Args:
            user_id: Идентификатор инициатора.
            urza_id: Идентификатор устройства.

        Returns:
            Созданный формуляр схем.
        """
        await self._ensure_access(user_id, urza_id)
        existing_form = await self.repository.get_form_by_urza_id(urza_id)
        if existing_form is not None:
            raise ValueError("Форма схем для данного URZA уже существует")
        schema_form = SchemaForm(
            urza_id=urza_id,
            created_by=user_id,
            updated_by=user_id,
        )
        await self.repository.add_form(schema_form)
        return schema_form

    async def create(
        self,
        user_id: UUID,
        urza_id: UUID,
        schema_number: str,
        schema_name: str,
        change_description: str,
        change_justification: str,
        upload_date: date,
        signed_form_file_id: UUID,
        scan_file_id: UUID | None = None,
        editable_file_id: UUID | None = None,
        task_id: UUID | None = None,
    ) -> SchemaRecord:
        """Создаёт запись изменения схем в формуляре УРЗА.

        Для записи обязателен подписанный формуляр; скан и редактируемый файл
        передаются дополнительно. При наличии task_id проверяется задача.

        Args:
            user_id: Идентификатор автора.
            urza_id: Идентификатор устройства.
            schema_number: Номер схемы.
            schema_name: Наименование схемы.
            change_description: Описание изменений.
            change_justification: Обоснование изменений.
            upload_date: Дата загрузки.
            signed_form_file_id: Идентификатор подписанного формуляра.
            scan_file_id: Необязательный скан схемы.
            editable_file_id: Необязательный редактируемый файл.
            task_id: Необязательная связанная задача.

        Returns:
            Созданная запись схем.
        """
        await self._ensure_access(user_id, urza_id)
        user = await self._get_user(user_id)
        if user.role not in _RECORD_ROLES:
            raise PermissionError("Создавать схемы с текущей ролью запрещено.")
        if signed_form_file_id is None:
            raise ValueError("Подписанный формуляр схемы обязателен.")
        if task_id is not None and scan_file_id is None and editable_file_id is None:
            raise ValueError(
                "Для задания по схемам необходим скан или редактируемый файл."
            )
        if task_id is not None:
            await self._validate_task_for_result(user_id, urza_id, task_id)

        schema_form = await self.repository.get_form_by_urza_id(urza_id)
        if schema_form is None:
            schema_form = SchemaForm(
                urza_id=urza_id,
                created_by=user_id,
                updated_by=user_id,
            )
            await self.repository.add_form(schema_form)

        if await self.repository.get_unfinished(schema_form.id) is not None:
            raise ValueError(
                "Для данного формуляра уже существует незавершённая запись схем."
            )

        status = (
            DocumentStatus.APPROVED
            if user.role is UserRole.MANAGER
            else DocumentStatus.DRAFT
        )
        record = SchemaRecord(
            schema_form_id=schema_form.id,
            schema_number=schema_number,
            schema_name=schema_name,
            change_description=change_description,
            change_justification=change_justification,
            upload_date=upload_date,
            status=status,
            created_by=user_id,
            updated_by=user_id,
            scan_file_id=scan_file_id,
            editable_file_id=editable_file_id,
            signed_form_file_id=signed_form_file_id,
            task_id=task_id,
        )
        try:
            return await self.repository.add_record(record)
        except IntegrityError as exc:
            await self.repository.rollback()

            if self._is_unfinished_conflict(exc):
                raise ValueError(
                    "Для данного формуляра уже существует незавершённая запись схем."
                ) from exc

            original = exc.orig
            constraint_name = getattr(original, "constraint_name", None)

            if (
                    constraint_name == _TASK_RECORD_INDEX
                    or _TASK_RECORD_INDEX in str(original)
            ):
                raise ValueError(
                    "Для задачи уже существует активный результат схем."
                ) from exc

            raise

    async def create_record(
        self,
        user_id: UUID,
        urza_id: UUID,
        schema_number: str,
        schema_name: str,
        change_description: str,
        change_justification: str,
        upload_date: date,
        signed_form_file_id: UUID,
        scan_file_id: UUID | None = None,
        editable_file_id: UUID | None = None,
        task_id: UUID | None = None,
    ) -> SchemaRecord:
        """Создаёт запись схем через основной сценарий create с теми же параметрами.
        """
        return await self.create(
            user_id=user_id,
            urza_id=urza_id,
            schema_number=schema_number,
            schema_name=schema_name,
            change_description=change_description,
            change_justification=change_justification,
            upload_date=upload_date,
            signed_form_file_id=signed_form_file_id,
            scan_file_id=scan_file_id,
            editable_file_id=editable_file_id,
            task_id=task_id,
        )

    async def update(
        self,
        user_id: UUID,
        urza_id: UUID,
        record_id: UUID,
        schema_number: str,
        schema_name: str,
        change_description: str,
        change_justification: str,
        upload_date: date,
        signed_form_file_id: UUID | None = None,
        scan_file_id: UUID | None = None,
        editable_file_id: UUID | None = None,
    ) -> SchemaRecord:
        """Обновляет запись схем в допустимом для редактирования состоянии.

        Args:
            user_id: Идентификатор пользователя.
            urza_id: Идентификатор устройства.
            record_id: Идентификатор записи.
            schema_number: Номер схемы.
            schema_name: Наименование схемы.
            change_description: Описание изменений.
            change_justification: Обоснование изменений.
            upload_date: Дата загрузки.
            signed_form_file_id: Новый подписанный формуляр или None.
            scan_file_id: Новый скан или None.
            editable_file_id: Новый редактируемый файл или None.

        Returns:
            Обновлённая запись схем.
        """
        record = await self._get_record_for_urza(user_id, urza_id, record_id)
        user = await self._get_user(user_id)
        if user.role not in _RECORD_ROLES:
            raise PermissionError("Редактировать схемы с текущей ролью запрещено.")
        if record.status is not DocumentStatus.DRAFT:
            raise ValueError("Изменять можно только черновик схемы.")

        effective_signed_file_id = signed_form_file_id or record.signed_form_file_id
        if effective_signed_file_id is None:
            raise ValueError("Подписанный формуляр схемы обязателен.")
        if (
            record.task_id is not None
            and scan_file_id is None
            and editable_file_id is None
        ):
            raise ValueError(
                "Для задания по схемам необходим скан или редактируемый файл."
            )

        record.schema_number = schema_number
        record.schema_name = schema_name
        record.change_description = change_description
        record.change_justification = change_justification
        record.upload_date = upload_date
        record.signed_form_file_id = effective_signed_file_id
        record.scan_file_id = scan_file_id
        record.editable_file_id = editable_file_id
        record.updated_by = user_id
        await self.repository.save(record)
        return record

    async def submit_for_review(
        self,
        user_id: UUID,
        urza_id: UUID,
        record_id: UUID,
    ) -> SchemaRecord:
        """Отправляет черновик схем на согласование.

        Args:
            user_id: Идентификатор автора.
            urza_id: Идентификатор устройства.
            record_id: Идентификатор записи.

        Returns:
            Запись схем в статусе UNDER_REVIEW.
        """
        record = await self._get_record_for_urza(user_id, urza_id, record_id)
        user = await self._get_user(user_id)
        if user.role not in _RECORD_ROLES:
            raise PermissionError("Направлять схемы на согласование запрещено.")
        if record.status is not DocumentStatus.DRAFT:
            raise ValueError("На согласование можно направить только черновик схемы.")
        if record.signed_form_file_id is None:
            raise ValueError("Подписанный формуляр схемы обязателен.")
        if (
            record.task_id is not None
            and record.scan_file_id is None
            and record.editable_file_id is None
        ):
            raise ValueError(
                "Для задания по схемам необходим скан или редактируемый файл."
            )
        record.status = DocumentStatus.UNDER_REVIEW
        record.updated_by = user_id
        await self.repository.save(record)
        return record

    async def approve(
        self,
        user_id: UUID,
        urza_id: UUID,
        record_id: UUID,
    ) -> SchemaRecord:
        """Утверждает запись схем руководителем.

        Args:
            user_id: Идентификатор руководителя.
            urza_id: Идентификатор устройства.
            record_id: Идентификатор записи.

        Returns:
            Утверждённая запись схем.
        """
        record = await self._get_record_for_urza(user_id, urza_id, record_id)
        if record.status is not DocumentStatus.UNDER_REVIEW:
            raise ValueError("Утвердить можно только схему на согласовании.")
        await self._check_manager_reviewer(user_id, urza_id)
        if record.signed_form_file_id is None:
            raise ValueError("Подписанный формуляр схемы обязателен.")
        record.status = DocumentStatus.APPROVED
        record.updated_by = user_id
        await self.repository.save(record)
        return record

    async def return_to_draft(
        self,
        user_id: UUID,
        urza_id: UUID,
        record_id: UUID,
    ) -> SchemaRecord:
        """Возвращает запись схем с согласования на доработку.

        Args:
            user_id: Идентификатор руководителя.
            urza_id: Идентификатор устройства.
            record_id: Идентификатор записи.

        Returns:
            Запись схем в статусе DRAFT.
        """
        record = await self._get_record_for_urza(user_id, urza_id, record_id)
        if record.status is not DocumentStatus.UNDER_REVIEW:
            raise ValueError("Вернуть в черновик можно только схему на согласовании.")
        await self._check_manager_reviewer(user_id, urza_id)
        record.status = DocumentStatus.DRAFT
        record.updated_by = user_id
        await self.repository.save(record)
        return record

    async def delete(
        self,
        user_id: UUID,
        urza_id: UUID,
        record_id: UUID,
    ) -> SchemaRecord:
        """Архивирует запись схем после проверки прав и принадлежности УРЗА.

        Args:
            user_id: Идентификатор пользователя.
            urza_id: Идентификатор устройства.
            record_id: Идентификатор записи.

        Returns:
            Архивированная запись.
        """
        record = await self._get_record_for_urza(user_id, urza_id, record_id)
        user = await self._get_user(user_id)
        if user.role not in {UserRole.ADMIN, UserRole.SUPERADMIN}:
            raise PermissionError(
                "Удалять записи схем может только ADMIN или SUPERADMIN."
            )
        return await self.repository.soft_delete(record, user_id)

    async def get_available_actions(
        self,
        user_id: UUID,
        record: SchemaRecord,
    ) -> set[str]:
        """Возвращает действия, доступные пользователю для записи схем.

        Args:
            user_id: Идентификатор пользователя.
            record: Проверяемая запись.

        Returns:
            Множество кодов действий с учётом статуса, роли и доступа.
        """
        if record.deleted_at is not None:
            return set()
        try:
            user = await self._get_user(user_id)
            schema_form = await self.repository.get_form_by_id(record.schema_form_id)
            if schema_form is None:
                return set()
            await self._ensure_access(user_id, schema_form.urza_id)
        except (PermissionError, ValueError):
            return set()

        actions: set[str] = set()
        if record.status is DocumentStatus.DRAFT and user.role in _RECORD_ROLES:
            actions.update({"edit", "submit"})
        elif record.status is DocumentStatus.UNDER_REVIEW:
            try:
                await self._check_manager_reviewer(user_id, schema_form.urza_id)
            except (PermissionError, ValueError):
                pass
            else:
                actions.update({"approve", "return"})
        elif (
            record.status is DocumentStatus.APPROVED
            and user.role in _RECORD_ROLES
            and await self.repository.get_unfinished(schema_form.id) is None
        ):
            actions.add("new_record")

        if user.role in {UserRole.MANAGER, UserRole.ADMIN, UserRole.SUPERADMIN}:
            actions.add("delete")
        return actions
