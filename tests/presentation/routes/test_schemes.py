from datetime import date, datetime, timezone
from types import SimpleNamespace
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from uuid6 import uuid7

from app.application.objects.exceptions import (
    ObjectAccessDeniedError,
    ObjectNotFoundError,
)
from app.domain.enums import DocumentStatus, UserRole
from app.presentation.app import app
from app.presentation.auth.dependencies import get_current_user
from app.presentation.dependencies.services import (
    get_file_service,
    get_object_service,
    get_schema_service,
    get_task_service,

)


def _record(
    urza_id: UUID,
    status: DocumentStatus,
    *,
    deleted_at=None,
    scan_file_id=None,
    editable_file_id=None,
    signed_form_file_id=None,
    task_id=None,
):
    return SimpleNamespace(
        id=uuid7(),
        schema_form_id=uuid7(),
        schema_number="SC-01",
        schema_name="Схема защиты",
        change_description="Изменение схемы",
        change_justification="Обоснование изменения",
        upload_date=date(2026, 9, 1),
        status=status,
        creator=SimpleNamespace(full_name="Автор"),
        scan_file_id=scan_file_id,
        editable_file_id=editable_file_id,
        signed_form_file_id=signed_form_file_id or uuid7(),
        task_id=task_id,
        deleted_at=deleted_at,
        urza_id=urza_id,
    )


class FakeObjectService:
    def __init__(self, error=None):
        self.error = error
        self.calls = []

    async def get_object(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return SimpleNamespace(id=kwargs["object_id"])


class FakeFileService:
    def __init__(self, *files):
        self.files = list(files)
        self.upload_calls = []
        self.archive_calls = []

    async def upload(self, **kwargs):
        self.upload_calls.append(kwargs)
        return self.files.pop(0)

    async def archive(self, *, file_id, user_id):
        self.archive_calls.append({"file_id": file_id, "user_id": user_id})


class FakeTaskService:
    async def can_issue_task(
        self,
        *,
        actor_id,
        urza_id,
        work_type=None,
    ):
        return False


class FakeSchemaService:
    def __init__(
        self,
        urza_id,
        *,
        records=None,
        current=None,
        actions=None,
        errors=None,
    ):
        self.urza_id = urza_id
        self.records = list(records or [])
        self.current = current
        self.actions = actions or {}
        self.errors = errors or {}
        self.calls = []
        self.schema_form = SimpleNamespace(id=uuid7(), urza_id=urza_id)

    def _error(self, method):
        error = self.errors.get(method)
        if error:
            raise error

    async def get_details(self, user_id, urza_id):
        self._error("get_details")
        records = [record for record in self.records if record.deleted_at is None]
        return self.schema_form, records

    async def get_current(self, user_id, urza_id):
        self._error("get_current")
        return self.current

    async def get_records(self, user_id, urza_id):
        self._error("get_records")
        return [record for record in self.records if record.deleted_at is None]

    async def get_available_actions(self, user_id, record):
        if record.id in self.actions:
            return self.actions[record.id]
        if record.status is DocumentStatus.DRAFT:
            return {"edit", "submit"}
        if record.status is DocumentStatus.UNDER_REVIEW:
            return {"approve", "return"} if user_role(user_id) is UserRole.MANAGER else set()
        if record.status is DocumentStatus.APPROVED:
            return {"new_record"}
        return set()

    async def create(self, **kwargs):
        self.calls.append(("create", kwargs))
        self._error("create")
        record = _record(
            self.urza_id,
            self.errors.get("create_status", DocumentStatus.DRAFT),
            scan_file_id=kwargs["scan_file_id"],
            editable_file_id=kwargs["editable_file_id"],
            signed_form_file_id=kwargs["signed_form_file_id"],
            task_id=kwargs["task_id"],
        )
        for key in (
            "schema_number", "schema_name", "change_description",
            "change_justification", "upload_date",
        ):
            setattr(record, key, kwargs[key])
        self.records.insert(0, record)
        if record.status is DocumentStatus.APPROVED:
            self.current = record
        return record

    async def validate_task_for_result(self, **kwargs):
        self.calls.append(("validate_task_for_result", kwargs))
        self._error("validate_task_for_result")
        return SimpleNamespace(id=kwargs["task_id"])

    async def update(self, **kwargs):
        self.calls.append(("update", kwargs))
        self._error("update")
        record = next(item for item in self.records if item.id == kwargs["record_id"])
        for field in (
            "schema_number", "schema_name", "change_description",
            "change_justification", "upload_date", "signed_form_file_id",
            "scan_file_id", "editable_file_id",
        ):
            if kwargs[field] is not None or field in {
                "scan_file_id", "editable_file_id"
            }:
                setattr(record, field, kwargs[field])
        return record

    async def submit_for_review(self, **kwargs):
        return await self._transition("submit_for_review", DocumentStatus.UNDER_REVIEW, kwargs)

    async def approve(self, **kwargs):
        return await self._transition("approve", DocumentStatus.APPROVED, kwargs)

    async def return_to_draft(self, **kwargs):
        return await self._transition("return_to_draft", DocumentStatus.DRAFT, kwargs)

    async def _transition(self, method, new_status, kwargs):
        self.calls.append((method, kwargs))
        self._error(method)
        record = next(item for item in self.records if item.id == kwargs["record_id"])
        record.status = new_status
        if new_status is DocumentStatus.APPROVED:
            self.current = record
        elif self.current is record:
            self.current = None
        return record

    async def delete(self, **kwargs):
        self.calls.append(("delete", kwargs))
        self._error("delete")
        record = next(item for item in self.records if item.id == kwargs["record_id"])
        record.deleted_at = datetime.now(timezone.utc)
        if self.current is record:
            self.current = None


_roles_by_user: dict[UUID, UserRole] = {}


def user_role(user_id):
    return _roles_by_user.get(user_id, UserRole.ENGINEER)


def _setup(
    user,
    urza_id,
    schema_service,
    *,
    file_service=None,
    object_error=None,
):
    object_service = FakeObjectService(object_error)
    task_service = FakeTaskService()

    _roles_by_user[user.id] = user.role
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_object_service] = lambda: object_service
    app.dependency_overrides[get_schema_service] = lambda: schema_service
    app.dependency_overrides[get_task_service] = lambda: task_service

    if file_service is not None:
        app.dependency_overrides[get_file_service] = lambda: file_service

    return object_service

