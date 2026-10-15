from types import SimpleNamespace

from fastapi.testclient import TestClient
from uuid6 import uuid7

from app.application.objects.exceptions import ObjectAccessDeniedError
from app.domain.enums import UserRole
from app.presentation.app import app
from app.presentation.auth.dependencies import get_current_user
from app.presentation.dependencies.services import (
    get_file_service,
    get_inspection_task_repository,
    get_inspection_task_service,
    get_object_service,
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


class FakeInspectionTaskService:
    def __init__(self, substation_id, assignees=(), validation_error=None):
        self.substation_repository = SimpleNamespace(
            get_by_id=self._get_substation
        )
        self.user_repository = SimpleNamespace(
            get_active_inspection_assignees_by_enterprise=self._get_assignees
        )
        self.substation_id = substation_id
        self.assignees = list(assignees)
        self.validation_error = validation_error
        self.calls = []

    async def _get_substation(self, substation_id):
        self.calls.append("get_substation")
        return SimpleNamespace(id=substation_id, enterprise_id=uuid7())

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


class FakeFileService:
    def __init__(self):
        self.upload_calls = []

    async def upload(self, **kwargs):
        self.upload_calls.append(kwargs)
        return SimpleNamespace(id=uuid7())


def _install(user, substation_id, service, repository=None, file_service=None):
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_object_service] = lambda: FakeObjectService(substation_id)
    app.dependency_overrides[get_inspection_task_service] = lambda: service
    if repository is not None:
        app.dependency_overrides[get_inspection_task_repository] = lambda: repository
    if file_service is not None:
        app.dependency_overrides[get_file_service] = lambda: file_service


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
        assert service.calls == ["get_substation", "get_assignees"]
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
        assert service.calls == ["create"]
    finally:
        app.dependency_overrides.clear()


def test_invalid_completion_is_checked_before_files_are_uploaded():
    user = SimpleNamespace(id=uuid7(), role=UserRole.ENGINEER)
    substation_id, task_id = uuid7(), uuid7()
    task = SimpleNamespace(id=task_id, substation_id=substation_id)
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
        assert service.calls == ["validate_completion"]
        assert files.upload_calls == []
    finally:
        app.dependency_overrides.clear()
