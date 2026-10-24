from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, Enum, ForeignKey, Index, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.domain.connection import Connection
from app.domain.enums import ArchiveEventType
from app.domain.substation import Substation
from app.domain.urza import URZA
from app.domain.user import User
from app.infrastructure.database.base import Base
from app.infrastructure.database.mixins import UUIDMixin


class ArchiveEvent(UUIDMixin, Base):
    __tablename__ = "archive_events"
    __table_args__ = (
        CheckConstraint(
            "(CASE WHEN substation_id IS NOT NULL THEN 1 ELSE 0 END) + "
            "(CASE WHEN connection_id IS NOT NULL THEN 1 ELSE 0 END) + "
            "(CASE WHEN urza_id IS NOT NULL THEN 1 ELSE 0 END) = 1",
            name="ck_archive_events_exactly_one_object",
        ),
        CheckConstraint(
            "reason IS NULL OR char_length(reason) <= 2000",
            name="ck_archive_events_reason_max_length",
        ),
        CheckConstraint(
            "event_type != 'archived' OR "
            "(reason IS NOT NULL AND char_length(btrim(reason)) > 0)",
            name="ck_archive_events_archived_reason_required",
        ),
        Index("ix_archive_events_operation_id", "operation_id"),
        Index(
            "ix_archive_events_substation_history",
            "substation_id",
            "occurred_at",
            postgresql_where=text("substation_id IS NOT NULL"),
        ),
        Index(
            "ix_archive_events_connection_history",
            "connection_id",
            "occurred_at",
            postgresql_where=text("connection_id IS NOT NULL"),
        ),
        Index(
            "ix_archive_events_urza_history",
            "urza_id",
            "occurred_at",
            postgresql_where=text("urza_id IS NOT NULL"),
        ),
        Index(
            "uq_archive_events_operation_substation",
            "operation_id",
            "substation_id",
            unique=True,
            postgresql_where=text("substation_id IS NOT NULL"),
        ),
        Index(
            "uq_archive_events_operation_connection",
            "operation_id",
            "connection_id",
            unique=True,
            postgresql_where=text("connection_id IS NOT NULL"),
        ),
        Index(
            "uq_archive_events_operation_urza",
            "operation_id",
            "urza_id",
            unique=True,
            postgresql_where=text("urza_id IS NOT NULL"),
        ),
    )

    operation_id: Mapped[UUID] = mapped_column(nullable=False)

    event_type: Mapped[ArchiveEventType] = mapped_column(
        Enum(
            ArchiveEventType,
            name="archive_event_type",
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=False,
    )

    actor_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", name="fk_archive_events_actor_id_users"),
        nullable=False,
    )

    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    substation_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("substations.id", name="fk_archive_events_substation_id_substations"),
        nullable=True,
    )

    connection_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("connections.id", name="fk_archive_events_connection_id_connections"),
        nullable=True,
    )

    urza_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("urzas.id", name="fk_archive_events_urza_id_urzas"),
        nullable=True,
    )

    actor: Mapped[User] = relationship()
    substation: Mapped[Substation | None] = relationship()
    connection: Mapped[Connection | None] = relationship()
    urza: Mapped[URZA | None] = relationship()
