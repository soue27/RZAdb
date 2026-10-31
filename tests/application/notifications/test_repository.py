
from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.notifications.repository import TaskNotificationRepository
from app.domain.task_notification import TaskNotification


@pytest.fixture
def session() -> Mock:
    """Подготовленная mock-сессия SQLAlchemy."""
    db_session = Mock(spec=AsyncSession)

    db_session.add = Mock()
    db_session.flush = AsyncMock()
    db_session.refresh = AsyncMock()
    db_session.scalars = AsyncMock()
    db_session.scalar = AsyncMock()
    db_session.execute = AsyncMock()

    return db_session


@pytest.fixture
def repository(session: Mock) -> TaskNotificationRepository:
    return TaskNotificationRepository(session)


def compile_statement(statement) -> tuple[str, dict]:
    """Возвращает SQL и параметры скомпилированного выражения."""
    compiled = statement.compile(
        dialect=postgresql.dialect(),
    )
    return str(compiled), compiled.params


def assert_statement_contains(statement, *fragments: str) -> dict:
    """Проверяет структуру SQL-запроса и возвращает его параметры."""
    sql, params = compile_statement(statement)

    normalized_sql = " ".join(sql.split()).lower()

    for fragment in fragments:
        assert fragment.lower() in normalized_sql

    return params


@pytest.mark.asyncio
async def test_create_notification(
    repository: TaskNotificationRepository,
    session: Mock,
) -> None:
    task_history_id = uuid4()
    recipient_id = uuid4()

    notification = await repository.create(
        task_history_id=task_history_id,
        recipient_id=recipient_id,
    )

    assert isinstance(notification, TaskNotification)
    assert notification.task_history_id == task_history_id
    assert notification.recipient_id == recipient_id
    assert notification.read_at is None

    session.add.assert_called_once_with(notification)
    session.flush.assert_awaited_once_with()
    session.refresh.assert_awaited_once_with(notification)


@pytest.mark.asyncio
async def test_get_unread_returns_notifications(
    repository: TaskNotificationRepository,
    session: Mock,
) -> None:
    recipient_id = uuid4()

    expected_notifications = [
        TaskNotification(
            task_history_id=uuid4(),
            recipient_id=recipient_id,
        ),
        TaskNotification(
            task_history_id=uuid4(),
            recipient_id=recipient_id,
        ),
    ]

    scalars_result = Mock()
    scalars_result.all.return_value = expected_notifications
    session.scalars.return_value = scalars_result

    result = await repository.get_unread(
        recipient_id=recipient_id,
    )

    assert result == expected_notifications

    session.scalars.assert_awaited_once()
    scalars_result.all.assert_called_once_with()

    statement = session.scalars.await_args.args[0]
    params = assert_statement_contains(
        statement,
        "task_notifications.recipient_id",
        "task_notifications.read_at is null",
    )

    assert recipient_id in params.values()


@pytest.mark.asyncio
async def test_get_unread_applies_pagination_and_sorting(
    repository: TaskNotificationRepository,
    session: Mock,
) -> None:
    recipient_id = uuid4()

    scalars_result = Mock()
    scalars_result.all.return_value = []
    session.scalars.return_value = scalars_result

    await repository.get_unread(
        recipient_id=recipient_id,
        limit=10,
        offset=20,
    )

    statement = session.scalars.await_args.args[0]

    sql, params = compile_statement(statement)
    normalized_sql = " ".join(sql.split()).lower()

    assert "order by task_notifications.created_at desc" in normalized_sql
    assert "task_notifications.id desc" in normalized_sql
    assert "limit" in normalized_sql
    assert "offset" in normalized_sql

    assert 10 in params.values()
    assert 20 in params.values()
    assert recipient_id in params.values()


@pytest.mark.asyncio
async def test_count_unread_returns_count(
    repository: TaskNotificationRepository,
    session: Mock,
) -> None:
    recipient_id = uuid4()
    session.scalar.return_value = 5

    result = await repository.count_unread(
        recipient_id=recipient_id,
    )

    assert result == 5

    session.scalar.assert_awaited_once()

    statement = session.scalar.await_args.args[0]
    params = assert_statement_contains(
        statement,
        "count",
        "task_notifications.recipient_id",
        "task_notifications.read_at is null",
    )

    assert recipient_id in params.values()


