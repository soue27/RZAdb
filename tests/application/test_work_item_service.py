from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.application.work_items.service import (
    InstructionWorkItemSource,
    ProgramWorkItemSource,
    TaskWorkItemSource,
    WorkItem,
    WorkItemService,
)
from app.domain.enums import (
    DocumentStatus,
    TaskStatus,
    TaskWorkType,
    UserRole,
)


class FakeSource:
    def __init__(self, items):
        self.items = items

    async def list_for_user(self, user_id, prior_items=()):
        return self.items


def _item(title, created_at):
    return WorkItem(
        item_type="Документ",
        title=title,
        status="Черновик",
        status_class="text-bg-secondary",
        created_at=created_at,
        author="Автор",
        assignee="—",
        parent="УРЗА",
        parent_id=uuid4(),
        url="/objects/urza/example/programs",
        actions=("Редактировать",),
    )


@pytest.mark.asyncio
async def test_work_item_service_combines_registered_sources_and_sorts():
    user_id = uuid4()
    older = _item("Старый документ", datetime(2026, 10, 1, tzinfo=UTC))
    newer = _item("Новое задание", datetime(2026, 10, 2, tzinfo=UTC))
    service = WorkItemService([FakeSource([older]), FakeSource([newer])])

    result = await service.list_for_user(user_id)

    assert [item.title for item in result] == ["Новое задание", "Старый документ"]


@pytest.mark.asyncio
async def test_task_source_keeps_assignment_and_access_filters():
    user_id = uuid4()
    assigned = SimpleNamespace(
        id=uuid4(),
        urza_id=uuid4(),
        urza=SimpleNamespace(dispatch_name="УРЗА-1"),
        work_type=TaskWorkType.SCHEMES,
        description="Задание исполнителя",
        assigned_to=user_id,
        assigned_to_user=SimpleNamespace(full_name="Инженер"),
        created_by_user=SimpleNamespace(full_name="Руководитель"),
        status=TaskStatus.IN_PROGRESS,
        created_at=datetime(2026, 10, 1, tzinfo=UTC),
        deleted_at=None,
    )
    reassigned = SimpleNamespace(
        **{**vars(assigned), "id": uuid4(), "assigned_to": uuid4()}
    )
    denied = SimpleNamespace(**{**vars(assigned), "id": uuid4(), "urza_id": uuid4()})

    class Repository:
        async def list_active(self):
            return [assigned, reassigned, denied]

    class Access:
        user_repository = SimpleNamespace(get_by_id=_active_engineer)

        async def can_access_urza(self, _user_id, urza_id):
            return urza_id != denied.urza_id

    class TaskActions:
        async def get_available_actions(self, **kwargs):
            return {"complete_task"}

    source = TaskWorkItemSource(Repository(), Access(), TaskActions())
    result = await source.list_for_user(user_id)

    assert [item.title for item in result] == ["Задание исполнителя"]
    assert result[0].status == "В работе"
    assert result[0].actions == ("Завершить",)


@pytest.mark.asyncio
async def test_instruction_version_used_by_task_is_not_added_twice():
    user_id = uuid4()
    urza_id = uuid4()
    instruction = SimpleNamespace(urza_id=urza_id, deleted_at=None)
    version = SimpleNamespace(
        urza_instruction=instruction,
        created_at=datetime(2026, 10, 2, tzinfo=UTC),
    )
    task_item = WorkItem(
        item_type="Задание · Инструкция",
        title="Создать инструкцию",
        status="Выполнено",
        status_class="text-bg-warning",
        created_at=datetime(2026, 10, 1, tzinfo=UTC),
        author="Руководитель",
        assignee="Инженер",
        parent="УРЗА-1",
        parent_id=urza_id,
        url="/tasks/example",
        actions=(),
    )

    class Repository:
        async def list_standalone_work_items(self):
            return [version]

    class Service:
        repository = Repository()

    source = InstructionWorkItemSource(Service())

    result = await source.list_for_user(user_id, (task_item,))

    assert result == []


@pytest.mark.asyncio
async def test_program_work_item_uses_urza_route_with_programs_tab():
    user_id = uuid4()
    urza_id = uuid4()
    program = SimpleNamespace(
        id=uuid4(),
        urza_id=urza_id,
        urza=SimpleNamespace(dispatch_name="УРЗА-1"),
        creator=SimpleNamespace(full_name="Инженер"),
        program_number="ПР-1",
        status=DocumentStatus.DRAFT,
        created_at=datetime(2026, 10, 2, tzinfo=UTC),
    )

    class Service:
        async def list_standalone_work_items(self, actor_id):
            assert actor_id == user_id
            return [program]

        async def get_available_actions(self, actor_id, candidate):
            assert actor_id == user_id
            assert candidate is program
            return {"edit", "submit"}

    source = ProgramWorkItemSource(Service())

    result = await source.list_for_user(user_id)

    assert result[0].url == f"/objects/urza/{urza_id}?tab=programs"


async def _active_engineer(user_id):
    return SimpleNamespace(
        id=user_id,
        role=UserRole.ENGINEER,
        active=True,
        deleted_at=None,
    )
