from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from app.application.access.service import AccessService
from app.application.inspections.repository import InspectionTaskRepository
from app.application.inspections.service import InspectionTaskService
from app.application.maintenance.service import TORecordService
from app.application.otd.service import OTDService
from app.application.programs.service import ProgramService
from app.application.rza_instructions.service import RZAInstructionService
from app.application.schema.service import SchemaService
from app.application.selectivity_schemes.service import SelectivitySchemeService
from app.application.settings.service import SettingsService
from app.application.tasks.repository import TaskRepository
from app.application.tasks.service import TaskService
from app.application.urza_instructions.service import URZAInstructionService
from app.domain.enums import DocumentStatus, TaskStatus, UserRole

_TASK_STATUS_LABELS = {
    "created": "Создано",
    "assigned": "Назначено",
    "in_progress": "В работе",
    "completed": "Выполнено",
    "under_review": "На согласовании",
    "closed": "Закрыто",
    "rejected": "Отклонено",
}
_TASK_STATUS_BADGES = {
    "created": "text-bg-secondary",
    "assigned": "text-bg-info",
    "in_progress": "text-bg-primary",
    "completed": "text-bg-warning",
    "under_review": "text-bg-warning",
    "closed": "text-bg-success",
    "rejected": "text-bg-danger",
}
_ACTION_LABELS = {
    "accept_task": "Принять",
    "reject_task": "Отказаться",
    "reassign_task": "Переназначить",
    "complete_task": "Завершить",
    "create_result": "Создать результат",
    "submit_for_review": "Отправить на согласование",
    "close_task": "Закрыть",
    "return_for_revision": "Вернуть на доработку",
    "submit": "Отправить на согласование",
    "edit": "Редактировать",
    "approve": "Утвердить",
    "return": "Вернуть на доработку",
    "new_version": "Создать новую версию",
    "new_record": "Новое изменение",
    "delete": "Удалить",
}


def _action_labels(actions: set[str]) -> tuple[str, ...]:
    """Преобразует коды доступных действий в подписи интерфейса.

    Args:
        actions: Множество кодов действий.

    Returns:
        Подписи в стабильном алфавитном порядке.
    """
    return tuple(_ACTION_LABELS[action] for action in sorted(actions))


def _document_work_item_status(status: DocumentStatus) -> tuple[str, str]:
    """Возвращает подпись и CSS-класс статуса документной записи.

    Args:
        status: Статус документа.

    Returns:
        Пара из текстовой подписи и CSS-класса.
    """
    if status is DocumentStatus.APPROVED:
        return _TASK_STATUS_LABELS["closed"], _TASK_STATUS_BADGES["closed"]
    return status.label, status.badge_class


def _task_tab(status: TaskStatus) -> str:
    """Определяет вкладку списка задач по статусу.

    Args:
        status: Статус задачи.

    Returns:
        Код вкладки work, review или completed.
    """
    if status is TaskStatus.UNDER_REVIEW:
        return "review"

    if status in {TaskStatus.CLOSED, TaskStatus.REJECTED}:
        return "completed"

    return "work"


def _document_tab(status: DocumentStatus) -> str:
    """Определяет вкладку списка документов по статусу.

    Args:
        status: Статус документа.

    Returns:
        Код вкладки work, review или completed.
    """
    if status is DocumentStatus.UNDER_REVIEW:
        return "review"

    if status is DocumentStatus.APPROVED:
        return "completed"

    return "work"


@dataclass(frozen=True)
class WorkItem:
    """Единый элемент рабочего списка, объединяющий задачи и документные действия разных типов.
    """
    item_type: str
    title: str
    status: str
    status_class: str
    created_at: datetime
    author: str
    assignee: str
    parent: str
    parent_id: UUID | None
    url: str
    actions: tuple[str, ...]
    tab: str = "work"
    can_approve: bool = False
    status_code: str | None = None
    deadline_at: datetime | None = None


class WorkItemSource(Protocol):
    """Контракт источника, который формирует рабочие элементы для пользователя.
    """
    async def list_for_user(
        self,
        user_id: UUID,
        prior_items: tuple[WorkItem, ...] = (),
    ) -> list[WorkItem]:
        """Формирует элементы этого источника для пользователя.

        Args:
            user_id: Идентификатор пользователя.
            prior_items: Уже собранные элементы, которые источник должен учитывать.

        Returns:
            Список рабочих элементов данного типа.
        """
        ...


