from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from uuid6 import uuid7

from app.application.objects.exceptions import ObjectAccessDeniedError
from app.domain.enums import TaskStatus, UserRole
from app.presentation.app import app
from app.presentation.auth.dependencies import get_current_user
from app.presentation.dependencies.services import (
    get_file_service,
    get_inspection_task_repository,
    get_inspection_task_service,
    get_object_service,
    get_tree_service,
)


class FakeObjectService:
    def __init__(self, substation_id):
        self.substation_id = substation_id

    async def get_object(self, *, user_id, object_type, object_id):
        if object_type != "substation" or object_id != self.substation_id:
            raise ObjectAccessDeniedError
        return SimpleNamespace(id=object_id)


class FakeInspectionRepository:
    def __init__(self, task=None):
        self.task = task

    async def get_active_by_id(self, task_id):
        return self.task if self.task and self.task.id == task_id else None

    async def get_history(self, task_id):
        return []


class FakeTreeService:
    async def get_tree(self, *, user_id):
        return []


class FakeInspectionTaskService:
    def __init__(self, substation_id, assignees=(), validation_error=None, complete_error=None):
        self.substation_repository = SimpleNamespace(
            get_by_id=self._get_substation
        )
        self.user_repository = SimpleNamespace(
            get_active_inspection_assignees_by_enterprise=self._get_assignees
        )
        self.substation_id = substation_id
        self.assignees = list(assignees)
        self.validation_error = validation_error
        self.complete_error = complete_error
        self.calls = []

    async def _get_substation(self, substation_id):
        self.calls.append("get_substation")
        return SimpleNamespace(
            id=substation_id, enterprise_id=uuid7(), dispatch_name="ПС Тестовая"
        )

    async def _get_assignees(self, enterprise_id):
        self.calls.append("get_assignees")
        return self.assignees

    async def create_and_assign(self, *, substation_id, actor_id, assignee_id):
        self.calls.append("create")
        if assignee_id is not None:
            self.calls.append("assign")
        return SimpleNamespace(id=uuid7())

    async def validate_completion(self, task_id, *, actor_id, remarks):
        self.calls.append("validate_completion")
        if self.validation_error:
            raise self.validation_error

    async def complete(self, *args, **kwargs):
        if self.complete_error:
            raise self.complete_error


class FakeFileService:
    def __init__(self):
        self.upload_calls = []
        self.archive_calls = []

    async def upload(self, **kwargs):
        self.upload_calls.append(kwargs)
        return SimpleNamespace(id=uuid7())

    async def archive(self, **kwargs):
        self.archive_calls.append(kwargs)


def _install(user, substation_id, service, repository=None, file_service=None):
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_object_service] = lambda: FakeObjectService(substation_id)
    app.dependency_overrides[get_inspection_task_service] = lambda: service
    if repository is not None:
        app.dependency_overrides[get_inspection_task_repository] = lambda: repository
    if file_service is not None:
        app.dependency_overrides[get_file_service] = lambda: file_service
    app.dependency_overrides[get_tree_service] = lambda: FakeTreeService()


def test_invalid_assignee_is_rejected_before_inspection_task_creation():
    user = SimpleNamespace(id=uuid7(), role=UserRole.MANAGER)
    substation_id = uuid7()
    service = FakeInspectionTaskService(substation_id)
    _install(user, substation_id, service)
    try:
        response = TestClient(app).post(
            f"/objects/substation/{substation_id}/inspection-tasks",
            data={"assignee_id": str(uuid7())},
        )

        assert response.status_code == 400
        assert "create" not in service.calls
        assert service.calls == [
            "get_substation", "get_assignees", "get_substation", "get_assignees"
        ]
    finally:
        app.dependency_overrides.clear()


def test_inspection_task_can_be_created_without_assignee():
    user = SimpleNamespace(id=uuid7(), role=UserRole.MANAGER)
    substation_id = uuid7()
    service = FakeInspectionTaskService(substation_id)
    _install(user, substation_id, service)
    try:
        response = TestClient(app).post(
            f"/objects/substation/{substation_id}/inspection-tasks",
            data={},
            follow_redirects=False,
        )

        assert response.status_code == 303
        assert response.headers["location"].endswith("?tab=inspections") is False
        assert "/inspection-tasks/" in response.headers["location"]
        assert service.calls == ["create"]
    finally:
        app.dependency_overrides.clear()


def test_manager_can_open_inspection_assignment_form():
    user = SimpleNamespace(id=uuid7(), role=UserRole.MANAGER)
    substation_id = uuid7()
    engineer = SimpleNamespace(id=uuid7(), full_name="Инженер")
    service = FakeInspectionTaskService(substation_id, assignees=[engineer])
    _install(user, substation_id, service)
    try:
        response = TestClient(app).get(
            f"/objects/substation/{substation_id}/inspection-tasks/new"
        )
        assert response.status_code == 200
        assert "Выдать задание на осмотр" in response.text
        assert "ПС Тестовая" in response.text
        assert "Инженер" in response.text
        assert 'name="assignee_id"' in response.text
    finally:
        app.dependency_overrides.clear()


