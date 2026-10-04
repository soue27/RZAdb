from datetime import date
from uuid import UUID

from sqlalchemy import Date, Enum, ForeignKey, Index, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.domain.enums import DocumentStatus
from app.domain.file import File
from app.domain.task import Task
from app.domain.urza import URZA
from app.domain.user import User
from app.infrastructure.database.base import Base
from app.infrastructure.database.mixins import (
    SoftDeleteMixin,
    TimestampMixin,
    UUIDMixin,
)


class SchemaForm(UUIDMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "schema_forms"

    urza_id: Mapped[UUID] = mapped_column(
        ForeignKey("urzas.id"),
        nullable=False,
        unique=True,
    )

    urza: Mapped[URZA] = relationship()


class SchemaRecord(UUIDMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "schema_records"
    __table_args__ = (
        Index(
            "uq_schema_records_one_active_unfinished_per_form",
            "schema_form_id",
            unique=True,
            postgresql_where=text(
                "deleted_at IS NULL AND status IN ('draft', 'under_review')"
            ),
        ),
        Index(
            "uq_schema_records_one_active_per_task",
            "task_id",
            unique=True,
            postgresql_where=text(
                "task_id IS NOT NULL AND deleted_at IS NULL"
            ),
        ),
    )

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

    status: Mapped[DocumentStatus] = mapped_column(
        Enum(
            DocumentStatus,
            name="document_status",
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=False,
    )

    scan_file_id: Mapped[UUID] = mapped_column(
        ForeignKey("files.id"),
        nullable=True,
    )

    editable_file_id: Mapped[UUID] = mapped_column(
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

    schema_form: Mapped[SchemaForm] = relationship()
    creator: Mapped[User] = relationship(
        foreign_keys=lambda: [SchemaRecord.created_by],
    )
    scan_file: Mapped[File | None] = relationship(
        foreign_keys=[scan_file_id],
    )

    editable_file: Mapped[File | None] = relationship(
        foreign_keys=[editable_file_id],
    )

    signed_form_file: Mapped[File] = relationship(
        foreign_keys=[signed_form_file_id],
    )
    task: Mapped[Task | None] = relationship()
