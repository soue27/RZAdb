from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.application.work_items.service import (
    InstructionWorkItemSource,
    OTDWorkItemSource,
    ProgramWorkItemSource,
    RZAInstructionWorkItemSource,
    SchemaWorkItemSource,
    SettingsWorkItemSource,
    SelectivitySchemeWorkItemSource,
    TaskWorkItemSource,
    WorkItem,
    WorkItemService, _document_tab, _task_tab, _action_labels
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
        deadline_at=None,
        deleted_at=None,
    )
    reassigned = SimpleNamespace(
        **{**vars(assigned), "id": uuid4(), "assigned_to": uuid4()}
    )
    denied = SimpleNamespace(**{**vars(assigned), "id": uuid4(), "urza_id": uuid4()})

    class Repository:
        async def list_active(self):
            return [assigned, reassigned, denied]
        async def list_reviewed_task_ids(self, actor_id):
            return set()

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
    assert result[0].tab == "work"




@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("is_author", "is_assignee", "is_reviewer", "expected_count"),
    [
        (True, False, False, 1),   # Автор
        (False, True, False, 1),   # Исполнитель
        (False, False, True, 1),   # Согласующий
        (False, False, False, 0),  # Не участник
    ],
)
async def test_superadmin_sees_only_tasks_where_is_participant(
    is_author, is_assignee, is_reviewer, expected_count
):
    user_id = uuid4()
    task = SimpleNamespace(
        id=uuid4(),
        urza_id=uuid4(),
        substation_id=None,
        urza=SimpleNamespace(dispatch_name="УРЗА-1"),
        work_type=TaskWorkType.SCHEMES,
        description="Задание для проверки",
        created_by=user_id if is_author else uuid4(),
        assigned_to=user_id if is_assignee else uuid4(),
        assigned_to_user=SimpleNamespace(full_name="Инженер"),
        created_by_user=SimpleNamespace(full_name="Автор"),
        status=TaskStatus.CLOSED if is_reviewer else TaskStatus.IN_PROGRESS,
        created_at=datetime(2026, 10, 1, tzinfo=UTC),
        deadline_at=None,
        deleted_at=None,
    )

    class Repository:
        async def list_active(self):
            return [task]

        async def list_reviewed_task_ids(self, actor_id):
            assert actor_id == user_id
            return {task.id} if is_reviewer else set()

    class Access:
        user_repository = SimpleNamespace(get_by_id=_active_superadmin)

        async def can_access_urza(self, *_):
            return True

    class TaskActions:
        async def get_available_actions(self, **_):
            return set()

    source = TaskWorkItemSource(Repository(), Access(), TaskActions())
    result = await source.list_for_user(user_id)

    assert len(result) == expected_count



async def _active_superadmin(user_id):
    return SimpleNamespace(
        id=user_id,
        role=UserRole.SUPERADMIN,
        active=True,
        deleted_at=None,
    )



@pytest.mark.asyncio
@pytest.mark.parametrize("source_kind", ["instruction", "scheme"])
async def test_substation_document_sources_include_accessible_latest_standalone(source_kind):
    user_id = uuid4()
    substation = SimpleNamespace(id=uuid4(), dispatch_name="ПС-1", deleted_at=None)
    document = SimpleNamespace(
        id=uuid4(), version_number=2, created_at=datetime(2026, 10, 10, tzinfo=UTC),
        created_by=user_id, creator=SimpleNamespace(full_name="Инженер"),
        status=DocumentStatus.DRAFT,
    )
    if source_kind == "instruction":
        document.rza_instruction = SimpleNamespace(substation=substation)
        document.rza_instruction_id = uuid4()
        service = SimpleNamespace(
            repository=SimpleNamespace(list_standalone_work_items=lambda: _items(document)),
            access_service=SimpleNamespace(can_access_substation=_can_access),
            get_available_actions=_draft_actions,
        )
        source = RZAInstructionWorkItemSource(service)
    else:
        document.selectivity_scheme = SimpleNamespace(substation=substation)
        document.selectivity_scheme_id = uuid4()
        document.number = "С-1"
        document.name = "Схема ПС-1"
        service = SimpleNamespace(
            repository=SimpleNamespace(list_standalone_work_items=lambda: _items(document)),
            access_service=SimpleNamespace(can_access_substation=_can_access),
            get_available_actions=_draft_actions,
        )
        source = SelectivitySchemeWorkItemSource(service)

    result = await source.list_for_user(user_id)

    assert len(result) == 1
    assert result[0].parent == "ПС-1"
    assert result[0].parent_id == substation.id
    assert result[0].author == "Инженер"
    assert result[0].actions == ("Отправить на согласование",)