class TaskWorkItemSource:
    """Формирует рабочие элементы из задач с учётом доступа и доступных действий.
    """
    def __init__(
        self,
        repository: TaskRepository,
        access_service: AccessService,
        task_service: TaskService,
    ) -> None:
        """Сохраняет репозитории и сервисы доступа и управления задачами.

        Args:
            repository: Репозиторий задач.
            access_service: Сервис проверки доступа.
            task_service: Сервис доступных действий и жизненного цикла задач.
        """
        self.repository = repository
        self.access_service = access_service
        self.task_service = task_service

    async def list_for_user(
        self,
        user_id: UUID,
        prior_items: tuple[WorkItem, ...] = (),
    ) -> list[WorkItem]:
        """Формирует рабочие элементы задач, доступных пользователю.

        Args:
            user_id: Идентификатор пользователя.
            prior_items: Уже собранные элементы для исключения повторов.

        Returns:
            Задачи с подписями статусов, сроками, ссылками и доступными действиями.
        """
        user = await self.access_service.user_repository.get_by_id(user_id)
        if user is None or not user.active or user.deleted_at is not None:
            return []

        items = []
        reviewed_task_ids = set()
        if user.role is UserRole.SUPERADMIN:
            reviewed_task_ids = await self.repository.list_reviewed_task_ids(user_id)
        for task in await self.repository.list_active():
            has_access = (
                await self.access_service.can_access_urza(user_id, task.urza_id)
                if task.urza_id is not None
                else await self.access_service.can_access_substation(
                    user_id, task.substation_id
                )
            )
            if not has_access:
                continue

            actions = await self.task_service.get_available_actions(
                task=task,
                actor_id=user_id,
            )

            if user.role is UserRole.ENGINEER and task.assigned_to != user_id:
                continue

            if user.role is UserRole.SUPERADMIN:
                is_author = task.created_by == user_id
                is_assignee = task.assigned_to == user_id
                is_reviewer = task.id in reviewed_task_ids

                if not (is_author or is_assignee or is_reviewer):
                    continue
            item_type = task.work_type.label
            title = task.description or f"Задание: {item_type}"
            items.append(
                WorkItem(
                    item_type="Задание · " + item_type,
                    title=title,
                    status=_TASK_STATUS_LABELS[task.status.value],
                    status_class=_TASK_STATUS_BADGES[task.status.value],
                    tab=_task_tab(task.status),
                    can_approve=bool(
                        actions.intersection({"close_task", "return_for_revision"})
                    ),
                    status_code=task.status.value,
                    deadline_at=task.deadline_at,
                    created_at=task.created_at,
                    author=(
                        task.created_by_user.full_name if task.created_by_user else "—"
                    ),
                    assignee=(
                        task.assigned_to_user.full_name
                        if task.assigned_to_user
                        else "Не назначен"
                    ),
                    parent=(
                        task.urza.dispatch_name
                        if task.urza is not None
                        else task.substation.dispatch_name
                    ),
                    parent_id=task.urza_id or task.substation_id,
                    url=f"/tasks/{task.id}",
                    actions=_action_labels(actions),
                )
            )
        return items


_INSPECTION_STATUS_LABELS = {
    TaskStatus.CREATED: "Создано",
    TaskStatus.ASSIGNED: "Назначено",
    TaskStatus.IN_PROGRESS: "В работе",
    TaskStatus.COMPLETED: "Выполнено",
    TaskStatus.UNDER_REVIEW: "На проверке",
    TaskStatus.CLOSED: "Закрыто",
    TaskStatus.REJECTED: "Отклонено",
}


