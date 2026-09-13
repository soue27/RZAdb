from datetime import date
from uuid import UUID
from typing import TYPE_CHECKING

from sqlalchemy import (Date, Enum, ForeignKey,
                        Integer, SmallInteger, String, UniqueConstraint)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.domain.urza import URZA
from app.infrastructure.database.base import Base
from app.infrastructure.database.mixins import (
    SoftDeleteMixin,
    TimestampMixin,
    UUIDMixin,
)
from app.domain.enums import OTDPurpose


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


class OTDVersion(
    UUIDMixin,
    TimestampMixin,
    SoftDeleteMixin,
    Base,
):
    __tablename__ = "otd_versions"

    __table_args__ = (
        UniqueConstraint(
            "otd_id",
            "version_number",
            name="uq_otd_versions_otd_id_version_number",
        ),
    )

    otd_id: Mapped[UUID] = mapped_column(
        ForeignKey("otds.id"),
        nullable=False,
    )

    version_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    effective_date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
    )

    panel_cabinet_type: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    panel_cabinet_serial: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
    )

    panel_cabinet_manufacture_year: Mapped[int | None] = mapped_column(
        SmallInteger,
        nullable=True,
    )

    terminal_type: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    terminal_serial: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
    )

    terminal_manufacture_year: Mapped[int | None] = mapped_column(
        SmallInteger,
        nullable=True,
    )

    urza_service_life: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    software_version: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
    )

    ct_ratio: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )

    vt_ratio: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )

    urza_scheme_designation: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    urza_purpose: Mapped[OTDPurpose] = mapped_column(
        Enum(
            OTDPurpose,
            name="otd_purpose",
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=False,
    )

    task_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("tasks.id"),
        nullable=True,
    )


    otd: Mapped[OTD] = relationship()

    if TYPE_CHECKING:
        from app.domain.task import Task
    task: Mapped["Task | None"] = relationship()