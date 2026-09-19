from datetime import date

import pytest
from sqlalchemy.exc import IntegrityError

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
async def test_urza_can_have_only_one_settings_form() -> None:
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

        first_form = SettingsForm(urza=urza)
        second_form = SettingsForm(urza=urza)

        session.add(first_form)
        await session.flush()

        session.add(second_form)

        with pytest.raises(IntegrityError):
            await session.flush()

        await session.rollback()