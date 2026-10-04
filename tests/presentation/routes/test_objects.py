from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import UUID
from types import SimpleNamespace

from fastapi.testclient import TestClient
import pytest
from uuid6 import uuid7


from app.domain.program import Program
from app.domain.file import File
from app.domain.rza_settings import SettingsForm
from app.domain.settings_record import SettingsRecord

from app.application.connections.schemas import ConnectionListItem
from app.application.objects.exceptions import (
    ObjectAccessDeniedError,
    ObjectNotFoundError,
)
from app.application.objects.schemas import SelectedObject
from app.application.substations.schemas import SubstationDetails
from app.domain.enums import (
    AccessCategory,
    DocumentStatus,
    HighestVoltage,
    OperationalCurrentType,
    ProgramType,
    UserRole,
)
from app.domain.inspection import Inspection
from app.domain.user import User
from app.presentation.app import app
from app.presentation.auth.dependencies import get_current_user
from app.presentation.dependencies.services import (
    get_connection_service,
    get_inspection_service,
    get_object_service,
    get_program_service,
    get_settings_service,
    get_substation_service,
    get_file_service,
    get_urza_instruction_service,
)


class FakeSubstationService:
    async def get_details(self, substation_id: UUID) -> SubstationDetails:
        return SubstationDetails(
            id=substation_id,
            dispatch_name="ПС Центральная",
            highest_voltage=HighestVoltage.KV_110,
            sap_code="SAP-001",
            asureo_code="ASUREO-001",
            address="г. Екатеринбург",
            latitude=Decimal("56.838900"),
            longitude=Decimal("60.605700"),
            operational_current_type=OperationalCurrentType.PERMANENT,
        )


class FakeConnectionService:
    def __init__(
        self,
        connections: list[ConnectionListItem] | None = None,
    ) -> None:
        self.connections = connections or []

    async def get_by_substation_id(
        self,
        substation_id: UUID,
    ) -> list[ConnectionListItem]:
        return self.connections


class FakeInspectionService:
    def __init__(
        self,
        inspections: list[Inspection] | None = None,
    ) -> None:
        self.inspections = inspections or []

    async def get_by_substation_id(
        self,
        substation_id: UUID,
    ) -> list[Inspection]:
        return self.inspections


class FakeFileService:
    def __init__(self, file: File) -> None:
        self.file = file
        self.upload_calls: list[dict] = []
        self.archive_calls: list[dict] = []

    async def upload(
        self,
        *,
        actor_id: UUID,
        content: bytes,
        original_name: str,
        display_name: str,
        extension: str,
        mime_type: str,
    ) -> File:
        self.upload_calls.append(
            {
                "actor_id": actor_id,
                "content": content,
                "original_name": original_name,
                "display_name": display_name,
                "extension": extension,
                "mime_type": mime_type,
            }
        )
        return self.file

    async def archive(self, *, file_id: UUID, user_id: UUID) -> File:
        self.archive_calls.append({"file_id": file_id, "user_id": user_id})
        return self.file


class FakeSettingsService:
    def __init__(
        self,
        *,
        records=None,
        current_approved=None,
        actions=None,
        error_by_method=None,
        create_status=DocumentStatus.DRAFT,
    ):
        self.records = records or []
        self.current_approved = current_approved
        self.actions = actions or {}
        self.error_by_method = error_by_method or {}
        self.create_status = create_status
        self.calls = []
        self.settings_form = None

    async def get_details(self, user_id, urza_id):
        records = [record for record in self.records if record.deleted_at is None]
        return self.settings_form, records

    async def get_current_approved(self, user_id, urza_id):
        return self.current_approved

    async def get_available_actions(self, user_id, record):
        return self.actions.get(record.id, set())

    async def create_record(self, **kwargs):
        self.calls.append(("create_record", kwargs))
        error = self.error_by_method.get("create_record")
        if error:
            raise error
        record = SimpleNamespace(
            id=uuid7(),
            settings_form_id=uuid7(),
            change_date=kwargs["change_date"],
            parameter_name=kwargs["parameter_name"],
            initial_setting=kwargs["initial_setting"],
            new_setting=kwargs["new_setting"],
            change_reason=kwargs["change_reason"],
            status=self.create_status,
            signed_form_file_id=kwargs["signed_form_file_id"],
            creator=SimpleNamespace(full_name="Автор"),
            deleted_at=None,
        )
        self.records.insert(0, record)
        return record

    async def update_draft(self, **kwargs):
        self.calls.append(("update_draft", kwargs))
        error = self.error_by_method.get("update_draft")
        if error:
            raise error
        record = next(record for record in self.records if record.id == kwargs["record_id"])
        for field in (
            "change_date", "parameter_name", "initial_setting",
            "new_setting", "change_reason",
        ):
            setattr(record, field, kwargs[field])
        if kwargs["signed_form_file_id"] is not None:
            record.signed_form_file_id = kwargs["signed_form_file_id"]
        return record

    async def submit_for_review(self, **kwargs):
        return await self._transition("submit_for_review", kwargs, DocumentStatus.UNDER_REVIEW)

    async def approve(self, **kwargs):
        return await self._transition("approve", kwargs, DocumentStatus.APPROVED)

    async def return_to_draft(self, **kwargs):
        return await self._transition("return_to_draft", kwargs, DocumentStatus.DRAFT)

    async def _transition(self, name, kwargs, new_status):
        self.calls.append((name, kwargs))
        error = self.error_by_method.get(name)
        if error:
            raise error
        record = next(record for record in self.records if record.id == kwargs["record_id"])
        record.status = new_status
        return record

    async def delete_record(self, **kwargs):
        self.calls.append(("delete_record", kwargs))
        error = self.error_by_method.get("delete_record")
        if error:
            raise error
        record = next(record for record in self.records if record.id == kwargs["record_id"])
        record.deleted_at = datetime.now(timezone.utc)


def override_settings_service(service: FakeSettingsService):
    def dependency():
        return service
    return dependency

