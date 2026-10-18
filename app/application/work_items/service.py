from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from app.application.access.service import AccessService
from app.application.otd.service import OTDService
from app.application.programs.service import ProgramService
from app.application.rza_instructions.service import RZAInstructionService
from app.application.schema.service import SchemaService
from app.application.settings.service import SettingsService
from app.application.selectivity_schemes.service import SelectivitySchemeService
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
}


def _action_labels(actions: set[str]) -> tuple[str, ...]:
    return tuple(_ACTION_LABELS[action] for action in sorted(actions))


def _document_work_item_status(status: DocumentStatus) -> tuple[str, str]:
    if status is DocumentStatus.APPROVED:
        return _TASK_STATUS_LABELS["closed"], _TASK_STATUS_BADGES["closed"]
    return status.label, status.badge_class


def _task_tab(status: TaskStatus) -> str:
    if status is TaskStatus.UNDER_REVIEW:
        return "review"

    if status is TaskStatus.CLOSED:
        return "completed"

    return "work"


def _document_tab(status: DocumentStatus) -> str:
    if status is DocumentStatus.UNDER_REVIEW:
        return "review"

    if status is DocumentStatus.APPROVED:
        return "completed"

    return "work"


@dataclass(frozen=True)
class WorkItem:
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


class WorkItemSource(Protocol):
    async def list_for_user(
        self,
        user_id: UUID,
        prior_items: tuple[WorkItem, ...] = (),
    ) -> list[WorkItem]: ...


class TaskWorkItemSource:
    def __init__(
        self,
        repository: TaskRepository,
        access_service: AccessService,
        task_service: TaskService,
    ) -> None:
        self.repository = repository
        self.access_service = access_service
        self.task_service = task_service

    async def list_for_user(
        self,
        user_id: UUID,
        prior_items: tuple[WorkItem, ...] = (),
    ) -> list[WorkItem]:
        user = await self.access_service.user_repository.get_by_id(user_id)
        if user is None or not user.active or user.deleted_at is not None:
            return []

        items = []
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
            if user.role is UserRole.ENGINEER and task.assigned_to != user_id:
                continue
            actions = await self.task_service.get_available_actions(
                task=task,
                actor_id=user_id,
            )
            item_type = task.work_type.label
            title = task.description or f"Задание: {item_type}"
            items.append(
                WorkItem(
                    item_type="Задание · " + item_type,
                    title=title,
                    status=_TASK_STATUS_LABELS[task.status.value],
                    status_class=_TASK_STATUS_BADGES[task.status.value],
                    tab=_task_tab(task.status),
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


class ProgramWorkItemSource:
    def __init__(self, service: ProgramService) -> None:
        self.service = service

    async def list_for_user(
        self,
        user_id: UUID,
        prior_items: tuple[WorkItem, ...] = (),
    ) -> list[WorkItem]:
        items = []
        for program in await self.service.list_standalone_work_items(user_id):
            actions = await self.service.get_available_actions(user_id, program)
            items.append(
                WorkItem(
                    item_type="Самостоятельная программа",
                    title=f"Программа № {program.program_number}",
                    status=program.status.label,
                    status_class=program.status.badge_class,
                    created_at=program.created_at,
                    author=program.creator.full_name if program.creator else "—",
                    assignee="—",
                    parent=program.urza.dispatch_name,
                    parent_id=program.urza_id,
                    url=f"/objects/urza/{program.urza_id}?tab=programs",
                    actions=_action_labels(actions),
                )
            )
        return items


class OTDWorkItemSource:
    def __init__(self, service: OTDService) -> None:
        self.service = service

    async def list_for_user(
        self,
        user_id: UUID,
        prior_items: tuple[WorkItem, ...] = (),
    ) -> list[WorkItem]:
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
            if (
                version.status is DocumentStatus.UNDER_REVIEW
                and version.created_by != user_id
                and "approve" not in actions
            ):
                continue
            status, status_class = _document_work_item_status(version.status)
            items.append(
                WorkItem(
                    item_type="Самостоятельное ОТД",
                    title=f"ОТД · версия {version.version_number}",
                    status=status,
                    status_class=status_class,
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
                )
            )
        return items


class SettingsWorkItemSource:
    def __init__(self, service: SettingsService) -> None:
        self.service = service

    async def list_for_user(
        self,
        user_id: UUID,
        prior_items: tuple[WorkItem, ...] = (),
    ) -> list[WorkItem]:
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
            if (
                record.status is DocumentStatus.UNDER_REVIEW
                and record.created_by != user_id
                and "approve" not in actions
            ):
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
                    created_at=record.created_at,
                    author=record.creator.full_name if record.creator else "—",
                    assignee="—",
                    parent=form.urza.dispatch_name,
                    parent_id=form.urza_id,
                    url=f"/objects/urza/{form.urza_id}?tab=settings",
                    actions=_action_labels(actions),
                )
            )
        return items