class InspectionTaskWorkItemSource:
    """Формирует рабочие элементы из задач осмотра подстанций.
    """
    def __init__(
        self,
        repository: InspectionTaskRepository,
        access_service: AccessService,
        inspection_service: InspectionTaskService,
    ) -> None:
        """Сохраняет репозитории и сервисы задач осмотра и проверки доступа.
        """
        self.repository = repository
        self.access_service = access_service
        self.inspection_service = inspection_service

    async def list_for_user(
        self,
        user_id: UUID,
        prior_items: tuple[WorkItem, ...] = (),
        *,
        role: UserRole | None = None,
    ) -> list[WorkItem]:
        """Формирует рабочие элементы задач осмотра в области доступа пользователя.

        Args:
            user_id: Идентификатор пользователя.
            prior_items: Уже собранные элементы.
            role: Необязательная роль для уточнения набора элементов.

        Returns:
            Задачи осмотра с действиями и ссылками на результат.
        """
        user = await self.access_service.user_repository.get_by_id(user_id)
        if user is None or not user.active or user.deleted_at is not None:
            return []
        role = role or user.role

        reviewed_task_ids = set()
        if role is UserRole.SUPERADMIN:
            reviewed_task_ids = await self.repository.list_reviewed_task_ids(user_id)

        items = []
        for task in await self.repository.list_active():
            if not await self.access_service.can_access_substation(
                user_id, task.substation_id
            ):
                continue

            if role is UserRole.ENGINEER and task.assigned_to != user_id:
                continue

            if role is UserRole.SUPERADMIN and not (
                task.created_by == user_id
                or task.assigned_to == user_id
                or task.id in reviewed_task_ids
            ):
                continue

            can_approve = await self.inspection_service.can_review(
                task.id,
                actor_id=user_id,
            )
            tab = (
                "review"
                if task.status is TaskStatus.UNDER_REVIEW
                else "completed"
                if task.status in {TaskStatus.CLOSED, TaskStatus.REJECTED}
                else "work"
            )
            items.append(
                WorkItem(
                    item_type="Задача осмотра",
                    title=f"Осмотр ПС · {task.substation.dispatch_name}",
                    status=_INSPECTION_STATUS_LABELS[task.status],
                    status_class=_TASK_STATUS_BADGES[task.status.value],
                    created_at=task.created_at,
                    author=(
                        task.created_by_user.full_name
                        if task.created_by_user
                        else "—"
                    ),
                    assignee=(
                        task.assigned_to_user.full_name
                        if task.assigned_to_user
                        else "Не назначен"
                    ),
                    parent=task.substation.dispatch_name,
                    parent_id=task.substation_id,
                    url=f"/objects/substation/inspection-tasks/{task.id}",
                    actions=(),
                    tab=tab,
                    can_approve=can_approve,
                    status_code=task.status.value,
                    deadline_at=task.deadline_at,
                )
            )
        return items


class ProgramWorkItemSource:
    """Формирует рабочие элементы из программ УРЗА.
    """
    def __init__(self, service: ProgramService) -> None:
        """Сохраняет сервис программ УРЗА.

        Args:
            service: Сервис программ.
        """
        self.service = service

    async def list_for_user(
        self,
        user_id: UUID,
        prior_items: tuple[WorkItem, ...] = (),
    ) -> list[WorkItem]:
        """Формирует рабочие элементы программ УРЗА, ожидающих действий пользователя.

        Args:
            user_id: Идентификатор пользователя.
            prior_items: Уже собранные элементы.

        Returns:
            Программы с подписями статусов и доступными действиями.
        """
        items = []
        for program in await self.service.list_standalone_work_items(user_id):
            actions = await self.service.get_available_actions(user_id, program)
            items.append(
                WorkItem(
                    item_type="Самостоятельная программа",
                    title=f"Программа № {program.program_number}",
                    status=program.status.label,
                    status_class=program.status.badge_class,
                    tab=_document_tab(program.status),
                    created_at=program.created_at,
                    author=program.creator.full_name if program.creator else "—",
                    assignee="—",
                    parent=program.urza.dispatch_name,
                    parent_id=program.urza_id,
                    url=f"/objects/urza/{program.urza_id}?tab=programs",
                    actions=_action_labels(actions),
                    can_approve=(
                            program.status is DocumentStatus.UNDER_REVIEW
                            and bool(actions.intersection({"approve", "return"}))
                    ),
                )
            )
        return items


class MaintenanceWorkItemSource:
    """Формирует рабочие элементы из записей технического обслуживания.
    """
    def __init__(self, service: TORecordService) -> None:
        """Сохраняет сервис технического обслуживания.

        Args:
            service: Сервис записей ТО.
        """
        self.service = service

    async def list_for_user(
        self,
        user_id: UUID,
        prior_items: tuple[WorkItem, ...] = (),
    ) -> list[WorkItem]:
        """Формирует рабочие элементы записей технического обслуживания.

        Args:
            user_id: Идентификатор пользователя.
            prior_items: Уже собранные элементы.

        Returns:
            Записи ТО с доступными действиями.
        """
        items = []
        for record in await self.service.list_standalone_work_items(user_id):
            actions = await self.service.get_available_actions(user_id, record)
            items.append(
                WorkItem(
                    item_type="Самостоятельное ТО",
                    title=f"ТО · {record.maintenance_type.value} · "
                    f"{record.maintenance_date:%d.%m.%Y}",
                    status=record.status.label,
                    status_class=record.status.badge_class,
                    tab=_document_tab(record.status),
                    created_at=record.created_at,
                    author=record.creator.full_name if record.creator else "—",
                    assignee="—",
                    parent=record.urza.dispatch_name,
                    parent_id=record.urza_id,
                    url=f"/objects/urza/{record.urza_id}?tab=maintenance",
                    actions=_action_labels(actions),
                    can_approve=(
                        record.status is DocumentStatus.UNDER_REVIEW
                        and bool(actions.intersection({"approve", "return"}))
                    ),
                    status_code=record.status.value,
                )
            )
        return items


