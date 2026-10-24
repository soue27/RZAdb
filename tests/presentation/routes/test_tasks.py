from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from uuid6 import uuid7

from app.application.objects.exceptions import ObjectAccessDeniedError
from app.application.work_items.service import (
    SchemaWorkItemSource,
    TaskWorkItemSource,
    WorkItem,
    WorkItemService,
)
from app.domain.enums import DocumentStatus, TaskStatus, TaskWorkType, UserRole
from app.presentation.app import app
from app.presentation.auth.dependencies import get_current_user
from app.presentation.dependencies.services import (
    get_access_service,
    get_inspection_task_repository,
    get_inspection_task_service,
    get_inspection_work_item_source,
    get_object_service,
    get_task_repository,
    get_task_service,
    get_tree_service,
    get_work_item_service,
)


def _task(user_id: UUID, status: TaskStatus = TaskStatus.COMPLETED):
    return SimpleNamespace(
        id=uuid7(),
        urza_id=uuid7(),
        urza=SimpleNamespace(dispatch_name="УРЗА-1"),
        work_type=TaskWorkType.SCHEMES,
        description="Проверить схему",
        assigned_to=user_id,
        assigned_to_user=SimpleNamespace(full_name="Инженер"),
        substation_id=None,
        created_by=user_id,
        created_by_user=SimpleNamespace(full_name="Автор"),
        status=status,
        created_at=datetime(2026, 10, 1, tzinfo=UTC),
        assigned_at=None,
        acceptance_deadline_at=None,
        deadline_at=datetime(2026, 10, 20, tzinfo=UTC),
        completed_at=datetime(2026, 10, 1, tzinfo=UTC),
        closed_at=None,
        deleted_at=None,
    )


class FakeTaskRepository:
    def __init__(self, tasks):
        self.tasks = tasks
        self.history = {}
        self.program_results = {}

    async def list_active(self):
        return [task for task in self.tasks if task.deleted_at is None]

    async def get_active_by_id(self, task_id):
        return next(
            (
                task
                for task in self.tasks
                if task.id == task_id and task.deleted_at is None
            ),
            None,
        )

    async def get_history(self, task_id):
        return self.history.get(task_id, [])

    async def get_program_by_task_id(self, task_id):
        return self.program_results.get(task_id)


class FakeInspectionTaskRepository:
    def __init__(self, tasks=(), reviewed_task_ids=()):
        self.tasks = list(tasks)
        self.reviewed_task_ids = set(reviewed_task_ids)

    async def list_active(self):
        return self.tasks

    async def list_reviewed_task_ids(self, actor_id):
        return self.reviewed_task_ids


class FakeInspectionTaskService:
    def __init__(self, reviewable_task_ids=()):
        self.reviewable_task_ids = set(reviewable_task_ids)

    async def can_review(self, task_id, *, actor_id):
        return task_id in self.reviewable_task_ids


class FakeTreeService:
    async def get_tree(self, *, user_id):
        urza = SimpleNamespace(id=uuid7(), dispatch_name="УРЗА из дерева")
        connection = SimpleNamespace(
            id=uuid7(),
            dispatch_name="Присоединение",
            urzas=[urza],
        )
        substation = SimpleNamespace(
            id=uuid7(),
            dispatch_name="Подстанция",
            connections=[connection],
        )
        return [
            SimpleNamespace(
                id=uuid7(),
                type="holding",
                full_name="Холдинг",
                children=[],
                substations=[substation],
            )
        ]



class FakeEmptyTreeService:
    async def get_tree(self, *, user_id):
        return []


def _work_item(
    *,
    title: str,
    tab: str = "review",
    can_approve: bool = False,
) -> WorkItem:
    return WorkItem(
        item_type="Тестовый документ",
        title=title,
        status="На согласовании",
        status_class="text-bg-warning",
        created_at=datetime(2026, 10, 1, tzinfo=UTC),
        author="Автор",
        assignee="Исполнитель",
        parent="ПС-Тест",
        parent_id=uuid7(),
        url=f"/test-items/{title}",
        actions=("approve", "return") if can_approve else (),
        tab=tab,
        can_approve=can_approve,
    )



class FakeSourceForTest:
    def __init__(self, items):
        self.items = items

    async def list_for_user(self, user_id, prior_items=()):
        return self.items


class FakeAccessService:
    def __init__(self, denied_urzas=(), denied_substations=()):
        self.denied_urzas = set(denied_urzas)
        self.denied_substations = set(denied_substations)
        self.urza_repository = FakeURZARepository()
        self.user_repository = SimpleNamespace(get_by_id=self._get_user)

    async def _get_user(self, user_id):
        return SimpleNamespace(
            id=user_id,
            role=UserRole.ENGINEER,
            active=True,
            deleted_at=None,
        )

    async def can_access_urza(self, user_id, urza_id):
        return urza_id not in self.denied_urzas

    async def can_access_substation(self, user_id, substation_id):
        return substation_id not in self.denied_substations

    async def get_accessible_enterprise_roots(self, user_id):
        return []


class FakeURZARepository:
    def __init__(self):
        self.urzas = {}

    async def get_by_id(self, urza_id):
        return self.urzas.get(urza_id)


class FakeTaskService:
    def __init__(self, actions=None, errors=None, *, can_issue=True, engineers=None):
        self.actions = actions or {}
        self.errors = errors or {}
        self.calls = []
        self.can_issue = can_issue
        self.engineers = engineers or []
        self.created_task = None

    async def can_issue_task(self, *, actor_id, urza_id=None, substation_id=None):
        self.calls.append(("can_issue_task", actor_id, urza_id or substation_id))
        return self.can_issue

    async def get_available_assignees(self, *, actor_id, urza_id=None, substation_id=None):
        self.calls.append(("get_available_assignees", actor_id, urza_id or substation_id))
        return self.engineers

    async def create_task(self, **kwargs):
        self.calls.append(("create_task", kwargs))
        error = self.errors.get("create_task")
        if error:
            raise error
        self.created_task = SimpleNamespace(
            id=uuid7(),
            status=TaskStatus.CREATED,
            **kwargs,
        )
        return self.created_task

    async def assign_task(self, *, task, assigned_to, actor_id):
        self.calls.append(("assign_task", task.id, assigned_to, actor_id))
        task.assigned_to = assigned_to
        task.status = TaskStatus.ASSIGNED
        return task

    async def reassign_task(self, *, task, assigned_to, actor_id):
        self.calls.append(("reassign_task", task.id, assigned_to, actor_id))
        error = self.errors.get("reassign_task")
        if error:
            raise error
        task.assigned_to = assigned_to
        task.assigned_to_user = next(
            (
                engineer
                for engineer in self.engineers
                if engineer.id == assigned_to
            ),
            None,
        )
        return task

    async def get_available_actions(self, *, task, actor_id):
        return self.actions.get(task.id, set())


    async def _run(
        self,
        name,
        *,
        task,
        actor_id,
        comment=None,
    ):
        self.calls.append((name, task.id, actor_id, comment))
        error = self.errors.get(name)
        if error:
            raise error

        if name == "accept_task":
            task.status = TaskStatus.IN_PROGRESS
        elif name == "reject_task":
            task.status = TaskStatus.REJECTED
        elif name == "complete_task":
            task.status = TaskStatus.COMPLETED
        elif name == "submit_for_review":
            task.status = TaskStatus.UNDER_REVIEW
        elif name == "close_task":
            task.status = TaskStatus.CLOSED
        elif name == "return_for_revision":
            task.status = TaskStatus.IN_PROGRESS

        return task

    async def accept_task(self, **kwargs):
        return await self._run("accept_task", **kwargs)

    async def reject_task(self, *, task, actor_id, reason):
        return await self._run(
            "reject_task",
            task=task,
            actor_id=actor_id,
            comment=reason,
        )

    async def complete_task(self, **kwargs):
        return await self._run("complete_task", **kwargs)

    async def submit_for_review(self, **kwargs):
        return await self._run("submit_for_review", **kwargs)

    async def close_task(self, **kwargs):
        return await self._run("close_task", **kwargs)

    async def return_for_revision(self, **kwargs):
        return await self._run("return_for_revision", **kwargs)