class FakeProgramService:
    def __init__(
        self,
        programs: list[Program] | None = None,
        actions: dict[UUID, set[str]] | None = None,
        error: Exception | None = None,
    ) -> None:
        self.programs = programs or []
        self.actions = actions or {}
        self.error = error

    async def get_by_urza(
        self,
        user_id: UUID,
        urza_id: UUID,
    ) -> list[Program]:
        if self.error is not None:
            raise self.error

        return self.programs

    async def get_available_actions(
        self,
        user_id: UUID,
        program: Program,
    ) -> set[str]:
        return self.actions.get(program.id, set())

    async def create(
            self,
            *,
            user_id: UUID,
            urza_id: UUID,
            program_type: ProgramType,
            program_number: str,
            scan_file_id: UUID,
            editable_file_id: UUID | None = None,
    ):
        program = Program(
            id=uuid7(),
            urza_id=urza_id,
            program_type=program_type,
            program_number=program_number,
            status=DocumentStatus.DRAFT,
            scan_file_id=scan_file_id,
            editable_file_id=editable_file_id,
            created_by=user_id,
            updated_by=user_id,
            created_at=datetime(2026, 9, 30, tzinfo=timezone.utc),
        )

        self.programs.append(program)

        return program

    async def submit_for_review(
        self,
        user_id: UUID,
        program_id: UUID,
        urza_id: UUID,
    ) -> Program:
        if self.error is not None:
            raise self.error

        program = next(
            program for program in self.programs
            if program.id == program_id
        )
        program.status = DocumentStatus.UNDER_REVIEW
        return program

    async def approve(
        self,
        user_id: UUID,
        program_id: UUID,
        urza_id: UUID,
    ) -> Program:
        if self.error is not None:
            raise self.error

        program = next(
            program for program in self.programs
            if program.id == program_id
        )
        program.status = DocumentStatus.APPROVED
        return program

    async def return_to_draft(
        self,
        user_id: UUID,
        program_id: UUID,
        urza_id: UUID,
    ) -> Program:
        if self.error is not None:
            raise self.error

        program = next(
            program for program in self.programs
            if program.id == program_id
        )
        program.status = DocumentStatus.DRAFT
        return program


def make_user(system_user_id) -> User:
    return User(
        id=uuid7(),
        full_name="Тестовый пользователь",
        role=UserRole.ENGINEER,
        email="test@example.com",
        password_hash="hash",
        access_category=AccessCategory.IV,
        active=True,
        created_by=system_user_id,
        updated_by=system_user_id,
    )


class FakeObjectService:
    def __init__(
        self,
        result: SelectedObject | None = None,
        error: Exception | None = None,
    ) -> None:
        self.result = result
        self.error = error

    async def get_object(
        self,
        user_id: UUID,
        object_type: str,
        object_id: UUID,
    ) -> SelectedObject:
        if self.error is not None:
            raise self.error

        assert self.result is not None
        return self.result


def override_user(user: User):
    async def dependency() -> User:
        return user

    return dependency


def override_object_service(service: FakeObjectService):
    def dependency() -> FakeObjectService:
        return service

    return dependency


def override_substation_service(service: FakeSubstationService):
    def dependency() -> FakeSubstationService:
        return service

    return dependency


def override_connection_service(service: FakeConnectionService):
    def dependency() -> FakeConnectionService:
        return service

    return dependency


def override_inspection_service(service: FakeInspectionService):
    def dependency() -> FakeInspectionService:
        return service

    return dependency


def override_program_service(service: FakeProgramService):
    def dependency() -> FakeProgramService:
        return service

    return dependency


class FakeURZAInstructionService:
    def __init__(self):
        self.instruction = None
        self.version = None
        self.calls = []

    async def get_by_urza(self, user_id, urza_id):
        return self.instruction

    async def get_versions(self, user_id, urza_id):
        return [self.version] if self.version else []

    async def get_current_version(self, user_id, urza_id):
        return self.version if self.version and self.version.status is DocumentStatus.APPROVED else None

    async def get_version_by_id(self, user_id, version_id):
        return self.version if self.version and self.version.id == version_id else None

    async def get_available_actions(self, user_id, version):
        return {"submit", "approve", "return", "new_version"}

    async def create(self, **kwargs):
        self.calls.append(("create", kwargs))

    async def create_version(self, **kwargs):
        self.calls.append(("create_version", kwargs))
        return self.version

    async def submit_for_review(self, *args):
        self.calls.append(("submit", args))

    async def approve(self, *args):
        self.calls.append(("approve", args))

    async def return_to_draft(self, *args):
        self.calls.append(("return", args))


def override_urza_instruction_service(service):
    def dependency():
        return service
    return dependency


def settings_record(
    urza_id: UUID,
    status: DocumentStatus,
    *,
    record_id: UUID | None = None,
    file_id: UUID | None = None,
    deleted_at=None,
):
    return SimpleNamespace(
        id=record_id or uuid7(),
        settings_form_id=uuid7(),
        urza_id=urza_id,
        change_date=date(2026, 9, 1),
        parameter_name="Ток срабатывания",
        initial_setting="1.0 A",
        new_setting="1.2 A",
        change_reason="Корректировка уставки",
        status=status,
        signed_form_file_id=file_id or uuid7(),
        creator=SimpleNamespace(full_name="Автор"),
        deleted_at=deleted_at,
    )


def settings_file(file_id: UUID, filename="signed.pdf") -> File:
    return File(
        id=file_id,
        s3_key=f"files/{filename}",
        original_name=filename,
        display_name=filename,
        extension=".pdf",
        size=4,
        mime_type="application/pdf",
        uploaded_at=datetime(2026, 9, 30, tzinfo=timezone.utc),
        created_by=uuid7(),
        updated_by=uuid7(),
    )


def set_settings_dependencies(user, urza_id, settings_service, file_service=None, object_error=None):
    app.dependency_overrides[get_current_user] = override_user(user)
    app.dependency_overrides[get_object_service] = override_object_service(
        FakeObjectService(
            result=SelectedObject(object_type="urza", id=urza_id, name="УРЗА 1"),
            error=object_error,
        )
    )
    app.dependency_overrides[get_settings_service] = override_settings_service(settings_service)
    if file_service is not None:
        app.dependency_overrides[get_file_service] = lambda: file_service


def instruction_file(file_id, name):
    return SimpleNamespace(id=file_id, original_name=name)


