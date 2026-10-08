from datetime import date
from types import SimpleNamespace
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from uuid6 import uuid7

from app.application.objects.exceptions import (
    ObjectAccessDeniedError,
    ObjectNotFoundError,
)
from app.domain.enums import MaintenanceType, UserRole
from app.presentation.app import app
from app.presentation.auth.dependencies import get_current_user
from app.presentation.dependencies.services import (
    get_file_service,
    get_maintenance_service,
    get_object_service,
    get_task_service,
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
        self.archive_calls.append(
            {
                "file_id": file_id,
                "user_id": user_id,
            }
        )


class FakeTaskService:
    def __init__(self, can_issue_task=False):
        self.can_issue_task_value = can_issue_task
        self.calls = []

    async def can_issue_task(
        self,
        *,
        actor_id,
        urza_id,
        work_type=None,
    ):
        self.calls.append(
            {
                "actor_id": actor_id,
                "urza_id": urza_id,
                "work_type": work_type,
            }
        )
        return self.can_issue_task_value


class FakeMaintenanceService:
    def __init__(
        self,
        *,
        records=None,
        create_error=None,
    ):
        self.records = list(records or [])
        self.create_error = create_error
        self.calls = []

    async def get_by_urza(self, *, user_id, urza_id):
        self.calls.append(
            (
                "get_by_urza",
                {
                    "user_id": user_id,
                    "urza_id": urza_id,
                },
            )
        )
        return self.records

    async def create(self, **kwargs):
        self.calls.append(("create", kwargs))

        if self.create_error:
            raise self.create_error

        record = SimpleNamespace(
            id=uuid7(),
            urza_id=kwargs["urza_id"],
            maintenance_date=kwargs["maintenance_date"],
            maintenance_type=kwargs["maintenance_type"],
            detected_deviations=kwargs["detected_deviations"],
            measures_taken=kwargs["measures_taken"],
            historical_data=kwargs["historical_data"],
            signed_form_file_id=kwargs["signed_form_file_id"],
            scan_protocol_id=kwargs["scan_protocol_id"],
            editable_protocol_id=kwargs["editable_protocol_id"],
            task_id=kwargs["task_id"],
            created_by=kwargs["user_id"],
            updated_by=kwargs["user_id"],
        )

        self.records.insert(0, record)
        return record


def _user(system_user_id, role=UserRole.ENGINEER):
    return SimpleNamespace(
        id=system_user_id,
        role=role,
    )


def _setup(
    user,
    *,
    object_error=None,
    maintenance_service=None,
    file_service=None,
    task_service=None,
):
    object_service = FakeObjectService(object_error)

    if maintenance_service is None:
        maintenance_service = FakeMaintenanceService()

    if file_service is None:
        file_service = FakeFileService()

    if task_service is None:
        task_service = FakeTaskService()

    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_object_service] = (
        lambda: object_service
    )
    app.dependency_overrides[get_maintenance_service] = (
        lambda: maintenance_service
    )
    app.dependency_overrides[get_file_service] = (
        lambda: file_service
    )
    app.dependency_overrides[get_task_service] = (
        lambda: task_service
    )

    return (
        object_service,
        maintenance_service,
        file_service,
        task_service,
    )


def _post_data(**extra):
    data = {
        "maintenance_date": "2026-10-01",
        "maintenance_type": MaintenanceType.K.value,
        "detected_deviations": "Не выявлено",
        "measures_taken": "Не требуется",
    }
    data.update(extra)
    return data


def _cleanup(user):
    app.dependency_overrides.clear()


def test_maintenance_routes_are_registered_in_openapi():
    paths = app.openapi()["paths"]

    root = "/objects/urza/{urza_id}/maintenance"

    assert "get" in paths[root]
    assert "post" in paths[root]
    assert "get" in paths[f"{root}/new"]


def test_get_maintenance_list_returns_records(system_user_id):
    user = _user(system_user_id)
    urza_id = uuid7()

    records = [
        SimpleNamespace(
            id=uuid7(),
            maintenance_date=date(2026, 9, 17),
            maintenance_type=MaintenanceType.K,
            detected_deviations="Не выявлено",
            measures_taken="Не требуется",
            historical_data=False,
            signed_form_file_id=uuid7(),
            scan_protocol_id=uuid7(),
            editable_protocol_id=None,
            creator=SimpleNamespace(full_name="Иванов Иван"),
        )
    ]

    maintenance_service = FakeMaintenanceService(records=records)

    _setup(
        user,
        maintenance_service=maintenance_service,
    )

    try:
        response = TestClient(app).get(
            f"/objects/urza/{urza_id}/maintenance"
        )

        assert response.status_code == 200
        assert "17.09.2026" in response.text
        assert "К" in response.text
        assert "Не выявлено" in response.text
        assert "Не требуется" in response.text
        assert "Иванов Иван" in response.text
        assert "Добавить запись ТО" in response.text

        assert maintenance_service.calls == [
            (
                "get_by_urza",
                {
                    "user_id": user.id,
                    "urza_id": urza_id,
                },
            )
        ]
    finally:
        _cleanup(user)


