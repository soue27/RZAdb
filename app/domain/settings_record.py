from datetime import date, datetime
from uuid import UUID

from sqlalchemy import Date, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.domain.file import File
from app.domain.rza_settings import SettingsForm
from app.domain.task import Task
from app.domain.user import User
from app.infrastructure.database.base import Base
from app.infrastructure.database.mixins import UUIDMixin


class SettingsRecord(UUIDMixin, Base):
    __tablename__ = "settings_records"

    settings_form_id: Mapped[UUID] = mapped_column(
        ForeignKey("settings_forms.id"),
        nullable=False,
    )

    change_date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
    )

    parameter_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    initial_setting: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    new_setting: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    change_reason: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    created_by: Mapped[UUID] = mapped_column(
        ForeignKey("users.id"),
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
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

    settings_form: Mapped[SettingsForm] = relationship()
    creator: Mapped[User] = relationship()
    signed_form_file: Mapped[File] = relationship()
    task: Mapped[Task | None] = relationship()