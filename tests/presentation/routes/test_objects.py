from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from uuid6 import uuid7

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
from app.domain.file import File
from app.domain.inspection import Inspection
from app.domain.program import Program
from app.domain.user import User
from app.presentation.app import app
from app.presentation.auth.dependencies import get_current_user
from app.presentation.dependencies.services import (
    get_connection_service,
    get_file_service,
    get_inspection_service,
    get_object_service,
    get_otd_service,
    get_program_service,
    get_settings_service,
    get_substation_service,
    get_task_service,
    get_tree_service,
    get_urza_instruction_service,
    get_urza_service,
)


class FakeSubstationService:
    def __init__(self):
        self.updated = None

    async def get_details(self, substation_id: UUID) -> SubstationDetails:
        if self.updated is not None:
            return SubstationDetails(id=substation_id, **self.updated)
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

    async def update_details(self, substation_id, data):
        self.updated = data.model_dump()
        return SubstationDetails(id=substation_id, **self.updated)


class FakeURZAService:
    def __init__(self, details):
        self.details = details

    async def get_details(self, urza_id):
        return self.details


class FakeOTDService:
    def __init__(self):
        self.create_calls = []

    async def get_details(self, *, user_id, urza_id, version_id=None):
        return SimpleNamespace(
            current_version=None,
            selected_version=None,
            versions=[],
        )

    async def get_versions(self, user_id, urza_id):
        return []

    async def get_available_actions(self, user_id, version):
        return set()

    async def get_available_create_actions(self, user_id, urza_id):
        return set()

    async def get_by_urza(self, user_id, urza_id):
        return None

    async def validate_task_for_result(self, user_id, urza_id, task_id):
        return None

    async def create(self, **kwargs):
        self.create_calls.append(kwargs)
        return SimpleNamespace(id=uuid7())


class FakeTreeService:
    async def get_tree(self, *, user_id):
        return []


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


class FakeObjectStorage:
    def __init__(self) -> None:
        self.delete_calls: list[dict] = []
        self.delete_error: Exception | None = None

    async def delete(self, *, key: str) -> None:
        self.delete_calls.append({"key": key})
        if self.delete_error is not None:
            raise self.delete_error


class FakeFileService:
    def __init__(self, file: File) -> None:
        self.file = file
        self.upload_calls: list[dict] = []
        self.archive_calls: list[dict] = []
        self.storage = FakeObjectStorage()

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
        record.deleted_at = datetime.now(UTC)


def override_settings_service(service: FakeSettingsService):
    def dependency():
        return service
    return dependency


class FakeTaskService:
    async def can_issue_task(
        self,
        *,
        actor_id,
        urza_id,
        work_type=None,
    ):
        return False


class FakeProgramService:
    def __init__(
        self,
        programs: list[Program] | None = None,
        actions: dict[UUID, set[str]] | None = None,
        error: Exception | None = None,
        create_error: Exception | None = None,

    ) -> None:
        self.programs = programs or []
        self.actions = actions or {}
        self.error = error
        self.create_error = create_error
        self.update_calls = []

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
            task_id: UUID | None = None,
    ):
        if self.create_error is not None:
            raise self.create_error

        program = Program(
            id=uuid7(),
            urza_id=urza_id,
            program_type=program_type,
            program_number=program_number,
            status=DocumentStatus.DRAFT,
            scan_file_id=scan_file_id,
            editable_file_id=editable_file_id,
            task_id=task_id,
            created_by=user_id,
            updated_by=user_id,
            created_at=datetime(2026, 9, 30, tzinfo=UTC),
        )

        self.programs.append(program)

        return program


    async def get_by_id(
        self,
        user_id: UUID,
        program_id: UUID,
        urza_id: UUID,
    ) -> Program | None:
        if self.error is not None:
            raise self.error

        return next(
            (
                program
                for program in self.programs
                if program.id == program_id
            ),
            None,
        )

    async def update(
        self,
        *,
        user_id: UUID,
        program_id: UUID,
        urza_id: UUID,
        program_type: ProgramType,
        program_number: str,
        scan_file_id: UUID | None = None,
        editable_file_id: UUID | None = None,
        remove_editable_file: bool = False,
    ) -> Program:
        if self.error is not None:
            raise self.error

        program = next(
            (
                program
                for program in self.programs
                if program.id == program_id
            ),
            None,
        )

        if program is None:
            raise ValueError("Программа не найдена.")

        self.update_calls.append(
            {
                "user_id": user_id,
                "program_id": program_id,
                "urza_id": urza_id,
                "program_type": program_type,
                "program_number": program_number,
                "scan_file_id": scan_file_id,
                "editable_file_id": editable_file_id,
                "remove_editable_file": remove_editable_file,
            }
        )

        program.program_type = program_type
        program.program_number = program_number

        if scan_file_id is not None:
            program.scan_file_id = scan_file_id

        if remove_editable_file:
            program.editable_file_id = None
        elif editable_file_id is not None:
            program.editable_file_id = editable_file_id

        program.updated_by = user_id

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
        comment: str | None = None,
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


