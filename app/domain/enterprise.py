from uuid import UUID

from sqlalchemy import Enum, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.domain.enums import EnterpriseType
from app.infrastructure.database.base import Base
from app.infrastructure.database.mixins import (
    SoftDeleteMixin,
    TimestampMixin,
    UUIDMixin,
)


class Enterprise(
    UUIDMixin,
    TimestampMixin,
    SoftDeleteMixin,
    Base,
):
    __tablename__ = "enterprises"

    type: Mapped[EnterpriseType] = mapped_column(
        Enum(
            EnterpriseType,
            name="enterprise_type",
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=False,
    )

    parent_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("enterprises.id"),
        nullable=True,
    )

    full_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    short_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    sap_code: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )

    parent: Mapped["Enterprise | None"] = relationship(
        back_populates="children",
        remote_side="Enterprise.id",
    )

    children: Mapped[list["Enterprise"]] = relationship(
        back_populates="parent",
    )