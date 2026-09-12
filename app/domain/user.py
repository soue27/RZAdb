from uuid import UUID

from sqlalchemy import (
    Boolean,
    Enum,
    ForeignKey,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.domain.enterprise import Enterprise
from app.domain.enums import AccessCategory, UserRole
from app.infrastructure.database.base import Base
from app.infrastructure.database.mixins import (
    SoftDeleteMixin,
    TimestampMixin,
    UUIDMixin,
)


class User(
    UUIDMixin,
    TimestampMixin,
    SoftDeleteMixin,
    Base,
):
    __tablename__ = "users"

    __table_args__ = (
        UniqueConstraint(
            "email",
            name="uq_users_email",
        ),
    )

    full_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    role: Mapped[UserRole] = mapped_column(
        Enum(
            UserRole,
            name="user_role",
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=False,
    )

    email: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    password_hash: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    enterprise_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("enterprises.id"),
        nullable=True,
    )

    access_category: Mapped[AccessCategory] = mapped_column(
        Enum(
            AccessCategory,
            name="access_category",
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=False,
    )

    sap_code: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )

    active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
    )

    enterprise: Mapped[Enterprise | None] = relationship()