class SchemaWorkItemSource:
    def __init__(self, service: SchemaService) -> None:
        self.service = service

    async def list_for_user(
        self,
        user_id: UUID,
        prior_items: tuple[WorkItem, ...] = (),
    ) -> list[WorkItem]:
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
            if (
                record.status is DocumentStatus.UNDER_REVIEW
                and record.created_by != user_id
                and "approve" not in actions
            ):
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
                    author=record.creator.full_name if record.creator else "—",
                    assignee="—",
                    parent=form.urza.dispatch_name,
                    parent_id=form.urza_id,
                    url=f"/objects/urza/{form.urza_id}?tab=schemas",
                    actions=_action_labels(actions),
                )
            )
        return items


class InstructionWorkItemSource:
    def __init__(self, service: URZAInstructionService) -> None:
        self.service = service

    async def list_for_user(
        self,
        user_id: UUID,
        prior_items: tuple[WorkItem, ...] = (),
    ) -> list[WorkItem]:
        items = []
        for version in await self.service.repository.list_standalone_work_items():
            instruction = version.urza_instruction
            if instruction is None or instruction.deleted_at is not None:
                continue
            if any(
                item.item_type == "Задание · Инструкция"
                and item.parent_id == instruction.urza_id
                and version.created_at > item.created_at
                for item in prior_items
            ):
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
                    created_at=version.created_at,
                    author=version.creator.full_name if version.creator else "—",
                    assignee="—",
                    parent=urza.dispatch_name,
                    parent_id=instruction.urza_id,
                    url=f"/objects/urza/{instruction.urza_id}?tab=instruction",
                    actions=_action_labels(actions),
                )
            )
        return items


class RZAInstructionWorkItemSource:
    def __init__(self, service: RZAInstructionService) -> None:
        self.service = service

    async def list_for_user(
        self, user_id: UUID, prior_items: tuple[WorkItem, ...] = ()
    ) -> list[WorkItem]:
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
            if version.status is DocumentStatus.UNDER_REVIEW and (
                version.created_by != user_id and not actions
            ):
                continue
            items.append(
                WorkItem(
                    item_type="Самостоятельная инструкция РЗА ПС",
                    title=f"Инструкция РЗА ПС · версия {version.version_number}",
                    status=version.status.label,
                    status_class=version.status.badge_class,
                    created_at=version.created_at,
                    author=version.creator.full_name if version.creator else "—",
                    assignee="—",
                    parent=substation.dispatch_name,
                    parent_id=substation.id,
                    url=f"/objects/substation/{substation.id}?tab=instructions",
                    actions=_action_labels(actions),
                )
            )
        return items


class SelectivitySchemeWorkItemSource:
    def __init__(self, service: SelectivitySchemeService) -> None:
        self.service = service

    async def list_for_user(
        self, user_id: UUID, prior_items: tuple[WorkItem, ...] = ()
    ) -> list[WorkItem]:
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
            if version.status is DocumentStatus.UNDER_REVIEW and (
                version.created_by != user_id and not actions
            ):
                continue
            items.append(
                WorkItem(
                    item_type="Самостоятельная схема селективности",
                    title=f"{version.number} · {version.name}",
                    status=version.status.label,
                    status_class=version.status.badge_class,
                    created_at=version.created_at,
                    author=version.creator.full_name if version.creator else "—",
                    assignee="—",
                    parent=substation.dispatch_name,
                    parent_id=substation.id,
                    url=f"/objects/substation/{substation.id}?tab=selectivity-schemes",
                    actions=_action_labels(actions),
                )
            )
        return items


class WorkItemService:
    """Собирает список рабочих элементов из независимых источников."""

    def __init__(self, sources: list[WorkItemSource]) -> None:
        self.sources = sources

    async def list_for_user(self, user_id: UUID) -> list[WorkItem]:
        items = []
        for source in self.sources:
            source_items = await source.list_for_user(user_id, tuple(items))
            items.extend(source_items)
        return sorted(items, key=lambda item: item.created_at, reverse=True)