class OTDWorkItemSource:
    """Формирует рабочие элементы из версий формуляров ОТД.
    """
    def __init__(self, service: OTDService) -> None:
        """Сохраняет сервис формуляров ОТД.

        Args:
            service: Сервис ОТД.
        """
        self.service = service

    async def list_for_user(
        self,
        user_id: UUID,
        prior_items: tuple[WorkItem, ...] = (),
    ) -> list[WorkItem]:
        """Формирует рабочие элементы версий ОТД.

        Args:
            user_id: Идентификатор пользователя.
            prior_items: Уже собранные элементы.

        Returns:
            Версии ОТД с доступными действиями.
        """
        items = []
        for version in await self.service.repository.list_standalone_work_items():
            otd = version.otd
            urza = otd.urza if otd is not None else None
            if (
                otd is None
                or urza is None
                or urza.deleted_at is not None
                or not await self.service.access_service.can_access_urza(
                    user_id, otd.urza_id
                )
            ):
                continue
            actions = await self.service.get_available_actions(user_id, version)
            if version.status is DocumentStatus.DRAFT and version.created_by != user_id:
                continue
            if version.status is DocumentStatus.DRAFT and "submit" not in actions:
                continue
            status, status_class = _document_work_item_status(version.status)
            items.append(
                WorkItem(
                    item_type="Самостоятельное ОТД",
                    title=f"ОТД · версия {version.version_number}",
                    status=status,
                    status_class=status_class,
                    tab=_document_tab(version.status),
                    created_at=version.created_at,
                    author=(
                        version.created_by_user.full_name
                        if version.created_by_user
                        else "—"
                    ),
                    assignee="—",
                    parent=urza.dispatch_name,
                    parent_id=otd.urza_id,
                    url=f"/objects/urza/{otd.urza_id}?tab=otd",
                    actions=_action_labels(actions),
                    can_approve=(
                            version.status is DocumentStatus.UNDER_REVIEW
                            and bool(actions.intersection({"approve", "return"}))
                    ),
                )
            )
        return items


class SettingsWorkItemSource:
    """Формирует рабочие элементы из записей изменений уставок.
    """
    def __init__(self, service: SettingsService) -> None:
        """Сохраняет сервис уставок.

        Args:
            service: Сервис формуляров и записей уставок.
        """
        self.service = service

    async def list_for_user(
        self,
        user_id: UUID,
        prior_items: tuple[WorkItem, ...] = (),
    ) -> list[WorkItem]:
        """Формирует рабочие элементы записей изменений уставок.

        Args:
            user_id: Идентификатор пользователя.
            prior_items: Уже собранные элементы.

        Returns:
            Записи уставок с доступными действиями.
        """
        items = []
        for record in await self.service.repository.list_standalone_work_items():
            form = record.settings_form
            urza = form.urza if form is not None else None
            if (
                form is None
                or form.deleted_at is not None
                or urza is None
                or urza.deleted_at is not None
                or not await self.service.access_service.can_access_urza(
                    user_id, form.urza_id
                )
            ):
                continue
            if record.task_id is not None:
                continue
            actions = await self.service.get_available_actions(user_id, record)
            if record.status is DocumentStatus.DRAFT and record.created_by != user_id:
                continue
                continue
            if record.status is DocumentStatus.DRAFT and not actions.intersection(
                {"edit", "submit"}
            ):
                continue
            status, status_class = _document_work_item_status(record.status)
            items.append(
                WorkItem(
                    item_type="Самостоятельные уставки",
                    title=record.parameter_name,
                    status=status,
                    status_class=status_class,
                    tab=_document_tab(record.status),
                    created_at=record.created_at,
                    author=record.creator.full_name if record.creator else "—",
                    assignee="—",
                    parent=form.urza.dispatch_name,
                    parent_id=form.urza_id,
                    url=f"/objects/urza/{form.urza_id}?tab=settings",
                    actions=_action_labels(actions),
                    can_approve=(
                            record.status is DocumentStatus.UNDER_REVIEW
                            and bool(actions.intersection({"approve", "return"}))
                    ),
                )
            )
        return items