def make_instruction_version(status=DocumentStatus.DRAFT):
    scan_id, version_id = uuid7(), uuid7()
    version = SimpleNamespace(
        id=version_id, version_number=1, status=status,
        effective_date=date(2026, 1, 1), change_description="Изменение",
        change_justification="Причина", creator=SimpleNamespace(full_name="Автор"),
        scan_file_id=scan_id, scan_file=instruction_file(scan_id, "scan.pdf"),
        editable_file_id=None, editable_file=None, urza_instruction_id=uuid7(),
    )
    return version


def test_instruction_get_and_forms(system_user_id):
    user = make_user(system_user_id)
    urza_id = uuid7()
    object_service = FakeObjectService(result=SelectedObject(object_type="urza", id=urza_id, name="УРЗА"))
    fake_service = FakeURZAInstructionService()
    fake_service.instruction = SimpleNamespace(id=uuid7(), urza_id=urza_id)
    app.dependency_overrides[get_current_user] = override_user(user)
    app.dependency_overrides[get_object_service] = override_object_service(object_service)
    app.dependency_overrides[get_urza_instruction_service] = override_urza_instruction_service(fake_service)
    try:
        client = TestClient(app)
        listing = client.get(f"/objects/urza/{urza_id}/instruction")
        first_form = client.get(f"/objects/urza/{urza_id}/instruction/new")
        next_form = client.get(f"/objects/urza/{urza_id}/instruction/new-version")
        assert listing.status_code == 200 and "ещё не создана" in listing.text
        assert first_form.status_code == 200 and "Подписанный скан" in first_form.text
        assert next_form.status_code == 200 and "Новая версия инструкции" in next_form.text
    finally:
        app.dependency_overrides.clear()


def test_instruction_get_denies_access(system_user_id):
    user = make_user(system_user_id)
    urza_id = uuid7()
    app.dependency_overrides[get_current_user] = override_user(user)
    app.dependency_overrides[get_object_service] = override_object_service(
        FakeObjectService(error=ObjectAccessDeniedError()))
    try:
        response = TestClient(app).get(f"/objects/urza/{urza_id}/instruction")
        assert response.status_code == 403
        assert "Доступ" in response.json()["detail"]
    finally:
        app.dependency_overrides.clear()


def test_instruction_submit_denies_access(system_user_id):
    user = make_user(system_user_id)
    urza_id, version_id = uuid7(), uuid7()
    fake_service = FakeURZAInstructionService()
    async def denied(*args):
        raise PermissionError("Доступ к URZA запрещён")
    fake_service.submit_for_review = denied
    app.dependency_overrides[get_current_user] = override_user(user)
    app.dependency_overrides[get_urza_instruction_service] = override_urza_instruction_service(fake_service)
    try:
        response = TestClient(app).post(
            f"/objects/urza/{urza_id}/instruction/versions/{version_id}/submit")
        assert response.status_code == 403
        assert response.json()["detail"] == "Доступ к URZA запрещён"
    finally:
        app.dependency_overrides.clear()


@pytest.mark.parametrize("new_version", [False, True])
def test_instruction_create_routes_upload_files(system_user_id, new_version):
    user = make_user(system_user_id)
    urza_id, instruction_id = uuid7(), uuid7()
    fake_service = FakeURZAInstructionService()
    fake_service.instruction = SimpleNamespace(id=instruction_id, urza_id=urza_id)
    fake_service.version = make_instruction_version()
    fake_files = FakeFileService(SimpleNamespace(id=uuid7()))
    app.dependency_overrides[get_current_user] = override_user(user)
    app.dependency_overrides[get_object_service] = override_object_service(FakeObjectService(
        result=SelectedObject(object_type="urza", id=urza_id, name="УРЗА")))
    app.dependency_overrides[get_urza_instruction_service] = override_urza_instruction_service(fake_service)
    app.dependency_overrides[get_file_service] = lambda: fake_files
    url = (f"/objects/urza/{urza_id}/instruction/{instruction_id}/versions"
           if new_version else f"/objects/urza/{urza_id}/instruction")
    try:
        response = TestClient(app).post(url, data={"effective_date": "2026-10-01"},
            files={"scan_file": ("signed.pdf", b"scan", "application/pdf")})
        assert response.status_code == 200
        assert len(fake_files.upload_calls) == 1
        assert fake_service.calls[0][0] == ("create_version" if new_version else "create")
        assert "Версия 1" in response.text
    finally:
        app.dependency_overrides.clear()


@pytest.mark.parametrize(("action", "method_name"), [
    ("submit", "submit_for_review"),
    ("approve", "approve"),
    ("return", "return_to_draft"),
])
def test_instruction_workflow_routes(system_user_id, action, method_name):
    user = make_user(system_user_id)
    urza_id = uuid7()
    fake_service = FakeURZAInstructionService()
    fake_service.instruction = SimpleNamespace(urza_id=urza_id)
    fake_service.version = make_instruction_version()
    app.dependency_overrides[get_current_user] = override_user(user)
    app.dependency_overrides[get_object_service] = override_object_service(FakeObjectService(
        result=SelectedObject(object_type="urza", id=urza_id, name="УРЗА")))
    app.dependency_overrides[get_urza_instruction_service] = override_urza_instruction_service(fake_service)
    try:
        response = TestClient(app).post(
            f"/objects/urza/{urza_id}/instruction/versions/{fake_service.version.id}/{action}")
        assert response.status_code == 200
        assert "Версия 1" in response.text
        assert any(call[0] == action for call in fake_service.calls)
    finally:
        app.dependency_overrides.clear()


def test_get_object_requires_authentication() -> None:
    app.dependency_overrides.clear()

    client = TestClient(app)

    response = client.get(f"/objects/substation/{uuid7()}")

    assert response.status_code == 401

    app.dependency_overrides.clear()


def test_get_object_returns_selected_object(system_user_id) -> None:
    user = make_user(system_user_id=system_user_id)
    object_id = uuid7()

    selected_object = SelectedObject(
        object_type="substation",
        id=object_id,
        name="ПС Свердловская",
    )

    app.dependency_overrides[get_current_user] = override_user(user)
    app.dependency_overrides[get_object_service] = override_object_service(
        FakeObjectService(result=selected_object)
    )
    app.dependency_overrides[get_substation_service] = override_substation_service(
        FakeSubstationService()
    )
    app.dependency_overrides[get_connection_service] = override_connection_service(
        FakeConnectionService()
    )

    try:
        client = TestClient(app)

        response = client.get(
            f"/objects/substation/{object_id}",
        )

        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "ПС Центральная" in response.text
        assert "110 кВ" in response.text
        assert "SAP-001" in response.text
        assert "ASUREO-001" in response.text
    finally:
        app.dependency_overrides.clear()