def test_substation_edit_is_role_protected_and_returns_htmx_details():
    user = make_user(uuid7())
    user.role = UserRole.MANAGER
    substation_id = uuid7()
    app.dependency_overrides[get_current_user] = override_user(user)
    app.dependency_overrides[get_object_service] = override_object_service(
        FakeObjectService(result=SelectedObject(object_type="substation", id=substation_id, name="ПС")),
    )
    substation_service = FakeSubstationService()
    app.dependency_overrides[get_substation_service] = override_substation_service(substation_service)
    try:
        with TestClient(app) as client:
            form = client.get(f"/objects/substation/{substation_id}/edit")
            assert form.status_code == 200
            assert 'value="ПС Центральная"' in form.text
            assert "event.detail.xhr.status === 422" in form.text
            saved = client.post(
                f"/objects/substation/{substation_id}/edit",
                headers={"HX-Request": "true"},
                data={"dispatch_name": "Обновлённая", "highest_voltage": "110",
                      "operational_current_type": "permanent", "sap_code": "", "asureo_code": "",
                      "address": "", "latitude": "", "longitude": ""},
            )
            assert saved.status_code == 200
            assert "Обновлённая" in saved.text
            assert "hx-get=\"/objects/substation/" in saved.text
            assert substation_service.updated["sap_code"] is None
    finally:
        app.dependency_overrides.clear()


def test_substation_edit_regular_post_redirects_to_full_card():
    user = make_user(uuid7())
    user.role = UserRole.ADMIN
    substation_id = uuid7()
    app.dependency_overrides[get_current_user] = override_user(user)
    app.dependency_overrides[get_object_service] = override_object_service(
        FakeObjectService(result=SelectedObject(object_type="substation", id=substation_id, name="ПС")),
    )
    app.dependency_overrides[get_substation_service] = override_substation_service(FakeSubstationService())
    try:
        response = TestClient(app).post(f"/objects/substation/{substation_id}/edit", data={
            "dispatch_name": "ПС обновлённая", "highest_voltage": "110",
            "operational_current_type": "permanent",
        }, follow_redirects=False)
        assert response.status_code == 303
        assert response.headers["location"] == f"/objects/substation/{substation_id}"
    finally:
        app.dependency_overrides.clear()


def test_substation_edit_validation_preserves_entered_values():
    user = make_user(uuid7())
    user.role = UserRole.ADMIN
    substation_id = uuid7()
    app.dependency_overrides[get_current_user] = override_user(user)
    app.dependency_overrides[get_object_service] = override_object_service(
        FakeObjectService(result=SelectedObject(object_type="substation", id=substation_id, name="ПС")),
    )
    app.dependency_overrides[get_substation_service] = override_substation_service(FakeSubstationService())
    try:
        with TestClient(app) as client:
            response = client.post(f"/objects/substation/{substation_id}/edit", headers={"HX-Request": "true"}, data={
                "dispatch_name": "Введённое имя", "highest_voltage": "110",
                "operational_current_type": "invalid", "sap_code": "значение",
            })
        assert response.status_code == 422
        assert "Проверьте введённые значения" in response.text
        assert "Введённое имя" in response.text
        assert "значение" in response.text
    finally:
        app.dependency_overrides.clear()


def test_substation_edit_denied_without_object_access():
    user = make_user(uuid7())
    user.role = UserRole.ADMIN
    app.dependency_overrides[get_current_user] = override_user(user)
    app.dependency_overrides[get_object_service] = override_object_service(
        FakeObjectService(error=ObjectAccessDeniedError()),
    )
    try:
        with TestClient(app) as client:
            response = client.get(f"/objects/substation/{uuid7()}/edit")
        assert response.status_code == 403
    finally:
        app.dependency_overrides.clear()


@pytest.mark.parametrize("role", [UserRole.ENGINEER, UserRole.SPECIALIST])
def test_substation_edit_post_denied_for_read_only_roles(role):
    user = make_user(uuid7())
    user.role = role
    substation_id = uuid7()
    app.dependency_overrides[get_current_user] = override_user(user)
    app.dependency_overrides[get_object_service] = override_object_service(
        FakeObjectService(result=SelectedObject(object_type="substation", id=substation_id, name="ПС")),
    )
    try:
        with TestClient(app) as client:
            response = client.post(f"/objects/substation/{substation_id}/edit", data={
                "dispatch_name": "ПС", "highest_voltage": "110",
                "operational_current_type": "permanent",
            })
            assert response.status_code == 403
    finally:
        app.dependency_overrides.clear()