class SchemaWorkItemSource:
    """Формирует рабочие элементы из записей схем УРЗА.
    """
    def __init__(self, service: SchemaService) -> None:
        """Сохраняет сервис схем УРЗА.

        Args:
            service: Сервис формуляров и записей схем.
        """
        self.service = service

    async def list_for_user(
        self,
        user_id: UUID,
        prior_items: tuple[WorkItem, ...] = (),
    ) -> list[WorkItem]:
        """Формирует рабочие элементы записей схем УРЗА.

        Args:
            user_id: Идентификатор пользователя.
            prior_items: Уже собранные элементы.

        Returns:
            Записи схем с доступными действиями.
        """
        items = []
        for record in await self.service.repository.list_standalone_work_items():
            form = record.schema_form
            urza = form.urza if form is not None else None
            if (
                form is None
                or form.deleted_at is not None
                or urza is None
                or urza.deleted_at is not None
                or not await self.service.access_service.can_access_urza(
                    user_id, form.urza_id
                )
            ):
                continue
            if record.task_id is not None:
                continue
            actions = await self.service.get_available_actions(user_id, record)
            if record.status is DocumentStatus.DRAFT and record.created_by != user_id:
                continue
            if record.status is DocumentStatus.DRAFT and not actions.intersection(
                {"edit", "submit"}
            ):
                continue
            status, status_class = _document_work_item_status(record.status)
            items.append(
                WorkItem(
                    item_type="Самостоятельная схема",
                    title=f"{record.schema_number} · {record.schema_name}",
                    status=status,
                    status_class=status_class,
                    created_at=record.created_at,
                    tab=_document_tab(record.status),
                    author=record.creator.full_name if record.creator else "—",
                    assignee="—",
                    parent=form.urza.dispatch_name,
                    parent_id=form.urza_id,
                    url=f"/objects/urza/{form.urza_id}?tab=schemas",
                    actions=_action_labels(actions),
                    can_approve=(
                            record.status is DocumentStatus.UNDER_REVIEW
                            and bool(actions.intersection({"approve", "return"}))
                    ),
                )
            )
        return items


class InstructionWorkItemSource:
    """Формирует рабочие элементы из версий инструкции УРЗА.
    """
    def __init__(self, service: URZAInstructionService) -> None:
        """Сохраняет сервис инструкций УРЗА.

        Args:
            service: Сервис версий инструкции.
        """
        self.service = service

    async def list_for_user(
        self,
        user_id: UUID,
        prior_items: tuple[WorkItem, ...] = (),
    ) -> list[WorkItem]:
        """Формирует рабочие элементы версий инструкции УРЗА.

        Args:
            user_id: Идентификатор пользователя.
            prior_items: Уже собранные элементы.

        Returns:
            Версии инструкции с доступными действиями.
        """
        items = []
        for version in await self.service.repository.list_standalone_work_items():
            instruction = version.urza_instruction
            if instruction is None or instruction.deleted_at is not None:
                continue
            if not await self.service.access_service.can_access_urza(
                user_id, instruction.urza_id
            ):
                continue
            actions = await self.service.get_available_actions(user_id, version)
            if version.status is DocumentStatus.DRAFT and version.created_by != user_id:
                continue
            if version.status is DocumentStatus.DRAFT and "submit" not in actions:
                continue
            urza = await self.service.urza_repository.get_by_id(instruction.urza_id)
            if urza is None:
                continue
            items.append(
                WorkItem(
                    item_type="Самостоятельная инструкция URZA",
                    title=f"Инструкция, версия {version.version_number}",
                    status=version.status.label,
                    status_class=version.status.badge_class,
                    tab=_document_tab(version.status),
                    created_at=version.created_at,
                    author=version.creator.full_name if version.creator else "—",
                    assignee="—",
                    parent=urza.dispatch_name,
                    parent_id=instruction.urza_id,
                    url=f"/objects/urza/{instruction.urza_id}?tab=instruction",
                    actions=_action_labels(actions),
                    can_approve=(
                            version.status is DocumentStatus.UNDER_REVIEW
                            and bool(actions.intersection({"approve", "return"}))
                    ),
                )
            )
        return items


