from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, Enum, ForeignKey, Index, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.domain.enums import MaintenanceType, TaskStatus, TaskWorkType
from app.domain.urza import URZA
from app.domain.substation import Substation
from app.domain.user import User
from app.infrastructure.database.base import Base
from app.infrastructure.database.mixins import (
    SoftDeleteMixin,
    TimestampMixin,
    UUIDMixin,
)


class Task(UUIDMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "tasks"

    __table_args__ = (
        CheckConstraint(
            "(urza_id IS NOT NULL AND substation_id IS NULL) OR "
            "(urza_id IS NULL AND substation_id IS NOT NULL)",
            name="ck_tasks_exactly_one_parent",
        ),
        CheckConstraint(
            "substation_id IS NULL OR work_type IN ('instruction', 'schemes')",
            name="ck_tasks_substation_work_type",
        ),
        Index("ix_tasks_substation_id", "substation_id"),
    )

    urza_id: Mapped[UUID] = mapped_column(
        ForeignKey("urzas.id"),
        nullable=True,
    )

    substation_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("substations.id", name="fk_tasks_substation_id_substations"),
        nullable=True,
    )

    work_type: Mapped[TaskWorkType] = mapped_column(
        Enum(
            TaskWorkType,
            name="task_work_type",
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=False,
    )

    maintenance_type: Mapped[MaintenanceType | None] = mapped_column(
        Enum(
            MaintenanceType,
            name="maintenance_type",
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=True,
    )

    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # При создании задача ещё может быть неназначенной.
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

    urza: Mapped[URZA | None] = relationship()
    substation: Mapped[Substation | None] = relationship()

    created_by_user: Mapped[User] = relationship(
        foreign_keys=lambda: [Task.created_by],
    )

    assigned_to_user: Mapped[User | None] = relationship(
        foreign_keys=[assigned_to],
    )
