from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from uuid6 import uuid7

from app.application.connections.schemas import ConnectionListItem
from app.application.connections.service import ConnectionNameConflictError
from app.application.enterprises.schemas import EnterpriseDetails
from app.application.objects.exceptions import (
    ObjectAccessDeniedError,
    ObjectNotFoundError,
)
from app.application.objects.schemas import SelectedObject
from app.application.objects.service import ObjectService
from app.application.files.access_service import FileAccessService
from app.application.files.owners import FileAccessTargetType, FileOwner, FileOwnerType
from app.application.rza_instructions.service import RZAInstructionService
from app.application.selectivity_schemes.service import SelectivitySchemeService
from app.application.programs.service import ProgramService
from app.application.schema.service import SchemaService
from app.application.settings.service import SettingsService
from app.application.urza_instructions.service import URZAInstructionService
from app.application.substations.schemas import SubstationDetails
from app.application.tree.service import TreeService
from app.application.urzas.service import URZANameConflictError
from app.domain.enums import (
    AccessCategory,
    DocumentStatus,
    EnterpriseType,
    HighestVoltage,
    OperationalCurrentType,
    ProgramType,
    TaskStatus,
    TaskWorkType,
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
    get_access_service,
    get_enterprise_service,
    get_file_service,
    get_file_access_service,
    get_inspection_service,
    get_inspection_task_service,
    get_inspection_task_repository,
    get_object_service,
    get_maintenance_service,
    get_otd_service,
    get_program_service,
    get_rza_instruction_service,
    get_schema_service,
    get_selectivity_scheme_service,
    get_settings_service,
    get_substation_service,
    get_task_service,
    get_task_repository,
    get_tree_service,
    get_urza_instruction_service,
    get_urza_service,
)


class FakeEnterpriseService:
    def __init__(self):
        self.updated = None

    async def get_department(self, enterprise_id: UUID) -> EnterpriseDetails:
        values = self.updated or {
            "full_name": "Производственное отделение",
            "short_name": "ПО-1",
            "sap_code": "SAP-DEP-001",
        }
        return EnterpriseDetails(id=enterprise_id, **values)

    async def update_department(self, enterprise_id, data, *, actor_id):
        self.updated = data.model_dump()
        return EnterpriseDetails(id=enterprise_id, **self.updated)


class FakeDepartmentSubstationService:
    def __init__(self):
        self.create_calls = []

    async def create(self, *, enterprise_id, actor_id, data):
        self.create_calls.append({
            "enterprise_id": enterprise_id,
            "actor_id": actor_id,
            "data": data,
        })
        return SimpleNamespace(id=uuid7())


class FakeSubstationService:
    def __init__(self, *, missing=False):
        self.updated = None
        self.missing = missing

    async def get_details(
        self, substation_id: UUID, *, include_archived: bool = False
    ) -> SubstationDetails:
        if self.missing:
            raise ObjectNotFoundError
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

    async def update_details(self, substation_id, actor_id, data):
        self.updated = data.model_dump()
        return SubstationDetails(id=substation_id, **self.updated)



class FakeURZAService:
    def __init__(self, details, *, error=None):
        self.details = details
        self.error = error
        self.update_calls = []

    async def get_details(self, urza_id, *, include_archived: bool = False):
        if self.details is None:
            raise ObjectNotFoundError
        return self.details

    async def update(self, **kwargs):
        self.update_calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return self.details


class FakeURZACreationService:
    def __init__(self, *, error=None):
        self.error = error
        self.create_calls = []
        self.urza = None

    async def create(self, **kwargs):
        self.create_calls.append(kwargs)
        if self.error:
            raise self.error

        self.urza = SimpleNamespace(
            id=uuid7(),
            dispatch_name=kwargs["data"].dispatch_name,
        )
        return self.urza

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


class FakeConnectionCreationService:
    def __init__(self, *, error=None):
        self.error = error
        self.create_calls = []
        self.connection = None
        self.update_calls = []

    async def create(self, **kwargs):
        self.create_calls.append(kwargs)
        if self.error:
            raise self.error
        self.connection = SimpleNamespace(
            id=uuid7(), dispatch_name=kwargs["data"].dispatch_name,
            sap_code=kwargs["data"].sap_code,
            asureo_code=kwargs["data"].asureo_code,
            rdu_subordination=kwargs["data"].rdu_subordination,
            substation_id=kwargs["substation_id"],
        )
        return self.connection

    async def get_by_id(self, connection_id, *, include_archived: bool = False):
        if self.connection and self.connection.id == connection_id:
            return self.connection
        return None

    async def update(self, *, connection_id, actor_id, data):
        self.update_calls.append(
            {
                "connection_id": connection_id,
                "actor_id": actor_id,
                "data": data,
            }
        )

        if self.error:
            raise self.error

        if self.connection is None or self.connection.id != connection_id:
            return None

        self.connection.dispatch_name = data.dispatch_name
        self.connection.rdu_subordination = data.rdu_subordination
        self.connection.sap_code = data.sap_code
        self.connection.asureo_code = data.asureo_code

        return self.connection


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



def make_urza_details(urza_id, connection_id):
    return SimpleNamespace(
        id=urza_id,
        dispatch_name="МП РЗА 110 кВ",
        rdu_subordination=True,
        inventory_number="INV-001",
        commissioning_date=date(2025, 1, 15),
        status=SimpleNamespace(value="in_operation"),
        element_base=SimpleNamespace(value="microprocessor"),
        category=SimpleNamespace(value="II"),
        room_category=SimpleNamespace(value="I"),
        complexity=False,
        connection=SimpleNamespace(
            id=connection_id,
            dispatch_name="ВЛ 110 кВ",
        ),
        substation=SimpleNamespace(
            id=uuid7(),
            dispatch_name="ПС Центральная",
        ),
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
        *,
        include_archived: bool = False,
    ) -> SelectedObject:
        if self.error is not None:
            raise self.error

        assert self.result is not None
        assert self.result.object_type == object_type
        assert self.result.id == object_id
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


def override_enterprise_service(service: FakeEnterpriseService):
    def dependency():
        return service

    return dependency


def override_department_substation_service(
    service: FakeDepartmentSubstationService,
):
    def dependency():
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
            assert saved.text.count('id="substation-tab-content"') == 1
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


@pytest.mark.parametrize("role", [UserRole.ADMIN, UserRole.MANAGER, UserRole.SUPERADMIN])
def test_new_connection_form_allows_creation_roles(role):
    user = make_user(uuid7())
    user.role = role
    substation_id = uuid7()
    app.dependency_overrides[get_current_user] = override_user(user)
    app.dependency_overrides[get_object_service] = override_object_service(
        FakeObjectService(result=SelectedObject(
            object_type="substation", id=substation_id, name="ПС",
        )),
    )
    app.dependency_overrides[get_substation_service] = override_substation_service(FakeSubstationService())
    app.dependency_overrides[get_tree_service] = lambda: FakeTreeService()
    try:
        response = TestClient(app).get(
            f"/objects/substation/{substation_id}/connections/new",
            headers={"HX-Request": "true"},
        )
        assert response.status_code == 200
        assert "Добавление присоединения" in response.text
    finally:
        app.dependency_overrides.clear()


def test_new_connection_form_regular_get_returns_full_page():
    user = make_user(uuid7())
    user.role = UserRole.MANAGER
    substation_id = uuid7()
    app.dependency_overrides[get_current_user] = override_user(user)
    app.dependency_overrides[get_object_service] = override_object_service(
        FakeObjectService(result=SelectedObject(
            object_type="substation", id=substation_id, name="ПС",
        )),
    )
    app.dependency_overrides[get_substation_service] = override_substation_service(FakeSubstationService())
    app.dependency_overrides[get_tree_service] = lambda: FakeTreeService()
    try:
        response = TestClient(app).get(
            f"/objects/substation/{substation_id}/connections/new",
        )
        assert response.status_code == 200
        assert "<!doctype html>" in response.text
        assert 'id="object-content"' in response.text
        assert 'name="dispatch_name"' in response.text
    finally:
        app.dependency_overrides.clear()


@pytest.mark.parametrize("role", [UserRole.ENGINEER, UserRole.SPECIALIST])
def test_new_connection_form_denies_read_only_roles(role):
    user = make_user(uuid7())
    user.role = role
    substation_id = uuid7()
    app.dependency_overrides[get_current_user] = override_user(user)
    app.dependency_overrides[get_object_service] = override_object_service(
        FakeObjectService(result=SelectedObject(
            object_type="substation", id=substation_id, name="ПС",
        )),
    )
    app.dependency_overrides[get_substation_service] = override_substation_service(FakeSubstationService())
    app.dependency_overrides[get_tree_service] = lambda: FakeTreeService()
    try:
        response = TestClient(app).get(
            f"/objects/substation/{substation_id}/connections/new",
        )
        assert response.status_code == 403
    finally:
        app.dependency_overrides.clear()


