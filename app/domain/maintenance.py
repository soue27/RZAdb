from datetime import date
from uuid import UUID

from sqlalchemy import Date, Enum, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.domain.enums import MaintenanceType
from app.domain.file import File
from app.domain.task import Task
from app.domain.user import User
from app.domain.urza import URZA
from app.infrastructure.database.base import Base
from app.infrastructure.database.mixins import SoftDeleteMixin, TimestampMixin, UUIDMixin


class TORecord(UUIDMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "to_records"

    urza_id: Mapped[UUID] = mapped_column(
        ForeignKey("urzas.id"),
        nullable=False,
    )

    historical_data: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    maintenance_date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
    )

    maintenance_type: Mapped[MaintenanceType] = mapped_column(
        Enum(
            MaintenanceType,
            name="maintenance_type",
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=False,
    )

    detected_deviations: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="Не выявлено",
    )

    measures_taken: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="Не требуется",
    )

    created_by: Mapped[UUID] = mapped_column(
        ForeignKey("users.id"),
        nullable=False,
    )

    scan_protocol_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("files.id"),
        nullable=True,
    )

    editable_protocol_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("files.id"),
        nullable=True,
    )

    signed_form_file_id: Mapped[UUID] = mapped_column(
        ForeignKey("files.id"),
        nullable=False,
    )

    task_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("tasks.id"),
        nullable=True,
    )

    urza: Mapped[URZA] = relationship()
    creator: Mapped[User] = relationship()
    scan_protocol: Mapped[File | None] = relationship(
        foreign_keys=[scan_protocol_id],
    )
    editable_protocol: Mapped[File | None] = relationship(
        foreign_keys=[editable_protocol_id],
    )
    signed_form_file: Mapped[File] = relationship(
        foreign_keys=[signed_form_file_id],
    )
    task: Mapped[Task | None] = relationship()