def test_get_object_returns_404_when_object_not_found(system_user_id) -> None:
    user = make_user(system_user_id=system_user_id)

    app.dependency_overrides[get_current_user] = override_user(user)
    app.dependency_overrides[get_object_service] = override_object_service(
        FakeObjectService(
            error=ObjectNotFoundError(),
        )
    )

    try:
        client = TestClient(app)

        response = client.get(
            f"/objects/substation/{uuid7()}",
        )

        assert response.status_code == 404
        assert response.json()["detail"] == "Объект не найден."
    finally:
        app.dependency_overrides.clear()


def test_get_object_returns_403_when_access_denied(system_user_id) -> None:
    user = make_user(system_user_id=system_user_id)

    app.dependency_overrides[get_current_user] = override_user(user)
    app.dependency_overrides[get_object_service] = override_object_service(
        FakeObjectService(
            error=ObjectAccessDeniedError(),
        )
    )

    try:
        client = TestClient(app)

        response = client.get(
            f"/objects/substation/{uuid7()}",
        )

        assert response.status_code == 403
        assert response.json()["detail"] == "Доступ к объекту запрещён."
    finally:
        app.dependency_overrides.clear()


def test_get_object_rejects_invalid_uuid(system_user_id) -> None:
    user = make_user(system_user_id=system_user_id)

    app.dependency_overrides[get_current_user] = override_user(user)
    app.dependency_overrides[get_object_service] = override_object_service(
        FakeObjectService()
    )
    app.dependency_overrides[get_substation_service] = override_substation_service(
        FakeSubstationService()
    )
    app.dependency_overrides[get_connection_service] = override_connection_service(
        FakeConnectionService()
    )

    try:
        client = TestClient(app)

        response = client.get(
            "/objects/substation/not-a-uuid",
        )

        assert response.status_code == 422
    finally:
        app.dependency_overrides.clear()


def test_get_substation_inspections_returns_inspections(system_user_id) -> None:
    user = make_user(system_user_id=system_user_id)
    substation_id = uuid7()

    inspections = [
        Inspection(
            id=uuid7(),
            substation_id=substation_id,
            inspection_task_id=uuid7(),
            inspection_date=date(2026, 9, 1),
            remarks="Замечаний нет.",
            created_by=user.id,
            updated_by=system_user_id,
        ),
        Inspection(
            id=uuid7(),
            substation_id=substation_id,
            inspection_task_id=uuid7(),
            inspection_date=date(2026, 8, 1),
            remarks="Обнаружено замечание.",
            created_by=user.id,
            updated_by=system_user_id,
        ),
    ]

    app.dependency_overrides[get_current_user] = override_user(user)
    app.dependency_overrides[get_object_service] = override_object_service(
        FakeObjectService(
            result=SelectedObject(
                object_type="substation",
                id=substation_id,
                name="ПС Центральная",
            ),
        )
    )
    app.dependency_overrides[get_inspection_service] = override_inspection_service(
        FakeInspectionService(inspections),
    )

    try:
        client = TestClient(app)

        response = client.get(
            f"/objects/substation/{substation_id}/inspections",
        )

        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    finally:
        app.dependency_overrides.clear()


def test_get_urza_programs_returns_programs(system_user_id) -> None:
    user = make_user(system_user_id=system_user_id)
    urza_id = uuid7()

    program = Program(
        id=uuid7(),
        urza_id=urza_id,
        program_type=ProgramType.WORK,
        program_number="1",
        status=DocumentStatus.DRAFT,
        scan_file_id=uuid7(),
        editable_file_id=None,
        created_by=user.id,
        updated_by=user.id,
        created_at=datetime(2026, 9, 30, tzinfo=timezone.utc),
    )

    program.creator = user

    program_service = FakeProgramService(
        programs=[program],
        actions={
            program.id: {"submit"},
        },
    )

    app.dependency_overrides[get_current_user] = override_user(user)
    app.dependency_overrides[get_object_service] = override_object_service(
        FakeObjectService(
            result=SelectedObject(
                object_type="urza",
                id=urza_id,
                name="УРЗА 1",
            ),
        )
    )
    app.dependency_overrides[get_program_service] = override_program_service(
        program_service,
    )

    try:
        client = TestClient(app)

        response = client.get(
            f"/objects/urza/{urza_id}/programs",
        )

        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

        assert "Рабочая программа" in response.text
        assert "Черновик" in response.text
        assert "Направить на согласование" in response.text
        assert "Утвердить" not in response.text
        assert "Вернуть на доработку" not in response.text

    finally:
        app.dependency_overrides.clear()


def test_get_new_urza_program_form(system_user_id) -> None:
    user = make_user(system_user_id=system_user_id)
    urza_id = uuid7()

    app.dependency_overrides[get_current_user] = override_user(user)
    app.dependency_overrides[get_object_service] = override_object_service(
        FakeObjectService(
            result=SelectedObject(
                object_type="urza",
                id=urza_id,
                name="УРЗА 1",
            ),
        )
    )

    try:
        client = TestClient(app)

        response = client.get(
            f"/objects/urza/{urza_id}/programs/new",
        )

        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

        assert "Добавление программы" in response.text
        assert "Ввод в работу" in response.text
        assert "Вывод из работы" in response.text
        assert "Рабочая программа" in response.text

    finally:
        app.dependency_overrides.clear()