def _user(system_user_id, role=UserRole.ENGINEER):
    return SimpleNamespace(id=system_user_id, role=role)


def _post_data(**extra):
    data = {
        "schema_number": "SC-02",
        "schema_name": "Новая схема защиты",
        "change_description": "Обновлены цепи",
        "change_justification": "Изменение оборудования",
        "upload_date": "2026-10-01",
    }
    data.update(extra)
    return data


def test_schemes_routes_are_registered_in_openapi():
    paths = app.openapi()["paths"]
    root = "/objects/urza/{urza_id}/schemas"
    assert "get" in paths[root]
    assert "post" in paths[root]
    assert "get" in paths[f"{root}/new"]
    assert "get" in paths[f"{root}/{{record_id}}/edit"]
    assert "post" in paths[f"{root}/{{record_id}}"]
    for action in ("submit", "approve", "return", "delete"):
        assert "post" in paths[f"{root}/{{record_id}}/{action}"]


def test_get_schemes_list_shows_status_current_files_and_hides_deleted(system_user_id):
    user = _user(system_user_id)
    urza_id = uuid7()
    current = _record(
        urza_id,
        DocumentStatus.APPROVED,
        scan_file_id=uuid7(),
        editable_file_id=uuid7(),
    )
    draft = _record(urza_id, DocumentStatus.DRAFT)
    deleted = _record(
        urza_id,
        DocumentStatus.APPROVED,
        deleted_at=datetime.now(timezone.utc),
    )
    service = FakeSchemaService(
        urza_id,
        records=[draft, current, deleted],
        current=current,
        actions={draft.id: {"edit", "submit"}, current.id: {"new_record"}},
    )
    _setup(user, urza_id, service)
    try:
        response = TestClient(app).get(f"/objects/urza/{urza_id}/schemas")
        assert response.status_code == 200
        assert "Черновик" in response.text
        assert "Утверждено" in response.text
        assert "Текущая" in response.text
        assert "Изменить" in response.text
        assert "Направить на согласование" in response.text
        assert "Новое изменение" in response.text
        assert str(deleted.id) not in response.text
        assert "/files/None/" not in response.text
    finally:
        app.dependency_overrides.clear()
        _roles_by_user.pop(user.id, None)


