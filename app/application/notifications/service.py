from collections.abc import Iterable
from datetime import datetime
from uuid import UUID

from app.application.notifications.repository import (
    TaskNotificationRepository,
)
from app.domain.task_history import TaskHistory
from app.domain.task_notification import TaskNotification


class NotificationService:
    """Сценарии работы с внутренними уведомлениями."""

    def __init__(
        self,
        repository: TaskNotificationRepository,
    ) -> None:
        self.repository = repository

    async def create_for_history(
        self,
        *,
        history: TaskHistory,
        recipient_ids: Iterable[UUID],
    ) -> list[TaskNotification]:
        """
        Создаёт уведомления получателям для события TaskHistory.

        Автор события не получает уведомление о собственном действии.
        Повторяющиеся идентификаторы получателей исключаются.
        """
        # Гарантируем сохранение TaskHistory и получение его UUID.
        await self.repository.session.flush()

        recipients = dict.fromkeys(
            recipient_id
            for recipient_id in recipient_ids
            if recipient_id != history.actor_id
        )

        notifications = []
        for recipient_id in recipients:
            notification = await self.repository.create(
                task_history_id=history.id,
                recipient_id=recipient_id,
            )
            notifications.append(notification)

        return notifications

    async def get_unread(
        self,
        *,
        recipient_id: UUID,
        limit: int = 20,
        offset: int = 0,
    ) -> list[TaskNotification]:
        return await self.repository.get_unread(
            recipient_id=recipient_id,
            limit=limit,
            offset=offset,
        )

    async def count_unread(self, *, recipient_id: UUID) -> int:
        return await self.repository.count_unread(
            recipient_id=recipient_id,
        )

    async def mark_as_read(
        self,
        *,
        notification_id: UUID,
        recipient_id: UUID,
        read_at: datetime | None = None,
    ) -> bool:
        return await self.repository.mark_as_read(
            notification_id=notification_id,
            recipient_id=recipient_id,
            read_at=read_at,
        )