async def _items(item):
    return [item]


async def _can_access(_user_id, _substation_id):
    return True


async def _draft_actions(_user_id, _version):
    return {"submit"}


@pytest.mark.asyncio
async def test_closed_maintenance_task_remains_in_work_items():
    user_id = uuid4()
    task = SimpleNamespace(
        id=uuid4(),
        urza_id=uuid4(),
        urza=SimpleNamespace(dispatch_name="УРЗА-1"),
        work_type=TaskWorkType.MAINTENANCE,
        description="Плановое ТО",
        assigned_to=user_id,
        assigned_to_user=SimpleNamespace(full_name="Инженер"),
        created_by_user=SimpleNamespace(full_name="Руководитель"),
        status=TaskStatus.CLOSED,
        created_at=datetime(2026, 10, 1, tzinfo=UTC),
        deadline_at=None,
        deleted_at=None,
    )

    class Repository:
        async def list_active(self):
            return [task]
        async def list_reviewed_task_ids(self, actor_id):
            return set()

    class Access:
        user_repository = SimpleNamespace(get_by_id=_active_engineer)

        async def can_access_urza(self, *_):
            return True

    class TaskActions:
        async def get_available_actions(self, **_):
            return set()

    result = await TaskWorkItemSource(
        Repository(), Access(), TaskActions()
    ).list_for_user(user_id)

    assert len(result) == 1
    assert result[0].status == "Закрыто"
    assert result[0].url == f"/tasks/{task.id}"
    assert result[0].tab == "completed"


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


@pytest.mark.parametrize(
    ("source_type", "record_factory", "tab", "title"),
    [
        (
            SettingsWorkItemSource,
            lambda user_id, form: SimpleNamespace(
                settings_form=form,
                task_id=None,
                deleted_at=None,
                created_by=user_id,
                created_at=datetime(2026, 10, 2, tzinfo=UTC),
                creator=SimpleNamespace(full_name="Инженер"),
                parameter_name="Ток срабатывания",
                status=DocumentStatus.APPROVED,
            ),
            "settings",
            "Ток срабатывания",
        ),
        (
            SchemaWorkItemSource,
            lambda user_id, form: SimpleNamespace(
                schema_form=form,
                task_id=None,
                deleted_at=None,
                created_by=user_id,
                created_at=datetime(2026, 10, 2, tzinfo=UTC),
                creator=SimpleNamespace(full_name="Инженер"),
                schema_number="СХ-1",
                schema_name="Основная схема",
                status=DocumentStatus.APPROVED,
            ),
            "schemas",
            "СХ-1 · Основная схема",
        ),
    ],
)
@pytest.mark.parametrize("is_author", [True, False])
@pytest.mark.asyncio
async def test_approved_standalone_records_remain_in_work_items(
    source_type, record_factory, tab, title, is_author
):
    user_id = uuid4()
    author_id = user_id if is_author else uuid4()
    urza_id = uuid4()
    urza = SimpleNamespace(dispatch_name="УРЗА-1", deleted_at=None)
    form = SimpleNamespace(urza_id=urza_id, urza=urza, deleted_at=None)
    records = [record_factory(author_id, form), record_factory(author_id, form)]

    class Repository:
        async def list_standalone_work_items(self):
            return records

    class Access:
        async def can_access_urza(self, actor_id, accessible_urza_id):
            return actor_id == user_id and accessible_urza_id == urza_id

    class Service:
        repository = Repository()
        access_service = Access()

        async def get_available_actions(self, *_):
            return set()

    result = await source_type(Service()).list_for_user(user_id)

    assert len(result) == 2
    assert all(item.title == title for item in result)
    assert all(item.status == "Закрыто" for item in result)
    assert all(item.status_class == "text-bg-success" for item in result)
    assert all(item.url == f"/objects/urza/{urza_id}?tab={tab}" for item in result)
    assert all(item.author == "Инженер" for item in result)


