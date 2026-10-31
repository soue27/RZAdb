from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.domain.task_history import TaskHistory
from app.domain.user import User
from app.infrastructure.database.base import Base
from app.infrastructure.database.mixins import UUIDMixin


class TaskNotification(UUIDMixin, Base):
    __tablename__ = "task_notifications"

    __table_args__ = (
        UniqueConstraint(
            "task_history_id",
            "recipient_id",
            name="uq_task_notifications_history_recipient",
        ),
        Index(
            "ix_task_notifications_unread_recipient_created",
            "recipient_id",
            "created_at",
            "id",
            postgresql_where=text("read_at IS NULL"),
        ),
    )

    task_history_id: Mapped[UUID] = mapped_column(
        ForeignKey("task_history.id"),
        nullable=False,
    )

    recipient_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id"),
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    read_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    task_history: Mapped[TaskHistory] = relationship()
    recipient: Mapped[User] = relationship()