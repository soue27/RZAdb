from datetime import date
from decimal import Decimal

import pytest

from app.domain.connection import Connection
from app.domain.enterprise import Enterprise
from app.domain.enums import (
    ElementBase,
    EnterpriseType,
    HighestVoltage,
    OperationalCurrentType,
    RoomCategory,
    URZACategory,
    URZAStatus,
)
from app.domain.rza_settings import SettingsForm
from app.domain.substation import Substation
from app.domain.urza import URZA
from app.infrastructure.database.engine import async_session_factory


@pytest.mark.asyncio
async def test_settings_form_persistence() -> None:
    async with async_session_factory() as session:
        department = Enterprise(
            type=EnterpriseType.DEPARTMENT,
            full_name="Тестовое производственное отделение",
            short_name="ТПО",
        )

        substation = Substation(
            enterprise=department,
            highest_voltage=HighestVoltage.KV_110,
            dispatch_name="ПС Тестовая",
            latitude=Decimal("56.123456"),
            longitude=Decimal("60.123456"),
        )

        connection = Connection(
            substation=substation,
            dispatch_name="Ввод 110 кВ",
            rdu_subordination=True,
            operational_current_type=OperationalCurrentType.PERMANENT,
        )

        urza = URZA(
            connection=connection,
            dispatch_name="ДЗЛ 110 кВ",
            rdu_subordination=False,
            commissioning_date=date(2020, 5, 15),
            status=URZAStatus.IN_OPERATION,
            element_base=ElementBase.MICROPROCESSOR,
            category=URZACategory.II,
            room_category=RoomCategory.I,
            complexity=True,
        )

        settings_form = SettingsForm(urza=urza)

        session.add(settings_form)
        await session.flush()

        assert settings_form.id is not None
        assert settings_form.urza_id == urza.id

        await session.rollback()