@pytest.mark.parametrize("role", [UserRole.ENGINEER, UserRole.SPECIALIST])
def test_create_connection_post_denies_read_only_roles(role):
    user = make_user(uuid7())
    user.role = role
    substation_id = uuid7()
    app.dependency_overrides[get_current_user] = override_user(user)
    app.dependency_overrides[get_object_service] = override_object_service(
        FakeObjectService(result=SelectedObject(
            object_type="substation", id=substation_id, name="ПС",
        )),
    )
    app.dependency_overrides[get_substation_service] = override_substation_service(FakeSubstationService())
    app.dependency_overrides[get_connection_service] = override_connection_service(
        FakeConnectionCreationService(),
    )
    app.dependency_overrides[get_tree_service] = lambda: FakeTreeService()
    try:
        response = TestClient(app).post(
            f"/objects/substation/{substation_id}/connections",
            data={"dispatch_name": "ВЛ", "rdu_subordination": "true"},
        )
        assert response.status_code == 403
    finally:
        app.dependency_overrides.clear()


def test_create_connection_denies_when_parent_access_is_missing():
    user = make_user(uuid7())
    user.role = UserRole.ADMIN
    substation_id = uuid7()
    app.dependency_overrides[get_current_user] = override_user(user)
    app.dependency_overrides[get_object_service] = override_object_service(
        FakeObjectService(error=ObjectAccessDeniedError()),
    )
    app.dependency_overrides[get_substation_service] = override_substation_service(FakeSubstationService())
    app.dependency_overrides[get_connection_service] = override_connection_service(
        FakeConnectionCreationService(),
    )
    try:
        response = TestClient(app).post(
            f"/objects/substation/{substation_id}/connections",
            data={"dispatch_name": "ВЛ", "rdu_subordination": "true"},
        )
        assert response.status_code == 403
    finally:
        app.dependency_overrides.clear()


def test_create_connection_returns_404_when_substation_is_missing():
    user = make_user(uuid7())
    user.role = UserRole.ADMIN
    substation_id = uuid7()
    app.dependency_overrides[get_current_user] = override_user(user)
    app.dependency_overrides[get_substation_service] = override_substation_service(
        FakeSubstationService(missing=True),
    )
    app.dependency_overrides[get_tree_service] = lambda: FakeTreeService()
    try:
        response = TestClient(app).get(
            f"/objects/substation/{substation_id}/connections/new",
        )
        assert response.status_code == 404
    finally:
        app.dependency_overrides.clear()


@pytest.mark.parametrize("headers,expected_status", [({"HX-Request": "true"}, 204), ({}, 303)])
def test_create_connection_success_redirects_to_connection_card(headers, expected_status):
    user = make_user(uuid7())
    user.role = UserRole.ADMIN
    substation_id = uuid7()
    service = FakeConnectionCreationService()
    app.dependency_overrides[get_current_user] = override_user(user)
    app.dependency_overrides[get_object_service] = override_object_service(
        FakeObjectService(result=SelectedObject(
            object_type="substation", id=substation_id, name="ПС",
        )),
    )
    app.dependency_overrides[get_substation_service] = override_substation_service(FakeSubstationService())
    app.dependency_overrides[get_connection_service] = override_connection_service(service)
    app.dependency_overrides[get_tree_service] = lambda: FakeTreeService()
    try:
        response = TestClient(app).post(
            f"/objects/substation/{substation_id}/connections",
            headers=headers,
            data={
                "dispatch_name": " ВЛ 110 кВ ", "rdu_subordination": "false",
                "sap_code": "", "asureo_code": "ASU-1",
            },
            follow_redirects=False,
        )
        assert response.status_code == expected_status
        connection = service.create_calls[0]["data"]
        assert service.create_calls[0]["substation_id"] == substation_id
        assert connection.dispatch_name == "ВЛ 110 кВ"
        assert connection.rdu_subordination is False
        assert connection.sap_code is None
        assert connection.asureo_code == "ASU-1"
        assert response.headers["HX-Redirect" if expected_status == 204 else "location"] == (
            f"/objects/connection/{service.connection.id}"
        )
    finally:
        app.dependency_overrides.clear()


@pytest.mark.parametrize(
    "headers,full_page",
    [({}, True), ({"HX-Request": "true"}, False)],
)
@pytest.mark.parametrize(
    "role,can_create_urza",
    [
        (UserRole.ADMIN, True),
        (UserRole.MANAGER, True),
        (UserRole.SUPERADMIN, True),
        (UserRole.ENGINEER, False),
        (UserRole.SPECIALIST, False),
    ],
)
def test_connection_card_route_supports_full_page_and_htmx(
    headers,
    full_page,
    role,
    can_create_urza,
):
    user = make_user(uuid7())
    user.role = role
    connection_id = uuid7()
    service = FakeConnectionCreationService()
    service.connection = SimpleNamespace(
        id=connection_id, dispatch_name="ВЛ 110 кВ", sap_code=None,
        asureo_code=None, rdu_subordination=False,
    )
    app.dependency_overrides[get_current_user] = override_user(user)
    app.dependency_overrides[get_object_service] = override_object_service(
        FakeObjectService(result=SelectedObject(
            object_type="connection", id=connection_id, name="ВЛ 110 кВ",
        )),
    )
    app.dependency_overrides[get_connection_service] = override_connection_service(service)
    app.dependency_overrides[get_substation_service] = override_substation_service(FakeSubstationService())
    app.dependency_overrides[get_urza_service] = lambda: FakeURZAService(None)
    app.dependency_overrides[get_otd_service] = lambda: FakeOTDService()
    app.dependency_overrides[get_settings_service] = lambda: FakeSettingsService()
    app.dependency_overrides[get_task_service] = lambda: FakeTaskService()
    app.dependency_overrides[get_tree_service] = lambda: FakeTreeService()
    try:
        response = TestClient(app).get(
            f"/objects/connection/{connection_id}", headers=headers,
        )
        assert response.status_code == 200
        assert ("<!doctype html>" in response.text) is full_page
        assert "ВЛ 110 кВ" in response.text
        assert ("Добавить УРЗА" in response.text) is can_create_urza
        assert (
                       f'href="/objects/connection/{connection_id}/edit"' in response.text
               ) is can_create_urza
    finally:
        app.dependency_overrides.clear()



@pytest.mark.parametrize(
    "headers,expected_status",
    [({}, 303), ({"HX-Request": "true"}, 204)],
)
def test_edit_connection_success_redirects_to_connection_card(
    headers,
    expected_status,
):
    user = make_user(uuid7())
    user.role = UserRole.ADMIN
    connection_id = uuid7()
    substation_id = uuid7()

    service = FakeConnectionCreationService()
    service.connection = SimpleNamespace(
        id=connection_id,
        substation_id=substation_id,
        dispatch_name="Старое имя",
        rdu_subordination=False,
        sap_code="SAP-OLD",
        asureo_code="ASU-OLD",
    )

    app.dependency_overrides[get_current_user] = override_user(user)
    app.dependency_overrides[get_object_service] = override_object_service(
        FakeObjectService(
            result=SelectedObject(
                object_type="connection",
                id=connection_id,
                name="Старое имя",
            )
        )
    )
    app.dependency_overrides[get_connection_service] = (
        override_connection_service(service)
    )

    try:
        with TestClient(app) as client:
            response = client.post(
                f"/objects/connection/{connection_id}",
                headers=headers,
                data={
                    "dispatch_name": "ВЛ 110 кВ",
                    "rdu_subordination": "true",
                    "sap_code": "SAP-NEW",
                    "asureo_code": "ASU-NEW",
                },
                follow_redirects=False,
            )

        assert response.status_code == expected_status
        assert service.connection.dispatch_name == "ВЛ 110 кВ"
        assert service.connection.rdu_subordination is True
        assert service.connection.sap_code == "SAP-NEW"
        assert service.connection.asureo_code == "ASU-NEW"

        call = service.update_calls[0]
        assert call["connection_id"] == connection_id
        assert call["actor_id"] == user.id
        assert call["data"].dispatch_name == "ВЛ 110 кВ"

        redirect_header = "HX-Redirect" if expected_status == 204 else "location"
        assert response.headers[redirect_header] == (
            f"/objects/connection/{connection_id}"
        )
    finally:
        app.dependency_overrides.clear()



@pytest.mark.parametrize(
    "headers,full_page",
    [({}, True), ({"HX-Request": "true"}, False)],
)
def test_edit_connection_form_shows_current_values(headers, full_page):
    user = make_user(uuid7())
    user.role = UserRole.ADMIN
    connection_id = uuid7()
    substation_id = uuid7()

    service = FakeConnectionCreationService()
    service.connection = SimpleNamespace(
        id=connection_id,
        substation_id=substation_id,
        dispatch_name="ВЛ 110 кВ",
        rdu_subordination=True,
        sap_code="SAP-123",
        asureo_code="ASU-456",
    )

    app.dependency_overrides[get_current_user] = override_user(user)
    app.dependency_overrides[get_object_service] = override_object_service(
        FakeObjectService(
            result=SelectedObject(
                object_type="connection",
                id=connection_id,
                name="ВЛ 110 кВ",
            )
        )
    )
    app.dependency_overrides[get_connection_service] = (
        override_connection_service(service)
    )
    app.dependency_overrides[get_tree_service] = lambda: FakeTreeService()

    try:
        with TestClient(app) as client:
            response = client.get(
                f"/objects/connection/{connection_id}/edit",
                headers=headers,
            )

        assert response.status_code == 200
        assert ("<!doctype html>" in response.text) is full_page
        assert "Редактирование присоединения" in response.text
        assert f'action="/objects/connection/{connection_id}"' in response.text
        assert 'value="ВЛ 110 кВ"' in response.text
        assert 'value="SAP-123"' in response.text
        assert 'value="ASU-456"' in response.text
        assert "Сохранить изменения" in response.text
    finally:
        app.dependency_overrides.clear()