def test_create_urza_program(system_user_id) -> None:
    user = make_user(system_user_id=system_user_id)
    urza_id = uuid7()
    scan_file = File(
        id=uuid7(),
        s3_key="files/test-scan.pdf",
        original_name="program.pdf",
        display_name="program.pdf",
        extension=".pdf",
        size=4,
        mime_type="application/pdf",
        uploaded_at=datetime(2026, 9, 30, tzinfo=timezone.utc),
        created_by=user.id,
        updated_by=user.id,
    )

    program_service = FakeProgramService()
    file_service = FakeFileService(scan_file)

    app.dependency_overrides[get_current_user] = override_user(user)
    app.dependency_overrides[get_object_service] = override_object_service(
        FakeObjectService(
            result=SelectedObject(
                object_type="urza",
                id=urza_id,
                name="УРЗА 1",
            ),
        )
    )
    app.dependency_overrides[get_program_service] = override_program_service(
        program_service,
    )
    app.dependency_overrides[get_file_service] = (
        lambda: file_service
    )

    try:
        client = TestClient(app)

        response = client.post(
            f"/objects/urza/{urza_id}/programs",
            data={
                "program_type": ProgramType.WORK.value,
                "program_number": "1",
            },
            files={
                "scan_file": (
                    "program.pdf",
                    b"test",
                    "application/pdf",
                ),
            },
        )

        assert response.status_code == 200
        assert len(file_service.upload_calls) == 1

        upload = file_service.upload_calls[0]

        assert upload["actor_id"] == user.id
        assert upload["content"] == b"test"
        assert upload["original_name"] == "program.pdf"
        assert upload["mime_type"] == "application/pdf"

        assert len(program_service.programs) == 1

        program = program_service.programs[0]

        assert program.urza_id == urza_id
        assert program.program_type is ProgramType.WORK
        assert program.program_number == "1"
        assert program.status is DocumentStatus.DRAFT
        assert program.scan_file_id == scan_file.id

    finally:
        app.dependency_overrides.clear()


def test_create_urza_program_with_editable_file(system_user_id) -> None:
    user = make_user(system_user_id=system_user_id)
    urza_id = uuid7()

    scan_file = File(
        id=uuid7(),
        s3_key="files/test-scan.pdf",
        original_name="program.pdf",
        display_name="program.pdf",
        extension=".pdf",
        size=4,
        mime_type="application/pdf",
        uploaded_at=datetime(2026, 9, 30, tzinfo=timezone.utc),
        created_by=user.id,
        updated_by=user.id,
    )

    editable_file = File(
        id=uuid7(),
        s3_key="files/test-editable.docx",
        original_name="program.docx",
        display_name="program.docx",
        extension=".docx",
        size=7,
        mime_type=(
            "application/vnd.openxmlformats-officedocument."
            "wordprocessingml.document"
        ),
        uploaded_at=datetime(2026, 9, 30, tzinfo=timezone.utc),
        created_by=user.id,
        updated_by=user.id,
    )

    class FakeFileServiceWithEditable(FakeFileService):
        def __init__(self) -> None:
            super().__init__(scan_file)
            self.upload_count = 0

        async def upload(
            self,
            *,
            actor_id: UUID,
            content: bytes,
            original_name: str,
            display_name: str,
            extension: str,
            mime_type: str,
        ) -> File:
            self.upload_calls.append(
                {
                    "actor_id": actor_id,
                    "content": content,
                    "original_name": original_name,
                    "display_name": display_name,
                    "extension": extension,
                    "mime_type": mime_type,
                }
            )

            self.upload_count += 1

            if self.upload_count == 1:
                return scan_file

            return editable_file

    program_service = FakeProgramService()
    file_service = FakeFileServiceWithEditable()

    app.dependency_overrides[get_current_user] = override_user(user)
    app.dependency_overrides[get_object_service] = override_object_service(
        FakeObjectService(
            result=SelectedObject(
                object_type="urza",
                id=urza_id,
                name="УРЗА 1",
            ),
        )
    )
    app.dependency_overrides[get_program_service] = override_program_service(
        program_service,
    )
    app.dependency_overrides[get_file_service] = (
        lambda: file_service
    )

    try:
        client = TestClient(app)

        response = client.post(
            f"/objects/urza/{urza_id}/programs",
            data={
                "program_type": ProgramType.WORK.value,
                "program_number": "1",
            },
            files=[
                (
                    "scan_file",
                    (
                        "program.pdf",
                        b"scan",
                        "application/pdf",
                    ),
                ),
                (
                    "editable_file",
                    (
                        "program.docx",
                        b"editable",
                        (
                            "application/vnd.openxmlformats-officedocument."
                            "wordprocessingml.document"
                        ),
                    ),
                ),
            ],
        )

        assert response.status_code == 200
        assert len(file_service.upload_calls) == 2

        assert file_service.upload_calls[0]["content"] == b"scan"
        assert file_service.upload_calls[0]["original_name"] == "program.pdf"

        assert file_service.upload_calls[1]["content"] == b"editable"
        assert (
            file_service.upload_calls[1]["original_name"]
            == "program.docx"
        )

        assert len(program_service.programs) == 1

        program = program_service.programs[0]

        assert program.scan_file_id == scan_file.id
        assert program.editable_file_id == editable_file.id
        assert program.status is DocumentStatus.DRAFT

    finally:
        app.dependency_overrides.clear()

def test_submit_urza_program(system_user_id) -> None:
    user = make_user(system_user_id=system_user_id)
    urza_id = uuid7()

    program = Program(
        id=uuid7(),
        urza_id=urza_id,
        program_type=ProgramType.WORK,
        program_number="1",
        status=DocumentStatus.DRAFT,
        scan_file_id=uuid7(),
        editable_file_id=None,
        created_by=user.id,
        updated_by=user.id,
        created_at=datetime(2026, 9, 30, tzinfo=timezone.utc),
    )

    program.creator = user

    program_service = FakeProgramService(
        programs=[program],
    )

    app.dependency_overrides[get_current_user] = override_user(user)
    app.dependency_overrides[get_object_service] = override_object_service(
        FakeObjectService(
            result=SelectedObject(
                object_type="urza",
                id=urza_id,
                name="УРЗА 1",
            ),
        )
    )
    app.dependency_overrides[get_program_service] = override_program_service(
        program_service,
    )

    try:
        client = TestClient(app)

        response = client.post(
            f"/objects/urza/{urza_id}/programs/{program.id}/submit",
        )

        assert response.status_code == 200
        assert program.status is DocumentStatus.UNDER_REVIEW
        assert "На согласовании" in response.text
        assert "Утвердить" not in response.text
        assert "Вернуть на доработку" not in response.text

    finally:
        app.dependency_overrides.clear()





