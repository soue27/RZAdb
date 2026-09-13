from datetime import date
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import Date, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.domain.file import File
from app.domain.substation import Substation
from app.domain.user import User
from app.infrastructure.database.base import Base
from app.infrastructure.database.mixins import TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.domain.inspection_task import InspectionTask


class Inspection(UUIDMixin, TimestampMixin, Base):
    """Результат проведённого осмотра подстанции."""

    __tablename__ = "inspections"

    substation_id: Mapped[UUID] = mapped_column(
        ForeignKey("substations.id"),
        nullable=False,
    )
    inspection_task_id: Mapped[UUID] = mapped_column(
        ForeignKey("inspection_tasks.id"),
        nullable=False,
        unique=True,
    )
    inspection_date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
    )
    remarks: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    scan_file_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("files.id"),
        nullable=True,
    )
    editable_file_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("files.id"),
        nullable=True,
    )
    created_by: Mapped[UUID] = mapped_column(
        ForeignKey("users.id"),
        nullable=False,
    )

    substation: Mapped[Substation] = relationship()
    inspection_task: Mapped["InspectionTask"] = relationship(
        back_populates="inspection",
    )
    creator: Mapped[User] = relationship()

    scan_file: Mapped[File | None] = relationship(
        foreign_keys=[scan_file_id],
    )
    editable_file: Mapped[File | None] = relationship(
        foreign_keys=[editable_file_id],
    )