def test_get_maintenance_list_returns_403_for_inaccessible_urza(
    system_user_id,
):
    user = _user(system_user_id)
    urza_id = uuid7()

    maintenance_service = FakeMaintenanceService()

    _setup(
        user,
        object_error=ObjectAccessDeniedError(),
        maintenance_service=maintenance_service,
    )

    try:
        response = TestClient(app).get(
            f"/objects/urza/{urza_id}/maintenance"
        )

        assert response.status_code == 403
        assert not maintenance_service.calls
    finally:
        _cleanup(user)


def test_get_maintenance_list_returns_404_for_missing_urza(
    system_user_id,
):
    user = _user(system_user_id)
    urza_id = uuid7()

    maintenance_service = FakeMaintenanceService()

    _setup(
        user,
        object_error=ObjectNotFoundError(),
        maintenance_service=maintenance_service,
    )

    try:
        response = TestClient(app).get(
            f"/objects/urza/{urza_id}/maintenance"
        )

        assert response.status_code == 404
        assert not maintenance_service.calls
    finally:
        _cleanup(user)


def test_get_new_maintenance_form_preserves_task_id(system_user_id):
    user = _user(system_user_id)
    urza_id = uuid7()
    task_id = uuid7()

    _setup(user)

    try:
        response = TestClient(app).get(
            f"/objects/urza/{urza_id}/maintenance/new"
            f"?task_id={task_id}"
        )

        assert response.status_code == 200

        assert 'name="maintenance_date"' in response.text
        assert 'name="maintenance_type"' in response.text
        assert 'name="historical_data"' in response.text
        assert 'name="detected_deviations"' in response.text
        assert 'name="measures_taken"' in response.text

        assert 'name="signed_form_file"' in response.text
        assert 'name="scan_protocol_file"' in response.text
        assert 'name="editable_protocol_file"' in response.text

        assert f'name="task_id" value="{task_id}"' in response.text

        assert 'name="signed_form_file"' in response.text
        assert "required" in response.text
    finally:
        _cleanup(user)


def test_create_maintenance_rejects_missing_signed_form(
    system_user_id,
):
    user = _user(system_user_id)
    urza_id = uuid7()

    files = FakeFileService()
    maintenance_service = FakeMaintenanceService()

    _setup(
        user,
        maintenance_service=maintenance_service,
        file_service=files,
    )

    try:
        response = TestClient(app).post(
            f"/objects/urza/{urza_id}/maintenance",
            data=_post_data(),
        )

        assert response.status_code == 422
        assert "подписан" in response.text.lower()

        assert not files.upload_calls
        assert not maintenance_service.calls
    finally:
        _cleanup(user)


def test_create_maintenance_direct_input_uploads_only_signed_form(
    system_user_id,
):
    user = _user(system_user_id)
    urza_id = uuid7()

    signed = SimpleNamespace(id=uuid7())

    files = FakeFileService(signed)
    maintenance_service = FakeMaintenanceService()

    _setup(
        user,
        maintenance_service=maintenance_service,
        file_service=files,
    )

    try:
        response = TestClient(app).post(
            f"/objects/urza/{urza_id}/maintenance",
            data=_post_data(
                maintenance_type=MaintenanceType.TK.value,
            ),
            files={
                "signed_form_file": (
                    "signed.pdf",
                    b"signed",
                    "application/pdf",
                ),
            },
        )

        assert response.status_code == 200

        assert len(files.upload_calls) == 1

        name, kwargs = maintenance_service.calls[0]

        assert name == "create"
        assert kwargs["signed_form_file_id"] == signed.id
        assert kwargs["scan_protocol_id"] is None
        assert kwargs["editable_protocol_id"] is None
        assert kwargs["task_id"] is None
    finally:
        _cleanup(user)