def test_schemes_list_returns_access_error(system_user_id):
    user = _user(system_user_id)
    urza_id = uuid7()
    service = FakeSchemaService(urza_id)
    _setup(
        user,
        urza_id,
        service,
        object_error=ObjectAccessDeniedError(),
    )
    try:
        response = TestClient(app).get(f"/objects/urza/{urza_id}/schemas")
        assert response.status_code == 403
    finally:
        app.dependency_overrides.clear()
        _roles_by_user.pop(user.id, None)


def test_get_new_schema_form_requires_signed_file_and_preserves_task_id(system_user_id):
    user = _user(system_user_id)
    urza_id, task_id = uuid7(), uuid7()
    service = FakeSchemaService(urza_id)
    _setup(user, urza_id, service)
    try:
        response = TestClient(app).get(
            f"/objects/urza/{urza_id}/schemas/new?task_id={task_id}"
        )
        assert response.status_code == 200
        assert 'name="signed_form_file"' in response.text
        assert 'id="signed_form_file"' in response.text
        assert 'name="scan_file"' in response.text
        assert 'name="editable_file"' in response.text
        assert f'name="task_id" value="{task_id}"' in response.text
        assert "required" in response.text
        assert service.calls == [
            (
                "validate_task_for_result",
                {"user_id": user.id, "urza_id": urza_id, "task_id": task_id},
            )
        ]
    finally:
        app.dependency_overrides.clear()
        _roles_by_user.pop(user.id, None)


def test_create_schema_direct_input_uploads_only_required_signed_file(system_user_id):
    user = _user(system_user_id)
    urza_id = uuid7()
    signed = SimpleNamespace(id=uuid7())
    files = FakeFileService(signed)
    service = FakeSchemaService(urza_id)
    _setup(user, urza_id, service, file_service=files)
    try:
        response = TestClient(app).post(
            f"/objects/urza/{urza_id}/schemas",
            data=_post_data(),
            files={"signed_form_file": ("signed.pdf", b"signed", "application/pdf")},
        )
        assert response.status_code == 200
        assert len(files.upload_calls) == 1
        name, kwargs = service.calls[0]
        assert name == "create"
        assert kwargs["signed_form_file_id"] == signed.id
        assert kwargs["scan_file_id"] is None
        assert kwargs["editable_file_id"] is None
        assert kwargs["task_id"] is None
    finally:
        app.dependency_overrides.clear()
        _roles_by_user.pop(user.id, None)


def test_create_schema_rejects_missing_signed_file(system_user_id):
    user = _user(system_user_id)
    urza_id = uuid7()
    files = FakeFileService()
    service = FakeSchemaService(urza_id)
    _setup(user, urza_id, service, file_service=files)
    try:
        response = TestClient(app).post(
            f"/objects/urza/{urza_id}/schemas",
            data=_post_data(),
        )
        assert response.status_code == 422
        assert "Загрузите подписанный формуляр" in response.text
        assert not files.upload_calls
        assert not service.calls
    finally:
        app.dependency_overrides.clear()
        _roles_by_user.pop(user.id, None)