@pytest.mark.parametrize("role", [UserRole.ENGINEER, UserRole.SPECIALIST])
def test_substation_edit_form_get_denied_for_read_only_roles(role):
    user = make_user(uuid7())
    user.role = role
    substation_id = uuid7()
    app.dependency_overrides[get_current_user] = override_user(user)
    app.dependency_overrides[get_object_service] = override_object_service(
        FakeObjectService(result=SelectedObject(object_type="substation", id=substation_id, name="ПС")),
    )
    try:
        response = TestClient(app).get(f"/objects/substation/{substation_id}/edit")
        assert response.status_code == 403
    finally:
        app.dependency_overrides.clear()


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
        uploaded_at=datetime(2026, 9, 30, tzinfo=UTC),
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
    app.dependency_overrides[get_task_service] = lambda: FakeTaskService()

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
    instruction_id = uuid7()
    fake_service.instruction = SimpleNamespace(id=instruction_id, urza_id=urza_id)
    fake_service.version = make_instruction_version(DocumentStatus.APPROVED)
    fake_service.version.urza_instruction_id = instruction_id
    app.dependency_overrides[get_current_user] = override_user(user)
    app.dependency_overrides[get_object_service] = override_object_service(object_service)
    app.dependency_overrides[get_urza_instruction_service] = override_urza_instruction_service(fake_service)
    try:
        client = TestClient(app)
        listing = client.get(f"/objects/urza/{urza_id}/instruction")
        first_form = client.get(f"/objects/urza/{urza_id}/instruction/new")
        next_form = client.get(f"/objects/urza/{urza_id}/instruction/new-version")
        assert listing.status_code == 200 and "Версия 1" in listing.text
        assert first_form.status_code == 200 and "Подписанный скан" in first_form.text
        assert next_form.status_code == 200 and "Новая версия инструкции" in next_form.text
    finally:
        app.dependency_overrides.clear()


def test_instruction_new_form_denies_roles_without_create_permission(system_user_id):
    user = make_user(system_user_id)
    user.role = UserRole.SPECIALIST
    urza_id = uuid7()
    app.dependency_overrides[get_current_user] = override_user(user)
    app.dependency_overrides[get_object_service] = override_object_service(FakeObjectService(
        result=SelectedObject(object_type="urza", id=urza_id, name="УРЗА")))
    try:
        response = TestClient(app).get(f"/objects/urza/{urza_id}/instruction/new")
        assert response.status_code == 403
    finally:
        app.dependency_overrides.clear()


def test_instruction_history_cannot_select_version_from_another_urza(system_user_id):
    user = make_user(system_user_id)
    urza_id = uuid7()
    instruction_id = uuid7()
    local_version = make_instruction_version(DocumentStatus.DRAFT)
    local_version.urza_instruction_id = instruction_id
    foreign_version = make_instruction_version(DocumentStatus.APPROVED)
    foreign_version.version_number = 99
    foreign_version.urza_instruction_id = uuid7()
    service = FakeURZAInstructionService()
    service.instruction = SimpleNamespace(id=instruction_id, urza_id=urza_id)
    service.version = local_version
    async def get_versions(*_):
        return [local_version]
    async def get_version_by_id(*_):
        return foreign_version
    service.get_versions = get_versions
    service.get_version_by_id = get_version_by_id
    app.dependency_overrides[get_current_user] = override_user(user)
    app.dependency_overrides[get_object_service] = override_object_service(FakeObjectService(
        result=SelectedObject(object_type="urza", id=urza_id, name="УРЗА")))
    app.dependency_overrides[get_urza_instruction_service] = override_urza_instruction_service(service)
    try:
        response = TestClient(app).get(
            f"/objects/urza/{urza_id}/instruction",
            params={"instruction_version": str(foreign_version.id)},
        )
        assert response.status_code == 200
        assert "Версия 1" in response.text
        assert "Версия 99" not in response.text
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
    fake_service.version = make_instruction_version()
    fake_service.instruction = SimpleNamespace(
        id=fake_service.version.urza_instruction_id, urza_id=urza_id
    )
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