def test_edit_connection_name_conflict_rerenders_form_with_values():
    user = make_user(uuid7())
    user.role = UserRole.MANAGER
    connection_id = uuid7()
    substation_id = uuid7()

    service = FakeConnectionCreationService(
        error=ConnectionNameConflictError("Присоединение с таким именем уже существует.")
    )
    service.connection = SimpleNamespace(
        id=connection_id,
        substation_id=substation_id,
        dispatch_name="Старое имя",
        rdu_subordination=False,
        sap_code="SAP-OLD",
        asureo_code="ASU-OLD",
    )

    app.dependency_overrides[get_current_user] = override_user(user)
    app.dependency_overrides[get_object_service] = override_object_service(
        FakeObjectService(
            result=SelectedObject(
                object_type="connection",
                id=connection_id,
                name="Старое имя",
            )
        )
    )
    app.dependency_overrides[get_connection_service] = (
        override_connection_service(service)
    )
    app.dependency_overrides[get_tree_service] = lambda: FakeTreeService()

    try:
        with TestClient(app) as client:
            response = client.post(
                f"/objects/connection/{connection_id}",
                headers={"HX-Request": "true"},
                data={
                    "dispatch_name": "Новое имя",
                    "rdu_subordination": "true",
                    "sap_code": "SAP-NEW",
                    "asureo_code": "ASU-NEW",
                },
            )

        assert response.status_code == 422
        assert "Присоединение с таким именем уже существует." in response.text
        assert "Новое имя" in response.text
        assert "SAP-NEW" in response.text
        assert "ASU-NEW" in response.text
        assert len(service.update_calls) == 1
    finally:
        app.dependency_overrides.clear()



@pytest.mark.parametrize("role", [UserRole.ENGINEER, UserRole.SPECIALIST])
def test_edit_connection_post_denies_read_only_roles(role):
    user = make_user(uuid7())
    user.role = role
    connection_id = uuid7()

    service = FakeConnectionCreationService()
    service.connection = SimpleNamespace(
        id=connection_id,
        substation_id=uuid7(),
        dispatch_name="ВЛ 110 кВ",
        rdu_subordination=False,
        sap_code=None,
        asureo_code=None,
    )

    app.dependency_overrides[get_current_user] = override_user(user)
    app.dependency_overrides[get_object_service] = override_object_service(
        FakeObjectService(
            result=SelectedObject(
                object_type="connection",
                id=connection_id,
                name="ВЛ 110 кВ",
            )
        )
    )
    app.dependency_overrides[get_connection_service] = (
        override_connection_service(service)
    )

    try:
        with TestClient(app) as client:
            response = client.post(
                f"/objects/connection/{connection_id}",
                data={
                    "dispatch_name": "Новое имя",
                    "rdu_subordination": "true",
                },
            )

        assert response.status_code == 403
        assert service.update_calls == []
    finally:
        app.dependency_overrides.clear()



@pytest.mark.parametrize(
    "service_error,message",
    [(None, "Проверьте введённые значения."),
     (ConnectionNameConflictError("Дубликат имени."), "Дубликат имени.")],
)
def test_create_connection_form_rerenders_errors_and_values(service_error, message):
    user = make_user(uuid7())
    user.role = UserRole.MANAGER
    substation_id = uuid7()
    service = FakeConnectionCreationService(error=service_error)
    app.dependency_overrides[get_current_user] = override_user(user)
    app.dependency_overrides[get_object_service] = override_object_service(
        FakeObjectService(result=SelectedObject(
            object_type="substation", id=substation_id, name="ПС",
        )),
    )
    app.dependency_overrides[get_substation_service] = override_substation_service(FakeSubstationService())
    app.dependency_overrides[get_connection_service] = override_connection_service(service)
    app.dependency_overrides[get_tree_service] = lambda: FakeTreeService()
    try:
        response = TestClient(app).post(
            f"/objects/substation/{substation_id}/connections",
            headers={"HX-Request": "true"},
            data={
                "dispatch_name": "Имя пользователя",
                "rdu_subordination": "true" if service_error else "nope",
                "sap_code": "SAP",
            },
        )
        assert response.status_code == 422
        assert message in response.text
        assert "Имя пользователя" in response.text
        assert "SAP" in response.text
        assert "event.detail.xhr.status === 422" in response.text
    finally:
        app.dependency_overrides.clear()


@pytest.mark.parametrize(
    "role",
    [UserRole.ADMIN, UserRole.MANAGER, UserRole.SUPERADMIN],
)
def test_new_urza_form_allows_creation_roles(role):
    user = make_user(uuid7())
    user.role = role
    connection_id = uuid7()

    app.dependency_overrides[get_current_user] = override_user(user)
    app.dependency_overrides[get_object_service] = override_object_service(
        FakeObjectService(
            result=SelectedObject(
                object_type="connection",
                id=connection_id,
                name="ВЛ 110 кВ",
            ),
        )
    )
    app.dependency_overrides[get_tree_service] = lambda: FakeTreeService()

    try:
        response = TestClient(app).get(
            f"/objects/connection/{connection_id}/urzas/new",
            headers={"HX-Request": "true"},
        )

        assert response.status_code == 200
        assert "Новое УРЗА" in response.text
        assert 'name="dispatch_name"' in response.text
        assert "обязательные поля" in response.text
    finally:
        app.dependency_overrides.clear()


@pytest.mark.parametrize(
    "role",
    [UserRole.ENGINEER, UserRole.SPECIALIST],
)
def test_new_urza_form_denies_read_only_roles(role):
    user = make_user(uuid7())
    user.role = role
    connection_id = uuid7()

    app.dependency_overrides[get_current_user] = override_user(user)
    app.dependency_overrides[get_object_service] = override_object_service(
        FakeObjectService(
            result=SelectedObject(
                object_type="connection",
                id=connection_id,
                name="ВЛ 110 кВ",
            ),
        )
    )

    try:
        response = TestClient(app).get(
            f"/objects/connection/{connection_id}/urzas/new",
        )

        assert response.status_code == 403
    finally:
        app.dependency_overrides.clear()


def test_create_urza_success_redirects_to_urza_card():
    user = make_user(uuid7())
    user.role = UserRole.ADMIN
    connection_id = uuid7()
    service = FakeURZACreationService()

    app.dependency_overrides[get_current_user] = override_user(user)
    app.dependency_overrides[get_object_service] = override_object_service(
        FakeObjectService(
            result=SelectedObject(
                object_type="connection",
                id=connection_id,
                name="ВЛ 110 кВ",
            ),
        )
    )
    app.dependency_overrides[get_urza_service] = lambda: service

    try:
        response = TestClient(app).post(
            f"/objects/connection/{connection_id}/urzas",
            headers={"HX-Request": "true"},
            data={
                "dispatch_name": "  МП РЗА 110 кВ  ",
                "rdu_subordination": "true",
                "inventory_number": "",
                "commissioning_date": "2026-10-01",
                "status": "in_operation",
                "element_base": "microprocessor",
                "category": "II",
                "room_category": "I",
                "complexity": "false",
            },
            follow_redirects=False,
        )

        assert response.status_code == 204
        assert response.headers["HX-Redirect"] == (
            f"/objects/urza/{service.urza.id}"
        )

        assert len(service.create_calls) == 1
        call = service.create_calls[0]
        assert call["connection_id"] == connection_id
        assert call["actor_id"] == user.id

        data = call["data"]
        assert data.dispatch_name == "МП РЗА 110 кВ"
        assert data.inventory_number is None
        assert data.rdu_subordination is True
        assert data.complexity is False
    finally:
        app.dependency_overrides.clear()



def test_urza_edit_success_redirects_to_urza_card():
    user = make_user(uuid7())
    user.role = UserRole.ADMIN
    urza_id = uuid7()
    connection_id = uuid7()
    service = FakeURZAService(make_urza_details(urza_id, connection_id))

    app.dependency_overrides[get_current_user] = override_user(user)
    app.dependency_overrides[get_object_service] = override_object_service(
        FakeObjectService(
            result=SelectedObject(
                object_type="urza",
                id=urza_id,
                name="МП РЗА 110 кВ",
            ),
        )
    )
    app.dependency_overrides[get_urza_service] = lambda: service

    try:
        with TestClient(app) as client:
            response = client.post(
                f"/objects/urza/{urza_id}/edit",
                headers={"HX-Request": "true"},
                data={
                    "dispatch_name": "МП РЗА 110 кВ обновлённое",
                    "rdu_subordination": "true",
                    "inventory_number": "INV-002",
                    "commissioning_date": "2025-01-15",
                    "status": "in_operation",
                    "element_base": "microprocessor",
                    "category": "II",
                    "room_category": "I",
                    "complexity": "false",
                },
                follow_redirects=False,
            )

        assert response.status_code == 204
        assert response.headers["HX-Redirect"] == f"/objects/urza/{urza_id}"
        assert len(service.update_calls) == 1

        call = service.update_calls[0]
        assert call["urza_id"] == urza_id
        assert call["actor_id"] == user.id
        assert call["data"].dispatch_name == "МП РЗА 110 кВ обновлённое"
        assert call["data"].inventory_number == "INV-002"
        assert call["data"].rdu_subordination is True
        assert call["data"].complexity is False
    finally:
        app.dependency_overrides.clear()


