from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from uuid6 import uuid7

from app.application.objects.exceptions import (
    ObjectAccessDeniedError,
    ObjectNotFoundError,
)
from app.application.objects.schemas import SelectedObject
from app.domain.enums import AccessCategory, UserRole
from app.domain.user import User
from app.presentation.app import app
from app.presentation.auth.dependencies import get_current_user
from app.presentation.dependencies.services import get_object_service


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

    try:
        client = TestClient(app)

        response = client.get(
            f"/objects/substation/{object_id}",
        )

        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "ПС Свердловская" in response.text
        assert "substation" in response.text
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

    try:
        client = TestClient(app)

        response = client.get(
            "/objects/substation/not-a-uuid",
        )

        assert response.status_code == 422
    finally:
        app.dependency_overrides.clear()