@pytest.mark.parametrize("headers", [{}, {"HX-Request": "true"}])
def test_urza_route_returns_full_page_or_htmx_fragment(
    system_user_id,
    headers,
):
    user = make_user(system_user_id=system_user_id)
    urza_id = uuid7()
    urza = SimpleNamespace(
        id=urza_id,
        dispatch_name="УРЗА тестовая",
        substation=SimpleNamespace(dispatch_name="ПС тестовая"),
        connection=SimpleNamespace(dispatch_name="ВЛ тестовая"),
        element_base=SimpleNamespace(label="Микропроцессорная"),
        complexity=False,
        category=SimpleNamespace(value="III"),
        rdu_subordination=False,
        status=SimpleNamespace(badge_class="text-bg-success", label="В работе"),
        inventory_number=None,
        commissioning_date=date(2020, 1, 1),
        room_category=SimpleNamespace(value="I"),
    )
    app.dependency_overrides[get_current_user] = override_user(user)
    app.dependency_overrides[get_object_service] = override_object_service(
        FakeObjectService(
            result=SelectedObject(
                object_type="urza",
                id=urza_id,
                name="УРЗА тестовая",
            )
        )
    )
    app.dependency_overrides[get_urza_service] = lambda: FakeURZAService(urza)
    app.dependency_overrides[get_otd_service] = lambda: FakeOTDService()
    app.dependency_overrides[get_settings_service] = lambda: FakeSettingsService()
    app.dependency_overrides[get_task_service] = lambda: FakeTaskService()
    app.dependency_overrides[get_tree_service] = lambda: FakeTreeService()

    try:
        response = TestClient(app).get(
            f"/objects/urza/{urza_id}?tab=otd",
            headers=headers,
        )

        assert response.status_code == 200
        assert "УРЗА тестовая" in response.text
        assert 'data-tab="otd"' in response.text
        if headers:
            assert "<!doctype html>" not in response.text.lower()
            assert 'id="object-content"' not in response.text
            assert 'id="urza-tab-content"' in response.text
        else:
            assert "<!doctype html>" in response.text.lower()
            assert 'id="app-sidebar"' in response.text
            assert 'id="object-content"' in response.text
    finally:
        app.dependency_overrides.clear()


def test_otd_first_version_form_and_submission(system_user_id):
    user = make_user(system_user_id=system_user_id)
    urza_id = uuid7()
    service = FakeOTDService()
    app.dependency_overrides[get_current_user] = override_user(user)
    app.dependency_overrides[get_object_service] = override_object_service(
        FakeObjectService(
            result=SelectedObject(
                object_type="urza", id=urza_id, name="УРЗА тестовая"
            )
        )
    )
    app.dependency_overrides[get_otd_service] = lambda: service
    app.dependency_overrides[get_tree_service] = lambda: FakeTreeService()

    try:
        client = TestClient(app)
        form_response = client.get(f"/objects/urza/{urza_id}/otd/new")

        assert form_response.status_code == 200
        assert "Первая версия ОТД" in form_response.text
        assert 'name="effective_date"' in form_response.text
        assert 'name="urza_purpose"' in form_response.text
        assert 'type="file"' not in form_response.text

        response = client.post(
            f"/objects/urza/{urza_id}/otd",
            data={
                "effective_date": "2026-10-14",
                "urza_service_life": "12",
                "urza_purpose": "rza",
            },
            follow_redirects=False,
        )

        assert response.status_code == 303, response.text
        assert response.headers["location"] == f"/objects/urza/{urza_id}?tab=otd"
        assert len(service.create_calls) == 1
        assert service.create_calls[0]["urza_id"] == urza_id
    finally:
        app.dependency_overrides.clear()

@pytest.mark.parametrize(
    "role,can_edit",
    [
        (UserRole.ADMIN, True),
        (UserRole.MANAGER, True),
        (UserRole.SUPERADMIN, True),
        (UserRole.ENGINEER, False),
        (UserRole.SPECIALIST, False),
    ],
)
def test_get_object_returns_selected_object(role, can_edit) -> None:
    user = make_user(system_user_id=uuid7())
    user.role = role
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
    app.dependency_overrides[get_urza_service] = lambda: FakeURZAService(None)
    app.dependency_overrides[get_otd_service] = lambda: FakeOTDService()
    app.dependency_overrides[get_settings_service] = lambda: FakeSettingsService()
    app.dependency_overrides[get_task_service] = lambda: FakeTaskService()
    app.dependency_overrides[get_tree_service] = lambda: FakeTreeService()

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
        assert ("Изменить" in response.text) is can_edit
        assert "Добавить присоединение" in response.text
    finally:
        app.dependency_overrides.clear()


def test_substation_details_htmx_reload_keeps_edit_button():
    user = make_user(system_user_id=uuid7())
    user.role = UserRole.MANAGER
    substation_id = uuid7()
    app.dependency_overrides[get_current_user] = override_user(user)
    app.dependency_overrides[get_object_service] = override_object_service(
        FakeObjectService(result=SelectedObject(
            object_type="substation", id=substation_id, name="ПС",
        )),
    )
    app.dependency_overrides[get_substation_service] = override_substation_service(FakeSubstationService())
    try:
        response = TestClient(app).get(f"/objects/substation/{substation_id}/details")
        assert response.status_code == 200
        assert "Изменить" in response.text
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
        created_at=datetime(2026, 9, 30, tzinfo=UTC),
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



def test_get_edit_urza_program_form(system_user_id) -> None:
    user = make_user(system_user_id=system_user_id)
    urza_id = uuid7()

    program = Program(
        id=uuid7(),
        urza_id=urza_id,
        program_type=ProgramType.WORK,
        program_number="123",
        status=DocumentStatus.DRAFT,
        scan_file_id=uuid7(),
        editable_file_id=None,
        created_by=user.id,
        updated_by=user.id,
        created_at=datetime(2026, 9, 30, tzinfo=UTC),
    )
    program.creator = user

    program_service = FakeProgramService(programs=[program])

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
            f"/objects/urza/{urza_id}/programs/{program.id}/edit",
        )
        assert response.status_code == 200
        assert "Редактирование программы" in response.text
        assert "123" in response.text
        assert f"/objects/urza/{urza_id}/programs/{program.id}/edit" in response.text

    finally:
        app.dependency_overrides.clear()