def _client(user, repository, access_service, task_service):
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_task_repository] = lambda: repository
    app.dependency_overrides[get_access_service] = lambda: access_service
    app.dependency_overrides[get_task_service] = lambda: task_service
    app.dependency_overrides[get_tree_service] = lambda: FakeTreeService()
    app.dependency_overrides[get_inspection_task_repository] = (
        lambda: FakeInspectionTaskRepository()
    )
    app.dependency_overrides[get_work_item_service] = lambda: WorkItemService(
        [TaskWorkItemSource(repository, access_service, task_service)]
    )
    app.dependency_overrides[get_inspection_task_service] = (
        lambda: FakeInspectionTaskService()
    )
    return TestClient(app)


class ScopedObjectService:
    def __init__(self, allowed_substation_id):
        self.allowed_substation_id = allowed_substation_id

    async def get_object(self, *, user_id, object_type, object_id):
        if object_type != "substation" or object_id != self.allowed_substation_id:
            raise ObjectAccessDeniedError
        return SimpleNamespace(id=object_id, dispatch_name="ПС-1")


def test_substation_task_form_checks_object_access_and_renders_parent():
    user = _user(uuid7(), role=UserRole.MANAGER)
    substation_id = uuid7()
    engineer = SimpleNamespace(id=uuid7(), full_name="Инженер")
    service = FakeTaskService(engineers=[engineer])
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_object_service] = lambda: ScopedObjectService(substation_id)
    app.dependency_overrides[get_task_service] = lambda: service
    app.dependency_overrides[get_tree_service] = lambda: FakeTreeService()
    try:
        response = TestClient(app).get(
            f"/tasks/substation/create?substation_id={substation_id}&work_type=instruction"
        )
        assert response.status_code == 200
        assert "ПС-1" in response.text
        assert "Тип работы: Инструкция РЗА подстанции" in response.text
        assert ("get_available_assignees", user.id, substation_id) in service.calls
    finally:
        app.dependency_overrides.clear()


def test_tasks_list_shows_only_accessible_assigned_inspection_tasks():
    user = _user(uuid7(), role=UserRole.ENGINEER)
    visible_substation_id, denied_substation_id = uuid7(), uuid7()

    def inspection_task(substation_id, assignee_id):
        return SimpleNamespace(
            id=uuid7(),
            substation_id=substation_id,
            substation=SimpleNamespace(dispatch_name=f"ПС-{substation_id.hex[:4]}"),
            created_by_user=SimpleNamespace(full_name="Руководитель"),
            assigned_to_user=SimpleNamespace(full_name="Инженер"),
            assigned_to=assignee_id,
            created_at=datetime(2026, 10, 1, tzinfo=UTC),
            status=TaskStatus.ASSIGNED,
            deadline_at=None,
        )

    visible = inspection_task(visible_substation_id, user.id)
    denied = inspection_task(denied_substation_id, user.id)
    unassigned = inspection_task(visible_substation_id, None)
    repository = FakeTaskRepository([])
    access = FakeAccessService(denied_substations={denied_substation_id})
    client = _client(user, repository, access, FakeTaskService())
    app.dependency_overrides[get_inspection_task_repository] = (
        lambda: FakeInspectionTaskRepository([visible, denied, unassigned])
    )
    try:
        response = client.get("/tasks")
        assert response.status_code == 200
        assert f"ПС-{visible_substation_id.hex[:4]}" in response.text
        assert f"/objects/substation/inspection-tasks/{denied.id}" not in response.text
        assert response.text.count(f"/objects/substation/inspection-tasks/{visible.id}") == 2
        assert f"/objects/substation/inspection-tasks/{unassigned.id}" not in response.text
    finally:
        app.dependency_overrides.clear()



def test_superadmin_sees_only_related_inspection_tasks():
    user = _user(uuid7(), role=UserRole.SUPERADMIN)
    substation_id = uuid7()

    def inspection_task(*, created_by, assigned_to=None):
        task_id = uuid7()
        return SimpleNamespace(
            id=task_id,
            substation_id=substation_id,
            substation=SimpleNamespace(dispatch_name="ПС-ТЕСТ"),
            created_by=created_by,
            created_by_user=SimpleNamespace(full_name="Руководитель"),
            assigned_to_user=SimpleNamespace(full_name="Инженер"),
            assigned_to=assigned_to,
            created_at=datetime(2026, 10, 1, tzinfo=UTC),
            status=TaskStatus.ASSIGNED,
                deadline_at=None,
        )

    authored = inspection_task(created_by=user.id)
    assigned = inspection_task(created_by=uuid7(), assigned_to=user.id)
    reviewed = inspection_task(created_by=uuid7())
    unrelated = inspection_task(created_by=uuid7(), assigned_to=uuid7())

    repository = FakeTaskRepository([])
    access = FakeAccessService()
    client = _client(user, repository, access, FakeTaskService())

    app.dependency_overrides[get_inspection_task_repository] = lambda: (
        FakeInspectionTaskRepository(
            [authored, assigned, reviewed, unrelated],
            reviewed_task_ids={reviewed.id},
        )
    )

    try:
        response = client.get("/tasks")

        assert response.status_code == 200
        for task in (authored, assigned, reviewed):
            assert f"/objects/substation/inspection-tasks/{task.id}" in response.text

        assert (
            f"/objects/substation/inspection-tasks/{unrelated.id}"
            not in response.text
        )
    finally:
        app.dependency_overrides.clear()



def test_substation_task_post_links_parent_and_returns_to_origin_tab():
    user = _user(uuid7(), role=UserRole.MANAGER)
    substation_id = uuid7()
    engineer = SimpleNamespace(id=uuid7(), full_name="Инженер")
    service = FakeTaskService(engineers=[engineer])
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_object_service] = lambda: ScopedObjectService(substation_id)
    app.dependency_overrides[get_task_service] = lambda: service
    app.dependency_overrides[get_tree_service] = lambda: FakeTreeService()
    try:
        response = TestClient(app).post(
            "/tasks/substation/create",
            data={
                "substation_id": str(substation_id),
                "work_type": "schemes",
                "engineer_id": str(engineer.id),
                "deadline_at": "2026-11-01",
                "description": "Обновить схему",
            },
            follow_redirects=False,
        )
        assert response.status_code == 303
        assert response.headers["location"] == (
            f"/objects/substation/{substation_id}?tab=selectivity-schemes"
        )
        create_call = next(call[1] for call in service.calls if call[0] == "create_task")
        assert create_call["substation_id"] == substation_id
        assert create_call.get("urza_id") is None
        assert create_call["work_type"] is TaskWorkType.SCHEMES
        assert any(call[0] == "assign_task" for call in service.calls)
    finally:
        app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def clear_dependency_overrides():
    app.dependency_overrides.clear()
    yield
    app.dependency_overrides.clear()


def _user(user_id, role=UserRole.ENGINEER):
    return SimpleNamespace(id=user_id, role=role, full_name="Пользователь")


def test_task_routes_are_registered_in_openapi():
    paths = app.openapi()["paths"]
    assert "get" in paths["/tasks"]
    assert "get" in paths["/tasks/create"]
    assert "get" in paths["/tasks/{task_id}"]
    assert "post" in paths["/tasks/{task_id}/submit-for-review"]
    assert "post" in paths["/tasks/{task_id}/close"]
    assert "post" in paths["/tasks/{task_id}/return-for-revision"]
    assert "post" in paths["/tasks/{task_id}/accept"]
    assert "post" in paths["/tasks/{task_id}/reject"]
    assert "post" in paths["/tasks/{task_id}/complete"]
    assert "post" in paths["/tasks/{task_id}/reassign"]


