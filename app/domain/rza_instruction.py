from datetime import date
from uuid import UUID

from sqlalchemy import Date, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.domain.file import File
from app.domain.substation import Substation
from app.domain.user import User
from app.infrastructure.database.base import Base
from app.infrastructure.database.mixins import (
    SoftDeleteMixin,
    TimestampMixin,
    UUIDMixin,
)


class RZAInstruction(UUIDMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "rza_instructions"

    substation_id: Mapped[UUID] = mapped_column(
        ForeignKey("substations.id"),
        nullable=False,
        unique=True,
    )

    substation: Mapped[Substation] = relationship()


class RZAInstructionVersion(
    UUIDMixin,
    TimestampMixin,
    SoftDeleteMixin,
    Base,
):
    __tablename__ = "rza_instruction_versions"

    rza_instruction_id: Mapped[UUID] = mapped_column(
        ForeignKey("rza_instructions.id"),
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

    scan_file_id: Mapped[UUID] = mapped_column(
        ForeignKey("files.id"),
        nullable=False,
    )

    editable_file_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("files.id"),
        nullable=True,
    )

    rza_instruction: Mapped[RZAInstruction] = relationship()
    creator: Mapped[User] = relationship(
        foreign_keys=lambda: [RZAInstructionVersion.created_by],
    )

    scan_file: Mapped[File] = relationship(
        foreign_keys=[scan_file_id],
    )

    editable_file: Mapped[File | None] = relationship(
        foreign_keys=[editable_file_id],
    )