def test_create_maintenance_with_task_and_protocol_files(
    system_user_id,
):
    user = _user(system_user_id)
    urza_id = uuid7()
    task_id = uuid7()

    signed = SimpleNamespace(id=uuid7())
    scan = SimpleNamespace(id=uuid7())
    editable = SimpleNamespace(id=uuid7())

    files = FakeFileService(
        signed,
        scan,
        editable,
    )
    maintenance_service = FakeMaintenanceService()

    _setup(
        user,
        maintenance_service=maintenance_service,
        file_service=files,
    )

    try:
        response = TestClient(app).post(
            f"/objects/urza/{urza_id}/maintenance",
            data=_post_data(
                task_id=str(task_id),
                maintenance_type=MaintenanceType.K.value,
            ),
            files={
                "signed_form_file": (
                    "signed.pdf",
                    b"signed",
                    "application/pdf",
                ),
                "scan_protocol_file": (
                    "protocol.pdf",
                    b"protocol",
                    "application/pdf",
                ),
                "editable_protocol_file": (
                    "protocol.docx",
                    b"editable",
                    "application/vnd.openxmlformats-officedocument"
                    ".wordprocessingml.document",
                ),
            },
        )

        assert response.status_code == 200
        assert len(files.upload_calls) == 3

        name, kwargs = maintenance_service.calls[0]

        assert name == "create"
        assert kwargs["task_id"] == task_id
        assert kwargs["signed_form_file_id"] == signed.id
        assert kwargs["scan_protocol_id"] == scan.id
        assert kwargs["editable_protocol_id"] == editable.id
    finally:
        _cleanup(user)


@pytest.mark.parametrize(
    "maintenance_type",
    [
        MaintenanceType.TK,
        MaintenanceType.O,
        MaintenanceType.OSM,
    ],
)
def test_create_maintenance_special_types_do_not_require_protocol(
    system_user_id,
    maintenance_type,
):
    user = _user(system_user_id)
    urza_id = uuid7()

    signed = SimpleNamespace(id=uuid7())

    files = FakeFileService(signed)
    maintenance_service = FakeMaintenanceService()

    _setup(
        user,
        maintenance_service=maintenance_service,
        file_service=files,
    )

    try:
        response = TestClient(app).post(
            f"/objects/urza/{urza_id}/maintenance",
            data=_post_data(
                maintenance_type=maintenance_type.value,
            ),
            files={
                "signed_form_file": (
                    "signed.pdf",
                    b"signed",
                    "application/pdf",
                ),
            },
        )

        assert response.status_code == 200

        assert len(files.upload_calls) == 1

        name, kwargs = maintenance_service.calls[0]

        assert name == "create"
        assert kwargs["scan_protocol_id"] is None
        assert kwargs["editable_protocol_id"] is None
    finally:
        _cleanup(user)


def test_create_maintenance_rejects_inaccessible_urza_before_upload(
    system_user_id,
):
    user = _user(system_user_id)
    urza_id = uuid7()

    files = FakeFileService(
        SimpleNamespace(id=uuid7())
    )
    maintenance_service = FakeMaintenanceService()

    _setup(
        user,
        object_error=ObjectAccessDeniedError(),
        maintenance_service=maintenance_service,
        file_service=files,
    )

    try:
        response = TestClient(app).post(
            f"/objects/urza/{urza_id}/maintenance",
            data=_post_data(),
            files={
                "signed_form_file": (
                    "signed.pdf",
                    b"signed",
                    "application/pdf",
                ),
            },
        )

        assert response.status_code == 403
        assert not files.upload_calls
        assert not maintenance_service.calls
    finally:
        _cleanup(user)


def test_create_maintenance_archives_uploaded_files_after_service_error(
    system_user_id,
):
    user = _user(system_user_id)
    urza_id = uuid7()

    signed = SimpleNamespace(id=uuid7())
    scan = SimpleNamespace(id=uuid7())

    files = FakeFileService(
        signed,
        scan,
    )

    maintenance_service = FakeMaintenanceService(
        create_error=ValueError("требуется протокол")
    )

    _setup(
        user,
        maintenance_service=maintenance_service,
        file_service=files,
    )

    try:
        response = TestClient(app).post(
            f"/objects/urza/{urza_id}/maintenance",
            data=_post_data(
                maintenance_type=MaintenanceType.K.value,
            ),
            files={
                "signed_form_file": (
                    "signed.pdf",
                    b"signed",
                    "application/pdf",
                ),
                "scan_protocol_file": (
                    "protocol.pdf",
                    b"protocol",
                    "application/pdf",
                ),
            },
        )

        assert response.status_code == 400
        assert len(files.archive_calls) == 2
        assert {
            call["file_id"]
            for call in files.archive_calls
        } == {
            signed.id,
            scan.id,
        }
    finally:
        _cleanup(user)