class RZAInstructionWorkItemSource:
    """Формирует рабочие элементы из версий инструкции РЗА подстанции.
    """
    def __init__(self, service: RZAInstructionService) -> None:
        """Сохраняет сервис инструкции РЗА подстанции.

        Args:
            service: Сервис инструкции РЗА.
        """
        self.service = service

    async def list_for_user(
        self, user_id: UUID, prior_items: tuple[WorkItem, ...] = ()
    ) -> list[WorkItem]:
        """Формирует рабочие элементы версий инструкции РЗА.

        Args:
            user_id: Идентификатор пользователя.
            prior_items: Уже собранные элементы.

        Returns:
            Версии инструкции с доступными действиями.
        """
        items = []
        for version in await self.service.repository.list_standalone_work_items():
            instruction = version.rza_instruction
            substation = instruction.substation if instruction else None
            if substation is None or substation.deleted_at is not None:
                continue
            if not await self.service.access_service.can_access_substation(
                user_id, substation.id
            ):
                continue
            actions = await self.service.get_available_actions(user_id, version)
            if version.status is DocumentStatus.DRAFT and (
                version.created_by != user_id or "submit" not in actions
            ):
                continue
            items.append(
                WorkItem(
                    item_type="Самостоятельная инструкция РЗА ПС",
                    title=f"Инструкция РЗА ПС · версия {version.version_number}",
                    status=version.status.label,
                    status_class=version.status.badge_class,
                    tab=_document_tab(version.status),
                    created_at=version.created_at,
                    author=version.creator.full_name if version.creator else "—",
                    assignee="—",
                    parent=substation.dispatch_name,
                    parent_id=substation.id,
                    url=f"/objects/substation/{substation.id}?tab=instructions",
                    actions=_action_labels(actions),
                    can_approve=(
                            version.status is DocumentStatus.UNDER_REVIEW
                            and bool(actions.intersection({"approve", "return"}))
                    ),
                )
            )
        return items


class SelectivitySchemeWorkItemSource:
    """Формирует рабочие элементы из версий схем селективности подстанций.
    """
    def __init__(self, service: SelectivitySchemeService) -> None:
        """Сохраняет сервис схем селективности.

        Args:
            service: Сервис схем селективности.
        """
        self.service = service

    async def list_for_user(
        self, user_id: UUID, prior_items: tuple[WorkItem, ...] = ()
    ) -> list[WorkItem]:
        """Формирует рабочие элементы версий схем селективности.

        Args:
            user_id: Идентификатор пользователя.
            prior_items: Уже собранные элементы.

        Returns:
            Версии схем с доступными действиями.
        """
        items = []
        for version in await self.service.repository.list_standalone_work_items():
            scheme = version.selectivity_scheme
            substation = scheme.substation if scheme else None
            if substation is None or substation.deleted_at is not None:
                continue
            if not await self.service.access_service.can_access_substation(
                user_id, substation.id
            ):
                continue
            actions = await self.service.get_available_actions(user_id, version)
            if version.status is DocumentStatus.DRAFT and (
                version.created_by != user_id or "submit" not in actions
            ):
                continue
            items.append(
                WorkItem(
                    item_type="Самостоятельная схема селективности",
                    title=f"{version.number} · {version.name}",
                    status=version.status.label,
                    status_class=version.status.badge_class,
                    tab=_document_tab(version.status),
                    created_at=version.created_at,
                    author=version.creator.full_name if version.creator else "—",
                    assignee="—",
                    parent=substation.dispatch_name,
                    parent_id=substation.id,
                    url=f"/objects/substation/{substation.id}?tab=selectivity-schemes",
                    actions=_action_labels(actions),
                    can_approve=(
                            version.status is DocumentStatus.UNDER_REVIEW
                            and bool(actions.intersection({"approve", "return"}))
                    ),
                )
            )
        return items


class WorkItemService:
    """Собирает список рабочих элементов из независимых источников."""

    def __init__(self, sources: list[WorkItemSource]) -> None:
        """Сохраняет набор источников рабочего списка.

        Args:
            sources: Специализированные источники задач и документных действий.
        """
        self.sources = sources

    async def list_for_user(self, user_id: UUID) -> list[WorkItem]:
        """Собирает и объединяет рабочие элементы всех подключённых источников.

        Args:
            user_id: Идентификатор пользователя.

        Returns:
            Общий список элементов, отсортированный для отображения в интерфейсе.
        """
        items = []
        for source in self.sources:
            source_items = await source.list_for_user(user_id, tuple(items))
            items.extend(source_items)
        return sorted(items, key=lambda item: item.created_at, reverse=True)