def test_update_urza_program_without_replacing_scan(system_user_id) -> None:
    user = make_user(system_user_id=system_user_id)
    urza_id = uuid7()
    task_id = uuid7()
    scan_file_id = uuid7()

    program = Program(
        id=uuid7(),
        urza_id=urza_id,
        program_type=ProgramType.WORK,
        program_number="123",
        status=DocumentStatus.DRAFT,
        scan_file_id=scan_file_id,
        editable_file_id=None,
        task_id=task_id,
        created_by=user.id,
        updated_by=user.id,
        created_at=datetime(2026, 9, 30, tzinfo=UTC),
    )
    program.creator = user

    program_service = FakeProgramService(programs=[program])

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
            f"/objects/urza/{urza_id}/programs/{program.id}/edit",
            data={
                "program_type": ProgramType.COMMISSIONING.value,
                "program_number": " 456 ",
            },
        )

        assert response.status_code == 200
        assert len(program_service.update_calls) == 1

        call = program_service.update_calls[0]
        assert call["program_type"] is ProgramType.COMMISSIONING
        assert call["program_number"] == "456"
        assert call["scan_file_id"] is None
        assert call["editable_file_id"] is None
        assert call["remove_editable_file"] is False

        assert program.scan_file_id == scan_file_id
        assert program.task_id == task_id
        assert program.program_type is ProgramType.COMMISSIONING
        assert program.program_number == "456"

    finally:
        app.dependency_overrides.clear()



def test_update_urza_program_rejects_approved_program(
    system_user_id,
) -> None:
    user = make_user(system_user_id=system_user_id)
    urza_id = uuid7()

    program = Program(
        id=uuid7(),
        urza_id=urza_id,
        program_type=ProgramType.WORK,
        program_number="123",
        status=DocumentStatus.APPROVED,
        scan_file_id=uuid7(),
        editable_file_id=None,
        created_by=user.id,
        updated_by=user.id,
        created_at=datetime(2026, 9, 30, tzinfo=UTC),
    )
    program.creator = user

    program_service = FakeProgramService(programs=[program])

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
            f"/objects/urza/{urza_id}/programs/{program.id}/edit",
            data={
                "program_type": ProgramType.WORK.value,
                "program_number": "456",
            },
        )

        assert response.status_code == 400
        assert response.json()["detail"] == (
            "Редактировать можно только черновик."
        )
        assert program_service.update_calls == []
        assert program.program_number == "123"

    finally:
        app.dependency_overrides.clear()



def test_update_urza_program_replaces_files(system_user_id) -> None:
    user = make_user(system_user_id=system_user_id)
    urza_id = uuid7()

    program = Program(
        id=uuid7(),
        urza_id=urza_id,
        program_type=ProgramType.WORK,
        program_number="123",
        status=DocumentStatus.DRAFT,
        scan_file_id=uuid7(),
        editable_file_id=None,
        created_by=user.id,
        updated_by=user.id,
        created_at=datetime(2026, 9, 30, tzinfo=UTC),
    )
    program.creator = user

    new_scan = File(
        id=uuid7(),
        s3_key="files/new-scan.pdf",
        original_name="new-scan.pdf",
        display_name="new-scan.pdf",
        extension=".pdf",
        size=4,
        mime_type="application/pdf",
        uploaded_at=datetime(2026, 9, 30, tzinfo=UTC),
        created_by=user.id,
        updated_by=user.id,
    )
    new_editable = File(
        id=uuid7(),
        s3_key="files/new-editable.docx",
        original_name="new-editable.docx",
        display_name="new-editable.docx",
        extension=".docx",
        size=7,
        mime_type=(
            "application/vnd.openxmlformats-officedocument."
            "wordprocessingml.document"
        ),
        uploaded_at=datetime(2026, 9, 30, tzinfo=UTC),
        created_by=user.id,
        updated_by=user.id,
    )

    class FakeFileServiceWithReplacements(FakeFileService):
        def __init__(self) -> None:
            super().__init__(new_scan)
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
            return new_scan if self.upload_count == 1 else new_editable

    program_service = FakeProgramService(programs=[program])
    file_service = FakeFileServiceWithReplacements()

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
    app.dependency_overrides[get_file_service] = lambda: file_service

    try:
        client = TestClient(app)

        response = client.post(
            f"/objects/urza/{urza_id}/programs/{program.id}/edit",
            data={
                "program_type": ProgramType.WORK.value,
                "program_number": "456",
            },
            files=[
                ("scan_file", ("new-scan.pdf", b"scan", "application/pdf")),
                (
                    "editable_file",
                    (
                        "new-editable.docx",
                        b"editable",
                        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    ),
                ),
            ],
        )

        assert response.status_code == 200
        assert len(file_service.upload_calls) == 2
        assert len(program_service.update_calls) == 1

        call = program_service.update_calls[0]
        assert call["scan_file_id"] == new_scan.id
        assert call["editable_file_id"] == new_editable.id
        assert call["remove_editable_file"] is False

    finally:
        app.dependency_overrides.clear()


