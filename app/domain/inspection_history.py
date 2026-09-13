from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.domain.enums import TaskStatus
from app.domain.inspection_task import InspectionTask
from app.domain.user import User
from app.infrastructure.database.base import Base
from app.infrastructure.database.mixins import UUIDMixin


class InspectionHistory(UUIDMixin, Base):
    """Неизменяемая история работы с задачей осмотра."""

    __tablename__ = "inspection_history"

    inspection_task_id: Mapped[UUID] = mapped_column(
        ForeignKey("inspection_tasks.id"),
        nullable=False,
    )
    event_type: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )
    old_status: Mapped[TaskStatus | None] = mapped_column(
        Enum(
            TaskStatus,
            name="task_status",
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=True,
    )
    new_status: Mapped[TaskStatus | None] = mapped_column(
        Enum(
            TaskStatus,
            name="task_status",
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=True,
    )
    actor_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id"),
        nullable=False,
    )
    comment: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    inspection_task: Mapped[InspectionTask] = relationship()
    actor: Mapped[User] = relationship()