def test_approve_urza_program(system_user_id) -> None:
    user = make_user(system_user_id=system_user_id)
    user.role = UserRole.MANAGER

    urza_id = uuid7()

    program = Program(
        id=uuid7(),
        urza_id=urza_id,
        program_type=ProgramType.WORK,
        program_number="1",
        status=DocumentStatus.UNDER_REVIEW,
        scan_file_id=uuid7(),
        editable_file_id=None,
        created_by=user.id,
        updated_by=user.id,
        created_at=datetime(2026, 9, 30, tzinfo=timezone.utc),
    )

    program.creator = user

    program_service = FakeProgramService(
        programs=[program],
    )

    app.dependency_overrides[get_current_user] = override_user(user)
    app.dependency_overrides[get_object_service] = override_object_service(
        FakeObjectService(
            result=SelectedObject(
                object_type="urza",
                id=urza_id,
                name="УРЗА 1",
            ),
        )
    )
    app.dependency_overrides[get_program_service] = override_program_service(
        program_service,
    )

    try:
        client = TestClient(app)

        response = client.post(
            f"/objects/urza/{urza_id}/programs/{program.id}/approve",
        )

        assert response.status_code == 200
        assert program.status is DocumentStatus.APPROVED
        assert "Утверждено" in response.text
        assert "Утвердить" not in response.text
        assert "Вернуть на доработку" not in response.text

    finally:
        app.dependency_overrides.clear()


def test_create_urza_program_access_denied(system_user_id) -> None:
    user = make_user(system_user_id=system_user_id)
    urza_id = uuid7()

    app.dependency_overrides[get_current_user] = override_user(user)
    app.dependency_overrides[get_object_service] = override_object_service(
        FakeObjectService(
            error=ObjectAccessDeniedError(),
        )
    )

    try:
        client = TestClient(app)

        response = client.post(
            f"/objects/urza/{urza_id}/programs",
            data={
                "program_type": ProgramType.WORK.value,
                "program_number": "1",
            },
            files={
                "scan_file": (
                    "program.pdf",
                    b"test",
                    "application/pdf",
                ),
            },
        )

        assert response.status_code == 403
        assert response.json()["detail"] == "Доступ к объекту запрещён."

    finally:
        app.dependency_overrides.clear()


def test_return_urza_program(system_user_id) -> None:
    user = make_user(system_user_id=system_user_id)
    user.role = UserRole.MANAGER

    urza_id = uuid7()

    program = Program(
        id=uuid7(),
        urza_id=urza_id,
        program_type=ProgramType.WORK,
        program_number="1",
        status=DocumentStatus.UNDER_REVIEW,
        scan_file_id=uuid7(),
        editable_file_id=None,
        created_by=user.id,
        updated_by=user.id,
        created_at=datetime(2026, 9, 30, tzinfo=timezone.utc),
    )

    program.creator = user

    program_service = FakeProgramService(
        programs=[program],
    )

    app.dependency_overrides[get_current_user] = override_user(user)
    app.dependency_overrides[get_object_service] = override_object_service(
        FakeObjectService(
            result=SelectedObject(
                object_type="urza",
                id=urza_id,
                name="УРЗА 1",
            ),
        )
    )
    app.dependency_overrides[get_program_service] = override_program_service(
        program_service,
    )

    try:
        client = TestClient(app)

        response = client.post(
            f"/objects/urza/{urza_id}/programs/{program.id}/return",
        )

        assert response.status_code == 200
        assert program.status is DocumentStatus.DRAFT
        assert "Черновик" in response.text
        assert "Направить на согласование" not in response.text
        assert "Утвердить" not in response.text
        assert "Вернуть на доработку" not in response.text

    finally:
        app.dependency_overrides.clear()


def test_get_urza_settings_renders_records_status_and_current(system_user_id):
    user = make_user(system_user_id)
    urza_id = uuid7()
    approved = settings_record(urza_id, DocumentStatus.APPROVED)
    draft = settings_record(urza_id, DocumentStatus.DRAFT)
    approved.parameter_name = "Approved параметр"
    draft.parameter_name = "Draft параметр"
    deleted = settings_record(
        urza_id, DocumentStatus.APPROVED, deleted_at=datetime.now(timezone.utc)
    )
    service = FakeSettingsService(
        records=[draft, approved, deleted],
        current_approved=approved,
        actions={draft.id: {"edit", "submit"}, approved.id: set()},
    )
    set_settings_dependencies(user, urza_id, service)

    try:
        response = TestClient(app).get(f"/objects/urza/{urza_id}/settings")
        assert response.status_code == 200
        assert "Draft параметр" in response.text
        assert "Черновик" in response.text
        assert "Утверждено" in response.text
        assert "Текущие уставки" in response.text
        assert str(deleted.id) not in response.text
        assert "Внести изменение уставок" in response.text
        assert response.text.index("Draft параметр") < response.text.index(
            "Approved параметр"
        )
    finally:
        app.dependency_overrides.clear()


def test_get_new_settings_form_is_blank_and_requires_signed_file(system_user_id):
    user = make_user(system_user_id)
    urza_id = uuid7()
    set_settings_dependencies(user, urza_id, FakeSettingsService())
    try:
        response = TestClient(app).get(f"/objects/urza/{urza_id}/settings/new")
        assert response.status_code == 200
        assert 'name="signed_form_file"' in response.text
        assert "required" in response.text
        assert "Ток срабатывания" not in response.text
    finally:
        app.dependency_overrides.clear()


def test_create_settings_record_uploads_required_file(system_user_id):
    user = make_user(system_user_id)
    urza_id = uuid7()
    uploaded_file = settings_file(uuid7())
    file_service = FakeFileService(uploaded_file)
    settings_service = FakeSettingsService()
    set_settings_dependencies(user, urza_id, settings_service, file_service)
    try:
        response = TestClient(app).post(
            f"/objects/urza/{urza_id}/settings",
            data={
                "change_date": "2026-09-01",
                "parameter_name": "Ток срабатывания",
                "initial_setting": "1.0 A",
                "new_setting": "1.2 A",
                "change_reason": "Корректировка",
            },
            files={"signed_form_file": ("signed.pdf", b"scan", "application/pdf")},
        )
        assert response.status_code == 200
        assert len(file_service.upload_calls) == 1
        assert settings_service.calls[0][0] == "create_record"
        assert settings_service.calls[0][1]["signed_form_file_id"] == uploaded_file.id
        assert "Ток срабатывания" in response.text
    finally:
        app.dependency_overrides.clear()