#Исправить
def test_update_urza_program_replaces_only_scan(system_user_id) -> None:
    user = make_user(system_user_id=system_user_id)
    urza_id = uuid7()
    old_scan_file_id = uuid7()
    old_editable_file_id = uuid7()
    task_id = uuid7()

    program = Program(
        id=uuid7(),
        urza_id=urza_id,
        program_type=ProgramType.WORK,
        program_number="123",
        status=DocumentStatus.DRAFT,
        scan_file_id=old_scan_file_id,
        editable_file_id=old_editable_file_id,
        task_id=task_id,
        created_by=user.id,
        updated_by=user.id,
        created_at=datetime(2026, 9, 30, tzinfo=UTC),
    )
    program.creator = user

    new_scan = File(
        id=uuid7(),
        s3_key="files/new-scan.pdf",
        original_name="new-scan.pdf",
        display_name="new-scan.pdf",
        extension=".pdf",
        size=4,
        mime_type="application/pdf",
        uploaded_at=datetime(2026, 9, 30, tzinfo=UTC),
        created_by=user.id,
        updated_by=user.id,
    )

    program_service = FakeProgramService(programs=[program])
    file_service = FakeFileService(new_scan)

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
    app.dependency_overrides[get_file_service] = lambda: file_service

    try:
        client = TestClient(app)

        response = client.post(
            f"/objects/urza/{urza_id}/programs/{program.id}/edit",
            data={
                "program_type": ProgramType.WORK.value,
                "program_number": "456",
            },
            files={
                "scan_file": (
                    "new-scan.pdf",
                    b"scan",
                    "application/pdf",
                ),
            },
        )

        assert response.status_code == 200, response.text
        assert len(file_service.upload_calls) == 1
        assert len(program_service.update_calls) == 1

        call = program_service.update_calls[0]

        # Новый скан передан сервису обновления.
        assert call["scan_file_id"] == new_scan.id

        # Другой файл не заменяется и не удаляется.
        assert call["editable_file_id"] is None
        assert call["remove_editable_file"] is False

        # Связанные данные исходного объекта не изменились.
        assert program.editable_file_id == old_editable_file_id
        assert program.task_id == task_id

    finally:
        app.dependency_overrides.clear()


def test_update_urza_program_replaces_only_editable_file(
    system_user_id,
) -> None:
    user = make_user(system_user_id=system_user_id)
    urza_id = uuid7()
    old_scan_file_id = uuid7()
    old_editable_file_id = uuid7()
    task_id = uuid7()

    program = Program(
        id=uuid7(),
        urza_id=urza_id,
        program_type=ProgramType.WORK,
        program_number="123",
        status=DocumentStatus.DRAFT,
        scan_file_id=old_scan_file_id,
        editable_file_id=old_editable_file_id,
        task_id=task_id,
        created_by=user.id,
        updated_by=user.id,
        created_at=datetime(2026, 9, 30, tzinfo=UTC),
    )
    program.creator = user

    new_editable = File(
        id=uuid7(),
        s3_key="files/new-editable.docx",
        original_name="new-editable.docx",
        display_name="new-editable.docx",
        extension=".docx",
        size=4,
        mime_type=(
            "application/vnd.openxmlformats-officedocument."
            "wordprocessingml.document"
        ),
        uploaded_at=datetime(2026, 9, 30, tzinfo=UTC),
        created_by=user.id,
        updated_by=user.id,
    )

    program_service = FakeProgramService(programs=[program])
    file_service = FakeFileService(new_editable)

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
    app.dependency_overrides[get_file_service] = lambda: file_service

    try:
        client = TestClient(app)

        response = client.post(
            f"/objects/urza/{urza_id}/programs/{program.id}/edit",
            data={
                "program_type": ProgramType.WORK.value,
                "program_number": "456",
            },
            files={
                "editable_file": (
                    "new-editable.docx",
                    b"docx",
                    (
                        "application/vnd.openxmlformats-officedocument."
                        "wordprocessingml.document"
                    ),
                ),
            },
        )

        assert response.status_code == 200
        assert len(file_service.upload_calls) == 1
        assert len(program_service.update_calls) == 1

        call = program_service.update_calls[0]

        # Новый редактируемый файл передан сервису.
        assert call["editable_file_id"] == new_editable.id

        # Скан не заменяется, удаление файла не запрашивается.
        assert call["scan_file_id"] is None
        assert call["remove_editable_file"] is False

        # Исходные ссылки на скан и задание сохраняются.
        assert program.scan_file_id == old_scan_file_id
        assert program.task_id == task_id

    finally:
        app.dependency_overrides.clear()


