import re
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from uuid6 import uuid7

from app.application.feedback.service import FeedbackService
from app.domain.enums import AccessCategory, UserRole
from app.domain.user import User
from app.presentation.app import app
from app.presentation.auth.dependencies import get_current_user
from app.presentation.dependencies.services import (
    get_enterprise_repository,
    get_feedback_service,
)
from app.presentation.routes import feedback as feedback_routes


def make_user() -> User:
    return User(
        id=uuid7(),
        full_name="Тестовый пользователь",
        role=UserRole.ENGINEER,
        email="user@example.test",
        password_hash="hash",
        access_category=AccessCategory.IV,
        active=True,
        created_by=uuid7(),
        updated_by=uuid7(),
    )


def extract_csrf_token(html: str) -> str:
    match = re.search(
        r'<input\b(?=[^>]*\bname=["\']csrf_token["\'])'
        r'(?=[^>]*\bvalue=["\']([^"\']+)["\'])[^>]*>',
        html,
    )

    assert match is not None, "CSRF-токен не найден."

    return match.group(1)


@pytest.fixture
def feedback_client(monkeypatch):
    user = make_user()
    service = AsyncMock(spec=FeedbackService)
    enterprise_repository = AsyncMock()

    monkeypatch.setattr(
        feedback_routes,
        "get_settings",
        lambda: SimpleNamespace(feedback_max_length=100),
    )

    async def override_current_user():
        return user

    app.dependency_overrides[get_current_user] = override_current_user
    app.dependency_overrides[get_feedback_service] = lambda: service
    app.dependency_overrides[get_enterprise_repository] = (
        lambda: enterprise_repository
    )

    try:
        yield TestClient(app), user, service, enterprise_repository
    finally:
        app.dependency_overrides.clear()


def test_feedback_page_renders_form(feedback_client):
    client, user, service, repository = feedback_client

    response = client.get("/feedback")

    assert response.status_code == 200
    assert "Обратная связь" in response.text
    assert 'name="message"' in response.text
    assert "csrf_token" in response.text
    assert "100" in response.text


def test_feedback_page_shows_success_without_form(feedback_client):
    client, user, service, repository = feedback_client

    response = client.get("/feedback?sent=1")

    assert response.status_code == 200
    assert "Сообщение успешно отправлено" in response.text
    assert 'name="message"' not in response.text


def test_feedback_requires_authentication():
    response = TestClient(app).get(
        "/feedback",
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/auth/login"


def test_submit_feedback_rejects_invalid_csrf(feedback_client):
    client, user, service, repository = feedback_client

    client.get("/feedback")

    response = client.post(
        "/feedback",
        data={
            "message": "Тестовое сообщение",
            "csrf_token": "invalid-token",
        },
    )

    assert response.status_code == 403
    service.send.assert_not_awaited()


def test_submit_feedback_rejects_empty_message(feedback_client):
    client, user, service, repository = feedback_client

    page = client.get("/feedback")
    csrf_token = extract_csrf_token(page.text)

    response = client.post(
        "/feedback",
        data={
            "message": "   ",
            "csrf_token": csrf_token,
        },
    )

    assert response.status_code == 422
    assert "Введите текст сообщения" in response.text
    service.send.assert_not_awaited()


def test_submit_feedback_rejects_message_over_limit(feedback_client):
    client, user, service, repository = feedback_client

    page = client.get("/feedback")
    csrf_token = extract_csrf_token(page.text)

    message = "А" * 101

    response = client.post(
        "/feedback",
        data={
            "message": message,
            "csrf_token": csrf_token,
        },
    )

    assert response.status_code == 422
    assert "не должно превышать 100 символов" in response.text
    assert message in response.text
    service.send.assert_not_awaited()


def test_submit_feedback_sends_message_and_redirects(feedback_client):
    client, user, service, repository = feedback_client

    page = client.get("/feedback")
    csrf_token = extract_csrf_token(page.text)

    response = client.post(
        "/feedback",
        data={
            "message": "Проверка обратной связи.",
            "csrf_token": csrf_token,
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/feedback?sent=1"

    service.send.assert_awaited_once_with(
        user_id=str(user.id),
        full_name=user.full_name,
        email=user.email,
        role=user.role.value,
        enterprise_name=None,
        message="Проверка обратной связи.",
    )

    repository.get_by_id.assert_not_awaited()


def test_submit_feedback_preserves_message_when_sending_fails(
    feedback_client,
):
    client, user, service, repository = feedback_client

    service.send.side_effect = RuntimeError("SMTP connection failed")

    page = client.get("/feedback")
    csrf_token = extract_csrf_token(page.text)

    message = "Не работает отображение документа."

    response = client.post(
        "/feedback",
        data={
            "message": message,
            "csrf_token": csrf_token,
        },
    )

    assert response.status_code == 503
    assert "Не удалось отправить сообщение" in response.text
    assert message in response.text

    service.send.assert_awaited_once()