def test_create_schema_rejects_inaccessible_urza_before_upload(system_user_id):
    user = _user(system_user_id)
    urza_id = uuid7()
    files = FakeFileService(SimpleNamespace(id=uuid7()))
    service = FakeSchemaService(urza_id)
    _setup(
        user,
        urza_id,
        service,
        file_service=files,
        object_error=ObjectAccessDeniedError(),
    )
    try:
        response = TestClient(app).post(
            f"/objects/urza/{urza_id}/schemas",
            data=_post_data(),
            files={"signed_form_file": ("signed.pdf", b"signed", "application/pdf")},
        )
        assert response.status_code == 403
        assert not files.upload_calls
    finally:
        app.dependency_overrides.clear()
        _roles_by_user.pop(user.id, None)


def test_create_task_linked_schema_passes_task_id_and_files_to_service(system_user_id):
    user = _user(system_user_id)
    urza_id, task_id = uuid7(), uuid7()
    signed, scan = SimpleNamespace(id=uuid7()), SimpleNamespace(id=uuid7())
    files = FakeFileService(signed, scan)
    service = FakeSchemaService(urza_id)
    _setup(user, urza_id, service, file_service=files)
    try:
        response = TestClient(app).post(
            f"/objects/urza/{urza_id}/schemas",
            data=_post_data(task_id=str(task_id)),
            files={
                "signed_form_file": ("signed.pdf", b"signed", "application/pdf"),
                "scan_file": ("scan.pdf", b"scan", "application/pdf"),
            },
        )
        assert response.status_code == 200
        kwargs = service.calls[0][1]
        assert kwargs["task_id"] == task_id
        assert kwargs["scan_file_id"] == scan.id
    finally:
        app.dependency_overrides.clear()
        _roles_by_user.pop(user.id, None)


def test_get_new_schema_form_rejects_invalid_task_context(system_user_id):
    user = _user(system_user_id)
    urza_id, task_id = uuid7(), uuid7()
    service = FakeSchemaService(
        urza_id,
        errors={
            "validate_task_for_result": ValueError("Задача относится к другой URZA.")
        },
    )
    _setup(user, urza_id, service)
    try:
        response = TestClient(app).get(
            f"/objects/urza/{urza_id}/schemas/new?task_id={task_id}"
        )
        assert response.status_code == 400
        assert "другой URZA" in response.text
    finally:
        app.dependency_overrides.clear()
        _roles_by_user.pop(user.id, None)


def test_post_schema_create_reports_tampered_task_context_rejection(system_user_id):
    user = _user(system_user_id)
    urza_id, task_id = uuid7(), uuid7()
    signed = SimpleNamespace(id=uuid7())
    files = FakeFileService(signed)
    service = FakeSchemaService(
        urza_id,
        errors={"create": PermissionError("Задача назначена другому исполнителю.")},
    )
    _setup(user, urza_id, service, file_service=files)
    try:
        response = TestClient(app).post(
            f"/objects/urza/{urza_id}/schemas",
            data=_post_data(task_id=str(task_id)),
            files={"signed_form_file": ("signed.pdf", b"signed", "application/pdf")},
        )
        assert response.status_code == 403
        assert "другому исполнителю" in response.text
    finally:
        app.dependency_overrides.clear()
        _roles_by_user.pop(user.id, None)


def test_create_schema_archives_uploaded_files_after_service_error(system_user_id):
    user = _user(system_user_id)
    urza_id = uuid7()
    signed, scan = SimpleNamespace(id=uuid7()), SimpleNamespace(id=uuid7())
    files = FakeFileService(signed, scan)
    service = FakeSchemaService(
        urza_id,
        errors={"create": ValueError("заданию нужен скан или редактируемый файл")},
    )
    _setup(user, urza_id, service, file_service=files)
    try:
        response = TestClient(app).post(
            f"/objects/urza/{urza_id}/schemas",
            data=_post_data(task_id=str(uuid7())),
            files={
                "signed_form_file": ("signed.pdf", b"signed", "application/pdf"),
                "scan_file": ("scan.pdf", b"scan", "application/pdf"),
            },
        )
        assert response.status_code == 400
        assert len(files.archive_calls) == 2
    finally:
        app.dependency_overrides.clear()
        _roles_by_user.pop(user.id, None)