def test_update_urza_program_cleans_up_uploaded_file_on_update_error(
    system_user_id,
) -> None:
    user = make_user(system_user_id=system_user_id)
    urza_id = uuid7()

    program = Program(
        id=uuid7(),
        urza_id=urza_id,
        program_type=ProgramType.WORK,
        program_number="123",
        status=DocumentStatus.DRAFT,
        scan_file_id=uuid7(),
        editable_file_id=None,
        created_by=user.id,
        updated_by=user.id,
        created_at=datetime(2026, 9, 30, tzinfo=UTC),
    )
    program.creator = user

    new_scan = File(
        id=uuid7(),
        s3_key="files/new-scan.pdf",
        original_name="new-scan.pdf",
        display_name="new-scan.pdf",
        extension=".pdf",
        size=4,
        mime_type="application/pdf",
        uploaded_at=datetime(2026, 9, 30, tzinfo=UTC),
        created_by=user.id,
        updated_by=user.id,
    )

    class FailingProgramService(FakeProgramService):
        async def update(self, **kwargs):
            raise ValueError("Ошибка обновления программы.")

    program_service = FailingProgramService(programs=[program])
    file_service = FakeFileService(new_scan)

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
    app.dependency_overrides[get_file_service] = lambda: file_service

    try:
        client = TestClient(app)

        response = client.post(
            f"/objects/urza/{urza_id}/programs/{program.id}/edit",
            data={
                "program_type": ProgramType.WORK.value,
                "program_number": "456",
            },
            files={
                "scan_file": (
                    "new-scan.pdf",
                    b"scan",
                    "application/pdf",
                ),
            },
        )

        assert response.status_code == 400
        assert response.json()["detail"] == (
            "Ошибка обновления программы."
        )
        assert file_service.storage.delete_calls == [
            {"key": "files/new-scan.pdf"},
        ]

        # Исходные данные программы не изменились.
        assert program.program_number == "123"

    finally:
        app.dependency_overrides.clear()


def test_update_urza_program_removes_editable_file(system_user_id) -> None:
    user = make_user(system_user_id=system_user_id)
    urza_id = uuid7()
    old_editable_file_id = uuid7()

    program = Program(
        id=uuid7(),
        urza_id=urza_id,
        program_type=ProgramType.WORK,
        program_number="123",
        status=DocumentStatus.DRAFT,
        scan_file_id=uuid7(),
        editable_file_id=old_editable_file_id,
        created_by=user.id,
        updated_by=user.id,
        created_at=datetime(2026, 9, 30, tzinfo=UTC),
    )
    program.creator = user

    program_service = FakeProgramService(programs=[program])
    file_service = FakeFileService(
        File(
            id=uuid7(),
            s3_key="files/unused.pdf",
            original_name="unused.pdf",
            display_name="unused.pdf",
            extension=".pdf",
            size=4,
            mime_type="application/pdf",
            uploaded_at=datetime(2026, 9, 30, tzinfo=UTC),
            created_by=user.id,
            updated_by=user.id,
        )
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
    app.dependency_overrides[get_file_service] = lambda: file_service

    try:
        client = TestClient(app)

        response = client.post(
            f"/objects/urza/{urza_id}/programs/{program.id}/edit",
            data={
                "program_type": ProgramType.WORK.value,
                "program_number": "123",
                "remove_editable_file": "true",
            },
        )

        assert response.status_code == 200
        assert file_service.upload_calls == []
        assert len(program_service.update_calls) == 1

        call = program_service.update_calls[0]
        assert call["scan_file_id"] is None
        assert call["editable_file_id"] is None
        assert call["remove_editable_file"] is True

        assert program.editable_file_id is None

    finally:
        app.dependency_overrides.clear()


def test_update_urza_program_cleans_up_scan_when_editable_upload_fails(
    system_user_id,
) -> None:
    user = make_user(system_user_id=system_user_id)
    urza_id = uuid7()

    program = Program(
        id=uuid7(),
        urza_id=urza_id,
        program_type=ProgramType.WORK,
        program_number="123",
        status=DocumentStatus.DRAFT,
        scan_file_id=uuid7(),
        editable_file_id=None,
        created_by=user.id,
        updated_by=user.id,
        created_at=datetime(2026, 9, 30, tzinfo=UTC),
    )
    program.creator = user

    new_scan = File(
        id=uuid7(),
        s3_key="files/new-scan.pdf",
        original_name="new-scan.pdf",
        display_name="new-scan.pdf",
        extension=".pdf",
        size=4,
        mime_type="application/pdf",
        uploaded_at=datetime(2026, 9, 30, tzinfo=UTC),
        created_by=user.id,
        updated_by=user.id,
    )

    class FailingEditableFileService(FakeFileService):
        def __init__(self) -> None:
            super().__init__(new_scan)
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
            self.upload_count += 1

            if self.upload_count == 1:
                return new_scan

            raise RuntimeError("Ошибка загрузки редактируемого файла.")

    program_service = FakeProgramService(programs=[program])
    file_service = FailingEditableFileService()

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
    app.dependency_overrides[get_file_service] = lambda: file_service

    try:
        client = TestClient(app, raise_server_exceptions=False)

        response = client.post(
            f"/objects/urza/{urza_id}/programs/{program.id}/edit",
            data={
                "program_type": ProgramType.WORK.value,
                "program_number": "456",
            },
            files=[
                ("scan_file", ("new-scan.pdf", b"scan", "application/pdf")),
                (
                    "editable_file",
                    (
                        "editable.docx",
                        b"editable",
                        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    ),
                ),
            ],
        )

        assert response.status_code == 500
        assert file_service.upload_count == 2
        assert file_service.storage.delete_calls == [
            {"key": "files/new-scan.pdf"},
        ]
        assert program_service.update_calls == []
        assert program.program_number == "123"

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
        uploaded_at=datetime(2026, 9, 30, tzinfo=UTC),
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
        uploaded_at=datetime(2026, 9, 30, tzinfo=UTC),
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
        uploaded_at=datetime(2026, 9, 30, tzinfo=UTC),
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


def test_create_urza_program_empty_editable_file_cleans_up_scan(
    system_user_id,
) -> None:
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
        uploaded_at=datetime(2026, 9, 30, tzinfo=UTC),
        created_by=user.id,
        updated_by=user.id,
    )

    file_service = FakeFileService(scan_file)
    program_service = FakeProgramService()

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
    app.dependency_overrides[get_file_service] = lambda: file_service

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
                    ("program.pdf", b"scan", "application/pdf"),
                ),
                (
                    "editable_file",
                    ("program.docx", b"", "application/octet-stream"),
                ),
            ],
        )

        assert response.status_code == 400
        assert response.json()["detail"] == "Загруженный редактируемый файл пуст."
        assert file_service.storage.delete_calls == [
            {"key": scan_file.s3_key},
        ]
        assert program_service.programs == []

    finally:
        app.dependency_overrides.clear()


