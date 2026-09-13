from datetime import date
from uuid import UUID

from sqlalchemy import Date, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.domain.urza import URZA
from app.domain.file import File
from app.domain.task import Task
from app.domain.user import User
from app.infrastructure.database.base import Base
from app.infrastructure.database.mixins import UUIDMixin


class SchemaForm(UUIDMixin, Base):
    __tablename__ = "schema_forms"

    urza_id: Mapped[UUID] = mapped_column(
        ForeignKey("urzas.id"),
        nullable=False,
        unique=True,
    )

    urza: Mapped[URZA] = relationship()


class SchemaRecord(UUIDMixin, Base):
    __tablename__ = "schema_records"

    schema_form_id: Mapped[UUID] = mapped_column(
        ForeignKey("schema_forms.id"),
        nullable=False,
    )

    schema_number: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    schema_name: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )

    change_description: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    change_justification: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    upload_date: Mapped[date] = mapped_column(
        Date,
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

    editable_file_id: Mapped[UUID] = mapped_column(
        ForeignKey("files.id"),
        nullable=False,
    )

    signed_form_file_id: Mapped[UUID] = mapped_column(
        ForeignKey("files.id"),
        nullable=False,
    )

    task_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("tasks.id"),
        nullable=True,
    )

    schema_form: Mapped[SchemaForm] = relationship()
    creator: Mapped[User] = relationship()
    scan_file: Mapped[File] = relationship(
        foreign_keys=[scan_file_id],
    )

    editable_file: Mapped[File] = relationship(
        foreign_keys=[editable_file_id],
    )

    signed_form_file: Mapped[File] = relationship(
        foreign_keys=[signed_form_file_id],
    )
    task: Mapped[Task | None] = relationship()