@pytest.mark.asyncio
async def test_count_unread_returns_zero_when_result_is_none(
    repository: TaskNotificationRepository,
    session: Mock,
) -> None:
    session.scalar.return_value = None

    result = await repository.count_unread(
        recipient_id=uuid4(),
    )

    assert result == 0


@pytest.mark.asyncio
async def test_get_by_id_returns_own_notification(
    repository: TaskNotificationRepository,
    session: Mock,
) -> None:
    notification_id = uuid4()
    recipient_id = uuid4()

    notification = TaskNotification(
        task_history_id=uuid4(),
        recipient_id=recipient_id,
    )

    scalars_result = Mock()
    scalars_result.scalar_one_or_none.return_value = notification
    session.scalars.return_value = scalars_result

    result = await repository.get_by_id(
        notification_id=notification_id,
        recipient_id=recipient_id,
    )

    assert result is notification

    scalars_result.scalar_one_or_none.assert_called_once_with()

    statement = session.scalars.await_args.args[0]
    params = assert_statement_contains(
        statement,
        "task_notifications.id",
        "task_notifications.recipient_id",
    )

    assert notification_id in params.values()
    assert recipient_id in params.values()


@pytest.mark.asyncio
async def test_get_by_id_returns_none_for_another_user(
    repository: TaskNotificationRepository,
    session: Mock,
) -> None:
    scalars_result = Mock()
    scalars_result.scalar_one_or_none.return_value = None
    session.scalars.return_value = scalars_result

    notification_id = uuid4()
    another_user_id = uuid4()

    result = await repository.get_by_id(
        notification_id=notification_id,
        recipient_id=another_user_id,
    )

    assert result is None

    statement = session.scalars.await_args.args[0]
    params = assert_statement_contains(
        statement,
        "task_notifications.id",
        "task_notifications.recipient_id",
    )

    assert notification_id in params.values()
    assert another_user_id in params.values()


@pytest.mark.asyncio
async def test_mark_as_read_returns_true(
    repository: TaskNotificationRepository,
    session: Mock,
) -> None:
    notification_id = uuid4()
    recipient_id = uuid4()
    read_at = datetime(2026, 10, 31, 12, 0, tzinfo=UTC)

    execute_result = Mock()
    execute_result.scalar_one_or_none.return_value = notification_id
    session.execute.return_value = execute_result

    result = await repository.mark_as_read(
        notification_id=notification_id,
        recipient_id=recipient_id,
        read_at=read_at,
    )

    assert result is True

    execute_result.scalar_one_or_none.assert_called_once_with()

    statement = session.execute.await_args.args[0]
    params = assert_statement_contains(
        statement,
        "update task_notifications",
        "task_notifications.id",
        "task_notifications.recipient_id",
        "task_notifications.read_at is null",
        "returning task_notifications.id",
    )

    assert notification_id in params.values()
    assert recipient_id in params.values()
    assert read_at in params.values()


@pytest.mark.asyncio
async def test_mark_as_read_returns_false_when_already_read(
    repository: TaskNotificationRepository,
    session: Mock,
) -> None:
    execute_result = Mock()
    execute_result.scalar_one_or_none.return_value = None
    session.execute.return_value = execute_result

    result = await repository.mark_as_read(
        notification_id=uuid4(),
        recipient_id=uuid4(),
    )

    assert result is False

    statement = session.execute.await_args.args[0]
    assert_statement_contains(
        statement,
        "update task_notifications",
        "task_notifications.read_at is null",
        "returning task_notifications.id",
    )


@pytest.mark.asyncio
async def test_mark_as_read_returns_false_for_another_user(
    repository: TaskNotificationRepository,
    session: Mock,
) -> None:
    notification_id = uuid4()
    another_user_id = uuid4()

    execute_result = Mock()
    execute_result.scalar_one_or_none.return_value = None
    session.execute.return_value = execute_result

    result = await repository.mark_as_read(
        notification_id=notification_id,
        recipient_id=another_user_id,
    )

    assert result is False

    statement = session.execute.await_args.args[0]
    params = assert_statement_contains(
        statement,
        "update task_notifications",
        "task_notifications.id",
        "task_notifications.recipient_id",
        "task_notifications.read_at is null",
    )

    assert notification_id in params.values()
    assert another_user_id in params.values()
