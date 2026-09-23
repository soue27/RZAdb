from datetime import date
from decimal import Decimal
from uuid import UUID

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
    HighestVoltage,
    OperationalCurrentType,
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
    get_substation_service,
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


def make_user() -> User:
    return User(
        id=uuid7(),
        full_name="Тестовый пользователь",
        role=UserRole.ENGINEER,
        email="test@example.com",
        password_hash="hash",
        access_category=AccessCategory.IV,
        active=True,
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


def test_get_object_requires_authentication() -> None:
    app.dependency_overrides.clear()

    client = TestClient(app)

    response = client.get(f"/objects/substation/{uuid7()}")

    assert response.status_code == 401

    app.dependency_overrides.clear()


def test_get_object_returns_selected_object() -> None:
    user = make_user()
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
    app.dependency_overrides[get_substation_service] = (
        override_substation_service(FakeSubstationService())
    )
    app.dependency_overrides[get_connection_service] = (
        override_connection_service(FakeConnectionService())
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


def test_get_object_returns_404_when_object_not_found() -> None:
    user = make_user()

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


def test_get_object_returns_403_when_access_denied() -> None:
    user = make_user()

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


def test_get_object_rejects_invalid_uuid() -> None:
    user = make_user()

    app.dependency_overrides[get_current_user] = override_user(user)
    app.dependency_overrides[get_object_service] = override_object_service(
        FakeObjectService()
    )
    app.dependency_overrides[get_substation_service] = (
        override_substation_service(FakeSubstationService())
    )
    app.dependency_overrides[get_connection_service] = (
        override_connection_service(FakeConnectionService())
    )

    try:
        client = TestClient(app)

        response = client.get(
            "/objects/substation/not-a-uuid",
        )

        assert response.status_code == 422
    finally:
        app.dependency_overrides.clear()


def test_get_substation_inspections_returns_inspections() -> None:
    user = make_user()
    substation_id = uuid7()

    inspections = [
        Inspection(
            id=uuid7(),
            substation_id=substation_id,
            inspection_task_id=uuid7(),
            inspection_date=date(2026, 9, 1),
            remarks="Замечаний нет.",
            created_by=user.id,
        ),
        Inspection(
            id=uuid7(),
            substation_id=substation_id,
            inspection_task_id=uuid7(),
            inspection_date=date(2026, 8, 1),
            remarks="Обнаружено замечание.",
            created_by=user.id,
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
    app.dependency_overrides[get_inspection_service] = (
        override_inspection_service(
            FakeInspectionService(inspections),
        )
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