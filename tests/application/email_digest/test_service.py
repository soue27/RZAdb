from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest

from app.application.email_digest.formatter import EmailDigestMessage
from app.application.email_digest.service import EmailDigestService
from app.domain.enums import UserRole


TZ = ZoneInfo("Asia/Yekaterinburg")
NOW = datetime(2026, 10, 29, 7, 30, tzinfo=TZ)


def make_user(
    *,
    role: UserRole,
    enterprise_id=None,
    email: str = "user@example.com",
):
    return SimpleNamespace(
        id=uuid4(),
        role=role,
        enterprise_id=enterprise_id,
        email=email,
        full_name="Тестовый пользователь",
    )


def make_task(
    *,
    assigned_to=None,
    assignee_name: str | None = None,
):
    assignee = (
        SimpleNamespace(full_name=assignee_name) if assignee_name is not None else None
    )
    return SimpleNamespace(
        description="Проверить защиту",
        status=SimpleNamespace(value="in_progress"),
        deadline_at=datetime(2026, 10, 30, 12, 0, tzinfo=TZ),
        assigned_to=assigned_to,
        assigned_to_user=assignee,
    )


def make_service(recipients):
    users = Mock()
    users.list_active_email_digest_recipients = AsyncMock(return_value=recipients)

    tasks = Mock()
    tasks.list_for_email_digest_engineer = AsyncMock(return_value=[])
    tasks.list_for_email_digest_manager = AsyncMock(return_value=[])

    formatter = Mock()
    formatter.format_engineer_digest.return_value = EmailDigestMessage(
        subject="Сводка инженера",
        text_body="Текст письма",
        html_body="<p>Текст письма</p>",
    )
    formatter.format_manager_digest.return_value = EmailDigestMessage(
        subject="Сводка руководителя",
        text_body="Текст письма",
        html_body="<p>Текст письма</p>",
    )

    sender = Mock()
    sender.send = AsyncMock()

    service = EmailDigestService(
        user_repository=users,
        task_repository=tasks,
        formatter=formatter,
        sender=sender,
    )

    return service, users, tasks, formatter, sender


@pytest.mark.asyncio
async def test_engineer_digest_is_sent():
    engineer = make_user(role=UserRole.ENGINEER)
    service, _, tasks, formatter, sender = make_service([engineer])
    tasks.list_for_email_digest_engineer.return_value = [
        make_task(assigned_to=engineer.id)
    ]

    result = await service.send_digests(now=NOW)

    assert result.recipients == 1
    assert result.sent == 1
    assert result.failed == 0
    tasks.list_for_email_digest_engineer.assert_awaited_once_with(engineer.id)
    formatter.format_engineer_digest.assert_called_once()
    sender.send.assert_awaited_once_with(
        to=engineer.email,
        subject="Сводка инженера",
        body="Текст письма",
        html_body="<p>Текст письма</p>",
    )


@pytest.mark.asyncio
async def test_manager_digest_uses_enterprise_tasks():
    enterprise_id = uuid4()
    manager = make_user(
        role=UserRole.MANAGER,
        enterprise_id=enterprise_id,
    )
    service, _, tasks, formatter, sender = make_service([manager])
    tasks.list_for_email_digest_manager.return_value = [
        make_task(
            assigned_to=manager.id,
            assignee_name=manager.full_name,
        )
    ]

    result = await service.send_digests(now=NOW)

    assert result.sent == 1
    tasks.list_for_email_digest_manager.assert_awaited_once_with(enterprise_id)
    formatter.format_manager_digest.assert_called_once()
    sender.send.assert_awaited_once()


@pytest.mark.asyncio
async def test_empty_digest_is_not_sent():
    engineer = make_user(role=UserRole.ENGINEER)
    service, _, _, formatter, sender = make_service([engineer])

    result = await service.send_digests(now=NOW)

    assert result.sent == 0
    assert result.skipped_empty == 1
    sender.send.assert_not_awaited()
    formatter.format_engineer_digest.assert_not_called()


@pytest.mark.asyncio
async def test_manager_without_enterprise_is_skipped():
    manager = make_user(
        role=UserRole.MANAGER,
        enterprise_id=None,
    )
    service, _, tasks, _, sender = make_service([manager])

    result = await service.send_digests(now=NOW)

    assert result.skipped_no_enterprise == 1
    assert result.sent == 0
    tasks.list_for_email_digest_manager.assert_not_awaited()
    sender.send.assert_not_awaited()


@pytest.mark.asyncio
async def test_failure_for_one_recipient_does_not_stop_next():
    first = make_user(role=UserRole.ENGINEER)
    second = make_user(
        role=UserRole.ENGINEER,
        email="second@example.com",
    )
    service, _, tasks, _, sender = make_service([first, second])
    tasks.list_for_email_digest_engineer.return_value = [make_task()]
    sender.send.side_effect = [
        RuntimeError("SMTP unavailable"),
        None,
    ]

    result = await service.send_digests(now=NOW)

    assert result.recipients == 2
    assert result.sent == 1
    assert result.failed == 1
    assert sender.send.await_count == 2


@pytest.mark.asyncio
async def test_naive_now_is_rejected():
    service, _, _, _, _ = make_service([])

    with pytest.raises(ValueError, match="timezone-aware"):
        await service.send_digests(now=datetime(2026, 10, 29, 7, 30))
