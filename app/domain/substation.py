from decimal import Decimal
from uuid import UUID

from sqlalchemy import Enum, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.domain.enterprise import Enterprise
from app.domain.enums import HighestVoltage
from app.infrastructure.database.base import Base
from app.infrastructure.database.mixins import (
    SoftDeleteMixin,
    TimestampMixin,
    UUIDMixin,
)


class Substation(
    UUIDMixin,
    TimestampMixin,
    SoftDeleteMixin,
    Base,
):
    __tablename__ = "substations"

    enterprise_id: Mapped[UUID] = mapped_column(
        ForeignKey("enterprises.id"),
        nullable=False,
    )

    highest_voltage: Mapped[HighestVoltage] = mapped_column(
        Enum(
            HighestVoltage,
            name="highest_voltage",
            values_callable=lambda enum: [item.value for item in enum],
        ),
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

    latitude: Mapped[Decimal | None] = mapped_column(
        Numeric(9, 6),
        nullable=True,
    )

    longitude: Mapped[Decimal | None] = mapped_column(
        Numeric(9, 6),
        nullable=True,
    )

    address: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    enterprise: Mapped[Enterprise] = relationship()