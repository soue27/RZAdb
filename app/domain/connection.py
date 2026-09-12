from uuid import UUID

from sqlalchemy import Boolean, Enum, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.domain.enums import OperationalCurrentType
from app.domain.substation import Substation
from app.infrastructure.database.base import Base
from app.infrastructure.database.mixins import (
    SoftDeleteMixin,
    TimestampMixin,
    UUIDMixin,
)


class Connection(
    UUIDMixin,
    TimestampMixin,
    SoftDeleteMixin,
    Base,
):
    __tablename__ = "connections"

    substation_id: Mapped[UUID] = mapped_column(
        ForeignKey("substations.id"),
        nullable=False,
    )

    dispatch_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    sap_code: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )

    asureo_code: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )

    rdu_subordination: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
    )

    operational_current_type: Mapped[OperationalCurrentType] = mapped_column(
        Enum(
            OperationalCurrentType,
            name="operational_current_type",
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=False,
    )

    substation: Mapped[Substation] = relationship()