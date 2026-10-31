
from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock, call
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.notifications.repository import TaskNotificationRepository
from app.application.notifications.service import NotificationService
from app.domain.task_history import TaskHistory
from app.domain.task_notification import TaskNotification


@pytest.fixture
def repository() -> TaskNotificationRepository:
    """Репозиторий с изолированными mock-зависимостями."""
    session = Mock(spec=AsyncSession)
    session.flush = AsyncMock()

    repo = TaskNotificationRepository(session)
    repo.create = AsyncMock()
    repo.get_unread = AsyncMock()
    repo.count_unread = AsyncMock()
    repo.mark_as_read = AsyncMock()

    return repo


@pytest.fixture
def service(
    repository: TaskNotificationRepository,
) -> NotificationService:
    return NotificationService(repository=repository)


@pytest.fixture
def history() -> TaskHistory:
    """Событие с заранее заданными UUID, как после flush в БД."""
    return TaskHistory(
        id=uuid4(),
        task_id=uuid4(),
        event_type="assigned",
        actor_id=uuid4(),
        created_at=datetime.now(UTC),
    )


@pytest.mark.asyncio
async def test_create_for_history_creates_notification_for_each_recipient(
    service: NotificationService,
    repository: TaskNotificationRepository,
    history: TaskHistory,
) -> None:
    recipient_ids = [uuid4(), uuid4(), uuid4()]
    expected_notifications = [
        TaskNotification(
            task_history_id=history.id,
            recipient_id=recipient_id,
        )
        for recipient_id in recipient_ids
    ]
    repository.create.side_effect = expected_notifications

    result = await service.create_for_history(
        history=history,
        recipient_ids=recipient_ids,
    )

    assert result == expected_notifications
    assert repository.session.flush.await_count == 1
    assert repository.create.await_count == len(recipient_ids)

    repository.create.assert_has_awaits(
        [
            call(
                task_history_id=history.id,
                recipient_id=recipient_id,
            )
            for recipient_id in recipient_ids
        ]
    )


@pytest.mark.asyncio
async def test_create_for_history_does_not_notify_event_actor(
    service: NotificationService,
    repository: TaskNotificationRepository,
    history: TaskHistory,
) -> None:
    recipient_id = uuid4()

    await service.create_for_history(
        history=history,
        recipient_ids=[history.actor_id, recipient_id],
    )

    repository.create.assert_awaited_once_with(
        task_history_id=history.id,
        recipient_id=recipient_id,
    )


@pytest.mark.asyncio
async def test_create_for_history_removes_duplicate_recipients(
    service: NotificationService,
    repository: TaskNotificationRepository,
    history: TaskHistory,
) -> None:
    first_recipient_id = uuid4()
    second_recipient_id = uuid4()

    await service.create_for_history(
        history=history,
        recipient_ids=[
            first_recipient_id,
            second_recipient_id,
            first_recipient_id,
            second_recipient_id,
            first_recipient_id,
        ],
    )

    assert repository.create.await_count == 2
    repository.create.assert_has_awaits(
        [
            call(
                task_history_id=history.id,
                recipient_id=first_recipient_id,
            ),
            call(
                task_history_id=history.id,
                recipient_id=second_recipient_id,
            ),
        ]
    )


@pytest.mark.asyncio
async def test_create_for_history_returns_empty_list_without_recipients(
    service: NotificationService,
    repository: TaskNotificationRepository,
    history: TaskHistory,
) -> None:
    result = await service.create_for_history(
        history=history,
        recipient_ids=[],
    )

    assert result == []
    repository.session.flush.assert_awaited_once_with()
    repository.create.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_for_history_returns_empty_list_when_only_actor_is_recipient(
    service: NotificationService,
    repository: TaskNotificationRepository,
    history: TaskHistory,
) -> None:
    result = await service.create_for_history(
        history=history,
        recipient_ids=[history.actor_id, history.actor_id],
    )

    assert result == []
    repository.create.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_for_history_flushes_before_creating_notifications(
    service: NotificationService,
    repository: TaskNotificationRepository,
    history: TaskHistory,
) -> None:
    recipient_id = uuid4()

    async def create_notification(
        *,
        task_history_id,
        recipient_id,
    ) -> TaskNotification:
        repository.session.flush.assert_awaited_once_with()

        return TaskNotification(
            task_history_id=task_history_id,
            recipient_id=recipient_id,
        )

    repository.create.side_effect = create_notification

    result = await service.create_for_history(
        history=history,
        recipient_ids=[recipient_id],
    )

    assert len(result) == 1
    repository.session.flush.assert_awaited_once_with()
    repository.create.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_unread_delegates_to_repository(
    service: NotificationService,
    repository: TaskNotificationRepository,
) -> None:
    recipient_id = uuid4()
    expected_notifications = [
        TaskNotification(
            task_history_id=uuid4(),
            recipient_id=recipient_id,
        ),
    ]
    repository.get_unread.return_value = expected_notifications

    result = await service.get_unread(
        recipient_id=recipient_id,
        limit=10,
        offset=20,
    )

    assert result == expected_notifications
    repository.get_unread.assert_awaited_once_with(
        recipient_id=recipient_id,
        limit=10,
        offset=20,
    )


@pytest.mark.asyncio
async def test_count_unread_delegates_to_repository(
    service: NotificationService,
    repository: TaskNotificationRepository,
) -> None:
    recipient_id = uuid4()
    repository.count_unread.return_value = 7

    result = await service.count_unread(
        recipient_id=recipient_id,
    )

    assert result == 7
    repository.count_unread.assert_awaited_once_with(
        recipient_id=recipient_id,
    )


@pytest.mark.asyncio
async def test_mark_as_read_delegates_to_repository(
    service: NotificationService,
    repository: TaskNotificationRepository,
) -> None:
    notification_id = uuid4()
    recipient_id = uuid4()
    read_at = datetime(2026, 10, 31, 12, 0, tzinfo=UTC)
    repository.mark_as_read.return_value = True

    result = await service.mark_as_read(
        notification_id=notification_id,
        recipient_id=recipient_id,
        read_at=read_at,
    )

    assert result is True
    repository.mark_as_read.assert_awaited_once_with(
        notification_id=notification_id,
        recipient_id=recipient_id,
        read_at=read_at,
    )


@pytest.mark.asyncio
async def test_mark_as_read_passes_none_when_read_at_not_provided(
    service: NotificationService,
    repository: TaskNotificationRepository,
) -> None:
    notification_id = uuid4()
    recipient_id = uuid4()
    repository.mark_as_read.return_value = False

    result = await service.mark_as_read(
        notification_id=notification_id,
        recipient_id=recipient_id,
    )

    assert result is False
    repository.mark_as_read.assert_awaited_once_with(
        notification_id=notification_id,
        recipient_id=recipient_id,
        read_at=None,
    )
