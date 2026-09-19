from datetime import date, datetime
from uuid import UUID

from sqlalchemy import Date, DateTime, ForeignKey, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.domain.file import File
from app.domain.urza import URZA
from app.domain.user import User
from app.infrastructure.database.base import Base
from app.infrastructure.database.mixins import UUIDMixin


class URZAInstruction(UUIDMixin, Base):
    __tablename__ = "urza_instructions"

    urza_id: Mapped[UUID] = mapped_column(
        ForeignKey("urzas.id"),
        nullable=False,
        unique=True,
    )

    urza: Mapped[URZA] = relationship()


class URZAInstructionVersion(UUIDMixin, Base):
    __tablename__ = "urza_instruction_versions"

    urza_instruction_id: Mapped[UUID] = mapped_column(
        ForeignKey("urza_instructions.id"),
        nullable=False,
    )

    version_number: Mapped[int] = mapped_column(
        nullable=False,
    )

    effective_date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
    )

    change_description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    change_justification: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    created_by: Mapped[UUID] = mapped_column(
        ForeignKey("users.id"),
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

    urza_instruction: Mapped[URZAInstruction] = relationship()
    creator: Mapped[User] = relationship()
    scan_file: Mapped[File] = relationship(
        foreign_keys=[scan_file_id],
    )
    editable_file: Mapped[File | None] = relationship(
        foreign_keys=[editable_file_id],
    )