import re
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from uuid6 import uuid7

from app.domain.enums import AccessCategory, TaskWorkType, UserRole
from app.domain.user import User
from app.presentation.app import app
from app.presentation.auth.dependencies import get_current_user
from app.presentation.dependencies.services import get_notification_service


def make_user() -> User:
    return User(
        id=uuid7(),
        full_name="Тестовый пользователь",
        role=UserRole.ENGINEER,
        email="notifications@example.test",
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

    assert match is not None, "CSRF-токен не найден в HTML-форме."

    return match.group(1)


def make_notification(
    *,
    notification_id: UUID | None = None,
    task_id: UUID | None = None,
    recipient_id: UUID | None = None,
    event_type: str = "assigned",
    read_at: datetime | None = None,
):
    task_id = task_id or uuid7()

    task = SimpleNamespace(
        id=task_id,
        description="Проверить устройство РЗА",
        work_type=TaskWorkType.OTD,
        urza=SimpleNamespace(dispatch_name="УРЗА-1"),
        substation=None,
    )

    history = SimpleNamespace(
        id=uuid7(),
        task_id=task_id,
        task=task,
        event_type=event_type,
        actor_id=uuid7(),
        actor=SimpleNamespace(full_name="Иванов Иван Иванович"),
        previous_assignee_id=None,
        new_assignee_id=None,
        comment="Тестовый комментарий",
        created_at=datetime.now(UTC),
    )

    return SimpleNamespace(
        id=notification_id or uuid7(),
        task_history_id=history.id,
        recipient_id=recipient_id or uuid7(),
        task_history=history,
        created_at=datetime.now(UTC),
        read_at=read_at,
    )


class FakeNotificationService:
    def __init__(
        self,
        *,
        notifications=None,
        notification=None,
        unread_count: int = 0,
    ):
        self.notifications = notifications or []
        self.notification = notification
        self.unread_count = unread_count

        self.get_unread = AsyncMock(return_value=self.notifications)
        self.count_unread = AsyncMock(return_value=unread_count)
        self.get_by_id = AsyncMock(return_value=notification)
        self.mark_as_read = AsyncMock(return_value=True)


@pytest.fixture
def notifications_client():
    user = make_user()
    service = FakeNotificationService()

    async def override_current_user():
        return user

    app.dependency_overrides[get_current_user] = override_current_user
    app.dependency_overrides[get_notification_service] = lambda: service

    try:
        yield TestClient(app), user, service
    finally:
        app.dependency_overrides.clear()


def test_notifications_page_renders_unread_notifications(
    notifications_client,
):
    client, user, service = notifications_client

    notification = make_notification(recipient_id=user.id)
    service.notifications = [notification]
    service.get_unread.return_value = [notification]
    service.count_unread.return_value = 1

    response = client.get("/notifications")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Проверить устройство РЗА" in response.text
    assert "УРЗА-1" in response.text

    service.get_unread.assert_awaited_once_with(
        recipient_id=user.id,
        limit=20,
        offset=0,
    )
    service.count_unread.assert_awaited_once_with(
        recipient_id=user.id,
    )


def test_notifications_page_renders_empty_state(notifications_client):
    client, user, service = notifications_client

    service.notifications = []
    service.get_unread.return_value = []
    service.count_unread.return_value = 0

    response = client.get("/notifications")

    assert response.status_code == 200

    service.get_unread.assert_awaited_once()
    service.count_unread.assert_awaited_once_with(
        recipient_id=user.id,
    )


def test_notifications_page_passes_pagination_offset(
    notifications_client,
):
    client, user, service = notifications_client

    response = client.get("/notifications?offset=20")

    assert response.status_code == 200

    service.get_unread.assert_awaited_once_with(
        recipient_id=user.id,
        limit=20,
        offset=20,
    )


def test_notifications_page_clamps_negative_offset(
    notifications_client,
):
    client, user, service = notifications_client

    response = client.get("/notifications?offset=-10")

    assert response.status_code == 200

    service.get_unread.assert_awaited_once_with(
        recipient_id=user.id,
        limit=20,
        offset=0,
    )


def test_notifications_count_returns_unread_count(
    notifications_client,
):
    client, user, service = notifications_client
    service.count_unread.return_value = 3

    response = client.get("/notifications/count")

    assert response.status_code == 200
    assert "3" in response.text

    service.count_unread.assert_awaited_once_with(
        recipient_id=user.id,
    )


def test_notifications_count_does_not_render_badge_when_zero(
    notifications_client,
):
    client, user, service = notifications_client
    service.count_unread.return_value = 0

    response = client.get("/notifications/count")

    assert response.status_code == 200
    assert "badge" not in response.text

    service.count_unread.assert_awaited_once_with(
        recipient_id=user.id,
    )


def test_notifications_page_requires_authentication():
    response = TestClient(app).get(
        "/notifications",
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/auth/login"


def test_notifications_count_requires_authentication():
    response = TestClient(app).get(
        "/notifications/count",
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/auth/login"


def test_open_notification_rejects_missing_csrf_token(
    notifications_client,
):
    client, user, service = notifications_client

    notification = make_notification(recipient_id=user.id)
    service.notification = notification
    service.get_by_id.return_value = notification

    response = client.post(
        f"/notifications/{notification.id}/open",
        data={},
        follow_redirects=False,
    )

    assert response.status_code == 422
    service.get_by_id.assert_not_awaited()
    service.mark_as_read.assert_not_awaited()


def test_open_notification_rejects_invalid_csrf_token(
    notifications_client,
):
    client, user, service = notifications_client

    notification = make_notification(recipient_id=user.id)
    service.notification = notification
    service.get_by_id.return_value = notification

    # Сначала получаем токен, который будет записан в сессию.
    page_response = client.get("/notifications")
    assert page_response.status_code == 200

    response = client.post(
        f"/notifications/{notification.id}/open",
        data={"csrf_token": "invalid-token"},
        follow_redirects=False,
    )

    assert response.status_code == 403
    service.get_by_id.assert_not_awaited()
    service.mark_as_read.assert_not_awaited()


def test_open_notification_marks_notification_as_read(
    notifications_client,
):
    client, user, service = notifications_client

    notification = make_notification(recipient_id=user.id)
    service.notification = notification
    service.get_by_id.return_value = notification

    service.notifications = [notification]
    service.get_unread.return_value = [notification]
    service.count_unread.return_value = 1

    # GET создаёт CSRF-токен и сохраняет его в сессии.
    page_response = client.get("/notifications")

    assert page_response.status_code == 200
    csrf_token = extract_csrf_token(page_response.text)

    response = client.post(
        f"/notifications/{notification.id}/open",
        data={"csrf_token": csrf_token},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == f"/tasks/{notification.task_history.task_id}"

    service.get_by_id.assert_awaited_once_with(
        notification_id=notification.id,
        recipient_id=user.id,
    )
    service.mark_as_read.assert_awaited_once_with(
        notification_id=notification.id,
        recipient_id=user.id,
    )


def test_open_notification_returns_404_for_foreign_notification(
    notifications_client,
):
    client, user, service = notifications_client

    # Уведомление для отображения формы и получения CSRF-токена.
    page_notification = make_notification(recipient_id=user.id)
    service.notifications = [page_notification]
    service.get_unread.return_value = [page_notification]
    service.count_unread.return_value = 1

    page_response = client.get("/notifications")

    assert page_response.status_code == 200
    csrf_token = extract_csrf_token(page_response.text)

    # Имитируем ситуацию, когда уведомление не принадлежит пользователю.
    notification_id = uuid7()
    service.get_by_id.return_value = None

    response = client.post(
        f"/notifications/{notification_id}/open",
        data={"csrf_token": csrf_token},
        follow_redirects=False,
    )

    assert response.status_code == 404

    service.get_by_id.assert_awaited_once_with(
        notification_id=notification_id,
        recipient_id=user.id,
    )
    service.mark_as_read.assert_not_awaited()


def test_open_notification_does_not_mark_read_before_csrf_validation(
    notifications_client,
):
    client, user, service = notifications_client

    notification = make_notification(recipient_id=user.id)
    service.notification = notification

    client.get("/notifications")

    response = client.post(
        f"/notifications/{notification.id}/open",
        data={"csrf_token": "wrong"},
        follow_redirects=False,
    )

    assert response.status_code == 403
    service.get_by_id.assert_not_awaited()
    service.mark_as_read.assert_not_awaited()


def test_rejected_notification_shows_actor_name(
    notifications_client,
):
    client, user, service = notifications_client

    notification = make_notification(
        recipient_id=user.id,
        event_type="rejected",
    )
    service.notifications = [notification]
    service.get_unread.return_value = [notification]
    service.count_unread.return_value = 1

    response = client.get("/notifications")

    assert response.status_code == 200
    assert "Исполнитель отказался от задания" in response.text
    assert "Исполнитель: Иванов Иван Иванович" in response.text


def test_reassigned_notification_shows_previous_assignee_message(
    notifications_client,
):
    client, user, service = notifications_client

    notification = make_notification(
        recipient_id=user.id,
        event_type="reassigned",
    )
    notification.task_history.previous_assignee_id = user.id
    notification.task_history.new_assignee_id = uuid7()

    service.notifications = [notification]
    service.get_unread.return_value = [notification]
    service.count_unread.return_value = 1

    response = client.get("/notifications")

    assert response.status_code == 200
    assert "Задание снято с вас" in response.text


def test_reassigned_notification_shows_new_assignee_message(
    notifications_client,
):
    client, user, service = notifications_client

    notification = make_notification(
        recipient_id=user.id,
        event_type="reassigned",
    )
    notification.task_history.previous_assignee_id = uuid7()
    notification.task_history.new_assignee_id = user.id

    service.notifications = [notification]
    service.get_unread.return_value = [notification]
    service.count_unread.return_value = 1

    response = client.get("/notifications")

    assert response.status_code == 200
    assert "Вам назначено задание" in response.text