def test_urza_edit_name_conflict_returns_422():
    user = make_user(uuid7())
    user.role = UserRole.ADMIN
    urza_id = uuid7()
    connection_id = uuid7()
    service = FakeURZAService(
        make_urza_details(urza_id, connection_id),
        error=URZANameConflictError(
            "УРЗА с таким диспетчерским наименованием уже существует."
        ),
    )

    app.dependency_overrides[get_current_user] = override_user(user)
    app.dependency_overrides[get_object_service] = override_object_service(
        FakeObjectService(
            result=SelectedObject(
                object_type="urza",
                id=urza_id,
                name="МП РЗА 110 кВ",
            ),
        )
    )
    app.dependency_overrides[get_urza_service] = lambda: service

    try:
        with TestClient(app) as client:
            response = client.post(
                f"/objects/urza/{urza_id}/edit",
                headers={"HX-Request": "true"},
                data={
                    "dispatch_name": "Дублирующее наименование",
                    "rdu_subordination": "true",
                    "inventory_number": "",
                    "commissioning_date": "2025-01-15",
                    "status": "in_operation",
                    "element_base": "microprocessor",
                    "category": "II",
                    "room_category": "I",
                    "complexity": "false",
                },
            )

        assert response.status_code == 422
        assert "уже существует" in response.text
        assert len(service.update_calls) == 1
    finally:
        app.dependency_overrides.clear()



@pytest.mark.parametrize(
    "role",
    [UserRole.ENGINEER, UserRole.SPECIALIST],
)
def test_urza_edit_post_denied_for_read_only_roles(role):
    user = make_user(uuid7())
    user.role = role
    urza_id = uuid7()

    app.dependency_overrides[get_current_user] = override_user(user)

    try:
        with TestClient(app) as client:
            response = client.post(
                f"/objects/urza/{urza_id}/edit",
                data={
                    "dispatch_name": "Новое имя",
                    "rdu_subordination": "true",
                    "inventory_number": "",
                    "commissioning_date": "2025-01-15",
                    "status": "in_operation",
                    "element_base": "microprocessor",
                    "category": "II",
                    "room_category": "I",
                    "complexity": "false",
                },
            )

        assert response.status_code == 403
    finally:
        app.dependency_overrides.clear()



def test_urza_edit_invalid_data_returns_422():
    user = make_user(uuid7())
    user.role = UserRole.ADMIN
    urza_id = uuid7()
    connection_id = uuid7()
    service = FakeURZAService(make_urza_details(urza_id, connection_id))

    app.dependency_overrides[get_current_user] = override_user(user)
    app.dependency_overrides[get_object_service] = override_object_service(
        FakeObjectService(
            result=SelectedObject(
                object_type="urza",
                id=urza_id,
                name="МП РЗА 110 кВ",
            ),
        )
    )
    app.dependency_overrides[get_urza_service] = lambda: service

    try:
        with TestClient(app) as client:
            response = client.post(
                f"/objects/urza/{urza_id}/edit",
                data={
                    "dispatch_name": "",
                    "rdu_subordination": "true",
                    "inventory_number": "",
                    "commissioning_date": "2025-01-15",
                    "status": "in_operation",
                    "element_base": "microprocessor",
                    "category": "II",
                    "room_category": "I",
                    "complexity": "false",
                },
            )

        assert response.status_code == 422
        assert len(service.update_calls) == 0
    finally:
        app.dependency_overrides.clear()



@pytest.mark.parametrize(
    "role",
    [UserRole.ADMIN, UserRole.MANAGER, UserRole.SUPERADMIN],
)
def test_urza_edit_form_get_allowed_roles(role):
    user = make_user(uuid7())
    user.role = role
    urza_id = uuid7()
    connection_id = uuid7()

    app.dependency_overrides[get_current_user] = override_user(user)
    app.dependency_overrides[get_object_service] = override_object_service(
        FakeObjectService(
            result=SelectedObject(
                object_type="urza",
                id=urza_id,
                name="МП РЗА 110 кВ",
            ),
        )
    )
    app.dependency_overrides[get_urza_service] = lambda: FakeURZAService(
        make_urza_details(urza_id, connection_id)
    )

    try:
        with TestClient(app) as client:
            response = client.get(f"/objects/urza/{urza_id}/edit")

        assert response.status_code == 200
        assert "Редактирование УРЗА" in response.text
        assert "МП РЗА 110 кВ" in response.text
    finally:
        app.dependency_overrides.clear()