def test_create_urza_program_cleans_up_files_on_create_error(
    system_user_id,
) -> None:
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
        uploaded_at=datetime(2026, 9, 30, tzinfo=UTC),
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
        uploaded_at=datetime(2026, 9, 30, tzinfo=UTC),
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
            return (
                scan_file
                if self.upload_count == 1
                else editable_file
            )

    file_service = FakeFileServiceWithEditable()
    program_service = FakeProgramService(
        create_error=ValueError("Ошибка создания программы"),
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
    app.dependency_overrides[get_file_service] = lambda: file_service

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
                    ("program.pdf", b"scan", "application/pdf"),
                ),
                (
                    "editable_file",
                    (
                        "program.docx",
                        b"editable",
                        "application/octet-stream",
                    ),
                ),
            ],
        )

        assert response.status_code == 400
        assert response.json()["detail"] == "Ошибка создания программы"
        assert file_service.storage.delete_calls == [
            {"key": scan_file.s3_key},
            {"key": editable_file.s3_key},
        ]
        assert program_service.programs == []

    finally:
        app.dependency_overrides.clear()



def test_create_urza_program_cleans_up_scan_when_editable_upload_fails(
    system_user_id,
) -> None:
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
        uploaded_at=datetime(2026, 9, 30, tzinfo=UTC),
        created_by=user.id,
        updated_by=user.id,
    )

    class FakeFileServiceWithUploadError(FakeFileService):
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

            raise RuntimeError("Ошибка загрузки редактируемого файла")

    file_service = FakeFileServiceWithUploadError()
    program_service = FakeProgramService()

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
    app.dependency_overrides[get_file_service] = lambda: file_service

    try:
        client = TestClient(app, raise_server_exceptions=False)

        response = client.post(
            f"/objects/urza/{urza_id}/programs",
            data={
                "program_type": ProgramType.WORK.value,
                "program_number": "1",
            },
            files=[
                (
                    "scan_file",
                    ("program.pdf", b"scan", "application/pdf"),
                ),
                (
                    "editable_file",
                    (
                        "program.docx",
                        b"editable",
                        "application/octet-stream",
                    ),
                ),
            ],
        )

        assert response.status_code == 500
        assert len(file_service.upload_calls) == 2
        assert file_service.storage.delete_calls == [
            {"key": scan_file.s3_key},
        ]
        assert program_service.programs == []

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
        created_at=datetime(2026, 9, 30, tzinfo=UTC),
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
        created_at=datetime(2026, 9, 30, tzinfo=UTC),
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
        created_at=datetime(2026, 9, 30, tzinfo=UTC),
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
        urza_id, DocumentStatus.APPROVED, deleted_at=datetime.now(UTC)
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