@pytest.mark.parametrize(
    ("method", "path", "data"),
    [
        ("get", "/tasks", None),
        ("get", "/tasks/create", None),
        ("get", "/tasks/00000000-0000-0000-0000-000000000001", None),
        ("post", "/tasks/create", {}),
        ("post", "/tasks/00000000-0000-0000-0000-000000000001/accept", {}),
        ("post", "/tasks/00000000-0000-0000-0000-000000000001/complete", {}),
        ("post", "/tasks/00000000-0000-0000-0000-000000000001/reject", {}),
        ("post", "/tasks/00000000-0000-0000-0000-000000000001/submit-for-review", {}),
        ("post", "/tasks/00000000-0000-0000-0000-000000000001/close", {}),
        ("post", "/tasks/00000000-0000-0000-0000-000000000001/return-for-revision", {}),
        ("post", "/tasks/00000000-0000-0000-0000-000000000001/reassign", {}),
    ],
)
def test_specialist_is_forbidden_from_all_task_routes(
    system_user_id, method, path, data
):
    repository = FakeTaskRepository([])
    access_service = FakeAccessService()
    service = FakeTaskService()
    client = _client(
        _user(system_user_id, UserRole.SPECIALIST),
        repository,
        access_service,
        service,
    )

    response = getattr(client, method)(path, data=data) if data is not None else getattr(client, method)(path)

    assert response.status_code == 403
    assert repository.tasks == []
    assert service.calls == []


@pytest.mark.parametrize(
    "role",
    [UserRole.SUPERADMIN, UserRole.ADMIN, UserRole.MANAGER, UserRole.ENGINEER],
)
def test_existing_roles_keep_task_list_access(system_user_id, role):
    client = _client(
        _user(system_user_id, role),
        FakeTaskRepository([]),
        FakeAccessService(),
        FakeTaskService(),
    )
    response = client.get("/tasks")
    assert response.status_code == 200


def test_task_create_form_shows_urza_work_type_and_available_engineers(
    system_user_id,
):
    user = _user(system_user_id, UserRole.MANAGER)
    urza_id = uuid7()
    engineer = SimpleNamespace(id=uuid7(), full_name="Инженер отделения")
    access = FakeAccessService()
    access.urza_repository.urzas[urza_id] = SimpleNamespace(
        id=urza_id,
        dispatch_name="УРЗА-42",
    )
    service = FakeTaskService(engineers=[engineer])

    with _client(user, FakeTaskRepository([]), access, service) as client:
        response = client.get(
            "/tasks/create",
            params={"urza_id": str(urza_id), "work_type": "instruction"},
        )

    assert response.status_code == 200
    assert "УРЗА-42" in response.text
    assert "Инструкция" in response.text
    assert "Инженер отделения" in response.text
    assert f'value="{engineer.id}"' in response.text
    assert service.calls == [
        ("can_issue_task", user.id, urza_id),
        ("get_available_assignees", user.id, urza_id),
    ]


def test_task_create_form_denies_user_without_issue_permission(system_user_id):
    user = _user(system_user_id, UserRole.ENGINEER)
    urza_id = uuid7()
    access = FakeAccessService()
    service = FakeTaskService(can_issue=False)

    with _client(user, FakeTaskRepository([]), access, service) as client:
        response = client.get(
            "/tasks/create",
            params={"urza_id": str(urza_id), "work_type": "schemes"},
        )

    assert response.status_code == 403
    assert service.calls == [("can_issue_task", user.id, urza_id)]


