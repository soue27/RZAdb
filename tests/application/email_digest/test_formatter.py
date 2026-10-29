from datetime import datetime
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest

from app.application.email_digest.formatter import (
    DigestTask,
    EmailDigestFormatter,
)

TZ = ZoneInfo("Asia/Yekaterinburg")


@pytest.fixture
def formatter() -> EmailDigestFormatter:
    return EmailDigestFormatter()


@pytest.fixture
def now() -> datetime:
    return datetime(2026, 10, 29, 7, 30, tzinfo=TZ)


def make_task(
    *,
    description: str = "Проверить защиту",
    status: str = "in_progress",
    deadline_at: datetime | None = None,
    assigned_to=None,
    assignee_name: str | None = None,
) -> DigestTask:
    return DigestTask(
        description=description,
        status=status,
        deadline_at=deadline_at,
        assigned_to=assigned_to,
        assignee_name=assignee_name,
    )


def test_engineer_digest_contains_task_and_counters(
    formatter: EmailDigestFormatter,
    now: datetime,
) -> None:
    engineer_id = uuid4()
    task = make_task(
        deadline_at=datetime(2026, 10, 31, 18, 0, tzinfo=TZ),
        assigned_to=engineer_id,
    )

    message = formatter.format_engineer_digest(
        recipient_name="Иван Иванов",
        recipient_id=engineer_id,
        tasks=[task],
        now=now,
    )

    assert "Сводка задач инженера" in message.subject
    assert "Иван Иванов" in message.text_body
    assert "Проверить защиту" in message.text_body
    assert "Всего активных задач: 1" in message.text_body
    assert "Просроченных задач: 0" in message.text_body
    assert "До срока: 2 кал. дн." in message.text_body
    assert "<html" in message.html_body
    assert "Проверить защиту" in message.html_body


def test_empty_engineer_digest_is_rendered(
    formatter: EmailDigestFormatter,
    now: datetime,
) -> None:
    message = formatter.format_engineer_digest(
        recipient_name="Иван Иванов",
        recipient_id=uuid4(),
        tasks=[],
        now=now,
    )

    assert "Активных задач нет." in message.text_body
    assert "Всего активных задач: 0" in message.text_body
    assert "Просроченных задач: 0" in message.text_body
    assert "Активных задач нет." in message.html_body


def test_task_overdue_on_same_calendar_day_has_zero_days_overdue(
    formatter: EmailDigestFormatter,
    now: datetime,
) -> None:
    task = make_task(
        deadline_at=datetime(2026, 10, 29, 7, 0, tzinfo=TZ),
    )

    message = formatter.format_engineer_digest(
        recipient_name="Инженер",
        recipient_id=uuid4(),
        tasks=[task],
        now=now,
    )

    assert "Просроченных задач: 1" in message.text_body
    assert "ПРОСРОЧЕНО на 0 кал. дн." in message.text_body


def test_task_due_later_today_is_not_overdue(
    formatter: EmailDigestFormatter,
    now: datetime,
) -> None:
    task = make_task(
        deadline_at=datetime(2026, 10, 29, 8, 0, tzinfo=TZ),
    )

    message = formatter.format_engineer_digest(
        recipient_name="Инженер",
        recipient_id=uuid4(),
        tasks=[task],
        now=now,
    )

    assert "Просроченных задач: 0" in message.text_body
    assert "До срока: 0 кал. дн." in message.text_body
    assert "ПРОСРОЧЕНО" not in message.text_body


def test_task_without_deadline_is_counted_separately(
    formatter: EmailDigestFormatter,
    now: datetime,
) -> None:
    message = formatter.format_engineer_digest(
        recipient_name="Инженер",
        recipient_id=uuid4(),
        tasks=[make_task(deadline_at=None)],
        now=now,
    )

    assert "Задач без срока: 1" in message.text_body
    assert "Срок: Не установлен" in message.text_body
    assert "Просроченных задач: 0" in message.text_body


def test_manager_digest_separates_own_workload(
    formatter: EmailDigestFormatter,
    now: datetime,
) -> None:
    manager_id = uuid4()
    engineer_id = uuid4()

    tasks = [
        make_task(
            description="Задача руководителя",
            deadline_at=datetime(2026, 10, 28, 12, 0, tzinfo=TZ),
            assigned_to=manager_id,
            assignee_name="Руководитель",
        ),
        make_task(
            description="Задача инженера",
            deadline_at=datetime(2026, 10, 30, 12, 0, tzinfo=TZ),
            assigned_to=engineer_id,
            assignee_name="Инженер",
        ),
        make_task(
            description="Задача без исполнителя",
            deadline_at=None,
            assigned_to=None,
            assignee_name=None,
        ),
    ]

    message = formatter.format_manager_digest(
        recipient_name="Руководитель",
        recipient_id=manager_id,
        tasks=tasks,
        now=now,
    )

    assert "Всего активных задач: 3" in message.text_body
    assert "Просроченных задач: 1" in message.text_body
    assert "Ваших задач в работе: 1" in message.text_body
    assert "Ваших просроченных задач: 1" in message.text_body
    assert "Исполнитель: Инженер" in message.text_body
    assert "Исполнитель: Не назначен" in message.text_body


def test_manager_own_overdue_count_excludes_other_executors(
    formatter: EmailDigestFormatter,
    now: datetime,
) -> None:
    manager_id = uuid4()
    engineer_id = uuid4()

    tasks = [
        make_task(
            description="Просроченная задача инженера",
            deadline_at=datetime(2026, 10, 28, 12, 0, tzinfo=TZ),
            assigned_to=engineer_id,
            assignee_name="Инженер",
        ),
    ]

    message = formatter.format_manager_digest(
        recipient_name="Руководитель",
        recipient_id=manager_id,
        tasks=tasks,
        now=now,
    )

    assert "Просроченных задач: 1" in message.text_body
    assert "Ваших задач в работе: 0" in message.text_body
    assert "Ваших просроченных задач: 0" in message.text_body


def test_naive_now_is_rejected(
    formatter: EmailDigestFormatter,
) -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        formatter.format_engineer_digest(
            recipient_name="Инженер",
            recipient_id=uuid4(),
            tasks=[],
            now=datetime(2026, 10, 29, 7, 30),
        )


def test_naive_deadline_is_rejected(
    formatter: EmailDigestFormatter,
    now: datetime,
) -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        formatter.format_engineer_digest(
            recipient_name="Инженер",
            recipient_id=uuid4(),
            tasks=[
                make_task(
                    deadline_at=datetime(2026, 10, 29, 8, 0),
                )
            ],
            now=now,
        )


def test_html_escapes_user_supplied_text(
    formatter: EmailDigestFormatter,
    now: datetime,
) -> None:
    task = make_task(description="<script>alert('x')</script>")

    message = formatter.format_engineer_digest(
        recipient_name="<b>Инженер</b>",
        recipient_id=uuid4(),
        tasks=[task],
        now=now,
    )

    assert "<script>" not in message.html_body
    assert "&lt;script&gt;" in message.html_body
    assert "<b>Инженер</b>" not in message.html_body
