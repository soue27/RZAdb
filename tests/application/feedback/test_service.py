from unittest.mock import AsyncMock

import pytest

from app.application.feedback.service import FeedbackService


@pytest.mark.asyncio
async def test_send_includes_user_data_and_message():
    sender = AsyncMock()

    service = FeedbackService(
        sender=sender,
        recipient="admin@example.test",
        app_base_url="https://rzadb.example.test",
    )

    await service.send(
        user_id="user-123",
        full_name="Иванов Иван Иванович",
        email="ivanov@example.test",
        role="engineer",
        enterprise_name="Пермские сети",
        message="Проблема с отображением документа.",
    )

    sender.send.assert_awaited_once()

    kwargs = sender.send.await_args.kwargs

    assert kwargs["to"] == "admin@example.test"
    assert "Иванов Иван Иванович" in kwargs["subject"]

    body = kwargs["body"]

    assert "Иванов Иван Иванович" in body
    assert "ivanov@example.test" in body
    assert "engineer" in body
    assert "Пермские сети" in body
    assert "user-123" in body
    assert "Проблема с отображением документа." in body
    assert "https://rzadb.example.test" in body
    assert "Дата и время:" in body


@pytest.mark.asyncio
async def test_send_uses_fallback_when_enterprise_is_missing():
    sender = AsyncMock()

    service = FeedbackService(
        sender=sender,
        recipient="admin@example.test",
    )

    await service.send(
        user_id="user-123",
        full_name="Иванов Иван",
        email="ivanov@example.test",
        role="engineer",
        enterprise_name=None,
        message="Тестовое сообщение.",
    )

    body = sender.send.await_args.kwargs["body"]

    assert "Предприятие: Не указано" in body
    assert "Приложение: Не указано" in body