def test_create_settings_record_without_file_returns_validation_message(system_user_id):
    user = make_user(system_user_id)
    urza_id = uuid7()
    file_service = FakeFileService(settings_file(uuid7()))
    settings_service = FakeSettingsService()
    set_settings_dependencies(user, urza_id, settings_service, file_service)
    try:
        response = TestClient(app).post(
            f"/objects/urza/{urza_id}/settings",
            data={
                "change_date": "2026-09-01",
                "parameter_name": "Параметр",
                "initial_setting": "1",
                "new_setting": "2",
                "change_reason": "Причина",
            },
        )
        assert response.status_code == 422
        assert "Загрузите подписанный формуляр" in response.text
        assert not file_service.upload_calls
        assert not settings_service.calls
    finally:
        app.dependency_overrides.clear()


def test_create_settings_record_unfinished_error_archives_uploaded_file(system_user_id):
    user = make_user(system_user_id)
    urza_id = uuid7()
    uploaded_file = settings_file(uuid7())
    file_service = FakeFileService(uploaded_file)
    settings_service = FakeSettingsService(
        error_by_method={"create_record": ValueError("Уже есть незавершённая запись.")}
    )
    set_settings_dependencies(user, urza_id, settings_service, file_service)
    try:
        response = TestClient(app).post(
            f"/objects/urza/{urza_id}/settings",
            data={
                "change_date": "2026-09-01",
                "parameter_name": "Параметр",
                "initial_setting": "1",
                "new_setting": "2",
                "change_reason": "Причина",
            },
            files={"signed_form_file": ("signed.pdf", b"scan", "application/pdf")},
        )
        assert response.status_code == 400
        assert "незавершённая запись" in response.text
        assert file_service.archive_calls == [{"file_id": uploaded_file.id, "user_id": user.id}]
    finally:
        app.dependency_overrides.clear()


def test_settings_routes_return_403_for_inaccessible_urza(system_user_id):
    user = make_user(system_user_id)
    urza_id = uuid7()
    set_settings_dependencies(
        user, urza_id, FakeSettingsService(), object_error=ObjectAccessDeniedError()
    )
    try:
        response = TestClient(app).get(f"/objects/urza/{urza_id}/settings")
        assert response.status_code == 403
        assert "Доступ к объекту запрещён" in response.text
    finally:
        app.dependency_overrides.clear()


def test_get_edit_settings_draft_shows_values_and_current_file(system_user_id):
    user = make_user(system_user_id)
    urza_id, file_id = uuid7(), uuid7()
    record = settings_record(urza_id, DocumentStatus.DRAFT, file_id=file_id)
    service = FakeSettingsService(records=[record], actions={record.id: {"edit", "submit"}})
    set_settings_dependencies(user, urza_id, service)
    try:
        response = TestClient(app).get(
            f"/objects/urza/{urza_id}/settings/{record.id}/edit"
        )
        assert response.status_code == 200
        assert "Изменение черновика уставок" in response.text
        assert "Ток срабатывания" in response.text
        assert "1.0 A" in response.text and "1.2 A" in response.text
        assert f'href="/files/{file_id}/view"' in response.text
        assert f'href="/files/{file_id}/download"' in response.text
    finally:
        app.dependency_overrides.clear()


@pytest.mark.parametrize("document_status", [DocumentStatus.APPROVED, DocumentStatus.UNDER_REVIEW])
def test_get_edit_settings_rejects_non_draft(system_user_id, document_status):
    user = make_user(system_user_id)
    urza_id = uuid7()
    record = settings_record(urza_id, document_status)
    service = FakeSettingsService(records=[record], actions={record.id: set()})
    set_settings_dependencies(user, urza_id, service)
    try:
        response = TestClient(app).get(
            f"/objects/urza/{urza_id}/settings/{record.id}/edit"
        )
        assert response.status_code == 403
    finally:
        app.dependency_overrides.clear()


def test_update_settings_draft_without_replacement_keeps_signed_file(system_user_id):
    user = make_user(system_user_id)
    urza_id, file_id = uuid7(), uuid7()
    record = settings_record(urza_id, DocumentStatus.DRAFT, file_id=file_id)
    service = FakeSettingsService(records=[record])
    file_service = FakeFileService(settings_file(uuid7()))
    set_settings_dependencies(user, urza_id, service, file_service)
    try:
        response = TestClient(app).post(
            f"/objects/urza/{urza_id}/settings/{record.id}",
            data={
                "change_date": "2026-09-02",
                "parameter_name": "Изменено",
                "initial_setting": "1.0 A",
                "new_setting": "1.3 A",
                "change_reason": "Причина",
            },
        )
        assert response.status_code == 200
        update_kwargs = next(kwargs for name, kwargs in service.calls if name == "update_draft")
        assert update_kwargs["signed_form_file_id"] is None
        assert record.signed_form_file_id == file_id
        assert not file_service.upload_calls
    finally:
        app.dependency_overrides.clear()


def test_update_settings_draft_replaces_file_and_archives_old(system_user_id):
    user = make_user(system_user_id)
    urza_id, old_file_id = uuid7(), uuid7()
    replacement = settings_file(uuid7(), "replacement.pdf")
    record = settings_record(urza_id, DocumentStatus.DRAFT, file_id=old_file_id)
    service = FakeSettingsService(records=[record])
    file_service = FakeFileService(replacement)
    set_settings_dependencies(user, urza_id, service, file_service)
    try:
        response = TestClient(app).post(
            f"/objects/urza/{urza_id}/settings/{record.id}",
            data={
                "change_date": "2026-09-02",
                "parameter_name": "Изменено",
                "initial_setting": "1.0 A",
                "new_setting": "1.3 A",
                "change_reason": "Причина",
            },
            files={"signed_form_file": ("replacement.pdf", b"new scan", "application/pdf")},
        )
        assert response.status_code == 200
        update_kwargs = next(kwargs for name, kwargs in service.calls if name == "update_draft")
        assert update_kwargs["signed_form_file_id"] == replacement.id
        assert file_service.archive_calls == [{"file_id": old_file_id, "user_id": user.id}]
    finally:
        app.dependency_overrides.clear()