@pytest.mark.parametrize(
    "role",
    [UserRole.ENGINEER, UserRole.SPECIALIST],
)
def test_urza_edit_form_get_denied_for_read_only_roles(role):
    user = make_user(uuid7())
    user.role = role
    urza_id = uuid7()

    app.dependency_overrides[get_current_user] = override_user(user)

    try:
        with TestClient(app) as client:
            response = client.get(f"/objects/urza/{urza_id}/edit")

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
        assert (f'hx-get="/objects/substation/{object_id}/edit"' in response.text) is can_edit
        assert ("Добавить присоединение" in response.text) is can_edit
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
        assert file_service.archive_calls == [
            {"file_id": new_scan.id, "user_id": user.id},
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
        assert file_service.archive_calls == [
            {"file_id": new_scan.id, "user_id": user.id},
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
        assert file_service.archive_calls == [
            {"file_id": scan_file.id, "user_id": user.id},
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
        assert file_service.archive_calls == [
            {"file_id": scan_file.id, "user_id": user.id},
            {"file_id": editable_file.id, "user_id": user.id},
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
        assert file_service.archive_calls == [
            {"file_id": scan_file.id, "user_id": user.id},
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
        assert f'href="/files/{uploaded_file.id}/view"' in response.text
        assert f'href="/files/{uploaded_file.id}/download"' in response.text
    finally:
        app.dependency_overrides.clear()


def test_create_settings_record_denies_inaccessible_urza_before_upload(system_user_id):
    user = make_user(system_user_id)
    urza_id = uuid7()
    file_service = FakeFileService(settings_file(uuid7()))
    settings_service = FakeSettingsService()
    set_settings_dependencies(
        user,
        urza_id,
        settings_service,
        file_service,
        object_error=ObjectAccessDeniedError(),
    )
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

        assert response.status_code == 403
        assert not file_service.upload_calls
        assert not settings_service.calls
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


@pytest.mark.parametrize("role", [UserRole.ADMIN, UserRole.MANAGER, UserRole.ENGINEER])
def test_department_edit_post_denied_for_non_superadmin(role):
    user = make_user(uuid7())
    user.role = role
    enterprise_id = uuid7()

    app.dependency_overrides[get_current_user] = override_user(user)
    app.dependency_overrides[get_object_service] = override_object_service(
        FakeObjectService(
            result=SelectedObject(
                object_type="department",
                id=enterprise_id,
                name="Производственное отделение",
            )
        )
    )

    try:
        response = TestClient(app).post(
            f"/objects/department/{enterprise_id}/edit",
            data={
                "full_name": "Новое название",
                "short_name": "ПО-1",
                "sap_code": "SAP-DEP-001",
            },
        )
        assert response.status_code == 403
    finally:
        app.dependency_overrides.clear()


def test_department_edit_superadmin_updates_and_redirects():
    user = make_user(uuid7())
    user.role = UserRole.SUPERADMIN
    enterprise_id = uuid7()
    enterprise_service = FakeEnterpriseService()

    app.dependency_overrides[get_current_user] = override_user(user)
    app.dependency_overrides[get_object_service] = override_object_service(
        FakeObjectService(
            result=SelectedObject(
                object_type="department",
                id=enterprise_id,
                name="Производственное отделение",
            )
        )
    )
    app.dependency_overrides[get_enterprise_service] = override_enterprise_service(
        enterprise_service
    )

    try:
        response = TestClient(app).post(
            f"/objects/department/{enterprise_id}/edit",
            data={
                "full_name": "Новое производственное отделение",
                "short_name": "ПО-2",
                "sap_code": "SAP-DEP-002",
            },
            follow_redirects=False,
        )

        assert response.status_code == 303
        assert response.headers["location"] == f"/objects/department/{enterprise_id}"
        assert enterprise_service.updated == {
            "full_name": "Новое производственное отделение",
            "short_name": "ПО-2",
            "sap_code": "SAP-DEP-002",
        }
    finally:
        app.dependency_overrides.clear()


@pytest.mark.parametrize(
    "role",
    [UserRole.ADMIN, UserRole.MANAGER, UserRole.SUPERADMIN],
)
def test_department_substation_creation_allowed_roles(role):
    user = make_user(uuid7())
    user.role = role
    enterprise_id = uuid7()
    enterprise_service = FakeEnterpriseService()
    substation_service = FakeDepartmentSubstationService()

    app.dependency_overrides[get_current_user] = override_user(user)
    app.dependency_overrides[get_object_service] = override_object_service(
        FakeObjectService(
            result=SelectedObject(
                object_type="department",
                id=enterprise_id,
                name="Производственное отделение",
            )
        )
    )
    app.dependency_overrides[get_enterprise_service] = override_enterprise_service(
        enterprise_service
    )
    app.dependency_overrides[get_substation_service] = (
        override_department_substation_service(substation_service)
    )

    try:
        response = TestClient(app).post(
            f"/objects/department/{enterprise_id}/substations",
            data={
                "dispatch_name": "ПС Центральная",
                "highest_voltage": "110",
                "operational_current_type": "permanent",
                "sap_code": "SAP-001",
                "asureo_code": "ASUREO-001",
                "address": "Екатеринбург",
                "latitude": "56.8389",
                "longitude": "60.6057",
            },
            follow_redirects=False,
        )

        assert response.status_code == 303
        assert len(substation_service.create_calls) == 1

        call = substation_service.create_calls[0]
        assert call["enterprise_id"] == enterprise_id
        assert call["actor_id"] == user.id
        assert call["data"].dispatch_name == "ПС Центральная"
    finally:
        app.dependency_overrides.clear()


@pytest.mark.parametrize(
    "role",
    [UserRole.ENGINEER, UserRole.SPECIALIST],
)
def test_department_substation_creation_denied_for_read_only_roles(role):
    user = make_user(uuid7())
    user.role = role
    enterprise_id = uuid7()

    app.dependency_overrides[get_current_user] = override_user(user)
    app.dependency_overrides[get_object_service] = override_object_service(
        FakeObjectService(
            result=SelectedObject(
                object_type="department",
                id=enterprise_id,
                name="Производственное отделение",
            )
        )
    )

    try:
        response = TestClient(app).post(
            f"/objects/department/{enterprise_id}/substations",
            data={
                "dispatch_name": "ПС Центральная",
                "highest_voltage": "110",
                "operational_current_type": "permanent",
            },
        )
        assert response.status_code == 403
    finally:
        app.dependency_overrides.clear()


class _HTTPArchiveTreeAccess:
    def __init__(self, root):
        self.root = root

    async def get_accessible_enterprise_roots(self, _user_id):
        return [self.root]


class _HTTPArchiveEnterpriseRepository:
    def __init__(self, enterprises):
        self.enterprises = enterprises

    async def get_all_active(self):
        return self.enterprises


class _HTTPArchiveEntityRepository:
    def __init__(self, items, parent_field):
        self.items = items
        self.parent_field = parent_field

    async def get_by_enterprise_ids(self, ids, *, include_archived=False):
        return [
            item for item in self.items
            if item.enterprise_id in ids
            and (include_archived or item.deleted_at is None)
        ]

    async def get_by_substation_ids(self, ids, *, include_archived=False):
        return [
            item for item in self.items
            if item.substation_id in ids
            and (include_archived or item.deleted_at is None)
        ]

    async def get_by_connection_ids(self, ids, *, include_archived=False):
        return [
            item for item in self.items
            if item.connection_id in ids
            and (include_archived or item.deleted_at is None)
        ]


class _HTTPArchiveAccess:
    def __init__(self, allowed=True):
        self.allowed = allowed
        self.calls = []

    async def can_access_substation(self, *, user_id, substation_id):
        self.calls.append(("substation", user_id, substation_id))
        return self.allowed

    async def can_access_connection(self, *, user_id, connection_id):
        self.calls.append(("connection", user_id, connection_id))
        return self.allowed

    async def can_access_urza(self, *, user_id, urza_id):
        self.calls.append(("urza", user_id, urza_id))
        return self.allowed


class _HTTPArchiveObjectResolver:
    def __init__(self, result):
        self.result = result
        self.calls = []

    async def resolve(self, *, object_type, object_id, include_archived=False):
        self.calls.append((object_type, object_id, include_archived))
        if self.result is None or self.result.id != object_id:
            return None
        if self.result.is_archived and not include_archived:
            return None
        return self.result


def _http_archive_object_service(object_type, object_id, *, allowed=True):
    selected = SelectedObject(
        object_type=object_type,
        id=object_id,
        name="Archive test object",
        is_archived=True,
    )
    access = _HTTPArchiveAccess(allowed=allowed)
    resolver = _HTTPArchiveObjectResolver(selected)
    return ObjectService(access, resolver), access, resolver


def _install_unused_object_route_dependencies():
    for dependency in (
        get_connection_service,
        get_urza_service,
        get_otd_service,
        get_settings_service,
        get_otd_service,
        get_task_service,
        get_tree_service,
        get_enterprise_service,
    ):
        app.dependency_overrides[dependency] = lambda: SimpleNamespace()


def _http_tree_service():
    enterprise = SimpleNamespace(
        id=uuid7(), parent_id=None, type=EnterpriseType.DEPARTMENT,
        full_name="Visible department", short_name="Visible",
    )
    outside = SimpleNamespace(
        id=uuid7(), parent_id=None, type=EnterpriseType.DEPARTMENT,
        full_name="Outside department", short_name="Outside",
    )
    station = SimpleNamespace(
        id=uuid7(), enterprise_id=enterprise.id,
        dispatch_name="Active station", deleted_at=None,
    )
    archived_station = SimpleNamespace(
        id=uuid7(), enterprise_id=enterprise.id,
        dispatch_name="Relay archived station", deleted_at=datetime.now(UTC),
    )
    outside_station = SimpleNamespace(
        id=uuid7(), enterprise_id=outside.id,
        dispatch_name="Private station", deleted_at=None,
    )
    line = SimpleNamespace(
        id=uuid7(), substation_id=station.id,
        dispatch_name="Active line", deleted_at=None,
    )
    archived_line = SimpleNamespace(
        id=uuid7(), substation_id=station.id,
        dispatch_name="Relay archived line", deleted_at=datetime.now(UTC),
    )
    outside_line = SimpleNamespace(
        id=uuid7(), substation_id=outside_station.id,
        dispatch_name="Private line", deleted_at=None,
    )
    active_urza = SimpleNamespace(
        id=uuid7(), connection_id=line.id,
        dispatch_name="Relay active", deleted_at=None,
    )
    archived_urza = SimpleNamespace(
        id=uuid7(), connection_id=line.id,
        dispatch_name="Relay archived", deleted_at=datetime.now(UTC),
    )
    private_urza = SimpleNamespace(
        id=uuid7(), connection_id=outside_line.id,
        dispatch_name="Private relay", deleted_at=None,
    )
    service = TreeService(
        enterprise_repository=_HTTPArchiveEnterpriseRepository(
            [enterprise, outside]
        ),
        substation_repository=_HTTPArchiveEntityRepository(
            [station, archived_station, outside_station], "enterprise_id"
        ),
        connection_repository=_HTTPArchiveEntityRepository(
            [line, archived_line, outside_line], "substation_id"
        ),
        urza_repository=_HTTPArchiveEntityRepository(
            [active_urza, archived_urza, private_urza], "connection_id"
        ),
        access_service=_HTTPArchiveTreeAccess(enterprise),
    )
    return service, {
        "outside": [outside_station.id, outside_line.id, private_urza.id],
        "active": [station.id, line.id, active_urza.id],
        "archived": [archived_station.id, archived_line.id, archived_urza.id],
    }


def test_tree_http_empty_query_is_active_only_and_search_includes_archive():
    user = make_user(uuid7())
    tree_service, ids = _http_tree_service()
    app.dependency_overrides[get_current_user] = override_user(user)
    app.dependency_overrides[get_tree_service] = lambda: tree_service

    try:
        with TestClient(app) as client:
            empty = client.get("/objects/tree")
            assert empty.status_code == 200
            assert empty.headers["content-type"].startswith("text/html")
            assert "Active station" in empty.text
            assert "Private station" not in empty.text
            for archived_id in ids["archived"]:
                assert str(archived_id) not in empty.text

            searched = client.get(
                "/objects/tree?query=relay",
                headers={"HX-Request": "true"},
            )
            assert searched.status_code == 200
            assert 'id="app-sidebar-tree"' in searched.text
            assert "Relay active" in searched.text
            assert "Relay archived" in searched.text
            assert "Relay archived station" in searched.text
            assert searched.text.count('>Архив</span>') >= 3
            assert "Private relay" not in searched.text
            for result_id in [ids["active"][2], ids["archived"][2]]:
                assert searched.text.count(f'data-object-id="{result_id}"') == 1
            assert 'id="sidebar-archive-toggle"' in searched.text
            assert 'type="checkbox"' not in searched.text
    finally:
        app.dependency_overrides.clear()


def test_archived_substation_card_requires_scope_and_archive_flag():
    user = make_user(uuid7())
    user.role = UserRole.MANAGER
    substation_id = uuid7()
    substation_service = FakeSubstationService()
    object_service, access, resolver = _http_archive_object_service(
        "substation", substation_id
    )
    app.dependency_overrides[get_current_user] = override_user(user)
    app.dependency_overrides[get_object_service] = lambda: object_service
    app.dependency_overrides[get_substation_service] = lambda: substation_service
    _install_unused_object_route_dependencies()

    try:
        with TestClient(app) as client:
            response = client.get(
                f"/objects/substation/{substation_id}?archived=true",
                headers={"HX-Request": "true"},
            )
            assert response.status_code == 200
            assert "Архивная запись · только чтение" in response.text
            assert "Добавить присоединение" not in response.text
            assert resolver.calls[-1] == ("substation", substation_id, True)

            without_flag = client.get(
                f"/objects/substation/{substation_id}",
                headers={"HX-Request": "true"},
            )
            assert without_flag.status_code == 404

            access.allowed = False
            outside_scope = client.get(
                f"/objects/substation/{substation_id}?archived=true",
                headers={"HX-Request": "true"},
            )
            assert outside_scope.status_code == 403
            assert resolver.calls[-1] == ("substation", substation_id, False)
    finally:
        app.dependency_overrides.clear()


def test_archive_flag_does_not_allow_substation_mutation():
    user = make_user(uuid7())
    user.role = UserRole.MANAGER
    substation_id = uuid7()
    object_service, _, resolver = _http_archive_object_service(
        "substation", substation_id
    )
    substation_service = FakeSubstationService()
    app.dependency_overrides[get_current_user] = override_user(user)
    app.dependency_overrides[get_object_service] = lambda: object_service
    app.dependency_overrides[get_substation_service] = lambda: substation_service

    try:
        response = TestClient(app).post(
            f"/objects/substation/{substation_id}/edit?archived=true",
            data={
                "dispatch_name": "Changed",
                "highest_voltage": "110",
                "operational_current_type": "permanent",
            },
        )
        assert response.status_code == 404
        assert substation_service.updated is None
        assert resolver.calls == [("substation", substation_id, False)]
    finally:
        app.dependency_overrides.clear()


def test_archived_object_creation_routes_reject_direct_posts():
    user = make_user(uuid7())
    user.role = UserRole.MANAGER
    substation_id, connection_id, urza_id, instruction_id = (
        uuid7(), uuid7(), uuid7(), uuid7()
    )
    overrides = (
        get_substation_service,
        get_connection_service,
        get_urza_service,
        get_tree_service,
        get_settings_service,
        get_otd_service,
        get_task_service,
        get_file_service,
        get_program_service,
        get_schema_service,
        get_maintenance_service,
        get_rza_instruction_service,
        get_selectivity_scheme_service,
        get_inspection_task_service,
        get_inspection_task_repository,
        get_task_repository,
    )
    app.dependency_overrides[get_current_user] = override_user(user)
    for dependency in overrides:
        app.dependency_overrides[dependency] = lambda: SimpleNamespace()
    app.dependency_overrides[get_substation_service] = lambda: FakeSubstationService()

    cases = [
        (
            f"/objects/substation/{substation_id}/edit?archived=true",
            "substation", substation_id,
            {"dispatch_name": "Changed", "highest_voltage": "110",
             "operational_current_type": "permanent"}, None,
        ),
        (
            f"/objects/connection/{connection_id}?archived=true",
            "connection", connection_id,
            {"dispatch_name": "Changed"}, None,
        ),
        (
            f"/objects/connection/{connection_id}/urzas?archived=true",
            "connection", connection_id,
            {"dispatch_name": "Relay"}, None,
        ),
        (
            f"/objects/substation/{substation_id}/instructions?archived=true",
            "substation", substation_id, {}, None,
        ),
        (
            f"/objects/substation/{substation_id}/selectivity-schemes?archived=true",
            "substation", substation_id, {}, None,
        ),
        (
            f"/objects/substation/{substation_id}/inspection-tasks?archived=true",
            "substation", substation_id, {}, None,
        ),
        (
            f"/objects/urza/{urza_id}/settings?archived=true",
            "urza", urza_id,
            {"change_date": "2026-10-01", "parameter_name": "P",
             "initial_setting": "1", "new_setting": "2", "change_reason": "R"},
            None,
        ),
        (
            f"/objects/urza/{urza_id}/otd?archived=true",
            "urza", urza_id,
            {
                "effective_date": "2026-10-01",
                "urza_service_life": "25",
                "urza_purpose": "rza",
            },
            None,
        ),
        (
            f"/objects/urza/{urza_id}/programs?archived=true",
            "urza", urza_id,
            {"program_type": "commissioning", "program_number": "P-1"},
            {"scan_file": ("scan.pdf", b"scan", "application/pdf")},
        ),
        (
            f"/objects/urza/{urza_id}/schemas?archived=true",
            "urza", urza_id,
            {"schema_number": "S-1", "schema_name": "Schema",
             "change_description": "Change", "change_justification": "Reason",
             "upload_date": "2026-10-01"}, None,
        ),
        (
            f"/objects/urza/{urza_id}/instruction?archived=true",
            "urza", urza_id,
            {"effective_date": "2026-10-01"},
            {"scan_file": ("scan.pdf", b"scan", "application/pdf")},
        ),
        (
            f"/objects/urza/{urza_id}/instruction/{instruction_id}/versions"
            "?archived=true",
            "urza", urza_id,
            {"effective_date": "2026-10-01"},
            {"scan_file": ("scan.pdf", b"scan", "application/pdf")},
        ),
        (
            f"/objects/urza/{urza_id}/maintenance?archived=true",
            "urza", urza_id,
            {"maintenance_date": "2026-10-01", "maintenance_type": "В",
             "detected_deviations": "None", "measures_taken": "None"}, None,
        ),
    ]

    try:
        with TestClient(app) as client:
            for url, object_type, object_id, data, files in cases:
                object_service, _, resolver = _http_archive_object_service(
                    object_type, object_id
                )
                app.dependency_overrides[get_object_service] = lambda: object_service
                response = client.post(url, data=data, files=files)
                assert response.status_code == 404, (url, response.status_code, response.text)
                assert resolver.calls == [(object_type, object_id, False)], (
                    url, response.text, resolver.calls
                )
    finally:
        app.dependency_overrides.clear()


@pytest.mark.parametrize(
    ("path", "payload"),
    [
        (
            "/objects/urza/{urza_id}/settings/{record_id}",
            {
                "change_date": "2026-10-01",
                "parameter_name": "P",
                "initial_setting": "1",
                "new_setting": "2",
                "change_reason": "replacement",
            },
        ),
        (
            "/objects/urza/{urza_id}/schemas/{record_id}",
            {
                "schema_number": "S-1",
                "schema_name": "Schema",
                "change_description": "Change",
                "change_justification": "Reason",
                "upload_date": "2026-10-01",
            },
        ),
        (
            "/objects/urza/{urza_id}/programs/{record_id}/edit",
            {"program_type": "commissioning", "program_number": "P-1"},
        ),
        ("/objects/urza/{urza_id}/settings/{record_id}/delete", {}),
        ("/objects/urza/{urza_id}/schemas/{record_id}/delete", {}),
    ],
)
def test_archived_urza_rejects_document_update_replacement_and_delete(
    path, payload
):
    user = make_user(uuid7())
    urza_id, record_id = uuid7(), uuid7()
    app.dependency_overrides[get_current_user] = override_user(user)
    for dependency in (
        get_settings_service,
        get_schema_service,
        get_program_service,
        get_file_service,
        get_task_service,
        get_tree_service,
    ):
        app.dependency_overrides[dependency] = lambda: SimpleNamespace()

    try:
        object_service, _, resolver = _http_archive_object_service(
            "urza", urza_id
        )
        app.dependency_overrides[get_object_service] = lambda: object_service
        response = TestClient(app).post(
            path.format(urza_id=urza_id, record_id=record_id)
            + "?archived=true",
            data=payload,
        )
        assert response.status_code == 404
        assert resolver.calls == [("urza", urza_id, False)]
    finally:
        app.dependency_overrides.clear()


class _HTTPTaskArchiveAccess:
    def __init__(self, actor):
        self.user_repository = self
        self.urza_repository = SimpleNamespace(
            lock_active_by_id=self._lock_archived_owner,
        )
        self.actor = actor

    async def _lock_archived_owner(self, _urza_id):
        return False

    async def get_by_id(self, user_id):
        return self.actor if user_id == self.actor.id else None

    async def can_access_urza(self, _user_id, _urza_id):
        return True

    async def can_modify_urza(self, _user_id, _urza_id):
        return False


class _HTTPTaskRepository:
    def __init__(self, task):
        self.task = task
        self.session = self

    async def get_active_by_id(self, task_id):
        return self.task if task_id == self.task.id else None

    async def get_history(self, _task_id):
        return []

    async def save(self, task):
        return task

    def add(self, _entity):
        return None


class _HTTPEmptyTreeService:
    async def get_tree(self, **_kwargs):
        return []


def test_task_mutation_http_route_rejects_archived_owner():
    user = make_user(uuid7())
    user.role = UserRole.ENGINEER
    task_id, urza_id = uuid7(), uuid7()
    task = SimpleNamespace(
        id=task_id, urza_id=urza_id, substation_id=None,
        assigned_to=user.id, deleted_at=None, status=TaskStatus.ASSIGNED,
        work_type=TaskWorkType.OTD,
        description=None, urza=SimpleNamespace(dispatch_name="Archive URZA"),
        substation=None, assigned_to_user=user, created_by_user=user,
        assigned_at=None, acceptance_deadline_at=None, deadline_at=None,
        completed_at=None, closed_at=None,
    )
    repository = _HTTPTaskRepository(task)
    access = _HTTPTaskArchiveAccess(user)
    from app.application.tasks.service import TaskService

    task_service = TaskService(repository, access, SimpleNamespace())
    app.dependency_overrides[get_current_user] = override_user(user)
    app.dependency_overrides[get_task_repository] = lambda: repository
    app.dependency_overrides[get_access_service] = lambda: access
    app.dependency_overrides[get_task_service] = lambda: task_service
    app.dependency_overrides[get_tree_service] = lambda: _HTTPEmptyTreeService()

    try:
        response = TestClient(app).post(
            f"/tasks/{task_id}/accept?archived=true",
            headers={"HX-Request": "true"},
        )
        assert response.status_code == 200
        assert "Нельзя изменять задание архивного объекта" in response.text
        assert task.status is TaskStatus.ASSIGNED
    finally:
        app.dependency_overrides.clear()


class _HTTPInspectionTaskRepository:
    def __init__(self, task):
        self.task = task

    async def get_active_by_id(self, task_id):
        return self.task if task_id == self.task.id else None


class _HTTPInspectionTaskMutationService:
    def __init__(self):
        self.calls = []

    async def assign(self, *args, **kwargs):
        self.calls.append(("assign", args, kwargs))

    async def accept(self, *args, **kwargs):
        self.calls.append(("accept", args, kwargs))

    async def validate_completion(self, *args, **kwargs):
        self.calls.append(("validate_completion", args, kwargs))

    async def send_to_review(self, *args, **kwargs):
        self.calls.append(("send_to_review", args, kwargs))

    async def review(self, *args, **kwargs):
        self.calls.append(("review", args, kwargs))


@pytest.mark.parametrize(
    ("action", "form_data"),
    [
        ("assign", {"assignee_id": str(uuid7())}),
        ("accept", {}),
        ("complete", {"inspection_date": "2026-10-23", "remarks": "test"}),
        ("send-to-review", {}),
        ("review", {"approve": "true", "reason": "test"}),
    ],
)
def test_inspection_task_mutation_routes_reject_archived_substation(
    action, form_data
):
    user = make_user(uuid7())
    user.role = UserRole.MANAGER
    substation_id, task_id = uuid7(), uuid7()
    task = SimpleNamespace(
        id=task_id,
        substation_id=substation_id,
        substation=SimpleNamespace(enterprise_id=uuid7()),
    )
    repository = _HTTPInspectionTaskRepository(task)
    service = _HTTPInspectionTaskMutationService()
    object_service, _, resolver = _http_archive_object_service(
        "substation", substation_id
    )
    app.dependency_overrides[get_current_user] = override_user(user)
    app.dependency_overrides[get_object_service] = lambda: object_service
    app.dependency_overrides[get_inspection_task_repository] = lambda: repository
    app.dependency_overrides[get_inspection_task_service] = lambda: service
    app.dependency_overrides[get_file_service] = lambda: SimpleNamespace()
    app.dependency_overrides[get_tree_service] = lambda: SimpleNamespace()

    try:
        response = TestClient(app).post(
            f"/objects/substation/inspection-tasks/{task_id}/{action}",
            data=form_data,
        )
        assert response.status_code == 404
        assert service.calls == []
        assert resolver.calls == [("substation", substation_id, False)]
    finally:
        app.dependency_overrides.clear()


class _HTTPArchivedOTDService:
    def __init__(self):
        self.calls = []

    async def submit_for_review(self, *args):
        self.calls.append(("submit", args))


def test_otd_version_transition_rejects_archived_urza_before_service_mutation():
    user = make_user(uuid7())
    urza_id, version_id = uuid7(), uuid7()
    object_service, _, resolver = _http_archive_object_service("urza", urza_id)
    service = _HTTPArchivedOTDService()
    app.dependency_overrides[get_current_user] = override_user(user)
    app.dependency_overrides[get_object_service] = lambda: object_service
    app.dependency_overrides[get_otd_service] = lambda: service

    try:
        response = TestClient(app).post(
            f"/objects/urza/{urza_id}/otd/{version_id}/submit?archived=true"
        )
        assert response.status_code == 404
        assert service.calls == []
        assert resolver.calls == [("urza", urza_id, False)]
    finally:
        app.dependency_overrides.clear()


class _HTTPArchivedInstructionRepository:
    def __init__(self, instruction, version):
        self.instruction = instruction
        self.version = version
        self.save_calls = []

    async def get_version_by_id(self, version_id):
        return self.version if version_id == self.version.id else None

    async def get_by_id(self, instruction_id):
        return (
            self.instruction
            if instruction_id == self.instruction.id
            else None
        )

    async def save(self, version):
        self.save_calls.append(version)
        return version


class _HTTPArchivedSubstationWriteAccess:
    async def can_modify_substation(self, _user_id, _substation_id):
        return False


def test_substation_instruction_transition_rejects_archived_owner_in_service():
    user = make_user(uuid7())
    substation_id, instruction_id, version_id = uuid7(), uuid7(), uuid7()
    instruction = SimpleNamespace(id=instruction_id, substation_id=substation_id)
    version = SimpleNamespace(
        id=version_id,
        rza_instruction_id=instruction_id,
        deleted_at=None,
        status=DocumentStatus.DRAFT,
    )
    repository = _HTTPArchivedInstructionRepository(instruction, version)
    service = RZAInstructionService(
        repository=repository,
        access_service=_HTTPArchivedSubstationWriteAccess(),
    )
    app.dependency_overrides[get_current_user] = override_user(user)
    app.dependency_overrides[get_rza_instruction_service] = lambda: service
    app.dependency_overrides[get_task_service] = lambda: SimpleNamespace()

    try:
        response = TestClient(app).post(
            f"/objects/substation/{substation_id}/instructions/"
            f"versions/{version_id}/submit?archived=true"
        )
        assert response.status_code == 403
        assert "Изменение архивной подстанции запрещено" in response.text
        assert version.status is DocumentStatus.DRAFT
        assert repository.save_calls == []
    finally:
        app.dependency_overrides.clear()


def test_selectivity_scheme_transition_rejects_archived_owner_in_service():
    user = make_user(uuid7())
    substation_id, scheme_id, version_id = uuid7(), uuid7(), uuid7()
    scheme = SimpleNamespace(id=scheme_id, substation_id=substation_id)
    version = SimpleNamespace(
        id=version_id,
        selectivity_scheme_id=scheme_id,
        deleted_at=None,
        status=DocumentStatus.DRAFT,
    )
    repository = _HTTPArchivedInstructionRepository(scheme, version)
    service = SelectivitySchemeService(
        repository=repository,
        access_service=_HTTPArchivedSubstationWriteAccess(),
    )
    app.dependency_overrides[get_current_user] = override_user(user)
    app.dependency_overrides[get_selectivity_scheme_service] = lambda: service

    try:
        response = TestClient(app).post(
            f"/objects/substation/{substation_id}/selectivity-schemes/"
            f"versions/{version_id}/submit?archived=true"
        )
        assert response.status_code == 403
        assert "Изменение архивной подстанции запрещено" in response.text
        assert version.status is DocumentStatus.DRAFT
        assert repository.save_calls == []
    finally:
        app.dependency_overrides.clear()


class _HTTPArchivedURZAWriteAccess:
    async def can_modify_urza(self, _user_id, _urza_id):
        return False


@pytest.mark.parametrize(
    ("route", "service_dependency", "make_service"),
    [
        (
            "/objects/urza/{urza_id}/settings/{record_id}/submit",
            get_settings_service,
            lambda access: SettingsService(
                repository=SimpleNamespace(), access_service=access
            ),
        ),
        (
            "/objects/urza/{urza_id}/schemas/{record_id}/submit",
            get_schema_service,
            lambda access: SchemaService(
                repository=SimpleNamespace(),
                access_service=access,
                task_repository=SimpleNamespace(),
            ),
        ),
        (
            "/objects/urza/{urza_id}/programs/{record_id}/submit",
            get_program_service,
            lambda access: ProgramService(
                repository=SimpleNamespace(),
                access_service=access,
                user_repository=SimpleNamespace(),
                urza_repository=SimpleNamespace(),
                task_repository=SimpleNamespace(),
                task_service=SimpleNamespace(),
            ),
        ),
    ],
)
def test_urza_document_workflow_routes_reject_archived_owner(
    route, service_dependency, make_service
):
    user = make_user(uuid7())
    urza_id, record_id = uuid7(), uuid7()
    access = _HTTPArchivedURZAWriteAccess()
    service = make_service(access)
    app.dependency_overrides[get_current_user] = override_user(user)
    app.dependency_overrides[service_dependency] = lambda: service
    app.dependency_overrides[get_task_service] = lambda: SimpleNamespace()
    app.dependency_overrides[get_tree_service] = lambda: SimpleNamespace()

    try:
        response = TestClient(app).post(
            route.format(urza_id=urza_id, record_id=record_id)
            + "?archived=true"
        )
        assert response.status_code == 403
        assert "архивной URZA" in response.text
    finally:
        app.dependency_overrides.clear()


def test_urza_instruction_version_transition_rejects_archived_owner_in_service():
    user = make_user(uuid7())
    urza_id, instruction_id, version_id = uuid7(), uuid7(), uuid7()
    instruction = SimpleNamespace(id=instruction_id, urza_id=urza_id)
    version = SimpleNamespace(
        id=version_id,
        urza_instruction_id=instruction_id,
        status=DocumentStatus.DRAFT,
    )
    repository = _HTTPArchivedInstructionRepository(instruction, version)
    service = URZAInstructionService(
        repository=repository,
        access_service=_HTTPArchivedURZAWriteAccess(),
        user_repository=SimpleNamespace(),
        urza_repository=SimpleNamespace(),
    )
    app.dependency_overrides[get_current_user] = override_user(user)
    app.dependency_overrides[get_urza_instruction_service] = lambda: service
    app.dependency_overrides[get_task_service] = lambda: SimpleNamespace()

    try:
        response = TestClient(app).post(
            f"/objects/urza/{urza_id}/instruction/versions/"
            f"{version_id}/submit?archived=true"
        )
        assert response.status_code == 403
        assert "архивной URZA" in response.text
        assert version.status is DocumentStatus.DRAFT
        assert repository.save_calls == []
    finally:
        app.dependency_overrides.clear()


class _HTTPArchiveInstructionService:
    def __init__(self, instruction, versions):
        self.instruction = instruction
        self.versions = versions

    async def get_by_urza(self, _user_id, _urza_id):
        return self.instruction

    async def get_versions(self, _user_id, _urza_id):
        return self.versions

    async def get_current_version(self, _user_id, _urza_id):
        return self.versions[0]

    async def get_version_by_id(self, _user_id, version_id):
        return next((item for item in self.versions if item.id == version_id), None)

    async def get_available_actions(self, _user_id, _version):
        return {"submit", "approve", "new_version"}


class _HTTPArchiveTaskService:
    async def can_issue_task(self, **_kwargs):
        return True


def test_archived_urza_instruction_history_preserves_context_and_file_routes():
    user = make_user(uuid7())
    urza_id, instruction_id = uuid7(), uuid7()
    versions = [
        SimpleNamespace(
            id=uuid7(), urza_instruction_id=instruction_id,
            version_number=2, effective_date=date(2026, 10, 1),
            change_description="Recent", change_justification="Reason",
            created_by_full_name="Test author", status=DocumentStatus.APPROVED,
            scan_file_id=uuid7(), scan_file_name="scan.pdf",
            scan_file=SimpleNamespace(original_name="scan.pdf"),
            creator=SimpleNamespace(full_name="Test author"),
            editable_file_id=None, editable_file_name=None, editable_file=None,
        ),
        SimpleNamespace(
            id=uuid7(), urza_instruction_id=instruction_id,
            version_number=1, effective_date=date(2026, 1, 1),
            change_description="Earlier", change_justification="Reason",
            created_by_full_name="Test author", status=DocumentStatus.APPROVED,
            scan_file_id=uuid7(), scan_file_name="old-scan.pdf",
            scan_file=SimpleNamespace(original_name="old-scan.pdf"),
            creator=SimpleNamespace(full_name="Test author"),
            editable_file_id=None, editable_file_name=None, editable_file=None,
        ),
    ]
    instruction = SimpleNamespace(id=instruction_id, urza_id=urza_id)
    object_service, access, resolver = _http_archive_object_service(
        "urza", urza_id
    )
    app.dependency_overrides[get_current_user] = override_user(user)
    app.dependency_overrides[get_object_service] = lambda: object_service
    app.dependency_overrides[get_urza_instruction_service] = lambda: (
        _HTTPArchiveInstructionService(instruction, versions)
    )
    app.dependency_overrides[get_task_service] = lambda: _HTTPArchiveTaskService()

    try:
        with TestClient(app) as client:
            response = client.get(
                f"/objects/urza/{urza_id}/instruction?instruction_version={versions[1].id}&archived=true"
            )
            assert response.status_code == 200
            assert "История версий" in response.text
            assert (
                f"instruction_version={versions[0].id}&archived=true"
                in response.text.replace("&amp;", "&")
            )
            assert f"/files/{versions[1].scan_file_id}/view" in response.text
            assert f"/files/{versions[1].scan_file_id}/download" in response.text
            assert "Новая версия" not in response.text
            assert 'id="submits"' not in response.text
            assert resolver.calls[-1] == ("urza", urza_id, True)

            access.allowed = False
            denied = client.get(
                f"/objects/urza/{urza_id}/instruction?archived=true"
            )
            assert denied.status_code == 403
            assert resolver.calls[-1] == ("urza", urza_id, True)
    finally:
        app.dependency_overrides.clear()


class _HTTPArchiveSubstationInstructionService:
    def __init__(self, versions):
        self.versions = versions

    async def get_details(self, **_kwargs):
        return SimpleNamespace(id=uuid7())

    async def get_versions(self, **_kwargs):
        return self.versions

    async def get_available_actions(self, *_args):
        return {"submit", "approve", "new_version"}


def test_archived_substation_instruction_tab_keeps_version_history_read_only():
    user = make_user(uuid7())
    substation_id = uuid7()
    versions = [
        SimpleNamespace(
            id=uuid7(), version_number=2,
            effective_date=date(2026, 10, 1),
            change_description="Latest", change_justification="Reason",
            created_by_full_name="Test author",
            status=DocumentStatus.APPROVED,
            scan_file_id=uuid7(), scan_file_name="scan.pdf",
            editable_file_id=None, editable_file_name=None,
        ),
        SimpleNamespace(
            id=uuid7(), version_number=1,
            effective_date=date(2026, 1, 1),
            change_description="Earlier", change_justification="Reason",
            created_by_full_name="Test author",
            status=DocumentStatus.APPROVED,
            scan_file_id=uuid7(), scan_file_name="old.pdf",
            editable_file_id=None, editable_file_name=None,
        ),
    ]
    object_service, _, resolver = _http_archive_object_service(
        "substation", substation_id
    )
    app.dependency_overrides[get_current_user] = override_user(user)
    app.dependency_overrides[get_object_service] = lambda: object_service
    app.dependency_overrides[get_rza_instruction_service] = lambda: (
        _HTTPArchiveSubstationInstructionService(versions)
    )
    app.dependency_overrides[get_task_service] = lambda: _HTTPArchiveTaskService()

    try:
        response = TestClient(app).get(
            f"/objects/substation/{substation_id}/instructions?archived=true"
        )
        assert response.status_code == 200
        assert "История версий" in response.text
        assert (
            f"instruction_version={versions[1].id}&archived=true"
            in response.text.replace("&amp;", "&")
        )
        assert f"/files/{versions[0].scan_file_id}/view" in response.text
        assert "Добавить инструкцию" not in response.text
        assert "Отправить на согласование" not in response.text
        assert resolver.calls[-1] == ("substation", substation_id, True)
    finally:
        app.dependency_overrides.clear()


class _HTTPFileRepository:
    def __init__(self, file):
        self.file = file

    async def get_by_id(self, _file_id):
        return self.file


class _HTTPFileOwnerResolver:
    def __init__(self, owner):
        self.owner = owner

    async def resolve(self, _file_id):
        return self.owner


class _HTTPFileAccess:
    async def can_access_urza(self, *, user_id, urza_id):
        return True

    async def can_access_substation(self, *, user_id, substation_id):
        return True


class _HTTPFileContent:
    def __init__(self):
        self.reads = 0

    async def read(self, _file):
        self.reads += 1
        return b"test file"


def test_file_http_route_uses_file_access_policy_for_archive_files():
    user = make_user(uuid7())
    file_id, urza_id = uuid7(), uuid7()
    file = SimpleNamespace(
        id=file_id, deleted_at=None, original_name="scan.pdf",
        mime_type="application/pdf",
    )
    owner = FileOwner(
        owner_type=FileOwnerType.URZA_INSTRUCTION_VERSION,
        owner_id=uuid7(), access_target_type=FileAccessTargetType.URZA,
        access_target_id=urza_id,
    )
    content = _HTTPFileContent()
    file_access = FileAccessService(
        file_repository=_HTTPFileRepository(file),
        owner_resolver=_HTTPFileOwnerResolver(owner),
        access_service=_HTTPFileAccess(),
    )
    app.dependency_overrides[get_current_user] = override_user(user)
    app.dependency_overrides[get_file_access_service] = lambda: file_access
    app.dependency_overrides[get_file_service] = lambda: content

    try:
        with TestClient(app) as client:
            allowed = client.get(f"/files/{file_id}/view")
            assert allowed.status_code == 200
            assert allowed.content == b"test file"
            assert content.reads == 1

            file.deleted_at = datetime.now(UTC)
            denied = client.get(f"/files/{file_id}/download")
            assert denied.status_code == 403
            assert content.reads == 1
    finally:
        app.dependency_overrides.clear()
