from uuid import UUID

from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.domain.urza import URZA
from app.infrastructure.database.base import Base
from app.infrastructure.database.mixins import (
    SoftDeleteMixin,
    TimestampMixin,
    UUIDMixin,
)


class OTD(
    UUIDMixin,
    TimestampMixin,
    SoftDeleteMixin,
    Base,
):
    __tablename__ = "otds"

    urza_id: Mapped[UUID] = mapped_column(
        ForeignKey("urzas.id"),
        nullable=False,
        unique=True,
    )

    urza: Mapped[URZA] = relationship()