@pytest.mark.parametrize(
    ("source_type", "record_attr"),
    [(SettingsWorkItemSource, "settings_form"), (SchemaWorkItemSource, "schema_form")],
)
@pytest.mark.parametrize(
    ("status", "is_author", "actions", "expected_count"),
    [
        (DocumentStatus.DRAFT, True, {"edit", "submit"}, 1),
        (DocumentStatus.DRAFT, False, {"edit", "submit"}, 0),
        (DocumentStatus.UNDER_REVIEW, True, set(), 1),
        (DocumentStatus.UNDER_REVIEW, False, {"approve", "return"}, 1),
        (DocumentStatus.UNDER_REVIEW, False, set(), 1),
    ],
)
@pytest.mark.asyncio
async def test_work_item_visibility_during_review_uses_author_and_reviewer_rights(
    source_type, record_attr, status, is_author, actions, expected_count
):
    user_id = uuid4()
    author_id = user_id if is_author else uuid4()
    urza_id = uuid4()
    urza = SimpleNamespace(dispatch_name="УРЗА-1", deleted_at=None)
    form = SimpleNamespace(urza_id=urza_id, urza=urza, deleted_at=None)
    record = SimpleNamespace(
        task_id=None,
        deleted_at=None,
        created_by=author_id,
        created_at=datetime(2026, 10, 2, tzinfo=UTC),
        creator=SimpleNamespace(full_name="Автор"),
        status=status,
        parameter_name="Уставка",
        schema_number="СХ-1",
        schema_name="Схема",
    )
    setattr(record, record_attr, form)

    class Repository:
        async def list_standalone_work_items(self):
            return [record]

    class Access:
        async def can_access_urza(self, *_):
            return True

    class Service:
        repository = Repository()
        access_service = Access()

        async def get_available_actions(self, *_):
            return actions

    result = await source_type(Service()).list_for_user(user_id)

    assert len(result) == expected_count

    if status is DocumentStatus.UNDER_REVIEW and expected_count:
        assert result[0].status == "На согласовании"

        if not is_author and actions.intersection({"approve", "return"}):
            assert result[0].actions == (
                "Утвердить",
                "Вернуть на доработку",
            )

        if not actions.intersection({"approve", "return"}):
            assert result[0].can_approve is False


@pytest.mark.parametrize(
    ("source_type", "record_attr"),
    [(SettingsWorkItemSource, "settings_form"), (SchemaWorkItemSource, "schema_form")],
)
@pytest.mark.parametrize(
    ("accessible", "deleted_form", "deleted_urza"),
    [(False, False, False), (True, True, False), (True, False, True)],
)
@pytest.mark.asyncio
async def test_work_item_sources_exclude_inaccessible_or_deleted_urza(
    source_type, record_attr, accessible, deleted_form, deleted_urza
):
    user_id = uuid4()
    urza_id = uuid4()
    deletion_time = datetime(2026, 10, 3, tzinfo=UTC)
    urza = SimpleNamespace(
        dispatch_name="УРЗА-1",
        deleted_at=deletion_time if deleted_urza else None,
    )
    form = SimpleNamespace(
        urza_id=urza_id,
        urza=urza,
        deleted_at=deletion_time if deleted_form else None,
    )
    record = SimpleNamespace(
        task_id=None,
        deleted_at=None,
        created_by=user_id,
        created_at=datetime(2026, 10, 2, tzinfo=UTC),
        creator=SimpleNamespace(full_name="Автор"),
        parameter_name="Уставка",
        schema_number="СХ-1",
        schema_name="Схема",
        status=DocumentStatus.APPROVED,
    )
    setattr(record, record_attr, form)

    class Repository:
        async def list_standalone_work_items(self):
            return [record]

    class Access:
        async def can_access_urza(self, *_):
            return accessible

    class Service:
        repository = Repository()
        access_service = Access()

        async def get_available_actions(self, *_):
            return set()

    assert await source_type(Service()).list_for_user(user_id) == []


