from uuid import UUID

from sqlalchemy import Enum, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.domain.enums import ProgramType
from app.domain.file import File
from app.domain.task import Task
from app.domain.urza import URZA
from app.infrastructure.database.base import Base
from app.infrastructure.database.mixins import (
    SoftDeleteMixin,
    TimestampMixin,
    UUIDMixin,
)


class Program(UUIDMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "programs"

    urza_id: Mapped[UUID] = mapped_column(
        ForeignKey("urzas.id"),
        nullable=False,
    )

    program_type: Mapped[ProgramType] = mapped_column(
        Enum(
            ProgramType,
            name="program_type",
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=False,
    )

    program_number: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    scan_file_id: Mapped[UUID] = mapped_column(
        ForeignKey("files.id"),
        nullable=False,
    )

    editable_file_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("files.id"),
        nullable=True,
    )

    task_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("tasks.id"),
        nullable=True,
    )

    urza: Mapped[URZA] = relationship()

    scan_file: Mapped[File] = relationship(
        foreign_keys=[scan_file_id],
    )

    editable_file: Mapped[File | None] = relationship(
        foreign_keys=[editable_file_id],
    )

    task: Mapped[Task | None] = relationship()