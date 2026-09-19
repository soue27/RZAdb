from fastapi.testclient import TestClient
from uuid6 import uuid7

from app.domain.enums import AccessCategory, UserRole
from app.domain.user import User
from app.presentation.app import app
from app.presentation.auth.dependencies import get_current_user


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


def test_home_requires_authentication() -> None:
    client = TestClient(app)

    response = client.get("/")

    assert response.status_code == 401


def test_home_authenticated() -> None:
    user = make_user()

    async def override_current_user() -> User:
        return user

    app.dependency_overrides[get_current_user] = override_current_user

    try:
        client = TestClient(app)

        response = client.get("/")

        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "RZAdb" in response.text
        assert "Тестовый пользователь" in response.text
    finally:
        app.dependency_overrides.clear()