def test_task_create_post_creates_and_assigns_task(system_user_id):
    user = _user(system_user_id, UserRole.MANAGER)
    urza_id = uuid7()
    engineer = SimpleNamespace(id=uuid7(), full_name="Исполнитель")
    access = FakeAccessService()
    access.urza_repository.urzas[urza_id] = SimpleNamespace(
        id=urza_id,
        dispatch_name="УРЗА-42",
    )
    service = FakeTaskService(engineers=[engineer])
    form_data = {
        "urza_id": str(urza_id),
        "work_type": "instruction",
        "engineer_id": str(engineer.id),
        "deadline_at": "2026-10-30T12:45",
        "description": "Проверить инструкцию",
    }

    with _client(user, FakeTaskRepository([]), access, service) as client:
        response = client.post("/tasks/create", data=form_data, follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == f"/tasks/{service.created_task.id}"
    assert service.created_task.status is TaskStatus.ASSIGNED
    assert service.created_task.assigned_to == engineer.id
    assert service.created_task.description == form_data["description"]
    assert service.created_task.deadline_at.replace(tzinfo=None) == datetime(
        2026,
        10,
        30,
        12,
        45,
    )
    assert service.calls == [
        ("can_issue_task", user.id, urza_id),
        ("get_available_assignees", user.id, urza_id),
        (
            "create_task",
            {
                "urza_id": urza_id,
                "work_type": TaskWorkType.INSTRUCTION,
                "created_by": user.id,
                "description": form_data["description"],
                "deadline_at": service.created_task.deadline_at,
                "maintenance_type": None,
            },
        ),
        ("assign_task", service.created_task.id, engineer.id, user.id),
    ]


def test_task_create_post_denies_user_without_issue_permission(system_user_id):
    user = _user(system_user_id, UserRole.ENGINEER)
    urza_id = uuid7()
    engineer = SimpleNamespace(id=uuid7(), full_name="Исполнитель")
    service = FakeTaskService(can_issue=False, engineers=[engineer])

    with _client(
        user,
        FakeTaskRepository([]),
        FakeAccessService(),
        service,
    ) as client:
        response = client.post(
            "/tasks/create",
            data={
                "urza_id": str(urza_id),
                "work_type": "schemes",
                "engineer_id": str(engineer.id),
                "deadline_at": "2026-10-30T12:45",
                "description": "",
            },
        )

    assert response.status_code == 403
    assert "не может выдавать задания" in response.text
    assert service.created_task is None
    assert service.calls == [("can_issue_task", user.id, urza_id)]


def test_task_create_post_rejects_engineer_outside_available_assignees(
    system_user_id,
):
    user = _user(system_user_id, UserRole.MANAGER)
    urza_id = uuid7()
    allowed_engineer = SimpleNamespace(id=uuid7(), full_name="Допустимый инженер")
    forged_engineer_id = uuid7()
    access = FakeAccessService()
    access.urza_repository.urzas[urza_id] = SimpleNamespace(
        id=urza_id,
        dispatch_name="УРЗА-42",
    )
    service = FakeTaskService(engineers=[allowed_engineer])

    with _client(user, FakeTaskRepository([]), access, service) as client:
        response = client.post(
            "/tasks/create",
            data={
                "urza_id": str(urza_id),
                "work_type": "schemes",
                "engineer_id": str(forged_engineer_id),
                "deadline_at": "2026-10-30T12:45",
                "description": "Проверка схемы",
            },
        )

    assert response.status_code == 400
    assert "не является доступным активным инженером" in response.text
    assert "Допустимый инженер" in response.text
    assert service.created_task is None
    assert all(call[0] != "create_task" for call in service.calls)


def test_task_list_shows_accessible_tasks_and_opens_details_for_actions(system_user_id):
    user = _user(system_user_id)
    visible = _task(user.id)
    hidden = _task(user.id)
    hidden.deleted_at = datetime.now(UTC)
    no_access = _task(user.id)
    repository = FakeTaskRepository([visible, hidden, no_access])
    access = FakeAccessService({no_access.urza_id})
    service = FakeTaskService({visible.id: {"submit_for_review"}})

    with _client(user, repository, access, service) as client:
        response = client.get("/tasks")
        detail_response = client.get(f"/tasks/{visible.id}")

    assert response.status_code == 200
    assert "Проверить схему" in response.text
    assert "УРЗА-1" in response.text
    assert "Инженер" in response.text
    assert "Выполнено" in response.text
    assert response.text.count("Проверить схему") == 1
    assert "Отправить на согласование" not in response.text
    assert "Отправить на согласование" in detail_response.text
    assert 'id="object-content"' in response.text
    assert 'hx-target="#object-content"' in response.text
    assert "УРЗА из дерева" in response.text


def test_task_list_uses_unified_work_items_table():
    user = _user(uuid7())
    repository = FakeTaskRepository([_task(user.id)])
    access = FakeAccessService()
    service = FakeTaskService()

    with _client(user, repository, access, service) as client:
        response = client.get("/tasks")

    assert response.status_code == 200
    assert "Текущая работа" in response.text
    assert "Задание · Схема" in response.text
    assert "Автор" in response.text
    assert "Исполнитель" in response.text
    assert "/tasks/" in response.text
    assert "Отправить на согласование" not in response.text
    assert "text-bg-info" not in response.text
    assert "class=\"btn btn-sm btn-outline-primary\">Открыть</a>" in response.text


def test_tasks_list_sorts_work_items_and_inspections_together():
    user = _user(uuid7(), role=UserRole.MANAGER)
    substation_id = uuid7()
    older = datetime(2026, 10, 1, tzinfo=UTC)
    middle = datetime(2026, 10, 2, tzinfo=UTC)
    newer = datetime(2026, 10, 3, tzinfo=UTC)

    document = WorkItem(
        item_type="Самостоятельная схема",
        title="Документ для проверки сортировки",
        status="Закрыто",
        status_class="text-bg-success",
        created_at=middle,
        author="Автор документа",
        assignee="—",
        parent="УРЗА-1",
        parent_id=uuid7(),
        url="/objects/urza/example?tab=schemas",
        actions=(),
        tab="completed",
    )

    inspection = SimpleNamespace(
        id=uuid7(),
        substation_id=substation_id,
        substation=SimpleNamespace(dispatch_name="ПС для проверки сортировки"),
        created_by_user=SimpleNamespace(full_name="Руководитель"),
        assigned_to_user=SimpleNamespace(full_name="Инженер"),
        assigned_to=user.id,
        created_at=newer,
        status=TaskStatus.CLOSED,
        deadline_at=datetime(2026, 10, 20, tzinfo=UTC),
    )

    task = _task(user.id, TaskStatus.CLOSED)
    task.created_at = older
    task.description = "Задание для проверки сортировки"

    repository = FakeTaskRepository([task])
    access = FakeAccessService()
    client = _client(user, repository, access, FakeTaskService())

    app.dependency_overrides[get_work_item_service] = lambda: WorkItemService(
        [
            FakeSourceForTest([document]),
            TaskWorkItemSource(repository, access, FakeTaskService()),
        ]
    )
    app.dependency_overrides[get_inspection_task_repository] = lambda: (
        FakeInspectionTaskRepository([inspection])
    )

    try:
        response = client.get("/tasks")
        assert response.status_code == 200

        positions = [
            response.text.index("ПС для проверки сортировки"),
            response.text.index("Документ для проверки сортировки"),
            response.text.index("Задание для проверки сортировки"),
        ]
        assert positions == sorted(positions)
    finally:
        app.dependency_overrides.clear()


def test_tasks_list_includes_schema_new_record_action_without_error(system_user_id):
    user = _user(system_user_id)
    urza_id = uuid7()
    schema_form = SimpleNamespace(
        id=uuid7(),
        urza_id=urza_id,
        urza=SimpleNamespace(dispatch_name="УРЗА-1", deleted_at=None),
        deleted_at=None,
    )
    record = SimpleNamespace(
        id=uuid7(),
        schema_form_id=schema_form.id,
        schema_form=schema_form,
        task_id=None,
        status=DocumentStatus.APPROVED,
        deleted_at=None,
        schema_number="С-1",
        schema_name="Схема защиты",
        created_at=datetime(2026, 10, 1, tzinfo=UTC),
        creator=SimpleNamespace(full_name="Автор"),
    )
    schema_service = SimpleNamespace(
        repository=SimpleNamespace(
            list_standalone_work_items=AsyncMock(return_value=[record]),
        ),
        access_service=FakeAccessService(),
        get_available_actions=AsyncMock(return_value={"new_record"}),
    )

    with _client(
        user,
        FakeTaskRepository([]),
        FakeAccessService(),
        FakeTaskService(),
    ) as client:
        app.dependency_overrides[get_work_item_service] = lambda: WorkItemService(
            [SchemaWorkItemSource(schema_service)]
        )
        response = client.get("/tasks")

    assert response.status_code == 200
    assert "Схема защиты" in response.text
    assert "Открыть" in response.text
    schema_service.get_available_actions.assert_awaited_once_with(
        user.id,
        record,
    )


def test_task_detail_displays_history_and_review_actions(system_user_id):
    user = _user(system_user_id, UserRole.MANAGER)
    task = _task(user.id, TaskStatus.UNDER_REVIEW)
    event = SimpleNamespace(
        event_type="sent_to_review",
        old_status=TaskStatus.COMPLETED,
        new_status=TaskStatus.UNDER_REVIEW,
        actor=SimpleNamespace(full_name="Инженер"),
        created_at=datetime(2026, 10, 2, tzinfo=UTC),
        comment="Проверьте, пожалуйста",
    )
    repository = FakeTaskRepository([task])
    repository.history[task.id] = [event]
    access = FakeAccessService()
    service = FakeTaskService({task.id: {"close_task", "return_for_revision"}})

    with _client(user, repository, access, service) as client:
        response = client.get(f"/tasks/{task.id}")

    assert response.status_code == 200
    assert "История задания" in response.text
    assert "Направлено на согласование" in response.text
    assert "Выполнено" in response.text
    assert "Проверьте, пожалуйста" in response.text
    assert "Закрыть" in response.text
    assert "Вернуть на доработку" in response.text
    assert 'id="object-content"' in response.text
    assert 'hx-target="#object-content"' in response.text
    assert "УРЗА из дерева" in response.text


@pytest.mark.parametrize(
    ("assignees", "expected_participants"),
    [
        (None, "Исполнитель не указан"),
        (("Прежний инженер", "Новый инженер"), "Прежний инженер"),
    ],
)
def test_task_detail_renders_reassignment_history_with_legacy_compatibility(
    system_user_id, assignees, expected_participants
):
    user = _user(system_user_id, UserRole.MANAGER)
    task = _task(user.id, TaskStatus.ASSIGNED)
    event_fields = {}
    if assignees:
        event_fields = {
            "previous_assignee": SimpleNamespace(full_name=assignees[0]),
            "new_assignee": SimpleNamespace(full_name=assignees[1]),
        }
    event = SimpleNamespace(
        event_type="reassigned",
        old_status=TaskStatus.ASSIGNED,
        new_status=TaskStatus.ASSIGNED,
        actor=SimpleNamespace(full_name="Руководитель"),
        created_at=datetime(2026, 10, 2, tzinfo=UTC),
        comment=None,
        **event_fields,
    )
    repository = FakeTaskRepository([task])
    repository.history[task.id] = [event]

    with _client(user, repository, FakeAccessService(), FakeTaskService()) as client:
        response = client.get(f"/tasks/{task.id}")

    assert response.status_code == 200
    assert expected_participants in response.text
    if assignees:
        assert "Новый инженер" in response.text
        assert "Переназначил: Руководитель" in response.text
    else:
        assert "Руководитель" in response.text


@pytest.mark.parametrize(
    ("work_type", "expected_path"),
    [
        (TaskWorkType.MAINTENANCE, "maintenance/new"),
        (TaskWorkType.OTD, "otd/new"),
        (TaskWorkType.PROGRAM, "programs/new"),
    ],
)
def test_task_result_link_uses_matching_work_type_route(
    system_user_id, work_type, expected_path
):
    user = _user(system_user_id)
    task = _task(user.id, TaskStatus.IN_PROGRESS)
    task.work_type = work_type
    repository = FakeTaskRepository([task])
    service = FakeTaskService({task.id: {"create_result"}})

    with _client(user, repository, FakeAccessService(), service) as client:
        response = client.get(f"/tasks/{task.id}")

    assert response.status_code == 200
    assert (
        f'href="/objects/urza/{task.urza_id}/{expected_path}?task_id={task.id}"'
        in response.text
    )


def test_task_detail_denies_user_without_urza_access(system_user_id):
    user = _user(system_user_id)
    task = _task(user.id)
    repository = FakeTaskRepository([task])
    access = FakeAccessService({task.urza_id})
    service = FakeTaskService()

    with _client(user, repository, access, service) as client:
        response = client.get(f"/tasks/{task.id}")

    assert response.status_code == 403


def test_reassign_task_accepts_available_engineer(system_user_id):
    manager = _user(system_user_id, UserRole.MANAGER)
    task = _task(uuid7(), TaskStatus.ASSIGNED)
    engineer = SimpleNamespace(
        id=uuid7(),
        full_name="Новый исполнитель",
        active=True,
        deleted_at=None,
    )
    repository = FakeTaskRepository([task])
    service = FakeTaskService(engineers=[engineer])

    with _client(manager, repository, FakeAccessService(), service) as client:
        response = client.post(
            f"/tasks/{task.id}/reassign",
            data={"engineer_id": str(engineer.id)},
            follow_redirects=False,
        )

    assert response.status_code == 303
    assert response.headers["location"] == f"/tasks/{task.id}"
    assert task.assigned_to == engineer.id
    assert ("reassign_task", task.id, engineer.id, manager.id) in service.calls


@pytest.mark.parametrize("engineer_id", ["not-a-uuid", str(uuid7())])
def test_reassign_task_rejects_invalid_or_unavailable_engineer(
    system_user_id, engineer_id
):
    manager = _user(system_user_id, UserRole.MANAGER)
    task = _task(uuid7(), TaskStatus.ASSIGNED)
    original_assignee = task.assigned_to
    repository = FakeTaskRepository([task])
    service = FakeTaskService()

    with _client(manager, repository, FakeAccessService(), service) as client:
        response = client.post(
            f"/tasks/{task.id}/reassign",
            data={"engineer_id": engineer_id},
        )

    assert response.status_code == 400
    assert task.assigned_to == original_assignee
    assert all(call[0] != "reassign_task" for call in service.calls)


def test_reassign_task_forbids_user_without_issue_permission(system_user_id):
    engineer_user = _user(system_user_id, UserRole.ENGINEER)
    task = _task(engineer_user.id, TaskStatus.ASSIGNED)
    repository = FakeTaskRepository([task])
    service = FakeTaskService(
        can_issue=False,
        engineers=[SimpleNamespace(id=uuid7(), active=True, deleted_at=None)],
    )

    with _client(engineer_user, repository, FakeAccessService(), service) as client:
        response = client.post(
            f"/tasks/{task.id}/reassign",
            data={"engineer_id": str(service.engineers[0].id)},
        )

    assert response.status_code == 403
    assert task.assigned_to == engineer_user.id
    assert all(call[0] != "reassign_task" for call in service.calls)


def test_reassign_task_returns_htmx_detail_partial(system_user_id):
    manager = _user(system_user_id, UserRole.MANAGER)
    task = _task(uuid7(), TaskStatus.ASSIGNED)
    engineer = SimpleNamespace(
        id=uuid7(),
        full_name="Новый исполнитель",
        active=True,
        deleted_at=None,
    )
    repository = FakeTaskRepository([task])
    service = FakeTaskService(
        {task.id: {"reassign_task"}},
        engineers=[engineer],
    )

    with _client(manager, repository, FakeAccessService(), service) as client:
        response = client.post(
            f"/tasks/{task.id}/reassign",
            data={"engineer_id": str(engineer.id)},
            headers={"HX-Request": "true"},
        )

    assert response.status_code == 200
    assert 'id="task-page-content"' in response.text
    assert "<html" not in response.text
    assert task.assigned_to == engineer.id
    assert "Новый исполнитель" in response.text


def test_reassigned_task_access_moves_from_previous_to_new_engineer():
    previous_engineer = _user(uuid7())
    new_engineer = _user(uuid7())
    new_engineer.full_name = "Новый исполнитель"
    manager = _user(uuid7(), UserRole.MANAGER)
    task = _task(previous_engineer.id, TaskStatus.ASSIGNED)
    repository = FakeTaskRepository([task])
    service = FakeTaskService(engineers=[new_engineer])
    access = FakeAccessService()

    with _client(manager, repository, access, service) as client:
        response = client.post(
            f"/tasks/{task.id}/reassign",
            data={"engineer_id": str(new_engineer.id)},
            follow_redirects=False,
        )
    assert response.status_code == 303

    with _client(previous_engineer, repository, access, service) as client:
        previous_response = client.get(f"/tasks/{task.id}")
    with _client(new_engineer, repository, access, service) as client:
        new_response = client.get(f"/tasks/{task.id}")

    assert previous_response.status_code == 403
    assert new_response.status_code == 200


def test_task_action_denies_direct_post_without_urza_access(system_user_id):
    user = _user(system_user_id, UserRole.MANAGER)
    task = _task(user.id, TaskStatus.UNDER_REVIEW)
    repository = FakeTaskRepository([task])
    access = FakeAccessService({task.urza_id})
    service = FakeTaskService()

    with _client(user, repository, access, service) as client:
        response = client.post(f"/tasks/{task.id}/close")

    assert response.status_code == 403
    assert not service.calls


@pytest.mark.parametrize(
    ("path", "method_name", "new_status"),
    [
        ("submit-for-review", "submit_for_review", TaskStatus.UNDER_REVIEW),
        ("close", "close_task", TaskStatus.CLOSED),
        ("return-for-revision", "return_for_revision", TaskStatus.IN_PROGRESS),
    ],
)
def test_task_post_actions_call_application_methods(
    system_user_id,
    path,
    method_name,
    new_status,
):
    user = _user(system_user_id, UserRole.MANAGER)
    initial_status = (
        TaskStatus.COMPLETED
        if method_name == "submit_for_review"
        else TaskStatus.UNDER_REVIEW
    )
    task = _task(user.id, initial_status)
    repository = FakeTaskRepository([task])
    access = FakeAccessService()
    service = FakeTaskService()

    with _client(user, repository, access, service) as client:
        response = client.post(
            f"/tasks/{task.id}/{path}",
            data={"comment": "Проверено"},
            follow_redirects=False,
        )

    assert response.status_code == 303
    assert response.headers["location"] == f"/tasks/{task.id}"
    assert task.status is new_status
    assert service.calls == [(method_name, task.id, user.id, "Проверено")]



@pytest.mark.parametrize(
    ("path", "method_name", "initial_status", "new_status"),
    [
        (
            "accept",
            "accept_task",
            TaskStatus.ASSIGNED,
            TaskStatus.IN_PROGRESS,
        ),
        (
            "complete",
            "complete_task",
            TaskStatus.IN_PROGRESS,
            TaskStatus.COMPLETED,
        ),
    ],
)
def test_task_executor_post_actions_call_application_methods(
    system_user_id,
    path,
    method_name,
    initial_status,
    new_status,
):
    user = _user(system_user_id, UserRole.ENGINEER)
    task = _task(user.id, initial_status)
    repository = FakeTaskRepository([task])
    service = FakeTaskService()

    with _client(
        user,
        repository,
        FakeAccessService(),
        service,
    ) as client:
        response = client.post(
            f"/tasks/{task.id}/{path}",
            follow_redirects=False,
        )

    assert response.status_code == 303
    assert response.headers["location"] == f"/tasks/{task.id}"
    assert task.status is new_status
    assert service.calls == [
        (method_name, task.id, user.id, None),
    ]


def test_task_executor_can_reject_task_with_reason(system_user_id):
    user = _user(system_user_id, UserRole.ENGINEER)
    task = _task(user.id, TaskStatus.ASSIGNED)
    repository = FakeTaskRepository([task])
    service = FakeTaskService()
    reason = "Нет необходимого допуска для выполнения работы"

    with _client(
        user,
        repository,
        FakeAccessService(),
        service,
    ) as client:
        response = client.post(
            f"/tasks/{task.id}/reject",
            data={"reason": reason},
            follow_redirects=False,
        )

    assert response.status_code == 303
    assert response.headers["location"] == f"/tasks/{task.id}"
    assert task.status is TaskStatus.REJECTED
    assert service.calls == [
        ("reject_task", task.id, user.id, reason),
    ]



@pytest.mark.parametrize(
    ("path", "method_name", "error", "expected_status"),
    [
        ("close", "close_task", PermissionError("Только MANAGER."), 403),
        ("close", "close_task", ValueError("Нет утверждённого результата схем."), 400),
    ],
)
def test_task_action_errors_are_rendered_without_traceback(
    system_user_id,
    path,
    method_name,
    error,
    expected_status,
):
    user = _user(system_user_id)
    task = _task(user.id, TaskStatus.UNDER_REVIEW)
    repository = FakeTaskRepository([task])
    service = FakeTaskService(errors={method_name: error})

    with _client(user, repository, FakeAccessService(), service) as client:
        response = client.post(f"/tasks/{task.id}/{path}")

    assert response.status_code == expected_status
    assert str(error) in response.text
    assert "Traceback" not in response.text


def test_htmx_task_action_returns_updated_task_fragment(system_user_id):
    user = _user(system_user_id, UserRole.MANAGER)
    task = _task(user.id, TaskStatus.UNDER_REVIEW)
    repository = FakeTaskRepository([task])
    service = FakeTaskService()

    with _client(user, repository, FakeAccessService(), service) as client:
        response = client.post(
            f"/tasks/{task.id}/close",
            headers={"HX-Request": "true"},
        )

    assert response.status_code == 200
    assert 'id="task-page-content"' in response.text
    assert "Закрыто" in response.text
    assert "История задания" in response.text
    assert "<!doctype html>" not in response.text.lower()


@pytest.mark.parametrize(
    ("error", "expected_error"),
    [
        (None, None),
        (
            ValueError("Нельзя завершить задание."),
            "Нельзя завершить задание.",
        ),
    ],
)
def test_program_result_remains_in_successful_and_error_htmx_action(
    system_user_id, error, expected_error
):
    user = _user(system_user_id)
    task = _task(user.id, TaskStatus.IN_PROGRESS)
    task.work_type = TaskWorkType.PROGRAM
    repository = FakeTaskRepository([task])
    repository.program_results[task.id] = SimpleNamespace(
        program_type=SimpleNamespace(label="Рабочая"),
        program_number="ПР-HTMX-01",
        status=SimpleNamespace(label="Утверждена"),
        deleted_at=None,
        scan_file_id=None,
        editable_file_id=None,
    )
    errors = {"complete_task": error} if error is not None else None
    service = FakeTaskService(
        {task.id: {"submit_for_review"}},
        errors=errors,
    )

    with _client(user, repository, FakeAccessService(), service) as client:
        response = client.post(
            f"/tasks/{task.id}/complete",
            headers={"HX-Request": "true"},
        )

    assert response.status_code == 200
    assert 'id="task-page-content"' in response.text
    assert "Результат задания" in response.text
    assert "ПР-HTMX-01" in response.text
    if expected_error:
        assert expected_error in response.text
    else:
        assert task.status is TaskStatus.COMPLETED


from html.parser import HTMLParser


class _PaneTextParser(HTMLParser):
    _VOID_TAGS = {
        "area", "base", "br", "col", "embed", "hr", "img",
        "input", "link", "meta", "param", "source", "track", "wbr",
    }

    def __init__(self, pane_id: str) -> None:
        super().__init__()
        self.pane_id = pane_id
        self.depth = 0
        self.parts: list[str] = []
        self.finished = False

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        if self.finished:
            return

        if self.depth == 0:
            if dict(attrs).get("id") == self.pane_id:
                self.depth = 1
            return

        if tag not in self._VOID_TAGS:
            self.depth += 1

    def handle_endtag(self, tag: str) -> None:
        if self.finished or self.depth == 0 or tag in self._VOID_TAGS:
            return

        self.depth -= 1
        if self.depth == 0:
            self.finished = True

    def handle_data(self, data: str) -> None:
        if self.depth > 0:
            self.parts.append(data)


def _pane_text(html: str, pane_id: str) -> str:
    parser = _PaneTextParser(pane_id)
    parser.feed(html)
    return "".join(parser.parts)



def test_reviewable_inspection_appears_in_both_review_tabs(system_user_id):
    user = _user(system_user_id, UserRole.MANAGER)
    substation_id = uuid7()

    reviewable = SimpleNamespace(
        id=uuid7(),
        substation_id=substation_id,
        substation=SimpleNamespace(dispatch_name="ПС-доступный-осмотр"),
        created_by=uuid7(),
        created_by_user=SimpleNamespace(full_name="Руководитель"),
        assigned_to=uuid7(),
        assigned_to_user=SimpleNamespace(full_name="Инженер"),
        created_at=datetime(2026, 10, 1, tzinfo=UTC),
        status=TaskStatus.UNDER_REVIEW,
        deadline_at=datetime(2026, 10, 20, tzinfo=UTC),
    )

    not_reviewable = SimpleNamespace(
        id=uuid7(),
        substation_id=substation_id,
        substation=SimpleNamespace(dispatch_name="ПС-чужой-осмотр"),
        created_by=uuid7(),
        created_by_user=SimpleNamespace(full_name="Руководитель"),
        assigned_to=user.id,
        assigned_to_user=SimpleNamespace(full_name="Менеджер"),
        created_at=datetime(2026, 10, 2, tzinfo=UTC),
        status=TaskStatus.UNDER_REVIEW,
        deadline_at=datetime(2026, 10, 21, tzinfo=UTC),
    )

    repository = FakeTaskRepository([])
    access = FakeAccessService()
    client = _client(user, repository, access, FakeTaskService())

    app.dependency_overrides[get_inspection_task_repository] = lambda: (
        FakeInspectionTaskRepository([reviewable, not_reviewable])
    )
    app.dependency_overrides[get_inspection_task_service] = lambda: (
        FakeInspectionTaskService({reviewable.id})
    )

    try:
        response = client.get("/tasks")

        assert response.status_code == 200

        review_text = _pane_text(response.text, "review-pane")
        approval_text = _pane_text(response.text, "approval-pane")

        assert "ПС-доступный-осмотр" in review_text
        assert "ПС-доступный-осмотр" in approval_text

        assert "ПС-чужой-осмотр" in review_text
        assert "ПС-чужой-осмотр" not in approval_text
    finally:
        app.dependency_overrides.clear()



def test_manager_sees_approval_tab_when_queue_is_empty(system_user_id):
    """MANAGER видит вкладку согласования даже при пустой очереди."""
    user = _user(system_user_id, UserRole.MANAGER)
    client = _client(
        user,
        FakeTaskRepository([]),
        FakeAccessService(),
        FakeTaskService(),
    )
    app.dependency_overrides[get_work_item_service] = lambda: WorkItemService(
        [FakeSourceForTest([])]
    )

    try:
        response = client.get("/tasks")

        assert response.status_code == 200
        assert 'id="approval-tab"' in response.text
        assert 'id="approval-pane"' in response.text
        assert "Согласовать" in response.text
    finally:
        app.dependency_overrides.clear()


def test_engineer_does_not_see_approval_tab(system_user_id):
    """ENGINEER не видит вкладку согласования."""
    user = _user(system_user_id, UserRole.ENGINEER)
    client = _client(
        user,
        FakeTaskRepository([]),
        FakeAccessService(),
        FakeTaskService(),
    )
    app.dependency_overrides[get_work_item_service] = lambda: WorkItemService(
        [FakeSourceForTest([])]
    )

    try:
        response = client.get("/tasks")

        assert response.status_code == 200
        assert 'id="approval-tab"' not in response.text
        assert 'id="approval-pane"' not in response.text
    finally:
        app.dependency_overrides.clear()


def test_manager_without_accessible_tree_does_not_see_approval_tab(
    system_user_id,
):
    """MANAGER без доступного дерева не видит вкладку согласования."""
    user = _user(system_user_id, UserRole.MANAGER)
    client = _client(
        user,
        FakeTaskRepository([]),
        FakeAccessService(),
        FakeTaskService(),
    )
    app.dependency_overrides[get_tree_service] = lambda: FakeEmptyTreeService()
    app.dependency_overrides[get_work_item_service] = lambda: WorkItemService(
        [FakeSourceForTest([])]
    )

    try:
        response = client.get("/tasks")

        assert response.status_code == 200
        assert 'id="approval-tab"' not in response.text
        assert 'id="approval-pane"' not in response.text
    finally:
        app.dependency_overrides.clear()


def test_approval_tab_contains_only_items_with_approval_actions(
    system_user_id,
):
    """Вкладка согласования содержит только элементы с соответствующими правами."""
    user = _user(system_user_id, UserRole.MANAGER)
    approvable = _work_item(
        title="Документ-доступен-для-согласования",
        can_approve=True,
    )
    not_approvable = _work_item(
        title="Документ-без-действий-согласования",
        can_approve=False,
    )

    client = _client(
        user,
        FakeTaskRepository([]),
        FakeAccessService(),
        FakeTaskService(),
    )
    app.dependency_overrides[get_work_item_service] = lambda: WorkItemService(
        [FakeSourceForTest([approvable, not_approvable])]
    )

    try:
        response = client.get("/tasks")

        review_text = _pane_text(response.text, "review-pane")
        approval_text = _pane_text(response.text, "approval-pane")

        assert approvable.title in review_text
        assert not_approvable.title in review_text

        assert approvable.title in approval_text
        assert not_approvable.title not in approval_text
    finally:
        app.dependency_overrides.clear()


def test_under_review_item_remains_in_review_tab_without_approval_rights(
    system_user_id,
):
    """
    UNDER_REVIEW означает ожидание решения, а не право пользователя
    самостоятельно принять это решение.
    """
    user = _user(system_user_id, UserRole.MANAGER)
    item = _work_item(
        title="Ожидает-решения-другого-сотрудника",
        tab="review",
        can_approve=False,
    )

    client = _client(
        user,
        FakeTaskRepository([]),
        FakeAccessService(),
        FakeTaskService(),
    )
    app.dependency_overrides[get_work_item_service] = lambda: WorkItemService(
        [FakeSourceForTest([item])]
    )

    try:
        response = client.get("/tasks")

        review_text = _pane_text(response.text, "review-pane")
        approval_text = _pane_text(response.text, "approval-pane")

        assert item.title in review_text
        assert item.title not in approval_text

        # Руководитель с доступным деревом видит вкладку,
        # даже если в очереди нет доступных ему действий.
        assert 'id="approval-tab"' in response.text
        assert 'id="approval-pane"' in response.text
    finally:
        app.dependency_overrides.clear()


@pytest.mark.parametrize(
    ("stat", "expected_titles"),
    [
        ("work", {"ITEM-CREATED", "ITEM-ASSIGNED", "ITEM-IN-PROGRESS"}),
        ("review", {"ITEM-REVIEW"}),
        ("closed", {"ITEM-CLOSED"}),
    ],
)
def test_task_statistics_filter_shows_matching_tasks_only(stat, expected_titles):
    user = _user(uuid7())
    now = datetime.now(UTC)
    values = [
        ("ITEM-CREATED", "Создано", TaskStatus.CREATED, "work"),
        ("ITEM-ASSIGNED", "Назначено", TaskStatus.ASSIGNED, "work"),
        ("ITEM-IN-PROGRESS", "В работе", TaskStatus.IN_PROGRESS, "work"),
        ("ITEM-REVIEW", "На проверке", TaskStatus.UNDER_REVIEW, "review"),
        ("ITEM-CLOSED", "Закрыто", TaskStatus.CLOSED, "completed"),
        ("ITEM-REJECTED", "Отклонено", TaskStatus.REJECTED, "completed"),
    ]
    work_items = [
        WorkItem(
            item_type="Задание · Схема",
            title=title,
            status=status_label,
            status_class="text-bg-secondary",
            created_at=now,
            author="Автор",
            assignee="Исполнитель",
            parent="УРЗА-1",
            parent_id=uuid7(),
            url=f"/tasks/{uuid7()}",
            actions=(),
            tab=tab,
            status_code=status.value,
            deadline_at=now - timedelta(days=1),
        )
        for title, status_label, status, tab in values
    ]
    access = FakeAccessService()
    client = _client(user, FakeTaskRepository([]), access, FakeTaskService())
    app.dependency_overrides[get_work_item_service] = lambda: WorkItemService(
        [FakeSourceForTest(work_items)]
    )

    try:
        response = client.get(f"/tasks?stat={stat}")
        reset_response = client.get("/tasks") if stat == "review" else None
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert '<a href="/tasks" class="ms-2">Сбросить фильтр</a>' in response.text
    for title in expected_titles:
        assert title in response.text
    for title, _, _, _ in values:
        if title not in expected_titles:
            assert title not in response.text

    if stat == "review":
        assert reset_response is not None
        assert reset_response.status_code == 200
        assert "Показаны задачи на рассмотрении." not in reset_response.text
        for title, _, _, _ in values:
            assert title in reset_response.text


def test_review_statistics_filter_matches_tasks_inspections_and_documents():
    user = _user(uuid7(), role=UserRole.MANAGER)
    now = datetime.now(UTC)
    review_tasks = [
        WorkItem(
            item_type="Задание · Схема",
            title=f"Задание-на-рассмотрении-{index}",
            status="На согласовании",
            status_class="text-bg-warning",
            created_at=now,
            author="Автор",
            assignee="Исполнитель",
            parent="УРЗА-1",
            parent_id=uuid7(),
            url=f"/tasks/review-{index}",
            actions=(),
            tab="review",
            can_approve=False,
            status_code=TaskStatus.UNDER_REVIEW.value,
        )
        for index in (1, 2)
    ]
    standalone_document = WorkItem(
        item_type="Самостоятельная программа",
        title="Документ-на-согласовании",
        status="На согласовании",
        status_class="text-bg-warning",
        created_at=now,
        author="Автор",
        assignee="—",
        parent="УРЗА-1",
        parent_id=uuid7(),
        url="/objects/urza/example?tab=programs",
        actions=(),
        tab="review",
    )
    inspection = SimpleNamespace(
        id=uuid7(),
        substation_id=uuid7(),
        substation=SimpleNamespace(dispatch_name="ПС осмотра"),
        created_by=user.id,
        created_by_user=SimpleNamespace(full_name="Руководитель"),
        assigned_to=uuid7(),
        assigned_to_user=SimpleNamespace(full_name="Инженер"),
        created_at=now,
        status=TaskStatus.UNDER_REVIEW,
        deadline_at=None,
        deleted_at=None,
    )
    client = _client(
        user,
        FakeTaskRepository([]),
        FakeAccessService(),
        FakeTaskService(),
    )
    app.dependency_overrides[get_work_item_service] = lambda: WorkItemService(
        [FakeSourceForTest([*review_tasks, standalone_document])]
    )
    app.dependency_overrides[get_inspection_task_repository] = lambda: (
        FakeInspectionTaskRepository([inspection])
    )

    try:
        all_response = client.get("/tasks")
        filtered_response = client.get("/tasks?stat=review")
    finally:
        app.dependency_overrides.clear()

    assert all_response.status_code == filtered_response.status_code == 200
    all_review = _pane_text(all_response.text, "review-pane")
    filtered = filtered_response.text
    for item in review_tasks:
        assert item.title in all_review
        assert item.title in filtered
    assert standalone_document.title in all_review
    assert standalone_document.title in filtered
    assert "Осмотр ПС · ПС осмотра" in all_review
    assert "Осмотр ПС · ПС осмотра" in filtered


def test_statistics_and_review_filter_include_standalone_program_and_instruction():
    from app.application.tasks.statistics import TaskStatisticsService
    from app.presentation.dependencies.services import get_task_statistics_service

    user = _user(uuid7(), role=UserRole.MANAGER)
    documents = [
        WorkItem(
            item_type="Самостоятельная программа",
            title="Скрытое-название-A",
            status="На согласовании",
            status_class="text-bg-warning",
            created_at=datetime.now(UTC),
            author="Автор",
            assignee="—",
            parent="УРЗА-Тест",
            parent_id=uuid7(),
            url="/objects/urza/test?tab=programs",
            actions=(),
            tab="review",
        ),
        WorkItem(
            item_type="Самостоятельная инструкция URZA",
            title="Скрытое-название-B",
            status="На согласовании",
            status_class="text-bg-warning",
            created_at=datetime.now(UTC),
            author="Автор",
            assignee="—",
            parent="УРЗА-Тест",
            parent_id=uuid7(),
            url="/objects/urza/test?tab=instruction",
            actions=(),
            tab="review",
        ),
    ]
    work_item_service = WorkItemService([FakeSourceForTest(documents)])

    class EmptyStatisticsRepository:
        async def count_dashboard_statuses(self, **kwargs):
            return {}, 0

    class EmptyInspectionSource:
        async def list_for_user(self, user_id, **kwargs):
            return []

    department_id = uuid7()
    statistics_user = SimpleNamespace(
        id=user.id,
        role=UserRole.MANAGER,
        enterprise_id=department_id,
        active=True,
        deleted_at=None,
    )
    statistics_access = SimpleNamespace(
        user_repository=SimpleNamespace(
            get_by_id=AsyncMock(return_value=statistics_user)
        )
    )
    statistics_service = TaskStatisticsService(
        task_repository=EmptyStatisticsRepository(),
        inspection_repository=EmptyStatisticsRepository(),
        enterprise_repository=SimpleNamespace(
            get_by_id=AsyncMock(
                return_value=SimpleNamespace(id=department_id)
            )
        ),
        access_service=statistics_access,
        work_item_service=work_item_service,
        inspection_work_item_source=EmptyInspectionSource(),
    )

    client = _client(
        user,
        FakeTaskRepository([]),
        FakeAccessService(),
        FakeTaskService(),
    )
    app.dependency_overrides[get_work_item_service] = lambda: work_item_service
    app.dependency_overrides[get_inspection_work_item_source] = EmptyInspectionSource
    app.dependency_overrides[get_task_statistics_service] = lambda: statistics_service

    try:
        full_list = client.get("/tasks")
        filtered = client.get("/tasks?stat=review")
        statistics = client.get("/task-statistics")
    finally:
        app.dependency_overrides.clear()

    assert (
        full_list.status_code
        == filtered.status_code
        == statistics.status_code
        == 200
    )
    review_pane = _pane_text(full_list.text, "review-pane")
    for item in documents:
        assert item.item_type in review_pane
        assert item.item_type in filtered.text
    assert "Самостоятельная программа" in review_pane
    assert "Самостоятельная инструкция URZA" in review_pane
    assert 'class="task-statistic-value">2</span>' in statistics.text


def test_review_list_stats_keep_archived_urza_task_and_inspection():
    from app.application.tasks.statistics import TaskStatisticsService
    from app.application.work_items.service import InspectionTaskWorkItemSource
    from app.presentation.dependencies.services import get_task_statistics_service

    user = _user(uuid7(), role=UserRole.MANAGER)
    task = _task(user.id, TaskStatus.UNDER_REVIEW)
    task.urza.deleted_at = datetime(2026, 10, 20, tzinfo=UTC)
    inspection = SimpleNamespace(
        id=uuid7(),
        substation_id=uuid7(),
        substation=SimpleNamespace(dispatch_name="ПС-Тест"),
        created_by=user.id,
        created_by_user=SimpleNamespace(full_name="Автор"),
        assigned_to=user.id,
        assigned_to_user=SimpleNamespace(full_name="Исполнитель"),
        created_at=datetime(2026, 10, 2, tzinfo=UTC),
        status=TaskStatus.UNDER_REVIEW,
        deadline_at=None,
        deleted_at=None,
    )

    class AccessForArchivedURZA(FakeAccessService):
        def __init__(self):
            super().__init__()
            self.department_id = uuid7()
            self.user_repository = SimpleNamespace(
                get_by_id=AsyncMock(
                    return_value=SimpleNamespace(
                        id=user.id,
                        role=user.role,
                        enterprise_id=self.department_id,
                        active=True,
                        deleted_at=None,
                    )
                )
            )
            self.accessed_urzas = []

        async def can_access_urza(self, user_id, urza_id):
            self.accessed_urzas.append(urza_id)
            return True

    class EmptyStatisticsRepository:
        async def count_dashboard_statuses(self, **kwargs):
            return {}, 0

    access = AccessForArchivedURZA()
    client = _client(
        user,
        FakeTaskRepository([task]),
        access,
        FakeTaskService(),
    )
    app.dependency_overrides[get_inspection_task_repository] = lambda: (
        FakeInspectionTaskRepository([inspection])
    )
    statistics_service = TaskStatisticsService(
        task_repository=EmptyStatisticsRepository(),
        inspection_repository=EmptyStatisticsRepository(),
        enterprise_repository=SimpleNamespace(
            get_by_id=AsyncMock(
                return_value=SimpleNamespace(id=access.department_id)
            )
        ),
        access_service=access,
        work_item_service=app.dependency_overrides[get_work_item_service](),
        inspection_work_item_source=InspectionTaskWorkItemSource(
            repository=app.dependency_overrides[
                get_inspection_task_repository
            ](),
            access_service=access,
            inspection_service=app.dependency_overrides[
                get_inspection_task_service
            ](),
        ),
    )
    app.dependency_overrides[get_task_statistics_service] = (
        lambda: statistics_service
    )

    try:
        full_list = client.get("/tasks")
        review_filter = client.get("/tasks?stat=review")
        statistics = client.get("/task-statistics")
    finally:
        app.dependency_overrides.clear()

    assert (
        full_list.status_code
        == review_filter.status_code
        == statistics.status_code
        == 200
    )
    for response in (full_list, review_filter):
        assert "Проверить схему" in response.text
        assert "Осмотр ПС · ПС-Тест" in response.text
    assert "Проверить схему" in _pane_text(full_list.text, "review-pane")
    assert "Осмотр ПС · ПС-Тест" in _pane_text(full_list.text, "review-pane")
    assert "На рассмотрении" in statistics.text
    assert ">2<" in statistics.text
    assert access.accessed_urzas == [task.urza_id] * 3


def test_overdue_statistics_filter_excludes_terminal_tasks():
    user = _user(uuid7())
    now = datetime.now(UTC)
    items = [
        WorkItem(
            item_type="Задание · Схема",
            title="Просроченное в работе",
            status="В работе",
            status_class="text-bg-primary",
            created_at=now,
            author="Автор",
            assignee="Исполнитель",
            parent="УРЗА-1",
            parent_id=uuid7(),
            url="/tasks/work",
            actions=(),
            tab="work",
            status_code=TaskStatus.IN_PROGRESS.value,
            deadline_at=now - timedelta(days=1),
        ),
        WorkItem(
            item_type="Задание · Схема",
            title="Просроченное закрытое",
            status="Закрыто",
            status_class="text-bg-success",
            created_at=now,
            author="Автор",
            assignee="Исполнитель",
            parent="УРЗА-1",
            parent_id=uuid7(),
            url="/tasks/closed",
            actions=(),
            tab="completed",
            status_code=TaskStatus.CLOSED.value,
            deadline_at=now - timedelta(days=1),
        ),
    ]
    inspection = SimpleNamespace(
        id=uuid7(),
        substation_id=uuid7(),
        substation=SimpleNamespace(dispatch_name="ПС статистики"),
        created_by=user.id,
        created_by_user=SimpleNamespace(full_name="Руководитель"),
        assigned_to=user.id,
        assigned_to_user=SimpleNamespace(full_name="Исполнитель"),
        created_at=now,
        status=TaskStatus.IN_PROGRESS,
        deadline_at=now - timedelta(days=1),
        deleted_at=None,
    )
    client = _client(
        user,
        FakeTaskRepository([]),
        FakeAccessService(),
        FakeTaskService(),
    )
    app.dependency_overrides[get_inspection_task_repository] = lambda: (
        FakeInspectionTaskRepository([inspection])
    )
    app.dependency_overrides[get_work_item_service] = lambda: WorkItemService(
        [FakeSourceForTest(items)]
    )

    try:
        response = client.get("/tasks?stat=overdue")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert "Просроченное в работе" in response.text
    assert "Осмотр ПС · ПС статистики" in response.text
    assert "Просроченное закрытое" not in response.text


def test_task_statistics_rejects_unknown_filter():
    user = _user(uuid7())
    client = _client(user, FakeTaskRepository([]), FakeAccessService(), FakeTaskService())

    try:
        response = client.get("/tasks?stat=unknown")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 400
