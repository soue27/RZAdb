from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import UUID

from fastapi.testclient import TestClient
from uuid6 import uuid7


from app.domain.program import Program
from app.domain.file import File

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
    get_substation_service,
    get_file_service,
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