@pytest.mark.parametrize(
    ("path_action", "initial_status", "expected_status", "service_method", "role"),
    [
        ("submit", DocumentStatus.DRAFT, DocumentStatus.UNDER_REVIEW, "submit_for_review", UserRole.ENGINEER),
        ("submit", DocumentStatus.DRAFT, DocumentStatus.UNDER_REVIEW, "submit_for_review", UserRole.MANAGER),
        ("approve", DocumentStatus.UNDER_REVIEW, DocumentStatus.APPROVED, "approve", UserRole.MANAGER),
        ("return", DocumentStatus.UNDER_REVIEW, DocumentStatus.DRAFT, "return_to_draft", UserRole.MANAGER),
    ],
)
def test_settings_workflow_routes(
    system_user_id, path_action, initial_status, expected_status, service_method, role
):
    user = make_user(system_user_id)
    user.role = role
    urza_id = uuid7()
    record = settings_record(urza_id, initial_status)
    service = FakeSettingsService(records=[record])
    set_settings_dependencies(user, urza_id, service)
    try:
        response = TestClient(app).post(
            f"/objects/urza/{urza_id}/settings/{record.id}/{path_action}"
        )
        assert response.status_code == 200
        assert record.status is expected_status
        assert any(name == service_method for name, _ in service.calls)
        assert expected_status.label in response.text
    finally:
        app.dependency_overrides.clear()


def test_settings_workflow_denies_wrong_reviewer(system_user_id):
    user = make_user(system_user_id)
    user.role = UserRole.MANAGER
    urza_id = uuid7()
    record = settings_record(urza_id, DocumentStatus.UNDER_REVIEW)
    service = FakeSettingsService(
        records=[record],
        error_by_method={"approve": PermissionError("Manager не отвечает за URZA.")},
    )
    set_settings_dependencies(user, urza_id, service)
    try:
        response = TestClient(app).post(
            f"/objects/urza/{urza_id}/settings/{record.id}/approve"
        )
        assert response.status_code == 403
        assert "не отвечает" in response.json()["detail"]
    finally:
        app.dependency_overrides.clear()


def test_settings_workflow_denies_non_manager_approval(system_user_id):
    user = make_user(system_user_id)
    urza_id = uuid7()
    record = settings_record(urza_id, DocumentStatus.UNDER_REVIEW)
    service = FakeSettingsService(
        records=[record],
        error_by_method={"approve": PermissionError("Согласовывать может только Manager.")},
    )
    set_settings_dependencies(user, urza_id, service)
    try:
        response = TestClient(app).post(
            f"/objects/urza/{urza_id}/settings/{record.id}/approve"
        )
        assert response.status_code == 403
        assert "только Manager" in response.json()["detail"]
    finally:
        app.dependency_overrides.clear()


def test_returned_settings_draft_can_be_submitted_again(system_user_id):
    user = make_user(system_user_id)
    user.role = UserRole.MANAGER
    urza_id = uuid7()
    record = settings_record(urza_id, DocumentStatus.UNDER_REVIEW)
    service = FakeSettingsService(records=[record])
    set_settings_dependencies(user, urza_id, service)
    try:
        client = TestClient(app)
        returned = client.post(
            f"/objects/urza/{urza_id}/settings/{record.id}/return"
        )
        assert returned.status_code == 200
        assert record.status is DocumentStatus.DRAFT
        resubmitted = client.post(
            f"/objects/urza/{urza_id}/settings/{record.id}/submit"
        )
        assert resubmitted.status_code == 200
        assert record.status is DocumentStatus.UNDER_REVIEW
    finally:
        app.dependency_overrides.clear()


@pytest.mark.parametrize("document_status", [DocumentStatus.APPROVED, DocumentStatus.UNDER_REVIEW])
def test_post_update_non_draft_is_rejected(system_user_id, document_status):
    user = make_user(system_user_id)
    urza_id = uuid7()
    record = settings_record(urza_id, document_status)
    service = FakeSettingsService(
        records=[record],
        error_by_method={"update_draft": ValueError("Изменять можно только черновик уставок.")},
    )
    file_service = FakeFileService(settings_file(uuid7()))
    set_settings_dependencies(user, urza_id, service, file_service)
    try:
        response = TestClient(app).post(
            f"/objects/urza/{urza_id}/settings/{record.id}",
            data={
                "change_date": "2026-09-02",
                "parameter_name": "Изменено",
                "initial_setting": "1",
                "new_setting": "2",
                "change_reason": "Причина",
            },
        )
        assert response.status_code == 400
        assert "только черновик" in response.text
        assert not file_service.upload_calls
    finally:
        app.dependency_overrides.clear()


@pytest.mark.parametrize("role", [UserRole.ADMIN, UserRole.SUPERADMIN])
def test_settings_delete_soft_deletes_and_hides_record(system_user_id, role):
    user = make_user(system_user_id)
    user.role = role
    urza_id = uuid7()
    record = settings_record(urza_id, DocumentStatus.APPROVED)
    service = FakeSettingsService(records=[record])
    set_settings_dependencies(user, urza_id, service)
    try:
        response = TestClient(app).post(
            f"/objects/urza/{urza_id}/settings/{record.id}/delete"
        )
        assert response.status_code == 200
        assert record.deleted_at is not None
        assert str(record.id) not in response.text
    finally:
        app.dependency_overrides.clear()


@pytest.mark.parametrize("role", [UserRole.ENGINEER, UserRole.MANAGER])
def test_settings_delete_denies_roles_without_permission(system_user_id, role):
    user = make_user(system_user_id)
    user.role = role
    urza_id = uuid7()
    record = settings_record(urza_id, DocumentStatus.APPROVED)
    service = FakeSettingsService(
        records=[record],
        error_by_method={"delete_record": PermissionError("Удаление запрещено")},
    )
    set_settings_dependencies(user, urza_id, service)
    try:
        response = TestClient(app).post(
            f"/objects/urza/{urza_id}/settings/{record.id}/delete"
        )
        assert response.status_code == 403
        assert record.deleted_at is None
    finally:
        app.dependency_overrides.clear()