def test_get_edit_schema_draft_shows_fields_and_existing_files(system_user_id):
    user = _user(system_user_id)
    urza_id = uuid7()
    scan_id, editable_id, signed_id = uuid7(), uuid7(), uuid7()
    record = _record(
        urza_id,
        DocumentStatus.DRAFT,
        scan_file_id=scan_id,
        editable_file_id=editable_id,
        signed_form_file_id=signed_id,
    )
    service = FakeSchemaService(urza_id, records=[record])
    _setup(user, urza_id, service)
    try:
        response = TestClient(app).get(
            f"/objects/urza/{urza_id}/schemas/{record.id}/edit"
        )
        assert response.status_code == 200
        assert "Изменение черновика схемы" in response.text
        assert "Схема защиты" in response.text
        assert "Изменение схемы" in response.text
        for file_id in (scan_id, editable_id, signed_id):
            assert f"/files/{file_id}/view" in response.text
            assert f"/files/{file_id}/download" in response.text
    finally:
        app.dependency_overrides.clear()
        _roles_by_user.pop(user.id, None)


@pytest.mark.parametrize(
    "document_status", [DocumentStatus.APPROVED, DocumentStatus.UNDER_REVIEW]
)
def test_edit_routes_reject_non_draft(system_user_id, document_status):
    user = _user(system_user_id)
    urza_id = uuid7()
    record = _record(urza_id, document_status)
    service = FakeSchemaService(urza_id, records=[record], actions={record.id: set()})
    files = FakeFileService()
    _setup(user, urza_id, service, file_service=files)
    try:
        client = TestClient(app)
        get_response = client.get(
            f"/objects/urza/{urza_id}/schemas/{record.id}/edit"
        )
        post_response = client.post(
            f"/objects/urza/{urza_id}/schemas/{record.id}",
            data=_post_data(),
        )
        assert get_response.status_code == 403
        assert post_response.status_code == 403
        assert not service.calls
    finally:
        app.dependency_overrides.clear()
        _roles_by_user.pop(user.id, None)


def test_update_draft_without_new_files_preserves_existing_files(system_user_id):
    user = _user(system_user_id)
    urza_id = uuid7()
    scan_id, editable_id, signed_id = uuid7(), uuid7(), uuid7()
    record = _record(
        urza_id,
        DocumentStatus.DRAFT,
        scan_file_id=scan_id,
        editable_file_id=editable_id,
        signed_form_file_id=signed_id,
    )
    service = FakeSchemaService(urza_id, records=[record])
    files = FakeFileService()
    _setup(user, urza_id, service, file_service=files)
    try:
        response = TestClient(app).post(
            f"/objects/urza/{urza_id}/schemas/{record.id}",
            data=_post_data(),
        )
        assert response.status_code == 200
        kwargs = service.calls[0][1]
        assert kwargs["signed_form_file_id"] is None
        assert kwargs["scan_file_id"] == scan_id
        assert kwargs["editable_file_id"] == editable_id
        assert not files.upload_calls
        assert not files.archive_calls
    finally:
        app.dependency_overrides.clear()
        _roles_by_user.pop(user.id, None)


def test_update_draft_replaces_file_and_archives_old_after_save(system_user_id):
    user = _user(system_user_id)
    urza_id = uuid7()
    old_scan, new_scan = uuid7(), SimpleNamespace(id=uuid7())
    signed_id = uuid7()
    record = _record(
        urza_id,
        DocumentStatus.DRAFT,
        scan_file_id=old_scan,
        signed_form_file_id=signed_id,
    )
    service = FakeSchemaService(urza_id, records=[record])
    files = FakeFileService(new_scan)
    _setup(user, urza_id, service, file_service=files)
    try:
        response = TestClient(app).post(
            f"/objects/urza/{urza_id}/schemas/{record.id}",
            data=_post_data(),
            files={"scan_file": ("new-scan.pdf", b"scan", "application/pdf")},
        )
        assert response.status_code == 200
        assert service.calls[0][1]["scan_file_id"] == new_scan.id
        assert files.archive_calls == [{"file_id": old_scan, "user_id": user.id}]
    finally:
        app.dependency_overrides.clear()
        _roles_by_user.pop(user.id, None)


