from app.domain.enums import ElementBase, RoomCategory
from app.infrastructure.database.base import Base
from app.infrastructure.database.mixins import UUIDMixin
from sqlalchemy import Enum, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column


class MaintenancePeriodRule(UUIDMixin, Base):
    __tablename__ = "maintenance_period_rules"

    room_category: Mapped[RoomCategory] = mapped_column(
        Enum(
            RoomCategory,
            name="room_category",
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

    maintenance_period_years: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint(
            "room_category",
            "element_base",
            name="uq_maintenance_period_rule_category_element",
        ),
    )