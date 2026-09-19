from fastapi.testclient import TestClient

from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

from app.application.auth.service import AuthService
from app.application.auth.service import InvalidCredentialsError
from app.domain.enums import AccessCategory, UserRole
from app.domain.user import User
from app.presentation.app import app
from app.presentation.dependencies.services import get_auth_service


def test_login_page() -> None:
    client = TestClient(app)

    response = client.get("/auth/login")

    assert response.status_code == 200
    assert response.json() == {
        "message": "Login page",
    }

def test_login_success() -> None:
    user = User(
        full_name="Тестовый пользователь",
        role=UserRole.ENGINEER,
        email="test@example.com",
        password_hash="hash",
        access_category=AccessCategory.IV,
        active=True,
    )

    auth_service = AsyncMock(spec=AuthService)
    auth_service.authenticate.return_value = user

    app.dependency_overrides[get_auth_service] = lambda: auth_service

    try:
        client = TestClient(app)

        response = client.post(
            "/auth/login",
            data={
                "email": "test@example.com",
                "password": "correct-password",
            },
            follow_redirects=False,
        )

        assert response.status_code == 303
        assert response.headers["location"] == "/"

        auth_service.authenticate.assert_awaited_once_with(
            email="test@example.com",
            password="correct-password",
        )

        session_cookie = response.cookies.get("session")

        assert session_cookie is not None

    finally:
        app.dependency_overrides.clear()

def test_login_invalid_credentials() -> None:
    auth_service = AsyncMock(spec=AuthService)
    auth_service.authenticate.side_effect = InvalidCredentialsError

    app.dependency_overrides[get_auth_service] = lambda: auth_service

    try:
        client = TestClient(app)

        response = client.post(
            "/auth/login",
            data={
                "email": "test@example.com",
                "password": "wrong-password",
            },
        )

        assert response.status_code == 401
        assert response.json() == {
            "detail": "Неверный email или пароль.",
        }

        auth_service.authenticate.assert_awaited_once_with(
            email="test@example.com",
            password="wrong-password",
        )

    finally:
        app.dependency_overrides.clear()