@pytest.mark.parametrize(
    ("action", "initial", "expected", "method", "role"),
    [
        ("submit", DocumentStatus.DRAFT, DocumentStatus.UNDER_REVIEW, "submit_for_review", UserRole.ENGINEER),
        ("approve", DocumentStatus.UNDER_REVIEW, DocumentStatus.APPROVED, "approve", UserRole.MANAGER),
        ("return", DocumentStatus.UNDER_REVIEW, DocumentStatus.DRAFT, "return_to_draft", UserRole.MANAGER),
    ],
)


def test_schema_workflow_routes(system_user_id, action, initial, expected, method, role):
    user = _user(system_user_id, role)
    urza_id = uuid7()
    record = _record(urza_id, initial)
    service = FakeSchemaService(urza_id, records=[record])
    _setup(user, urza_id, service)
    try:
        response = TestClient(app).post(
            f"/objects/urza/{urza_id}/schemas/{record.id}/{action}"
        )
        assert response.status_code == 200
        assert record.status is expected
        assert any(name == method for name, _ in service.calls)
        assert expected.label in response.text
    finally:
        app.dependency_overrides.clear()
        _roles_by_user.pop(user.id, None)


def test_schema_workflow_access_error_is_403(system_user_id):
    user = _user(system_user_id, UserRole.MANAGER)
    urza_id = uuid7()
    record = _record(urza_id, DocumentStatus.UNDER_REVIEW)
    service = FakeSchemaService(
        urza_id,
        records=[record],
        errors={"approve": PermissionError("Manager не отвечает за URZA.")},
    )
    _setup(user, urza_id, service)
    try:
        response = TestClient(app).post(
            f"/objects/urza/{urza_id}/schemas/{record.id}/approve"
        )
        assert response.status_code == 403
        assert "не отвечает" in response.json()["detail"]
    finally:
        app.dependency_overrides.clear()
        _roles_by_user.pop(user.id, None)


@pytest.mark.parametrize("role", [UserRole.ADMIN, UserRole.SUPERADMIN])
def test_schema_delete_soft_deletes_and_hides_record(system_user_id, role):
    user = _user(system_user_id, role)
    urza_id = uuid7()
    record = _record(urza_id, DocumentStatus.APPROVED)
    service = FakeSchemaService(urza_id, records=[record], current=record)
    _setup(user, urza_id, service)
    try:
        response = TestClient(app).post(
            f"/objects/urza/{urza_id}/schemas/{record.id}/delete"
        )
        assert response.status_code == 200
        assert record.deleted_at is not None
        assert str(record.id) not in response.text
    finally:
        app.dependency_overrides.clear()
        _roles_by_user.pop(user.id, None)


@pytest.mark.parametrize("role", [UserRole.ENGINEER, UserRole.MANAGER])
def test_schema_delete_denies_engineer_and_manager(system_user_id, role):
    user = _user(system_user_id, role)
    urza_id = uuid7()
    record = _record(urza_id, DocumentStatus.APPROVED)
    service = FakeSchemaService(
        urza_id,
        records=[record],
        errors={"delete": PermissionError("Удаление запрещено")},
    )
    _setup(user, urza_id, service)
    try:
        response = TestClient(app).post(
            f"/objects/urza/{urza_id}/schemas/{record.id}/delete"
        )
        assert response.status_code == 403
        assert record.deleted_at is None
    finally:
        app.dependency_overrides.clear()
        _roles_by_user.pop(user.id, None)