@pytest.mark.parametrize(
    ("source_type", "record_attr"),
    [(SettingsWorkItemSource, "settings_form"), (SchemaWorkItemSource, "schema_form")],
)
@pytest.mark.asyncio
async def test_work_item_sources_do_not_duplicate_task_results(
    source_type, record_attr
):
    user_id = uuid4()
    urza_id = uuid4()
    form = SimpleNamespace(
        urza_id=urza_id,
        urza=SimpleNamespace(dispatch_name="УРЗА-1", deleted_at=None),
        deleted_at=None,
    )
    record = SimpleNamespace(
        task_id=uuid4(),
        deleted_at=None,
        created_by=user_id,
        created_at=datetime(2026, 10, 2, tzinfo=UTC),
        creator=SimpleNamespace(full_name="Автор"),
        parameter_name="Уставка",
        schema_number="СХ-1",
        schema_name="Схема",
        status=DocumentStatus.APPROVED,
    )
    setattr(record, record_attr, form)

    class Repository:
        async def list_standalone_work_items(self):
            return [record]

    class Access:
        async def can_access_urza(self, *_):
            return True

    class Service:
        repository = Repository()
        access_service = Access()

        async def get_available_actions(self, *_):
            return set()

    assert await source_type(Service()).list_for_user(user_id) == []


async def _active_engineer(user_id):
    return SimpleNamespace(
        id=user_id,
        role=UserRole.ENGINEER,
        active=True,
        deleted_at=None,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "actions", "expected_status", "expected_actions"),
    [
        (
            DocumentStatus.DRAFT,
            {"submit"},
            "Черновик",
            {"Отправить на согласование"},
        ),
        (
            DocumentStatus.UNDER_REVIEW,
            {"approve", "return"},
            "На согласовании",
            {"Утвердить", "Вернуть на доработку"},
        ),
        (
            DocumentStatus.APPROVED,
            {"new_version"},
            "Закрыто",
            {"Создать новую версию"},
        ),
    ],
)
async def test_otd_work_items_show_standalone_versions_and_actions(
    status, actions, expected_status, expected_actions
):
    user_id = uuid4()
    urza_id = uuid4()
    version = SimpleNamespace(
        id=uuid4(),
        version_number=2,
        status=status,
        deleted_at=None,
        task_id=None,
        created_by=user_id,
        created_at=datetime(2026, 10, 14, tzinfo=UTC),
        created_by_user=SimpleNamespace(full_name="Автор"),
        otd=SimpleNamespace(
            urza_id=urza_id,
            deleted_at=None,
            urza=SimpleNamespace(dispatch_name="УРЗА-1", deleted_at=None),
        ),
    )

    class Repository:
        async def list_standalone_work_items(self):
            return [version]

    class Access:
        async def can_access_urza(self, *_):
            return True

    class Service:
        repository = Repository()
        access_service = Access()

        async def get_available_actions(self, *_):
            return actions

    items = await OTDWorkItemSource(Service()).list_for_user(user_id)

    assert len(items) == 1
    assert items[0].status == expected_status
    assert items[0].author == "Автор"
    assert items[0].url == f"/objects/urza/{urza_id}?tab=otd"
    assert set(items[0].actions) == expected_actions


@pytest.mark.parametrize(
    ("status", "expected_tab"),
    [
        (DocumentStatus.DRAFT, "work"),
        (DocumentStatus.UNDER_REVIEW, "review"),
        (DocumentStatus.APPROVED, "completed"),
    ],
)
def test_document_tab_matches_status(status, expected_tab):
    assert _document_tab(status) == expected_tab


@pytest.mark.parametrize(
    ("status", "expected_tab"),
    [
        (TaskStatus.CREATED, "work"),
        (TaskStatus.ASSIGNED, "work"),
        (TaskStatus.IN_PROGRESS, "work"),
        (TaskStatus.COMPLETED, "work"),
        (TaskStatus.UNDER_REVIEW, "review"),
        (TaskStatus.CLOSED, "completed"),
        (TaskStatus.REJECTED, "completed"),
    ],
)
def test_task_tab_matches_status(status, expected_tab):
    assert _task_tab(status) == expected_tab


def test_action_labels_support_delete():
    assert _action_labels({"delete"}) == ("Удалить",)