def test_invalid_completion_is_checked_before_files_are_uploaded():
    user = SimpleNamespace(id=uuid7(), role=UserRole.ENGINEER)
    substation_id, task_id = uuid7(), uuid7()
    task = SimpleNamespace(
        id=task_id,
        substation_id=substation_id,
        substation=SimpleNamespace(enterprise_id=uuid7(), dispatch_name="ПС"),
        created_by_user=None,
        assigned_to_user=None,
        assigned_to=user.id,
        status=TaskStatus.IN_PROGRESS,
        created_at=datetime.now(UTC),
        deadline_at=None,
        inspection=None,
    )
    service = FakeInspectionTaskService(
        substation_id, validation_error=ValueError("Недопустимый переход")
    )
    files = FakeFileService()
    _install(
        user,
        substation_id,
        service,
        repository=FakeInspectionRepository(task),
        file_service=files,
    )
    try:
        response = TestClient(app).post(
            f"/objects/substation/inspection-tasks/{task_id}/complete",
            data={"inspection_date": "2026-10-15", "remarks": "Проверено"},
            files={"scan_file": ("scan.pdf", b"scan", "application/pdf")},
        )

        assert response.status_code == 400
        assert "Недопустимый переход" in response.text
        assert "Проверено" in response.text
        assert service.calls == ["validate_completion"]
        assert files.upload_calls == []
    finally:
        app.dependency_overrides.clear()


def test_completion_failure_preserves_values_and_archives_uploaded_files():
    user = SimpleNamespace(id=uuid7(), role=UserRole.ENGINEER)
    substation_id, task_id = uuid7(), uuid7()
    task = SimpleNamespace(
        id=task_id,
        substation_id=substation_id,
        substation=SimpleNamespace(enterprise_id=uuid7(), dispatch_name="ПС"),
        created_by_user=None,
        assigned_to_user=None,
        assigned_to=user.id,
        status=TaskStatus.IN_PROGRESS,
        created_at=datetime.now(UTC),
        deadline_at=None,
        inspection=None,
    )
    service = FakeInspectionTaskService(
        substation_id, complete_error=ValueError("Состояние уже изменилось")
    )
    files = FakeFileService()
    _install(
        user,
        substation_id,
        service,
        repository=FakeInspectionRepository(task),
        file_service=files,
    )
    try:
        response = TestClient(app).post(
            f"/objects/substation/inspection-tasks/{task_id}/complete",
            data={"inspection_date": "2026-10-15", "remarks": "Введённые замечания"},
            files={"scan_file": ("scan.pdf", b"scan", "application/pdf")},
        )
        assert response.status_code == 400
        assert "Состояние уже изменилось" in response.text
        assert "Введённые замечания" in response.text
        assert len(files.archive_calls) == 1
    finally:
        app.dependency_overrides.clear()


@pytest.mark.parametrize(
    "role",
    [UserRole.ENGINEER, UserRole.ADMIN, UserRole.SUPERADMIN],
)
def test_non_manager_cannot_open_inspection_task_form(role):
    user = SimpleNamespace(id=uuid7(), role=role)
    substation_id = uuid7()
    service = FakeInspectionTaskService(substation_id)
    _install(user, substation_id, service)

    try:
        response = TestClient(app).get(
            f"/objects/substation/{substation_id}/inspection-tasks/new"
        )

        assert response.status_code == 403
        assert service.calls == []
    finally:
        app.dependency_overrides.clear()


@pytest.mark.parametrize(
    "role",
    [UserRole.ENGINEER, UserRole.ADMIN, UserRole.SUPERADMIN],
)
def test_non_manager_cannot_create_inspection_task(role):
    user = SimpleNamespace(id=uuid7(), role=role)
    substation_id = uuid7()
    service = FakeInspectionTaskService(substation_id)
    _install(user, substation_id, service)

    try:
        response = TestClient(app).post(
            f"/objects/substation/{substation_id}/inspection-tasks",
            data={},
        )

        assert response.status_code == 403
        assert service.calls == []
    finally:
        app.dependency_overrides.clear()


def test_user_without_substation_access_cannot_open_inspection_task():
    user = SimpleNamespace(id=uuid7(), role=UserRole.ENGINEER)
    substation_id, task_id = uuid7(), uuid7()
    task = SimpleNamespace(id=task_id, substation_id=substation_id)
    service = FakeInspectionTaskService(substation_id)
    repository = FakeInspectionRepository(task)

    # Разрешённая подстанция отличается от подстанции задания.
    _install(
        user,
        uuid7(),
        service,
        repository=repository,
    )

    try:
        response = TestClient(app).get(
            f"/objects/substation/inspection-tasks/{task_id}"
        )

        assert response.status_code == 403
        assert service.calls == []
    finally:
        app.dependency_overrides.clear()


def test_user_without_substation_access_cannot_complete_inspection_task():
    user = SimpleNamespace(id=uuid7(), role=UserRole.ENGINEER)
    substation_id, task_id = uuid7(), uuid7()
    task = SimpleNamespace(id=task_id, substation_id=substation_id)
    service = FakeInspectionTaskService(substation_id)
    repository = FakeInspectionRepository(task)
    files = FakeFileService()

    # Пользователь не имеет доступа к подстанции задания.
    _install(
        user,
        uuid7(),
        service,
        repository=repository,
        file_service=files,
    )

    try:
        response = TestClient(app).post(
            f"/objects/substation/inspection-tasks/{task_id}/complete",
            data={
                "inspection_date": "2026-10-15",
                "remarks": "Проверено",
            },
            files={
                "scan_file": (
                    "scan.pdf",
                    b"test file",
                    "application/pdf",
                )
            },
        )

        assert response.status_code == 403
        assert service.calls == []
        assert files.upload_calls == []
    finally:
        app.dependency_overrides.clear()
