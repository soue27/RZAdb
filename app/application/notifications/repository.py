from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.domain.task import Task
from app.domain.task_history import TaskHistory

from app.domain.task_notification import TaskNotification


class TaskNotificationRepository:
    """Работа с внутренними уведомлениями пользователей."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        *,
        task_history_id: UUID,
        recipient_id: UUID,
    ) -> TaskNotification:
        """Создаёт уведомление одному получателю."""
        notification = TaskNotification(
            task_history_id=task_history_id,
            recipient_id=recipient_id,
        )

        self.session.add(notification)
        await self.session.flush()
        await self.session.refresh(notification)

        return notification

    async def get_unread(
        self,
        *,
        recipient_id: UUID,
        limit: int = 20,
        offset: int = 0,
    ) -> list[TaskNotification]:
        """Возвращает непрочитанные уведомления конкретного пользователя."""
        result = await self.session.scalars(
            select(TaskNotification)
            .options(
                selectinload(TaskNotification.task_history).options(
                    selectinload(TaskHistory.task).options(
                        selectinload(Task.urza),
                        selectinload(Task.substation),
                    ),
                    selectinload(TaskHistory.actor),
                )
            )
            .where(
                TaskNotification.recipient_id == recipient_id,
                TaskNotification.read_at.is_(None),
            )
            .order_by(
                TaskNotification.created_at.desc(),
                TaskNotification.id.desc(),
            )
            .limit(limit)
            .offset(offset)
        )

        return list(result.all())

    async def count_unread(self, *, recipient_id: UUID) -> int:
        """Возвращает количество непрочитанных уведомлений пользователя."""
        result = await self.session.scalar(
            select(func.count())
            .select_from(TaskNotification)
            .where(
                TaskNotification.recipient_id == recipient_id,
                TaskNotification.read_at.is_(None),
            )
        )

        return result or 0

    async def get_by_id(
            self,
            *,
            notification_id: UUID,
            recipient_id: UUID,
    ) -> TaskNotification | None:
        """Получает уведомление только в пределах владельца."""
        result = await self.session.scalars(
            select(TaskNotification)
            .options(
                selectinload(TaskNotification.task_history),
            )
            .where(
                TaskNotification.id == notification_id,
                TaskNotification.recipient_id == recipient_id,
            )
        )

        return result.scalar_one_or_none()

    async def mark_as_read(
        self,
        *,
        notification_id: UUID,
        recipient_id: UUID,
        read_at: datetime | None = None,
    ) -> bool:
        """
        Помечает уведомление прочитанным.

        Возвращает True, если запись была изменена.
        Повторное выполнение безопасно и возвращает False.
        """
        result = await self.session.execute(
            update(TaskNotification)
            .where(
                TaskNotification.id == notification_id,
                TaskNotification.recipient_id == recipient_id,
                TaskNotification.read_at.is_(None),
            )
            .values(read_at=read_at or datetime.now(UTC))
            .returning(TaskNotification.id)
        )

        return result.scalar_one_or_none() is not None
