from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, Enum, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.domain.enums import TaskStatus
from app.domain.substation import Substation
from app.domain.user import User
from app.infrastructure.database.base import Base
from app.infrastructure.database.mixins import (
    SoftDeleteMixin,
    TimestampMixin,
    UUIDMixin,
)


class InspectionTask(UUIDMixin, TimestampMixin, SoftDeleteMixin, Base):
    """Задача на проведение осмотра подстанции."""

    __tablename__ = "inspection_tasks"

    substation_id: Mapped[UUID] = mapped_column(
        ForeignKey("substations.id"),
        nullable=False,
    )
    created_by: Mapped[UUID] = mapped_column(
        ForeignKey("users.id"),
        nullable=False,
    )
    assigned_to: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id"),
        nullable=True,
    )
    status: Mapped[TaskStatus] = mapped_column(
        Enum(
            TaskStatus,
            name="task_status",
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=False,
        default=TaskStatus.CREATED,
    )
    assigned_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    acceptance_deadline_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    deadline_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    closed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    substation: Mapped[Substation] = relationship()
    created_by_user: Mapped[User] = relationship(
        foreign_keys=[created_by],
    )
    assigned_to_user: Mapped[User | None] = relationship(
        foreign_keys=[assigned_to],
    )
    inspection: Mapped["Inspection | None"] = relationship(
        back_populates="inspection_task",
        uselist=False,
    )