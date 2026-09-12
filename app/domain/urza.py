from datetime import date
from uuid import UUID

from sqlalchemy import Boolean, Date, Enum, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.domain.connection import Connection
from app.domain.enums import (
    ElementBase,
    RoomCategory,
    URZACategory,
    URZAStatus,
)
from app.infrastructure.database.base import Base
from app.infrastructure.database.mixins import (
    SoftDeleteMixin,
    TimestampMixin,
    UUIDMixin,
)


class URZA(
    UUIDMixin,
    TimestampMixin,
    SoftDeleteMixin,
    Base,
):
    __tablename__ = "urzas"

    connection_id: Mapped[UUID] = mapped_column(
        ForeignKey("connections.id"),
        nullable=False,
    )

    dispatch_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    rdu_subordination: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
    )

    inventory_number: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )

    commissioning_date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
    )

    status: Mapped[URZAStatus] = mapped_column(
        Enum(
            URZAStatus,
            name="urza_status",
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=False,
    )

    element_base: Mapped[ElementBase] = mapped_column(
        Enum(
            ElementBase,
            name="element_base",
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=False,
    )

    category: Mapped[URZACategory] = mapped_column(
        Enum(
            URZACategory,
            name="urza_category",
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=False,
    )

    room_category: Mapped[RoomCategory] = mapped_column(
        Enum(
            RoomCategory,
            name="room_category",
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=False,
    )

    complexity: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
    )

    connection: Mapped[Connection] = relationship()